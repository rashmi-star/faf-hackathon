"""Director FAL — the film director voice agent (SPEC sections 2-6).

Pipeline: speech-to-text -> fal-hosted LLM -> ElevenLabs Flash v2.5 TTS,
over a LiveKit AgentSession. All UI state flows through state.publish_state
on the ``state_update`` data topic.
"""

import logging
import os
import textwrap
import time

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    APIConnectOptions,
    ConversationItemAddedEvent,
    JobContext,
    TurnHandlingOptions,
    cli,
    room_io,
)
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.plugins import ai_coustics, deepgram, elevenlabs, openai
from openai import AsyncOpenAI

from state import STATE, TranscriptEntry, publish_state, publish_state_soon, set_room
from tools import ALL_TOOLS

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# SPEC section 9 uses ELEVENLABS_API_KEY; the plugin reads ELEVEN_API_KEY. Bridge.
if os.getenv("ELEVENLABS_API_KEY") and not os.getenv("ELEVEN_API_KEY"):
    os.environ["ELEVEN_API_KEY"] = os.environ["ELEVENLABS_API_KEY"]

# fal exposes OpenRouter's chat-completions API through an OpenAI-compatible
# endpoint, so the same FAL_KEY powers both the director brain and media tools.
FAL_LLM_MODEL = os.getenv("FAL_LLM_MODEL", "google/gemini-2.5-flash-lite")
FAL_LLM_BASE_URL = "https://fal.run/openrouter/router/openai/v1"

# STT backend: "deepgram" (default) or "elevenlabs" (Scribe — reuses the
# ElevenLabs key, so no separate Deepgram key needed).
STT_BACKEND = os.getenv("DIRECTOR_STT", "deepgram").lower()

# ai-coustics noise cancellation defaults to LiveKit Cloud auth, which local
# dev (livekit-server --dev) does not provide. Off by default; set
# DIRECTOR_NOISE_CANCELLATION=1 only when running against LiveKit Cloud.
NOISE_CANCELLATION = os.getenv("DIRECTOR_NOISE_CANCELLATION", "0") == "1"

# Allow enough time for a cold hosted-model request while preserving normal
# LiveKit retry/error handling.
LLM_TIMEOUT = float(os.getenv("DIRECTOR_LLM_TIMEOUT", "20"))


def build_llm():
    """Build the director LLM on fal's OpenAI-compatible OpenRouter endpoint."""
    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        raise RuntimeError(
            "FAL_KEY is required for the director LLM and media generation."
        )
    client = AsyncOpenAI(
        base_url=FAL_LLM_BASE_URL,
        api_key="not-needed",
        default_headers={"Authorization": f"Key {fal_key}"},
    )
    logger.info("LLM backend: fal OpenRouter (%s)", FAL_LLM_MODEL)
    return openai.LLM(model=FAL_LLM_MODEL, client=client)


def build_stt():
    """Deepgram Nova-3, or ElevenLabs Scribe when DIRECTOR_STT=elevenlabs."""
    if STT_BACKEND == "elevenlabs":
        return elevenlabs.STT(
            model="scribe_v2_realtime",
            language_code="en",
            server_vad={
                "vad_silence_threshold_secs": 0.5,
                "min_speech_duration_ms": 100,
                "min_silence_duration_ms": 500,
            },
        )
    return deepgram.STT(model="nova-3", language="en")

# ElevenLabs Flash v2.5 director voice (override with ELEVENLABS_VOICE_ID)
TTS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")  # Daniel

DIRECTOR_INSTRUCTIONS = textwrap.dedent(
    """\
    You are The Director — the creative lead of a voice-driven film studio.
    You are warm, decisive, and encouraging: a seasoned film director who
    loves the user's ideas, sharpens them fast, and always knows the next
    step. You speak with confidence and momentum, never rambling.

    # Voice output rules

    You speak through text-to-speech, so:
    - Plain conversational text only. No markdown, lists, emojis, or stage directions.
    - Keep replies short: one to three sentences. One question at a time.
    - Spell out numbers and timecodes ("around fifteen seconds").
    - Never reveal tool names, parameters, or internal state.

    # The production workflow (follow strictly, in order)

    1. Brainstorm. Riff on the user's idea with energy. Propose a tight
       logline, scene, and visual style. When you both agree, lock it with
       set_story.
    2. Characters. Create each main character with create_character, writing a
       vivid sheet (appearance, wardrobe, personality). After each portrait
       appears, ask the user to approve it. Do not move on until every
       portrait is approved by voice. A named or recurring person in any shot
       MUST have a character card first, including in fast-demo requests.
    3. Scene and storyboard. Confirm the scenery and style in one sentence,
       then propose three to four shots totalling twenty to thirty seconds and
       call plan_shots. Walk the user through the stills.
    4. Generate. ONLY after the user approves the storyboard, call render_all.
       Never render video before the storyboard and characters are approved —
       preview before spend. During rendering, do not invent or repeat progress
       updates; the render tool and visual timeline provide status.
    5. Review and edit. When the user references a moment in time, call
       highlight with that range IMMEDIATELY, before you even reply. Then
       confirm what changes and call replace_segment. If only a line of
       dialogue changes, say the fix is quick.
    6. Score, then export. If the film needs music, call set_music and WAIT
       for it to finish. Only in a later tool step call export with all four
       formats. Never call set_music and export in parallel. Export must be
       the final operation after every timeline edit, then congratulate the
       user on the finished film.

    # Tool rules

    - Every change the user should see happens through a tool; never pretend.
    - If the user asks how it's going, call show_status and speak the result.
    - If a tool reports an error, say so once, plainly, and suggest the next step.
    """
)


class DirectorAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            llm=build_llm(),
            instructions=DIRECTOR_INSTRUCTIONS,
            tools=ALL_TOOLS,
        )


server = AgentServer()


@server.rtc_session(agent_name="my-agent")
async def director_session(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    session = AgentSession(
        # STT: Deepgram (default) or ElevenLabs Scribe (DIRECTOR_STT=elevenlabs).
        stt=build_stt(),
        # TTS: ElevenLabs Flash v2.5 (user's Pro key)
        tts=elevenlabs.TTS(model="eleven_flash_v2_5", voice_id=TTS_VOICE_ID),
        turn_handling=TurnHandlingOptions(
            # Local dev credentials cannot use LiveKit's cloud turn detector.
            # ElevenLabs server VAD commits turns after 500ms of silence.
            turn_detection="stt",
        ),
        conn_options=SessionConnectOptions(
            llm_conn_options=APIConnectOptions(timeout=LLM_TIMEOUT),
        ),
        preemptive_generation=True,
    )

    # mirror the conversation into project state for the live transcript panel
    session_t0 = time.time()

    @session.on("conversation_item_added")
    def _on_conversation_item(ev: ConversationItemAddedEvent) -> None:
        # Non-message items (e.g. AgentHandoff) have no text_content — skip them.
        text = getattr(ev.item, "text_content", None)
        if not text:
            return
        role = "agent" if ev.item.role == "assistant" else "user"
        STATE.transcript.append(
            TranscriptEntry(role=role, text=text, ts=round(time.time() - session_t0, 1))
        )
        publish_state_soon(session)

    # ai-coustics noise cancellation needs LiveKit Cloud auth; skip it in local
    # dev unless explicitly enabled (DIRECTOR_NOISE_CANCELLATION=1).
    if NOISE_CANCELLATION:
        room_options = room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                ),
            ),
        )
    else:
        room_options = room_io.RoomOptions()

    await session.start(
        agent=DirectorAgent(),
        room=ctx.room,
        room_options=room_options,
    )

    set_room(ctx.room)
    await ctx.connect()
    await publish_state(session)

    session.generate_reply(
        instructions=(
            "Greet the user warmly as their director and ask: what are we making today?"
        )
    )


if __name__ == "__main__":
    cli.run_app(server)
