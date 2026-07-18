"""Director FAL — the film director voice agent (SPEC sections 2-6).

Pipeline: Deepgram STT -> Anthropic Claude (tool calling) -> ElevenLabs
Flash v2.5 TTS, over a LiveKit AgentSession. All UI state flows through
state.publish_state on the ``state_update`` data topic.
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
    ConversationItemAddedEvent,
    JobContext,
    TurnHandlingOptions,
    cli,
    inference,
    room_io,
)
from livekit.plugins import ai_coustics, anthropic, deepgram, elevenlabs

from state import STATE, TranscriptEntry, publish_state, publish_state_soon, set_room
from tools import ALL_TOOLS

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# SPEC section 9 uses ELEVENLABS_API_KEY; the plugin reads ELEVEN_API_KEY. Bridge.
if os.getenv("ELEVENLABS_API_KEY") and not os.getenv("ELEVEN_API_KEY"):
    os.environ["ELEVEN_API_KEY"] = os.environ["ELEVENLABS_API_KEY"]

# Anthropic model: primary claude-fable-5; if unavailable on your key, fall
# back by setting DIRECTOR_LLM_MODEL=claude-sonnet-5 in .env.local.
LLM_MODEL = os.getenv("DIRECTOR_LLM_MODEL", "claude-fable-5")

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
       portrait is approved by voice.
    3. Scene and storyboard. Confirm the scenery and style in one sentence,
       then propose three to four shots totalling twenty to thirty seconds and
       call plan_shots. Walk the user through the stills.
    4. Generate. ONLY after the user approves the storyboard, call render_all.
       Never render video before the storyboard and characters are approved —
       preview before spend. While renders run, keep the user company: narrate
       progress naturally, like a director on set.
    5. Review and edit. When the user references a moment in time, call
       highlight with that range IMMEDIATELY, before you even reply. Then
       confirm what changes and call replace_segment. If only a line of
       dialogue changes, say the fix is quick.
    6. Export. When the user asks to export, call export with all four
       formats, then congratulate them on the finished film.

    # Tool rules

    - Every change the user should see happens through a tool; never pretend.
    - If the user asks how it's going, call show_status and speak the result.
    - If a tool reports an error, say so once, plainly, and suggest the next step.
    """
)


class DirectorAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            llm=anthropic.LLM(model=LLM_MODEL),
            instructions=DIRECTOR_INSTRUCTIONS,
            tools=ALL_TOOLS,
        )


server = AgentServer()


@server.rtc_session(agent_name="my-agent")
async def director_session(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    session = AgentSession(
        # STT: Deepgram plugin (default). Alternative: ElevenLabs Scribe —
        #   stt=elevenlabs.STT(model="scribe_v2_realtime")
        # (same ELEVEN_API_KEY, saves one vendor if Deepgram is unavailable).
        stt=deepgram.STT(model="nova-3", language="en"),
        # TTS: ElevenLabs Flash v2.5 (user's Pro key)
        tts=elevenlabs.TTS(model="eleven_flash_v2_5", voice_id=TTS_VOICE_ID),
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
        ),
        preemptive_generation=True,
    )

    # mirror the conversation into project state for the live transcript panel
    session_t0 = time.time()

    @session.on("conversation_item_added")
    def _on_conversation_item(ev: ConversationItemAddedEvent) -> None:
        text = ev.item.text_content
        if not text:
            return
        role = "agent" if ev.item.role == "assistant" else "user"
        STATE.transcript.append(
            TranscriptEntry(role=role, text=text, ts=round(time.time() - session_t0, 1))
        )
        publish_state_soon(session)

    await session.start(
        agent=DirectorAgent(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                ),
            ),
        ),
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
