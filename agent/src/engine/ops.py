"""Editing operations for the Director FAL edit engine.

Every operation is a pure function ``(Timeline, ...) -> (Timeline,
ChangelogEntry)``: the input timeline is never mutated, the returned timeline
is a deep copy with the edit applied, and the changelog entry is a spoken-ready
sentence plus machine details. Invalid edits raise
:class:`~engine.timeline.ValidationError` with a clear message.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from engine.timeline import (
    ASPECT_RATIOS,
    POSITIONS,
    SPEED_MAX,
    SPEED_MIN,
    STYLE_PRESETS,
    AudioTrack,
    Caption,
    ChangelogEntry,
    Clip,
    TextOverlay,
    Timeline,
    Transition,
    ValidationError,
    resolution_for_aspect,
)

OpResult = tuple[Timeline, ChangelogEntry]

_BOUNDARY_EPS = 1e-3  # splits this close to a cut are rejected as no-ops


# --- internal helpers ------------------------------------------------------


def _clip_or_raise(timeline: Timeline, clip_id: str) -> Clip:
    clip = timeline.get_clip(clip_id)
    if clip is None:
        known = ", ".join(c.clip_id for c in timeline.clips) or "none"
        raise ValidationError(f"No clip {clip_id!r} on the timeline (clips: {known}).")
    return clip


def _text_or_raise(timeline: Timeline, text_id: str) -> TextOverlay:
    text = timeline.get_text(text_id)
    if text is None:
        known = ", ".join(t.text_id for t in timeline.texts) or "none"
        raise ValidationError(f"No text overlay {text_id!r} (overlays: {known}).")
    return text


def _check_range(start: float, end: float, what: str) -> None:
    if start < 0:
        raise ValidationError(f"{what} start must be >= 0, got {start:g}.")
    if end <= start:
        raise ValidationError(
            f"{what} end must be after start, got {start:g} -> {end:g}."
        )


def _check_speed(speed: float) -> None:
    if not SPEED_MIN <= speed <= SPEED_MAX:
        raise ValidationError(
            f"Speed must be between {SPEED_MIN:g}x and {SPEED_MAX:g}x, got {speed:g}."
        )


def _unique_clip_id(timeline: Timeline, base: str) -> str:
    if timeline.get_clip(base) is None:
        return base
    n = 2
    while timeline.get_clip(f"{base}-{n}") is not None:
        n += 1
    return f"{base}-{n}"


def _unique_text_id(timeline: Timeline, base: str) -> str:
    if timeline.get_text(base) is None:
        return base
    n = 2
    while timeline.get_text(f"{base}-{n}") is not None:
        n += 1
    return f"{base}-{n}"


# --- clip operations -------------------------------------------------------


def split_clip(timeline: Timeline, at: float) -> OpResult:
    """Split the clip playing at timeline time ``at`` into two clips.

    The first half keeps the clip id and any incoming transition; the second
    half gets a derived id and butts against the first (no transition).
    """
    tl = copy.deepcopy(timeline)
    clip = tl.clip_at(at)
    if clip is None:
        raise ValidationError(
            f"No clip at {at:g}s — the program is {tl.duration:g}s long."
        )
    start = tl.clip_start_times()[tl.clips.index(clip)]
    if not (start + _BOUNDARY_EPS < at < start + clip.duration - _BOUNDARY_EPS):
        raise ValidationError(
            f"Cannot split {clip.clip_id!r} at {at:g}s: that is a cut point already."
        )
    src_at = clip.in_point + (at - start) * clip.speed
    second = Clip(
        clip_id=_unique_clip_id(tl, f"{clip.clip_id}-b"),
        src=clip.src,
        in_point=src_at,
        out_point=clip.out_point,
        speed=clip.speed,
    )
    clip.out_point = src_at
    tl.clips.insert(tl.clips.index(clip) + 1, second)
    return tl, ChangelogEntry(
        op="split_clip",
        summary=(
            f"Split {clip.clip_id!r} at {at:g}s into "
            f"{clip.clip_id!r} and {second.clip_id!r}."
        ),
        details={"at": at, "first": clip.clip_id, "second": second.clip_id},
    )


def trim(timeline: Timeline, clip_id: str, new_in: float, new_out: float) -> OpResult:
    """Set a clip's source in/out points (seconds in the source file)."""
    _check_range(new_in, new_out, f"Trim of {clip_id!r}:")
    tl = copy.deepcopy(timeline)
    clip = _clip_or_raise(tl, clip_id)
    old = (clip.in_point, clip.out_point)
    clip.in_point, clip.out_point = new_in, new_out
    return tl, ChangelogEntry(
        op="trim",
        summary=(
            f"Trimmed {clip_id!r} to source {new_in:g}s-{new_out:g}s "
            f"({clip.duration:g}s on the timeline)."
        ),
        details={"clip_id": clip_id, "old": old, "new": (new_in, new_out)},
    )


def reorder(timeline: Timeline, clip_id: str, index: int) -> OpResult:
    """Move a clip to ``index`` on the track (0-based)."""
    tl = copy.deepcopy(timeline)
    clip = _clip_or_raise(tl, clip_id)
    if not 0 <= index < len(tl.clips):
        raise ValidationError(f"Index {index} out of range for {len(tl.clips)} clips.")
    tl.clips.remove(clip)
    tl.clips.insert(index, clip)
    if tl.clips[0].transition_in is not None:
        tl.clips[0].transition_in = None  # nothing before the first clip
    return tl, ChangelogEntry(
        op="reorder",
        summary=f"Moved {clip_id!r} to position {index + 1} of {len(tl.clips)}.",
        details={"clip_id": clip_id, "index": index},
    )


def delete_clip(timeline: Timeline, clip_id: str) -> OpResult:
    """Remove a clip from the track."""
    tl = copy.deepcopy(timeline)
    clip = _clip_or_raise(tl, clip_id)
    tl.clips.remove(clip)
    if tl.clips and tl.clips[0].transition_in is not None:
        tl.clips[0].transition_in = None
    return tl, ChangelogEntry(
        op="delete_clip",
        summary=f"Deleted {clip_id!r}; {len(tl.clips)} clips remain.",
        details={"clip_id": clip_id},
    )


def set_speed(timeline: Timeline, clip_id: str, speed: float) -> OpResult:
    """Set a clip's playback speed (0.25x-4x, audio pitch-corrected)."""
    _check_speed(speed)
    tl = copy.deepcopy(timeline)
    clip = _clip_or_raise(tl, clip_id)
    clip.speed = speed
    return tl, ChangelogEntry(
        op="set_speed",
        summary=f"Set {clip_id!r} to {speed:g}x ({clip.duration:g}s on the timeline).",
        details={"clip_id": clip_id, "speed": speed},
    )


def replace_clip_media(
    timeline: Timeline,
    clip_id: str,
    new_src: str,
    new_in: float | None = None,
    new_out: float | None = None,
) -> OpResult:
    """Swap a clip's source file, keeping its window unless new points are given."""
    tl = copy.deepcopy(timeline)
    clip = _clip_or_raise(tl, clip_id)
    clip.src = new_src
    if new_in is not None or new_out is not None:
        in_point = clip.in_point if new_in is None else new_in
        out_point = clip.out_point if new_out is None else new_out
        _check_range(in_point, out_point, f"Trim of {clip_id!r}:")
        clip.in_point, clip.out_point = in_point, out_point
    return tl, ChangelogEntry(
        op="replace_clip_media",
        summary=f"Replaced the media in {clip_id!r} with {new_src!r}.",
        details={"clip_id": clip_id, "src": new_src},
    )


def insert_clip(
    timeline: Timeline,
    src: str,
    in_point: float,
    out_point: float,
    index: int | None = None,
    clip_id: str | None = None,
) -> OpResult:
    """Insert a new clip at ``index`` (default: append to the end)."""
    _check_range(in_point, out_point, "New clip:")
    tl = copy.deepcopy(timeline)
    if index is None:
        index = len(tl.clips)
    if not 0 <= index <= len(tl.clips):
        raise ValidationError(
            f"Insert index {index} out of range for {len(tl.clips)} clips."
        )
    if clip_id is not None and tl.get_clip(clip_id) is not None:
        raise ValidationError(f"Clip id {clip_id!r} already exists.")
    clip = Clip(
        clip_id=clip_id or _unique_clip_id(tl, f"c{len(tl.clips) + 1}"),
        src=src,
        in_point=in_point,
        out_point=out_point,
    )
    tl.clips.insert(index, clip)
    return tl, ChangelogEntry(
        op="insert_clip",
        summary=(
            f"Inserted {clip.clip_id!r} ({clip.duration:g}s) at position {index + 1}."
        ),
        details={"clip_id": clip.clip_id, "index": index, "src": src},
    )


def add_transition(
    timeline: Timeline, clip_id: str, duration: float, kind: str = "crossfade"
) -> OpResult:
    """Crossfade into ``clip_id`` from the previous clip over ``duration`` seconds."""
    if kind != "crossfade":
        raise ValidationError(f"Unknown transition kind {kind!r}; only 'crossfade'.")
    if duration <= 0:
        raise ValidationError(f"Transition duration must be > 0, got {duration:g}.")
    tl = copy.deepcopy(timeline)
    clip = _clip_or_raise(tl, clip_id)
    index = tl.clips.index(clip)
    if index == 0:
        raise ValidationError(
            f"{clip_id!r} is the first clip; there is nothing to crossfade from."
        )
    prev = tl.clips[index - 1]
    limit = min(prev.duration, clip.duration)
    if duration >= limit:
        raise ValidationError(
            f"A {duration:g}s crossfade needs both neighbours longer than that "
            f"(shortest is {limit:g}s)."
        )
    clip.transition_in = Transition(kind=kind, duration=duration)
    return tl, ChangelogEntry(
        op="add_transition",
        summary=f"Added a {duration:g}s crossfade from {prev.clip_id!r} into {clip_id!r}.",
        details={"clip_id": clip_id, "duration": duration, "kind": kind},
    )


# --- text and caption operations -------------------------------------------


def add_text(
    timeline: Timeline,
    text: str,
    start: float,
    end: float,
    style_preset: str = "title",
    position: str | None = None,
    text_id: str | None = None,
) -> OpResult:
    """Add a styled text overlay between ``start`` and ``end`` (timeline s)."""
    _check_range(start, end, "Text overlay:")
    if style_preset not in STYLE_PRESETS:
        raise ValidationError(
            f"Unknown style preset {style_preset!r}; expected one of {STYLE_PRESETS}."
        )
    if position is not None and position not in POSITIONS:
        raise ValidationError(
            f"Unknown position {position!r}; expected one of {POSITIONS}."
        )
    tl = copy.deepcopy(timeline)
    if text_id is not None and tl.get_text(text_id) is not None:
        raise ValidationError(f"Text id {text_id!r} already exists.")
    overlay = TextOverlay(
        text_id=text_id or _unique_text_id(tl, f"t{len(tl.texts) + 1}"),
        text=text,
        start=start,
        end=end,
        style_preset=style_preset,
        position=position,
    )
    tl.texts.append(overlay)
    return tl, ChangelogEntry(
        op="add_text",
        summary=f'Added {style_preset} "{text}" from {start:g}s to {end:g}s.',
        details={"text_id": overlay.text_id, "style_preset": style_preset},
    )


def update_text(
    timeline: Timeline,
    text_id: str,
    text: str | None = None,
    start: float | None = None,
    end: float | None = None,
    style_preset: str | None = None,
    position: str | None = None,
) -> OpResult:
    """Change any field of an existing text overlay (None = keep current)."""
    tl = copy.deepcopy(timeline)
    overlay = _text_or_raise(tl, text_id)
    if text is not None:
        overlay.text = text
    new_start = overlay.start if start is None else start
    new_end = overlay.end if end is None else end
    _check_range(new_start, new_end, f"Text overlay {text_id!r}:")
    overlay.start, overlay.end = new_start, new_end
    if style_preset is not None:
        if style_preset not in STYLE_PRESETS:
            raise ValidationError(
                f"Unknown style preset {style_preset!r}; "
                f"expected one of {STYLE_PRESETS}."
            )
        overlay.style_preset = style_preset
    if position is not None:
        if position not in POSITIONS:
            raise ValidationError(
                f"Unknown position {position!r}; expected one of {POSITIONS}."
            )
        overlay.position = position
    return tl, ChangelogEntry(
        op="update_text",
        summary=f'Updated {text_id!r} to "{overlay.text}" '
        f"({overlay.start:g}s-{overlay.end:g}s).",
        details={"text_id": text_id},
    )


def remove_text(timeline: Timeline, text_id: str) -> OpResult:
    """Remove a text overlay."""
    tl = copy.deepcopy(timeline)
    overlay = _text_or_raise(tl, text_id)
    tl.texts.remove(overlay)
    return tl, ChangelogEntry(
        op="remove_text",
        summary=f'Removed the text "{overlay.text}".',
        details={"text_id": text_id},
    )


def add_captions(
    timeline: Timeline, phrases: Sequence[Mapping[str, Any] | Caption]
) -> OpResult:
    """Add timed caption phrases (dicts with text/start/end, or Captions).

    Captions are burned in with the 'caption' preset and also mark dialogue
    intervals for music ducking.
    """
    tl = copy.deepcopy(timeline)
    added: list[Caption] = []
    for phrase in phrases:
        cap = phrase if isinstance(phrase, Caption) else Caption.from_dict(dict(phrase))
        _check_range(cap.start, cap.end, f'Caption "{cap.text}":')
        added.append(cap)
    tl.captions.extend(added)
    tl.captions.sort(key=lambda c: c.start)
    return tl, ChangelogEntry(
        op="add_captions",
        summary=f"Added {len(added)} captions ({len(tl.captions)} total).",
        details={"count": len(added)},
    )


# --- music operations ------------------------------------------------------


def set_music(
    timeline: Timeline,
    src: str,
    gain_db: float = 0.0,
    duck_under_dialogue: bool = True,
) -> OpResult:
    """Set (or replace) the music bed. It loops to fill the program."""
    tl = copy.deepcopy(timeline)
    tl.music = AudioTrack(
        src=src, gain_db=gain_db, duck_under_dialogue=duck_under_dialogue
    )
    ducked = "with dialogue ducking" if duck_under_dialogue else "no ducking"
    return tl, ChangelogEntry(
        op="set_music",
        summary=f"Set music to {src!r} at {gain_db:g} dB, {ducked}.",
        details={"src": src, "gain_db": gain_db},
    )


def set_gain(timeline: Timeline, gain_db: float) -> OpResult:
    """Adjust the music gain in dB (requires music to be set)."""
    if timeline.music is None:
        raise ValidationError("No music on the timeline; call set_music first.")
    tl = copy.deepcopy(timeline)
    assert tl.music is not None  # for the type checker; validated above
    tl.music.gain_db = gain_db
    return tl, ChangelogEntry(
        op="set_gain",
        summary=f"Set music gain to {gain_db:g} dB.",
        details={"gain_db": gain_db},
    )


# --- reframe ---------------------------------------------------------------


def reframe(timeline: Timeline, aspect: str) -> OpResult:
    """Reframe the timeline to '16:9', '9:16', or '1:1' (smart center-crop)."""
    if aspect not in ASPECT_RATIOS:
        raise ValidationError(
            f"Unknown aspect {aspect!r}; expected one of {sorted(ASPECT_RATIOS)}."
        )
    tl = copy.deepcopy(timeline)
    tl.resolution = resolution_for_aspect(tl.resolution, aspect)
    tl.aspect = aspect
    return tl, ChangelogEntry(
        op="reframe",
        summary=f"Reframed to {aspect} ({tl.resolution[0]}x{tl.resolution[1]}).",
        details={"aspect": aspect, "resolution": tl.resolution},
    )
