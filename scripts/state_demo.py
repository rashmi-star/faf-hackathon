#!/usr/bin/env python
"""Publish the SPEC section 4 golden-path ``state_update`` sequence to a LiveKit room.

Proves the frontend's live mode end-to-end with ZERO cloud keys: run
``livekit-server --dev`` locally, open http://localhost:3000/studio, click the
talk orb, then run this script. It discovers the room the browser created,
joins it as an agent-kind participant, and replays the scripted golden path
(same timings and payloads as the mock director in
``frontend/lib/project-state.ts``) on the ``state_update`` data topic — so the
studio renders the full demo: transcript, character cards, shot pipeline,
the instant highlight beat, and export cards. No Python agent, no fal,
no Anthropic/ElevenLabs/Deepgram keys.

Run from the repo root:

    uv run --project agent python scripts/state_demo.py

Environment (all optional; defaults match ``livekit-server --dev``):

    LIVEKIT_URL         ws://localhost:7880
    LIVEKIT_API_KEY     devkey
    LIVEKIT_API_SECRET  secret
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import copy
import json
import os
import sys
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import aiohttp
from livekit import api, rtc

# livekit-server --dev intentionally uses the short secret "secret"; silence
# PyJWT's key-length warning for that dev-only credential.
warnings.filterwarnings("ignore", message="The HMAC key is")

STATE_TOPIC = "state_update"  # must match frontend/lib/project-state.ts
CHAT_TOPIC = "lk.chat"  # orb caption stream read by useSessionMessages
AGENT_STATE_ATTR = "lk.agent.state"  # drives the talk orb via useAgent()
ROOM_PREFIX = "voice_assistant_room_"  # rooms minted by frontend/app/api/token

DEFAULT_URL = "ws://localhost:7880"
DEFAULT_API_KEY = "devkey"
DEFAULT_API_SECRET = "secret"

# ---------------------------------------------------------------------------
# Golden-path content — mirrors MOCK_* in frontend/lib/project-state.ts.
# Keep the two in sync; the frontend file is the source of truth.
# ---------------------------------------------------------------------------

StateDict = dict[str, Any]
Apply = Callable[[StateDict, float], None]

PLACEHOLDERS = "/placeholders"  # served from frontend/public
MOCK_VIDEO = f"{PLACEHOLDERS}/hero-video-bg.mp4"

STORY: StateDict = {
    "logline": "A couple at the Golden Gate Bridge — one line changes everything.",
    "scene": "Golden hour at the Golden Gate Bridge, wind off the bay",
    "style": "cinematic 35mm, warm backlight, shallow depth of field",
}

CHARACTERS: list[StateDict] = [
    {
        "id": "her",
        "name": "Maya",
        "sheet": "Late 20s, windswept dark hair, denim jacket. Fierce, wounded, decisive.",
        "image_url": f"{PLACEHOLDERS}/hero-modern-left.jpg",
        "approved": False,
    },
    {
        "id": "him",
        "name": "James",
        "sheet": "Early 30s, wool coat, open face. Earnest, easily broken, wears his heart.",
        "image_url": f"{PLACEHOLDERS}/hero-modern-right.jpg",
        "approved": False,
    },
]

SHOTS: list[StateDict] = [
    {
        "id": "s1",
        "start": 0,
        "end": 7,
        "prompt": "Wide establishing: golden hour, Golden Gate Bridge, couple silhouetted at the rail",
        "dialogue": None,
        "still_url": None,
        "video_url": None,
        "status": "planned",
    },
    {
        "id": "s2",
        "start": 7,
        "end": 13,
        "prompt": "Close on Maya, wind in her hair, jaw set, bay glittering behind",
        "dialogue": None,
        "still_url": None,
        "video_url": None,
        "status": "planned",
    },
    {
        "id": "s3",
        "start": 13,
        "end": 20,
        "prompt": "Two-shot at the rail: Maya turns and delivers the line, James takes it",
        "dialogue": "I really hate you.",
        "still_url": None,
        "video_url": None,
        "status": "planned",
    },
    {
        "id": "s4",
        "start": 20,
        "end": 26,
        "prompt": "James alone at the rail, heartbroken, city lights flickering on",
        "dialogue": None,
        "still_url": None,
        "video_url": None,
        "status": "planned",
    },
]

STILLS: dict[str, str] = {
    "s1": f"{PLACEHOLDERS}/hero-kingdom-left.jpg",
    "s2": f"{PLACEHOLDERS}/hero-modern-left.jpg",
    "s3": f"{PLACEHOLDERS}/hero-modern-right.jpg",
    "s4": f"{PLACEHOLDERS}/hero-rock-right.jpg",
}

EXPORTS: list[StateDict] = [
    {"format": "16:9", "url": MOCK_VIDEO},
    {"format": "9:16", "url": MOCK_VIDEO},
    {"format": "1:1", "url": MOCK_VIDEO},
    {"format": "loop", "url": MOCK_VIDEO},
]

INITIAL_STATE: StateDict = {
    "phase": "brainstorm",
    "story": None,
    "characters": [],
    "shots": [],
    "highlight": None,
    "exports": [],
    "transcript": [],
}


def say(role: str, text: str) -> Apply:
    """Append one transcript entry (role: 'user' | 'agent')."""

    def _apply(state: StateDict, ts: float) -> None:
        state["transcript"].append({"role": role, "text": text, "ts": ts})

    return _apply


def merge(**patch: Any) -> Apply:
    """Shallow-merge a patch into the state (deep-copied so constants stay pristine)."""

    def _apply(state: StateDict, _ts: float) -> None:
        state.update(copy.deepcopy(patch))

    return _apply


def patch_shot(shot_id: str, **patch: Any) -> Apply:
    """Update one shot in place by id."""

    def _apply(state: StateDict, _ts: float) -> None:
        for shot in state["shots"]:
            if shot["id"] == shot_id:
                shot.update(patch)

    return _apply


def approve_characters(state: StateDict, _ts: float) -> None:
    """Lock the cast and advance to the scene phase."""
    state["phase"] = "scene"
    for character in state["characters"]:
        character["approved"] = True


@dataclass(frozen=True)
class Step:
    """One beat of the golden path: wait ``delay_ms``, then mutate/emit."""

    delay_ms: int
    agent_state: str | None = None  # listening | thinking | speaking | initializing
    apply: Apply | None = None


# Timings and lines transcribed 1:1 from MOCK_SCRIPT in
# frontend/lib/project-state.ts (total runtime ~80 seconds).
GOLDEN_PATH: list[Step] = [
    # brainstorm
    Step(1200, "speaking", say("agent", "What are we making today?")),
    Step(2400, "listening"),
    Step(
        1400,
        None,
        say(
            "user",
            "A couple at the Golden Gate Bridge at sunset. She tells him she hates him "
            "— and it breaks his heart.",
        ),
    ),
    Step(700, "thinking"),
    Step(
        1400,
        "speaking",
        say(
            "agent",
            "Love it. Golden hour, wind off the bay, one brutal line. Sketching your leads now.",
        ),
    ),
    Step(400, None, merge(phase="characters", story=STORY)),
    # characters appear
    Step(1800, None, merge(characters=CHARACTERS)),
    Step(1200, None, say("agent", "Meet Maya and James. Should I lock them in?")),
    Step(2200, "listening"),
    Step(1300, None, say("user", "Yes — they are perfect.")),
    Step(800, "thinking"),
    Step(900, "speaking", approve_characters),
    Step(
        200,
        None,
        say(
            "agent",
            "Locked. Scene: golden hour on the Golden Gate Bridge, cinematic 35mm.",
        ),
    ),
    # shot plan
    Step(2200, None, merge(phase="generating", shots=SHOTS)),
    Step(
        300,
        "speaking",
        say(
            "agent",
            "Here is the shot plan — four shots, twenty-six seconds. Boarding it now.",
        ),
    ),
    # stills
    Step(1500, None, patch_shot("s1", status="still", still_url=STILLS["s1"])),
    Step(700, None, patch_shot("s2", status="still", still_url=STILLS["s2"])),
    Step(700, None, patch_shot("s3", status="still", still_url=STILLS["s3"])),
    Step(700, None, patch_shot("s4", status="still", still_url=STILLS["s4"])),
    Step(
        1000,
        "speaking",
        say(
            "agent",
            "Storyboard is up. Rendering all four shots — talk to me while I work.",
        ),
    ),
    # renders
    Step(800, None, patch_shot("s1", status="rendering")),
    Step(600, None, patch_shot("s2", status="rendering")),
    Step(600, None, patch_shot("s3", status="rendering")),
    Step(600, None, patch_shot("s4", status="rendering")),
    Step(2600, None, patch_shot("s1", status="ready", video_url=MOCK_VIDEO)),
    Step(2200, None, patch_shot("s2", status="ready", video_url=MOCK_VIDEO)),
    Step(2000, None, patch_shot("s3", status="ready", video_url=MOCK_VIDEO)),
    Step(2200, None, patch_shot("s4", status="ready", video_url=MOCK_VIDEO)),
    Step(900, None, merge(phase="review")),
    Step(
        200,
        "speaking",
        say("agent", "First cut is assembled — twenty-six seconds. Take a look."),
    ),
    # the magic moment: voice edit
    Step(3200, "listening"),
    Step(
        2400,
        None,
        say(
            "user",
            "Around 15 seconds — change 'I really hate you' to 'I really love you', "
            "and he's very happy about it.",
        ),
    ),
    Step(700, None, merge(highlight={"start": 15, "end": 20})),
    Step(
        300,
        "speaking",
        say("agent", "Got it — re-cutting that beat with the new line."),
    ),
    Step(500, None, patch_shot("s3", status="replacing")),
    Step(
        3800,
        None,
        patch_shot(
            "s3", status="ready", dialogue="I really love you.", video_url=MOCK_VIDEO
        ),
    ),
    Step(300, None, merge(highlight=None)),
    Step(
        300,
        "speaking",
        say("agent", "Done — new line, new reaction, dropped straight into place."),
    ),
    # export
    Step(2600, "listening"),
    Step(1600, None, say("user", "Export it.")),
    Step(800, "thinking"),
    Step(600, None, merge(phase="exporting")),
    Step(300, "speaking", say("agent", "Exporting every format now.")),
    Step(2600, None, merge(exports=EXPORTS)),
    Step(
        400,
        "speaking",
        say(
            "agent",
            "All formats ready — YouTube, Reels, square, and a loop. That is a wrap.",
        ),
    ),
    Step(3000, "listening"),
]

LOOP_HOLD_MS = 12_000  # mock director holds the finished project, then restarts


# ---------------------------------------------------------------------------
# LiveKit plumbing
# ---------------------------------------------------------------------------


class ServerUnreachableError(RuntimeError):
    """Raised when the LiveKit server cannot be reached at all."""


def http_url(ws_url: str) -> str:
    """Convert a ws(s):// LiveKit URL to its http(s):// API endpoint."""
    return ws_url.replace("ws://", "http://", 1).replace("wss://", "https://", 1)


async def discover_room(url: str, api_key: str, api_secret: str, timeout: float) -> str:
    """Poll the server until the studio browser tab has created a room.

    Prefers rooms named by the frontend token route (``voice_assistant_room_*``),
    falls back to any open room.
    """
    lkapi = api.LiveKitAPI(http_url(url), api_key, api_secret)
    try:
        deadline = asyncio.get_running_loop().time() + timeout
        announced = False
        while True:
            try:
                listing = await lkapi.room.list_rooms(api.ListRoomsRequest())
            except (aiohttp.ClientError, OSError) as exc:
                raise ServerUnreachableError(str(exc)) from exc
            names = [room.name for room in listing.rooms]
            preferred = [name for name in names if name.startswith(ROOM_PREFIX)]
            if preferred or names:
                return (preferred or names)[0]
            if not announced:
                print(
                    "Waiting for a browser room — open http://localhost:3000/studio "
                    "and click the talk orb ('Tap to talk')."
                )
                announced = True
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(
                    f"no room appeared within {timeout:.0f}s "
                    "(is the studio open and connected?)"
                )
            await asyncio.sleep(1.0)
    finally:
        await lkapi.aclose()


def mint_token(api_key: str, api_secret: str, room_name: str) -> str:
    """Mint an agent-kind join token so the studio's useAgent() adopts us."""
    return (
        api.AccessToken(api_key=api_key, api_secret=api_secret)
        .with_identity("director-demo")
        .with_name("Director (demo)")
        .with_kind("agent")
        .with_attributes({AGENT_STATE_ATTR: "initializing"})
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_publish_data=True,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )


async def publish_state(local: rtc.LocalParticipant, state: StateDict) -> None:
    """Send the full project state on the ``state_update`` topic (agent parity)."""
    await local.publish_data(json.dumps(state), reliable=True, topic=STATE_TOPIC)


async def set_agent_state(local: rtc.LocalParticipant, value: str) -> None:
    """Best-effort update of the talk-orb state attribute (cosmetic only)."""
    with contextlib.suppress(Exception):
        await local.set_attributes({AGENT_STATE_ATTR: value})


async def send_caption(local: rtc.LocalParticipant, text: str) -> None:
    """Best-effort chat-stream message so the orb caption shows the agent line."""
    with contextlib.suppress(Exception):
        await local.send_text(text, topic=CHAT_TOPIC)


async def play_sequence(room: rtc.Room, speed: float) -> None:
    """Run the golden path once against the connected room."""
    local = room.local_participant
    state = copy.deepcopy(INITIAL_STATE)
    await publish_state(local, state)  # baseline: clean brainstorm phase
    elapsed_ms = 0.0
    for step in GOLDEN_PATH:
        await asyncio.sleep(step.delay_ms / 1000.0 / speed)
        elapsed_ms += step.delay_ms
        if step.agent_state:
            await set_agent_state(local, step.agent_state)
        if step.apply:
            before = len(state["transcript"])
            step.apply(state, round(elapsed_ms / 1000.0))
            await publish_state(local, state)
            entries = state["transcript"]
            if len(entries) > before and entries[-1]["role"] == "agent":
                line = entries[-1]["text"]
                print(f"  [{elapsed_ms / 1000.0:5.1f}s] director: {line}")
                await send_caption(local, line)


async def run(args: argparse.Namespace) -> int:
    """Connect, play the golden path, and hold the room open. Returns exit code."""
    try:
        room_name = args.room or await discover_room(
            args.url, args.api_key, args.api_secret, args.wait
        )
    except ServerUnreachableError as exc:
        print(
            f"error: LiveKit server not reachable at {args.url} ({exc})",
            file=sys.stderr,
        )
        print(
            "Start the local dev server first:  livekit-server --dev"
            "   (install: brew install livekit)",
            file=sys.stderr,
        )
        return 1
    except TimeoutError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    room = rtc.Room()
    try:
        await room.connect(
            args.url, mint_token(args.api_key, args.api_secret, room_name)
        )
    except rtc.ConnectError as exc:
        print(
            f"error: could not join room '{room_name}' at {args.url}: {exc}",
            file=sys.stderr,
        )
        print(
            "Is livekit-server --dev running, and do LIVEKIT_API_KEY/SECRET match "
            "(devkey/secret for --dev)?",
            file=sys.stderr,
        )
        return 1

    print(f"Joined '{room_name}' as director-demo — playing the golden path (~80s).")
    try:
        while True:
            await play_sequence(room, args.speed)
            if not args.loop:
                break
            await asyncio.sleep(LOOP_HOLD_MS / 1000.0 / args.speed)
            print("Looping — resetting the studio to a clean slate.")
        print("Golden path complete — the studio should show the export cards.")
        print("Holding the room open so the UI keeps its state. Ctrl-C to exit.")
        await asyncio.Event().wait()  # keep the agent participant present
    finally:
        await room.disconnect()
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish the golden-path state_update sequence into a LiveKit room "
            "so the studio frontend renders the full demo without any cloud keys."
        ),
    )
    parser.add_argument(
        "--url",
        default=os.getenv("LIVEKIT_URL", DEFAULT_URL),
        help=f"LiveKit server URL (env LIVEKIT_URL, default {DEFAULT_URL})",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("LIVEKIT_API_KEY", DEFAULT_API_KEY),
        help=f"API key (env LIVEKIT_API_KEY, default {DEFAULT_API_KEY})",
    )
    parser.add_argument(
        "--api-secret",
        default=os.getenv("LIVEKIT_API_SECRET", DEFAULT_API_SECRET),
        help=f"API secret (env LIVEKIT_API_SECRET, default {DEFAULT_API_SECRET})",
    )
    parser.add_argument(
        "--room",
        default=None,
        help="join this room instead of auto-discovering the browser's room",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=300.0,
        help="seconds to wait for the browser to create a room (default 300)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="playback speed multiplier, e.g. 2 halves every delay (default 1)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="replay the golden path forever (mirrors the frontend mock loop)",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nBye — left the room.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
