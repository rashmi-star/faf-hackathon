"""Project state for Director FAL (SPEC section 4).

One in-memory ProjectState per agent process, mirrored to
``agent/project_state.json`` and pushed to the room on topic
``state_update`` after every mutation. The frontend is a pure renderer
of this JSON.

Beyond the SPEC fields, the state carries the edit-engine session: a live
:class:`~engine.timeline.Timeline` (clips, text overlays, captions, music)
plus the changelog of applied edits. :func:`apply_edit` commits an engine op
result (snapshotting the previous timeline for :func:`undo_last_edit`);
serialization only ADDS keys — every pre-existing field name is unchanged,
which is the contract the frontend renders against.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from livekit import rtc

from engine.timeline import ChangelogEntry, Timeline

if TYPE_CHECKING:
    from livekit.agents import AgentSession

logger = logging.getLogger("director.state")

STATE_TOPIC = "state_update"
STATE_FILE = Path(__file__).resolve().parent.parent / "project_state.json"

PHASES = ("brainstorm", "characters", "scene", "generating", "review", "exporting")

CHANGELOG_PUBLISHED = 10  # changelog entries included in each state_update
UNDO_DEPTH = 20  # timeline snapshots kept for undo


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
    # Reference-sheet fields (SPEC section 10). Populated by FalMedia when keys
    # are present; empty otherwise so the Cast tab degrades to a portrait card.
    role: str = ""
    age: str = ""
    personality: list[str] = field(default_factory=list)
    palette: list[str] = field(default_factory=list)  # hex swatches
    turnaround_urls: list[str] = field(default_factory=list)  # front/3-4/side/back
    expression_urls: list[str] = field(default_factory=list)  # emotion grid
    notes: list[str] = field(default_factory=list)


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


def _timeline_dict(timeline: Timeline) -> dict[str, Any]:
    """Timeline JSON for the frontend, with per-clip placement precomputed.

    Each clip carries its engine fields (``clip_id``, ``src``, ``in_point``,
    ``out_point``, ``speed``, ``transition_in``) plus the derived ``start``
    and ``duration`` in timeline seconds, so the timeline strip can be drawn
    without re-deriving crossfade math client-side.
    """
    return {
        "fps": timeline.fps,
        "aspect": timeline.aspect,
        "resolution": list(timeline.resolution),
        "duration": round(timeline.duration, 3),
        "clips": [
            {
                **clip.to_dict(),
                "start": round(start, 3),
                "duration": round(clip.duration, 3),
            }
            for clip, start in zip(timeline.clips, timeline.clip_start_times())
        ],
        "texts": [t.to_dict() for t in timeline.texts],
        "captions": [c.to_dict() for c in timeline.captions],
        "music": timeline.music.to_dict() if timeline.music else None,
    }


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
    timeline: Timeline = field(default_factory=Timeline)  # the edit-engine session
    changelog: list[ChangelogEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        # keep the reliable data packet comfortably under the 15KiB limit
        data["transcript"] = data["transcript"][-100:]
        data["timeline"] = _timeline_dict(self.timeline)
        data["changelog"] = data["changelog"][-CHANGELOG_PUBLISHED:]
        return data

    def get_shot(self, shot_id: str) -> Shot | None:
        return next((s for s in self.shots if s.id == shot_id), None)


# ---------------------------------------------------------------------------
# module-level singleton + publishing

STATE = ProjectState()

_undo_stack: list[Timeline] = []


def apply_edit(new_timeline: Timeline, entry: ChangelogEntry) -> ChangelogEntry:
    """Commit an engine op result to the session.

    Snapshots the outgoing timeline for undo, swaps in the new one, and
    appends the changelog entry the agent narrates from. Callers publish
    state themselves (they know whether they are batching edits).
    """
    _undo_stack.append(STATE.timeline)
    del _undo_stack[:-UNDO_DEPTH]
    STATE.timeline = new_timeline
    STATE.changelog.append(entry)
    return entry


def undo_last_edit() -> ChangelogEntry | None:
    """Revert the most recent timeline edit; None when there is nothing to undo."""
    if not _undo_stack:
        return None
    undone = STATE.changelog[-1].summary if STATE.changelog else "the last edit"
    STATE.timeline = _undo_stack.pop()
    entry = ChangelogEntry(op="undo", summary=f"Undid: {undone}")
    STATE.changelog.append(entry)
    return entry

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
