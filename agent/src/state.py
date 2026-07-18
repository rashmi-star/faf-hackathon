"""Project state for Director FAL (SPEC section 4).

One in-memory ProjectState per agent process, mirrored to
``agent/project_state.json`` and pushed to the room on topic
``state_update`` after every mutation. The frontend is a pure renderer
of this JSON.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from livekit import rtc

if TYPE_CHECKING:
    from livekit.agents import AgentSession

logger = logging.getLogger("director.state")

STATE_TOPIC = "state_update"
STATE_FILE = Path(__file__).resolve().parent.parent / "project_state.json"

PHASES = ("brainstorm", "characters", "scene", "generating", "review", "exporting")


@dataclass
class Story:
    logline: str = ""
    scene: str = ""
    style: str = ""


@dataclass
class Character:
    id: str
    name: str
    sheet: str  # appearance + personality prompt, reused for consistency
    image_url: str = ""
    approved: bool = False


@dataclass
class Shot:
    id: str
    start: float
    end: float
    prompt: str
    dialogue: str | None = None
    still_url: str = ""
    video_url: str = ""
    status: str = "planned"  # planned | still | rendering | ready | replacing


@dataclass
class Highlight:
    start: float
    end: float


@dataclass
class ExportItem:
    format: str
    url: str


@dataclass
class TranscriptEntry:
    role: str  # "user" | "agent"
    text: str
    ts: float


@dataclass
class ProjectState:
    phase: str = "brainstorm"
    story: Story = field(default_factory=Story)
    characters: list[Character] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)
    highlight: Highlight | None = None
    exports: list[ExportItem] = field(default_factory=list)
    transcript: list[TranscriptEntry] = field(default_factory=list)
    timeline_url: str = ""  # assembled master video

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # keep the reliable data packet comfortably under the 15KiB limit
        data["transcript"] = data["transcript"][-100:]
        return data

    def get_shot(self, shot_id: str) -> Shot | None:
        return next((s for s in self.shots if s.id == shot_id), None)


# ---------------------------------------------------------------------------
# module-level singleton + publishing

STATE = ProjectState()

_room: rtc.Room | None = None
_bg_tasks: set[asyncio.Task[Any]] = set()


def set_room(room: rtc.Room) -> None:
    """Attach the LiveKit room used by publish_state. Call once at session start."""
    global _room
    _room = room


async def publish_state(session: AgentSession | None = None) -> None:
    """Send the full state JSON to the room (topic ``state_update``) and save to disk.

    Call after every state mutation. ``session`` is accepted for call-site
    symmetry; the room itself is registered via :func:`set_room`.
    """
    payload = json.dumps(STATE.to_dict())
    try:
        STATE_FILE.write_text(payload)
    except OSError:
        logger.exception("failed to save project_state.json")
    if _room is None:
        logger.debug("publish_state called before set_room; skipping room publish")
        return
    try:
        await _room.local_participant.publish_data(
            payload, reliable=True, topic=STATE_TOPIC
        )
    except Exception:
        logger.exception("failed to publish state_update")


def publish_state_soon(session: AgentSession | None = None) -> None:
    """Fire-and-forget publish for sync call sites (e.g. event handlers)."""
    task = asyncio.create_task(publish_state(session))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)
