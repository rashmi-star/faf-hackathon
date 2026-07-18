"""The eight Director tools (SPEC section 5).

Every tool mutates the ProjectState singleton and immediately publishes a
``state_update`` to the room. Long-running tools are async LiveKit function
tools: they call ``ctx.update()`` for spoken progress and ``ctx.with_filler()``
for gaps, so the agent keeps talking during renders.
"""

from __future__ import annotations

import json
import logging

from livekit.agents import RunContext, function_tool

from media import DIALOGUE_VOICE_ID, EXPORT_SPECS, get_media
from state import STATE, Character, ExportItem, Highlight, Shot, Story, publish_state

logger = logging.getLogger("director.tools")


def _slug(name: str) -> str:
    return "".join(c for c in name.lower().replace(" ", "-") if c.isalnum() or c == "-")


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
    """Render video for every shot and assemble the timeline.

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
    STATE.highlight = None
    STATE.phase = "review"
    await publish_state(ctx.session)
    return f"The new take for {shot_id} is in the timeline. Ask how it looks."


@function_tool
async def export(ctx: RunContext, formats: list[str]) -> str:
    """Export the finished film in the requested formats.

    Args:
        formats: Any of "16:9", "9:16", "1:1", "loop". When the user just says
            "export", pass all four.
    """
    if not STATE.timeline_url:
        return "Nothing to export yet — render the timeline first."
    STATE.phase = "exporting"
    await publish_state(ctx.session)
    await ctx.update("Exporting every format now.")
    media = get_media()
    for fmt in formats:
        if fmt not in EXPORT_SPECS:
            continue
        url = await media.export(STATE.timeline_url, fmt)
        STATE.exports = [e for e in STATE.exports if e.format != fmt]
        STATE.exports.append(ExportItem(format=fmt, url=url))
        await publish_state(ctx.session)
    return (
        f"All set — {len(STATE.exports)} download cards are on screen. "
        "Tell the user their film is ready in every format."
    )


@function_tool
async def show_status(ctx: RunContext) -> str:
    """Report the current phase and render queue so you can speak it."""
    lines = [f"Phase: {STATE.phase}."]
    for s in STATE.shots:
        lines.append(f"Shot {s.id} ({s.start:g}-{s.end:g}s): {s.status}.")
    if STATE.exports:
        lines.append(f"Exports ready: {', '.join(e.format for e in STATE.exports)}.")
    return " ".join(lines)


ALL_TOOLS = [
    set_story,
    create_character,
    plan_shots,
    render_all,
    highlight,
    replace_segment,
    export,
    show_status,
]
