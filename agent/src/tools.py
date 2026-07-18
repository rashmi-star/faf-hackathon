"""The Director's full tool surface: generation plus every timeline edit.

Two layers, one contract. The generation tools (SPEC section 5) drive the
media backend behind :mod:`media` (MockMedia or FalMedia) — story, characters,
storyboards, shot renders, dialogue replacement. The editing tools are 1:1
wrappers over the pure operations in :mod:`engine.ops`, applied to the session
:class:`~engine.timeline.Timeline` held in project state. Every mutation is
committed through :func:`state.apply_edit` (which records the changelog entry
and an undo snapshot) and immediately followed by ``publish_state``, so the
frontend timeline always mirrors the engine.

Each tool returns one short human sentence — for edits, the changelog
summary itself — which the agent speaks back to the user. Long-running tools
are async LiveKit function tools: they call ``ctx.update()`` for spoken
progress and ``ctx.with_filler()`` for gaps, so the agent keeps talking
during renders.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from livekit.agents import RunContext, function_tool

from engine import ops as engine_ops
from engine.render import probe_media, render
from engine.timeline import ChangelogEntry, Clip, Timeline, ValidationError
from media import (
    DIALOGUE_VOICE_ID,
    EXPORT_SPECS,
    LOOP_DURATION_S,
    get_media,
    resolve_local,
)
from state import (
    STATE,
    Character,
    ExportItem,
    Highlight,
    Shot,
    Story,
    apply_edit,
    publish_state,
    undo_last_edit,
)

logger = logging.getLogger("director.tools")

# 720p keeps local ffmpeg renders demo-fast; exports reframe from this base.
TIMELINE_RESOLUTION = (1280, 720)
TIMELINE_FPS = 30

EXPORT_DIR = Path(
    os.getenv("DIRECTOR_EXPORT_DIR")
    or Path(__file__).resolve().parent.parent / "exports"
)


def _slug(name: str) -> str:
    return "".join(c for c in name.lower().replace(" ", "-") if c.isalnum() or c == "-")


async def _apply(
    ctx: RunContext, op: Callable[..., engine_ops.OpResult], /, *args: Any, **kwargs: Any
) -> str:
    """Run an engine op on the session timeline, commit it, publish, narrate.

    Validation failures come back as a plain sentence (not an exception) so
    the agent can speak the correction and move on.
    """
    try:
        new_timeline, entry = op(STATE.timeline, *args, **kwargs)
    except ValidationError as err:
        return f"That edit did not apply: {err}"
    apply_edit(new_timeline, entry)
    await publish_state(ctx.session)
    return entry.summary


async def _clip_from_shot(shot: Shot) -> Clip:
    """Build a timeline clip for a rendered shot, clamped to the real media."""
    src = await resolve_local(shot.video_url)
    wanted = shot.end - shot.start
    info = await asyncio.to_thread(probe_media, src)
    out_point = min(wanted, info.duration) if info.duration else wanted
    return Clip(clip_id=shot.id, src=src, in_point=0.0, out_point=out_point)


def _clipped_copy(timeline: Timeline, seconds: float) -> Timeline:
    """A copy of ``timeline`` cut down to its first ``seconds`` seconds."""
    tl = copy.deepcopy(timeline)
    kept: list[Clip] = []
    remaining = seconds
    for clip in tl.clips:
        overlap = (
            clip.transition_in.duration if kept and clip.transition_in else 0.0
        )
        contribution = clip.duration - overlap
        if contribution >= remaining - 1e-6:
            clip.out_point = clip.in_point + (remaining + overlap) * clip.speed
            kept.append(clip)
            break
        kept.append(clip)
        remaining -= contribution
    tl.clips = kept
    tl.texts = [t for t in tl.texts if t.start < seconds]
    for text in tl.texts:
        text.end = min(text.end, seconds)
    tl.captions = [c for c in tl.captions if c.start < seconds]
    for caption in tl.captions:
        caption.end = min(caption.end, seconds)
    return tl


# ---------------------------------------------------------------------------
# Production tools (SPEC section 5): story -> cast -> storyboard -> render


@function_tool
async def set_story(ctx: RunContext, logline: str, scene: str, style: str) -> str:
    """Lock the brainstormed story and advance to character creation.

    Call this once you and the user have agreed on the story.

    Args:
        logline: One-sentence summary of the story.
        scene: Where and when it takes place (location, time of day, mood).
        style: Visual style, e.g. "cinematic, golden hour, anamorphic".
    """
    STATE.story = Story(logline=logline, scene=scene, style=style)
    STATE.phase = "characters"
    await publish_state(ctx.session)
    return "Story locked. Now create each main character with create_character."


@function_tool
async def create_character(ctx: RunContext, name: str, sheet: str) -> str:
    """Generate a character portrait and show it as a card in the studio.

    Args:
        name: Character name, e.g. "Maya".
        sheet: Full character sheet — appearance, wardrobe, and personality —
            written as an image prompt. This exact sheet is reused in every
            later generation for consistency, so make it vivid and specific.
    """
    await ctx.update(f"Painting a portrait of {name} now.")
    url = await get_media().portrait(name, sheet, STATE.story.style)
    char = Character(id=_slug(name), name=name, sheet=sheet, image_url=url)
    STATE.characters = [c for c in STATE.characters if c.id != char.id]
    STATE.characters.append(char)
    await publish_state(ctx.session)
    return (
        f"Portrait of {name} is on screen. Ask the user to approve it before moving on."
    )


@function_tool
async def plan_shots(ctx: RunContext, shots_json: str) -> str:
    """Write the shot plan and render a storyboard still for every shot.

    Only call this after the user has approved all character portraits.

    Args:
        shots_json: JSON array of 3-4 shot objects covering 20-30 seconds
            total. Each object: {"id": "s1", "start": 0.0, "end": 8.0,
            "prompt": "what happens, camera, characters by name",
            "dialogue": "spoken line or null"}.
    """
    for c in STATE.characters:
        c.approved = True  # voice approval happened before this call
    shots = json.loads(shots_json)
    STATE.shots = [
        Shot(
            id=s["id"],
            start=float(s["start"]),
            end=float(s["end"]),
            prompt=s["prompt"],
            dialogue=s.get("dialogue"),
        )
        for s in shots
    ]
    STATE.phase = "scene"
    await publish_state(ctx.session)
    await ctx.update(
        f"Shot plan is set: {len(STATE.shots)} shots. Drawing the storyboard."
    )
    for shot in STATE.shots:
        shot.still_url = await get_media().still(shot.prompt, STATE.story.style)
        shot.status = "still"
        await publish_state(ctx.session)
    return (
        "Storyboard stills are on the timeline. Walk the user through them and "
        "get approval before calling render_all."
    )


@function_tool
async def render_all(ctx: RunContext) -> str:
    """Render video for every shot and assemble the editable timeline.

    Only call this after the user has approved the storyboard. Never render
    video before approval.
    """
    if not STATE.shots:
        return "No shot plan exists yet. Call plan_shots first."
    media = get_media()
    STATE.phase = "generating"
    await publish_state(ctx.session)
    total = len(STATE.shots)
    await ctx.update(f"Rolling cameras on all {total} shots. This takes a moment.")
    for i, shot in enumerate(STATE.shots, start=1):
        shot.status = "rendering"
        await publish_state(ctx.session)
        async with ctx.with_filler(
            "Still rendering, the frames are looking great.", delay=8, interval=15
        ):
            shot.video_url = await media.shot_video(
                shot.still_url, shot.prompt, shot.end - shot.start
            )
            if shot.dialogue:
                audio_url = await media.dialogue_audio(shot.dialogue, DIALOGUE_VOICE_ID)
                shot.video_url = await media.lipsync(shot.video_url, audio_url)
        shot.status = "ready"
        await publish_state(ctx.session)
        if i < total:
            await ctx.update(f"Shot {i} of {total} is in the can.")
    STATE.timeline_url = await media.assemble(
        [(s.video_url, s.end - s.start) for s in STATE.shots]
    )
    # Build the edit-engine session timeline: one clip per rendered shot.
    timeline = Timeline(
        fps=TIMELINE_FPS,
        resolution=TIMELINE_RESOLUTION,
        clips=[await _clip_from_shot(shot) for shot in STATE.shots],
    )
    apply_edit(
        timeline,
        ChangelogEntry(
            op="assemble",
            summary=(
                f"Assembled {total} shots into a {timeline.duration:g} second timeline."
            ),
            details={"clips": [c.clip_id for c in timeline.clips]},
        ),
    )
    STATE.phase = "review"
    await publish_state(ctx.session)
    return (
        "That's a wrap on the first cut — the full timeline is playing. "
        "Ask the user what they'd like to change."
    )


@function_tool
async def highlight(ctx: RunContext, start: float, end: float) -> str:
    """Instantly highlight a time range on the timeline.

    Call this IMMEDIATELY whenever the user references a moment in time
    (e.g. "around 15 seconds"), before discussing or making any change.

    Args:
        start: Range start in seconds.
        end: Range end in seconds.
    """
    STATE.highlight = Highlight(start=start, end=end)
    await publish_state(ctx.session)
    return f"Highlighted {start:g}s to {end:g}s on the timeline."


@function_tool
async def replace_segment(
    ctx: RunContext, shot_id: str, new_prompt: str = "", new_dialogue: str = ""
) -> str:
    """Re-render one shot with a new prompt and/or new dialogue.

    If only the dialogue changes, the existing clip is kept and lipsynced to a
    new voice line (fast). If the prompt changes, the shot is re-rendered.
    This spends generation credits — confirm the change with the user first.

    Args:
        shot_id: The id of the shot to replace, e.g. "s2".
        new_prompt: New visual prompt; empty string keeps the current visuals.
        new_dialogue: New spoken line; empty string keeps the current line.
    """
    shot = STATE.get_shot(shot_id)
    if shot is None:
        return f"No shot named {shot_id}. Use show_status to see the shot list."
    media = get_media()
    shot.status = "replacing"
    await publish_state(ctx.session)
    await ctx.update(f"Reworking shot {shot_id} now.")
    async with ctx.with_filler("Almost there, dropping the new take in.", delay=8):
        if new_prompt:
            shot.prompt = new_prompt
            shot.still_url = await media.still(shot.prompt, STATE.story.style)
            shot.video_url = await media.shot_video(
                shot.still_url, shot.prompt, shot.end - shot.start
            )
        if new_dialogue:
            shot.dialogue = new_dialogue
        if new_dialogue or (new_prompt and shot.dialogue):
            audio_url = await media.dialogue_audio(
                shot.dialogue or "", DIALOGUE_VOICE_ID
            )
            shot.video_url = await media.lipsync(shot.video_url, audio_url)
        shot.status = "ready"
        await publish_state(ctx.session)
        STATE.timeline_url = await media.assemble(
            [(s.video_url, s.end - s.start) for s in STATE.shots]
        )
    # Drop the new take into the engine timeline when the clip is on the track.
    if STATE.timeline.get_clip(shot_id) is not None:
        new_clip = await _clip_from_shot(shot)
        apply_edit(
            *engine_ops.replace_clip_media(
                STATE.timeline, shot_id, new_clip.src, 0.0, new_clip.out_point
            )
        )
    STATE.highlight = None
    STATE.phase = "review"
    await publish_state(ctx.session)
    return f"The new take for {shot_id} is in the timeline. Ask how it looks."


@function_tool
async def export(ctx: RunContext, formats: list[str]) -> str:
    """Export the finished film in the requested formats.

    Renders each format from the session timeline with the real edit engine
    (16:9, 9:16, and 1:1 reframes; "loop" is the first 8 seconds in 16:9).

    Args:
        formats: Any of "16:9", "9:16", "1:1", "loop". When the user just says
            "export", pass all four.
    """
    if not STATE.timeline.clips and not STATE.timeline_url:
        return "Nothing to export yet — render the timeline first."
    STATE.phase = "exporting"
    await publish_state(ctx.session)
    await ctx.update("Exporting every format now.")
    for fmt in formats:
        if fmt not in EXPORT_SPECS:
            continue
        if STATE.timeline.clips:
            timeline = STATE.timeline
            aspect = fmt
            if fmt == "loop":
                timeline = _clipped_copy(timeline, LOOP_DURATION_S)
                aspect = "16:9"
            out = EXPORT_DIR / f"export-{fmt.replace(':', 'x')}.mp4"
            await asyncio.to_thread(render, timeline, out, aspect)
            url = str(out)
        else:  # no engine timeline (e.g. crash recovery): fal compose fallback
            url = await get_media().export(STATE.timeline_url, fmt)
        STATE.exports = [e for e in STATE.exports if e.format != fmt]
        STATE.exports.append(ExportItem(format=fmt, url=url))
        await publish_state(ctx.session)
    return (
        f"All set — {len(STATE.exports)} download cards are on screen. "
        "Tell the user their film is ready in every format."
    )


@function_tool
async def show_status(ctx: RunContext) -> str:
    """Report the current phase, shots, timeline, and last edit so you can speak it."""
    lines = [f"Phase: {STATE.phase}."]
    for s in STATE.shots:
        lines.append(f"Shot {s.id} ({s.start:g}-{s.end:g}s): {s.status}.")
    tl = STATE.timeline
    if tl.clips:
        lines.append(
            f"Timeline: {len(tl.clips)} clips, {tl.duration:g}s, {tl.aspect}, "
            f"{len(tl.texts)} text overlays, {len(tl.captions)} captions, "
            f"music {'on' if tl.music else 'off'}."
        )
    if STATE.changelog:
        lines.append(f"Last edit: {STATE.changelog[-1].summary}")
    if STATE.exports:
        lines.append(f"Exports ready: {', '.join(e.format for e in STATE.exports)}.")
    return " ".join(lines)


# ---------------------------------------------------------------------------
# Editing tools: 1:1 with engine.ops, applied to the session timeline


@function_tool
async def split(ctx: RunContext, at: float) -> str:
    """Cut whatever clip is playing at a timeline moment into two clips.

    Args:
        at: Timeline time in seconds to cut at (must fall inside a clip,
            not on an existing cut).
    """
    return await _apply(ctx, engine_ops.split_clip, at)


@function_tool
async def trim(ctx: RunContext, clip_id: str, new_in: float, new_out: float) -> str:
    """Set a clip's in and out points (seconds within its source media).

    Args:
        clip_id: The clip to trim, e.g. "s2".
        new_in: New in point in source seconds.
        new_out: New out point in source seconds (must be after new_in).
    """
    return await _apply(ctx, engine_ops.trim, clip_id, new_in, new_out)


@function_tool
async def reorder(ctx: RunContext, clip_id: str, index: int) -> str:
    """Move a clip to a new position on the track.

    Args:
        clip_id: The clip to move.
        index: Target position, 0-based (0 = first clip).
    """
    return await _apply(ctx, engine_ops.reorder, clip_id, index)


@function_tool
async def delete(ctx: RunContext, clip_id: str) -> str:
    """Remove a clip from the timeline entirely.

    Args:
        clip_id: The clip to delete.
    """
    return await _apply(ctx, engine_ops.delete_clip, clip_id)


@function_tool
async def speed(ctx: RunContext, clip_id: str, factor: float) -> str:
    """Change a clip's playback speed (slow motion or speed ramp).

    Args:
        clip_id: The clip to retime.
        factor: Playback speed from 0.25 (slow motion) to 4.0 (timelapse);
            1.0 is normal.
    """
    return await _apply(ctx, engine_ops.set_speed, clip_id, factor)


@function_tool
async def add_text(
    ctx: RunContext,
    text: str,
    start: float,
    end: float,
    style_preset: str = "title",
    position: str = "",
) -> str:
    """Burn a styled text overlay into the film between two timeline times.

    Args:
        text: The text to display.
        start: When it appears, in timeline seconds.
        end: When it disappears, in timeline seconds.
        style_preset: "title" (big centered card), "lower-third" (name/label
            block), or "caption" (bottom pill).
        position: Optional override: "center", "top", "bottom", "top-left",
            "top-right", "bottom-left", or "bottom-right". Empty uses the
            preset's default placement.
    """
    return await _apply(
        ctx,
        engine_ops.add_text,
        text,
        start,
        end,
        style_preset=style_preset,
        position=position or None,
    )


@function_tool
async def update_text(
    ctx: RunContext,
    text_id: str,
    text: str = "",
    start: float = -1.0,
    end: float = -1.0,
    position: str = "",
) -> str:
    """Edit an existing text overlay's wording, timing, or placement.

    Args:
        text_id: The overlay to change (e.g. "t1").
        text: New wording; empty keeps the current text.
        start: New start in seconds; -1 keeps the current start.
        end: New end in seconds; -1 keeps the current end.
        position: New placement (see add_text); empty keeps the current one.
    """
    return await _apply(
        ctx,
        engine_ops.update_text,
        text_id,
        text=text or None,
        start=None if start < 0 else start,
        end=None if end < 0 else end,
        position=position or None,
    )


@function_tool
async def remove_text(ctx: RunContext, text_id: str) -> str:
    """Delete a text overlay from the film.

    Args:
        text_id: The overlay to remove (e.g. "t1").
    """
    return await _apply(ctx, engine_ops.remove_text, text_id)


@function_tool
async def add_captions(ctx: RunContext, captions_json: str) -> str:
    """Burn timed dialogue captions into the film (they also duck the music).

    Args:
        captions_json: JSON array of phrases, each {"text": "...",
            "start": 4.2, "end": 6.0} in timeline seconds.
    """
    try:
        phrases = json.loads(captions_json)
    except json.JSONDecodeError as err:
        return f"That caption list was not valid JSON: {err}"
    return await _apply(ctx, engine_ops.add_captions, phrases)


@function_tool
async def set_music(ctx: RunContext, prompt: str, gain_db: float = -12.0) -> str:
    """Generate a music bed and lay it under the whole film.

    The music loops to fill the program and automatically ducks under
    dialogue captions. Generating music spends credits — confirm the vibe
    with the user first.

    Args:
        prompt: The music to generate, e.g. "warm ambient strings, hopeful".
        gain_db: Music level in dB relative to full scale; -12 sits nicely
            under dialogue.
    """
    await ctx.update("Scoring the film now.")
    duration = max(STATE.timeline.duration, LOOP_DURATION_S)
    url = await get_media().music(prompt, duration)
    src = await resolve_local(url)
    return await _apply(ctx, engine_ops.set_music, src, gain_db=gain_db)


@function_tool
async def set_gain(ctx: RunContext, gain_db: float) -> str:
    """Adjust how loud the music bed is.

    Args:
        gain_db: New music level in dB (0 is full scale, negative is quieter).
    """
    return await _apply(ctx, engine_ops.set_gain, gain_db)


@function_tool
async def transition(ctx: RunContext, clip_id: str, duration: float = 0.5) -> str:
    """Crossfade into a clip from the one before it.

    Args:
        clip_id: The clip the crossfade lands on (not the first clip).
        duration: Crossfade length in seconds; both neighbours must be longer.
    """
    return await _apply(ctx, engine_ops.add_transition, clip_id, duration)


@function_tool
async def reframe(ctx: RunContext, aspect: str) -> str:
    """Reframe the whole film for a different aspect ratio (smart center-crop).

    Args:
        aspect: "16:9" (YouTube), "9:16" (Reels/Shorts), or "1:1" (square).
    """
    return await _apply(ctx, engine_ops.reframe, aspect)


@function_tool
async def insert_clip(
    ctx: RunContext, prompt: str, duration: float, index: int = -1
) -> str:
    """Generate a brand-new clip (b-roll) and insert it into the timeline.

    This spends generation credits — confirm the shot idea with the user
    first, preview-before-spend.

    Args:
        prompt: What the new clip shows, e.g. "aerial of the Golden Gate
            Bridge at golden hour".
        duration: Clip length in seconds.
        index: Track position to insert at, 0-based; -1 appends to the end.
    """
    media = get_media()
    await ctx.update("Shooting that new clip now.")
    async with ctx.with_filler("The new footage is almost in.", delay=8):
        still_url = await media.still(prompt, STATE.story.style)
        video_url = await media.shot_video(still_url, prompt, duration)
    src = await resolve_local(video_url)
    info = await asyncio.to_thread(probe_media, src)
    out_point = min(duration, info.duration) if info.duration else duration
    return await _apply(
        ctx,
        engine_ops.insert_clip,
        src,
        0.0,
        out_point,
        index=None if index < 0 else index,
    )


@function_tool
async def undo_last(ctx: RunContext) -> str:
    """Undo the most recent timeline edit (one step back through the changelog)."""
    entry = undo_last_edit()
    if entry is None:
        return "There is nothing to undo yet."
    await publish_state(ctx.session)
    return entry.summary


ALL_TOOLS = [
    # production
    set_story,
    create_character,
    plan_shots,
    render_all,
    highlight,
    replace_segment,
    export,
    show_status,
    # editing (engine.ops)
    split,
    trim,
    reorder,
    delete,
    speed,
    add_text,
    update_text,
    remove_text,
    add_captions,
    set_music,
    set_gain,
    transition,
    reframe,
    insert_clip,
    undo_last,
]
