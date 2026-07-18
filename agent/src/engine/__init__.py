"""Director FAL edit engine.

A small, real video-edit engine the director agent drives:

- :mod:`engine.timeline` — the data model (clips, text, captions, music) with
  JSON (de)serialization and changelog entries the agent narrates from.
- :mod:`engine.ops` — pure editing operations on a Timeline (split, trim,
  reorder, speed, text, captions, music, transitions, reframe).
- :mod:`engine.render` — the only module that touches ffmpeg. It compiles a
  Timeline into one deterministic ``filter_complex`` and renders a real mp4.
  fal's compose API can replace it later behind the same ``render()`` surface.
"""

from engine.timeline import (
    AudioTrack,
    Caption,
    ChangelogEntry,
    Clip,
    EngineError,
    TextOverlay,
    Timeline,
    Transition,
    ValidationError,
)

__all__ = [
    "AudioTrack",
    "Caption",
    "ChangelogEntry",
    "Clip",
    "EngineError",
    "TextOverlay",
    "Timeline",
    "Transition",
    "ValidationError",
]
