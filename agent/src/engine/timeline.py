"""Timeline data model for the Director FAL edit engine.

A :class:`Timeline` is the single source of truth for an edit: an ordered
video track of :class:`Clip` objects, burned-in :class:`TextOverlay` and
:class:`Caption` items, and an optional music :class:`AudioTrack`. It is plain
data — no ffmpeg here — and serializes losslessly to JSON so the agent can
mirror it into project state and the renderer can be swapped (local ffmpeg
today, fal compose later) without touching the model.

Editing operations live in :mod:`engine.ops`; every operation returns a fresh
Timeline plus a :class:`ChangelogEntry` the agent narrates from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --- errors ----------------------------------------------------------------


class EngineError(Exception):
    """Base error for the edit engine."""


class ValidationError(EngineError):
    """An operation or timeline failed validation (bad ranges, unknown ids...)."""


# --- constants -------------------------------------------------------------

ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "16:9": (16, 9),
    "9:16": (9, 16),
    "1:1": (1, 1),
}

STYLE_PRESETS = ("title", "lower-third", "caption")

POSITIONS = (
    "center",
    "top",
    "bottom",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
)

SPEED_MIN = 0.25
SPEED_MAX = 4.0

_EPS = 1e-6  # tolerance for "at a clip boundary" checks


def resolution_for_aspect(base: tuple[int, int], aspect: str) -> tuple[int, int]:
    """Target resolution for an aspect variant of ``base``.

    Keeps the shorter side of ``base`` as the constrained dimension, so a
    1920x1080 timeline reframes to 1080x1920 (9:16) or 1080x1080 (1:1)
    without inventing pixels. Dimensions are rounded to even numbers for
    h264 compatibility.
    """
    if aspect not in ASPECT_RATIOS:
        raise ValidationError(
            f"Unknown aspect {aspect!r}; expected one of {sorted(ASPECT_RATIOS)}."
        )
    rw, rh = ASPECT_RATIOS[aspect]
    short = min(base)
    if rw >= rh:
        width, height = round(short * rw / rh), short
    else:
        width, height = short, round(short * rh / rw)
    return (width // 2 * 2, height // 2 * 2)


# --- model -----------------------------------------------------------------


@dataclass
class Transition:
    """A transition applied at the head of a clip, from the previous clip."""

    kind: str = "crossfade"
    duration: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "duration": self.duration}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transition:
        return cls(kind=data["kind"], duration=float(data["duration"]))


@dataclass
class Clip:
    """One clip on the video track: a source-time window of a media file.

    ``in_point``/``out_point`` are seconds in the *source* file; ``speed``
    scales playback (2.0 = twice as fast). ``transition_in`` crossfades from
    the previous clip and consumes that duration of overlap.
    """

    clip_id: str
    src: str
    in_point: float
    out_point: float
    speed: float = 1.0
    transition_in: Transition | None = None

    @property
    def duration(self) -> float:
        """Duration of this clip on the timeline, in seconds (speed-adjusted)."""
        return (self.out_point - self.in_point) / self.speed

    def to_dict(self) -> dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "src": self.src,
            "in_point": self.in_point,
            "out_point": self.out_point,
            "speed": self.speed,
            "transition_in": self.transition_in.to_dict()
            if self.transition_in
            else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Clip:
        transition = data.get("transition_in")
        return cls(
            clip_id=data["clip_id"],
            src=data["src"],
            in_point=float(data["in_point"]),
            out_point=float(data["out_point"]),
            speed=float(data.get("speed", 1.0)),
            transition_in=Transition.from_dict(transition) if transition else None,
        )


@dataclass
class TextOverlay:
    """A styled text overlay burned in between ``start`` and ``end`` (timeline s)."""

    text_id: str
    text: str
    start: float
    end: float
    style_preset: str = "title"  # one of STYLE_PRESETS
    position: str | None = None  # one of POSITIONS; None = preset default

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_id": self.text_id,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "style_preset": self.style_preset,
            "position": self.position,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TextOverlay:
        return cls(
            text_id=data["text_id"],
            text=data["text"],
            start=float(data["start"]),
            end=float(data["end"]),
            style_preset=data.get("style_preset", "title"),
            position=data.get("position"),
        )


@dataclass
class Caption:
    """One timed caption phrase, burned in with the 'caption' style."""

    text: str
    start: float
    end: float

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Caption:
        return cls(
            text=data["text"], start=float(data["start"]), end=float(data["end"])
        )


@dataclass
class AudioTrack:
    """Background music: looped under the program, optionally ducked.

    When ``duck_under_dialogue`` is true the renderer lowers the music during
    caption intervals (captions mark dialogue) — a volume-automation
    approximation of sidechain compression.
    """

    src: str
    gain_db: float = 0.0
    duck_under_dialogue: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "src": self.src,
            "gain_db": self.gain_db,
            "duck_under_dialogue": self.duck_under_dialogue,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AudioTrack:
        return cls(
            src=data["src"],
            gain_db=float(data.get("gain_db", 0.0)),
            duck_under_dialogue=bool(data.get("duck_under_dialogue", True)),
        )


@dataclass
class ChangelogEntry:
    """What one operation did, in words the agent can speak.

    ``summary`` is a human sentence; ``details`` carries the machine facts
    (ids, times) for logging or UI.
    """

    op: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Timeline:
    """The whole edit: video track, overlays, captions, music, output format."""

    fps: int = 30
    resolution: tuple[int, int] = (1920, 1080)
    aspect: str = "16:9"
    clips: list[Clip] = field(default_factory=list)
    texts: list[TextOverlay] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)
    music: AudioTrack | None = None

    # -- queries ------------------------------------------------------------

    @property
    def duration(self) -> float:
        """Total program duration in seconds (crossfades overlap clips)."""
        total = sum(clip.duration for clip in self.clips)
        for clip in self.clips[1:]:
            if clip.transition_in is not None:
                total -= clip.transition_in.duration
        return total

    def get_clip(self, clip_id: str) -> Clip | None:
        return next((c for c in self.clips if c.clip_id == clip_id), None)

    def get_text(self, text_id: str) -> TextOverlay | None:
        return next((t for t in self.texts if t.text_id == text_id), None)

    def clip_start_times(self) -> list[float]:
        """Timeline start time of each clip, in track order."""
        starts: list[float] = []
        t = 0.0
        for i, clip in enumerate(self.clips):
            if i > 0 and clip.transition_in is not None:
                t -= clip.transition_in.duration
            starts.append(t)
            t += clip.duration
        return starts

    def clip_at(self, at: float) -> Clip | None:
        """The clip playing at timeline time ``at`` (None outside the program)."""
        for clip, start in zip(self.clips, self.clip_start_times()):
            if start - _EPS <= at < start + clip.duration - _EPS:
                return clip
        return None

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "fps": self.fps,
            "resolution": list(self.resolution),
            "aspect": self.aspect,
            "clips": [c.to_dict() for c in self.clips],
            "texts": [t.to_dict() for t in self.texts],
            "captions": [c.to_dict() for c in self.captions],
            "music": self.music.to_dict() if self.music else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Timeline:
        music = data.get("music")
        return cls(
            fps=int(data.get("fps", 30)),
            resolution=tuple(data.get("resolution", (1920, 1080))),  # type: ignore[arg-type]
            aspect=data.get("aspect", "16:9"),
            clips=[Clip.from_dict(c) for c in data.get("clips", [])],
            texts=[TextOverlay.from_dict(t) for t in data.get("texts", [])],
            captions=[Caption.from_dict(c) for c in data.get("captions", [])],
            music=AudioTrack.from_dict(music) if music else None,
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, payload: str) -> Timeline:
        return cls.from_dict(json.loads(payload))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def load(cls, path: str | Path) -> Timeline:
        return cls.from_json(Path(path).read_text())
