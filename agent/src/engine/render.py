"""Local ffmpeg renderer for the Director FAL edit engine.

This is the ONLY module that touches ffmpeg. It compiles a
:class:`~engine.timeline.Timeline` into one deterministic ``filter_complex``
(trims, speed via setpts/atempo, xfade/acrossfade crossfades, drawtext
overlays and caption burn-in, looped music with volume-automation ducking,
center-crop reframes) and runs it with subprocess. Because everything goes
through :func:`render`, fal's compose API can replace this renderer later
behind the same signature.

Text is drawn with the bundled Inter typeface (OFL) from
``agent/assets/fonts`` — run ``scripts/fetch_fonts.sh`` to install it — with
a fallback to the system Helvetica when Inter is missing. All text sizes,
margins, and paddings are fractions of the output resolution, never absolute
pixels.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from engine.timeline import (
    STYLE_PRESETS,
    Caption,
    Clip,
    EngineError,
    TextOverlay,
    Timeline,
    ValidationError,
    resolution_for_aspect,
)

logger = logging.getLogger("director.engine.render")


class RenderError(EngineError):
    """ffmpeg/ffprobe failed; the message carries the tool's stderr tail."""


# --- tool + font discovery -------------------------------------------------

_HOMEBREW_BIN = "/opt/homebrew/bin"
_HOMEBREW_FFMPEG_FULL_BIN = "/opt/homebrew/opt/ffmpeg-full/bin"


def _find_tool(name: str, env_var: str) -> str:
    """Resolve an ffmpeg-suite binary: env override, PATH, then Homebrew."""
    override = os.getenv(env_var)
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    candidate = f"{_HOMEBREW_BIN}/{name}"
    if Path(candidate).exists():
        return candidate
    raise RenderError(f"{name} not found; install ffmpeg or set {env_var}.")


def ffmpeg_bin() -> str:
    """Resolve an ffmpeg build with the text filters required by the renderer."""
    override = os.getenv("FFMPEG_BIN")
    if override:
        return override

    full = f"{_HOMEBREW_FFMPEG_FULL_BIN}/ffmpeg"
    if Path(full).exists():
        return full

    return _find_tool("ffmpeg", "FFMPEG_BIN")


def ffprobe_bin() -> str:
    return _find_tool("ffprobe", "FFPROBE_BIN")


_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_FALLBACK_FONT = "/System/Library/Fonts/Helvetica.ttc"
_FONT_FILES = {
    "regular": _FONT_DIR / "Inter-Regular.ttf",
    "semibold": _FONT_DIR / "Inter-SemiBold.ttf",
}


def font_path(weight: str = "regular") -> str:
    """Path to the bundled Inter weight, falling back to system Helvetica."""
    inter = _FONT_FILES.get(weight, _FONT_FILES["regular"])
    if inter.exists():
        return str(inter)
    if Path(_FALLBACK_FONT).exists():
        logger.warning(
            "Inter not found at %s; falling back to Helvetica. "
            "Run scripts/fetch_fonts.sh to bundle Inter.",
            inter,
        )
        return _FALLBACK_FONT
    raise RenderError(
        f"No usable font: {inter} is missing and {_FALLBACK_FONT} does not exist."
    )


# --- probing ---------------------------------------------------------------


@dataclass(frozen=True)
class MediaInfo:
    """What ffprobe knows about a media file."""

    duration: float
    width: int
    height: int
    has_video: bool
    has_audio: bool


@lru_cache(maxsize=256)
def probe_media(path: str) -> MediaInfo:
    """Probe a media file with ffprobe (cached per path)."""
    result = subprocess.run(
        [
            ffprobe_bin(),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RenderError(f"ffprobe failed for {path}: {result.stderr.strip()[-400:]}")
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return MediaInfo(
        duration=float(data.get("format", {}).get("duration", 0.0)),
        width=int(video.get("width", 0)) if video else 0,
        height=int(video.get("height", 0)) if video else 0,
        has_video=video is not None,
        has_audio=audio is not None,
    )


# --- text styling ----------------------------------------------------------
# Modeled on pro-editor presets. Every dimension is a fraction of the output
# frame so the same preset renders correctly at any resolution or aspect.


@dataclass(frozen=True)
class TextStyle:
    weight: str  # font weight key for font_path()
    size: float  # font size as a fraction of the frame's short edge
    default_position: str
    color: str = "white"
    box: bool = False  # pill/block background
    box_color: str = "black@0.55"
    box_pad: float = 0.0  # box padding as a fraction of the short edge
    shadow: bool = False  # soft drop shadow

    def option_string(self, width: int, height: int, position: str | None) -> str:
        """The style + placement part of a drawtext filter for this frame size.

        Sizes scale with the short edge of the frame, so a preset reads the
        same in 16:9, 9:16, and 1:1 variants.
        """
        base = min(width, height)
        opts = [
            f"fontfile={_quote(font_path(self.weight))}",
            f"fontsize={max(8, round(base * self.size))}",
            f"fontcolor={self.color}",
        ]
        x, y = _position_exprs(position or self.default_position, width, height)
        opts += [f"x={x}", f"y={y}"]
        if self.box:
            opts += [
                "box=1",
                f"boxcolor={self.box_color}",
                f"boxborderw={max(2, round(base * self.box_pad))}",
            ]
        if self.shadow:
            offset = max(1, round(base * 0.004))
            opts += ["shadowcolor=black@0.45", f"shadowx={offset}", f"shadowy={offset}"]
        return ":".join(opts)


_STYLES: dict[str, TextStyle] = {
    # Big centered card: SemiBold, large, soft shadow.
    "title": TextStyle(
        weight="semibold", size=0.082, default_position="center", shadow=True
    ),
    # Left-aligned block sitting on the lower-third baseline.
    "lower-third": TextStyle(
        weight="regular",
        size=0.046,
        default_position="bottom-left",
        box=True,
        box_color="black@0.55",
        box_pad=0.014,
    ),
    # Bottom-centered pill inside safe margins.
    "caption": TextStyle(
        weight="regular",
        size=0.042,
        default_position="bottom",
        box=True,
        box_color="black@0.62",
        box_pad=0.016,
    ),
}
assert set(_STYLES) == set(STYLE_PRESETS)

_MARGIN_X = 0.06  # horizontal safe margin, fraction of width
_MARGIN_Y = 0.08  # vertical safe margin, fraction of height


def _position_exprs(position: str, width: int, height: int) -> tuple[str, str]:
    """drawtext x/y expressions for a named position with safe margins."""
    mx = round(width * _MARGIN_X)
    my = round(height * _MARGIN_Y)
    x_center, y_center = "(w-text_w)/2", "(h-text_h)/2"
    x_left, x_right = str(mx), f"w-{mx}-text_w"
    y_top, y_bottom = str(my), f"h-{my}-text_h"
    return {
        "center": (x_center, y_center),
        "top": (x_center, y_top),
        "bottom": (x_center, y_bottom),
        "top-left": (x_left, y_top),
        "top-right": (x_right, y_top),
        "bottom-left": (x_left, y_bottom),
        "bottom-right": (x_right, y_bottom),
    }[position]


# --- filtergraph helpers ---------------------------------------------------


def _f(value: float) -> str:
    """Compact float formatting for filter arguments (no trailing zeros)."""
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _quote(value: str) -> str:
    """Filtergraph-quote a value with no embedded single quotes (paths, exprs)."""
    return f"'{value}'"


def _backslash_escape(value: str, specials: str) -> str:
    out: list[str] = []
    for ch in value:
        if ch in specials:
            out.append("\\")
        out.append(ch)
    return "".join(out)


def _escape_text(text: str) -> str:
    """Escape arbitrary user text for a drawtext ``text`` option value.

    ffmpeg parses filter option values twice (see its "Quoting and escaping"
    docs), so two levels of backslash escaping are applied: first for the
    option value itself (quote, colon, comma), then for the filtergraph
    parser (quote, brackets, comma, semicolon). ``expansion=none`` on the
    drawtext filter keeps ``%`` sequences literal.
    """
    option_level = _backslash_escape(text, "\\':,")
    return _backslash_escape(option_level, "\\'[],;")


def _atempo_chain(speed: float) -> list[str]:
    """atempo filters for ``speed`` (chained: each stage must be in [0.5, 2])."""
    factors: list[float] = []
    remaining = speed
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    if not math.isclose(remaining, 1.0, abs_tol=1e-9):
        factors.append(remaining)
    return [f"atempo={_f(factor)}" for factor in factors]


def _drawtext(
    text: str,
    start: float,
    end: float,
    style: TextStyle,
    position: str | None,
    width: int,
    height: int,
) -> str:
    return (
        f"drawtext=expansion=none:text={_escape_text(text)}"
        f":{style.option_string(width, height, position)}"
        f":enable='between(t,{_f(start)},{_f(end)})'"
    )


_AUDIO_FMT = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
_DUCK_DB = -12.0  # music attenuation under dialogue


def _music_volume_filter(timeline: Timeline) -> str:
    """volume filter for the music bed: gain plus caption-interval ducking."""
    assert timeline.music is not None
    base = 10.0 ** (timeline.music.gain_db / 20.0)
    intervals = timeline.captions if timeline.music.duck_under_dialogue else []
    if not intervals:
        return f"volume={_f(base)}"
    ducked = base * 10.0 ** (_DUCK_DB / 20.0)
    cond = "+".join(f"between(t,{_f(c.start)},{_f(c.end)})" for c in intervals)
    return f"volume='if(gt({cond},0),{_f(ducked)},{_f(base)})':eval=frame"


# --- validation ------------------------------------------------------------


def _validate_for_render(timeline: Timeline) -> None:
    if not timeline.clips:
        raise ValidationError("The timeline has no clips; nothing to render.")
    for i, clip in enumerate(timeline.clips):
        if not Path(clip.src).exists():
            raise ValidationError(f"Clip {clip.clip_id!r}: source {clip.src} missing.")
        info = probe_media(clip.src)
        if not info.has_video:
            raise ValidationError(f"Clip {clip.clip_id!r}: {clip.src} has no video.")
        if clip.out_point > info.duration + 0.05:
            raise ValidationError(
                f"Clip {clip.clip_id!r}: out point {clip.out_point:g}s is past the "
                f"end of {clip.src} ({info.duration:g}s)."
            )
        if clip.transition_in is not None:
            if i == 0:
                raise ValidationError(
                    f"First clip {clip.clip_id!r} cannot have a transition in."
                )
            limit = min(timeline.clips[i - 1].duration, clip.duration)
            if clip.transition_in.duration >= limit:
                raise ValidationError(
                    f"Crossfade into {clip.clip_id!r} ({clip.transition_in.duration:g}s) "
                    f"is longer than its shortest neighbour ({limit:g}s)."
                )
    if timeline.music is not None and not Path(timeline.music.src).exists():
        raise ValidationError(f"Music source {timeline.music.src} is missing.")


# --- the renderer ----------------------------------------------------------


def build_render_command(
    timeline: Timeline, out_path: str | Path, aspect: str | None = None
) -> list[str]:
    """Compile a Timeline into a complete, deterministic ffmpeg command.

    Exposed separately from :func:`render` so tests and callers can inspect
    the exact filtergraph without running it.
    """
    _validate_for_render(timeline)
    width, height = (
        resolution_for_aspect(timeline.resolution, aspect)
        if aspect is not None
        else timeline.resolution
    )
    fps = timeline.fps

    # Inputs: one per unique clip source, plus looped music at the end.
    sources = list(dict.fromkeys(clip.src for clip in timeline.clips))
    input_args: list[str] = []
    for src in sources:
        input_args += ["-i", src]
    music_index: int | None = None
    if timeline.music is not None:
        music_index = len(sources)
        input_args += ["-stream_loop", "-1", "-i", timeline.music.src]

    chains: list[str] = []

    # Per-clip normalization: trim -> speed -> fps -> center-crop -> format.
    for i, clip in enumerate(timeline.clips):
        src_index = sources.index(clip.src)
        chains.append(
            f"[{src_index}:v]"
            f"trim=start={_f(clip.in_point)}:end={_f(clip.out_point)},"
            f"setpts=(PTS-STARTPTS)/{_f(clip.speed)},fps={fps},"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,format=yuv420p,settb=AVTB"
            f"[v{i}]"
        )
        if probe_media(clip.src).has_audio:
            audio_steps = [
                f"atrim=start={_f(clip.in_point)}:end={_f(clip.out_point)}",
                "asetpts=PTS-STARTPTS",
                *_atempo_chain(clip.speed),
                _AUDIO_FMT,
            ]
            chains.append(f"[{src_index}:a]" + ",".join(audio_steps) + f"[a{i}]")
        else:  # silent bed so concat/crossfade/mix always has audio to work with
            chains.append(
                f"anullsrc=channel_layout=stereo:sample_rate=48000,"
                f"atrim=duration={_f(clip.duration)}[a{i}]"
            )

    # Fold clips left-to-right: crossfade where requested, hard cut otherwise.
    v_label, a_label = "v0", "a0"
    elapsed = timeline.clips[0].duration
    for i, clip in enumerate(timeline.clips[1:], start=1):
        if clip.transition_in is not None:
            dur = clip.transition_in.duration
            chains.append(
                f"[{v_label}][v{i}]xfade=transition=fade:duration={_f(dur)}"
                f":offset={_f(elapsed - dur)}[vx{i}]"
            )
            chains.append(f"[{a_label}][a{i}]acrossfade=d={_f(dur)}[ax{i}]")
            v_label, a_label = f"vx{i}", f"ax{i}"
            elapsed += clip.duration - dur
        else:
            chains.append(f"[{v_label}][v{i}]concat=n=2:v=1:a=0[vc{i}]")
            chains.append(f"[{a_label}][a{i}]concat=n=2:v=0:a=1[ac{i}]")
            v_label, a_label = f"vc{i}", f"ac{i}"
            elapsed += clip.duration

    # Burn in overlays, then captions, in start order.
    draw_items: list[tuple[TextOverlay | Caption, TextStyle, str | None]] = [
        (t, _STYLES[t.style_preset], t.position)
        for t in sorted(timeline.texts, key=lambda t: t.start)
    ]
    draw_items += [
        (c, _STYLES["caption"], None)
        for c in sorted(timeline.captions, key=lambda c: c.start)
    ]
    if draw_items:
        draws = ",".join(
            _drawtext(item.text, item.start, item.end, style, pos, width, height)
            for item, style, pos in draw_items
        )
        chains.append(f"[{v_label}]{draws}[vtext]")
        v_label = "vtext"

    # Music bed: loop, trim to program length, gain + ducking, mix under program.
    if music_index is not None:
        chains.append(
            f"[{music_index}:a]{_AUDIO_FMT},atrim=duration={_f(elapsed)},"
            f"asetpts=PTS-STARTPTS,{_music_volume_filter(timeline)}[mus]"
        )
        chains.append(f"[{a_label}][mus]amix=inputs=2:duration=first:normalize=0[amix]")
        a_label = "amix"

    chains.append(f"[{v_label}]format=yuv420p[vout]")

    return [
        ffmpeg_bin(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *input_args,
        "-filter_complex",
        ";".join(chains),
        "-map",
        "[vout]",
        "-map",
        f"[{a_label}]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "19",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(out_path),
    ]


def render(timeline: Timeline, out_path: str | Path, aspect: str | None = None) -> Path:
    """Render a Timeline to a real mp4 (h264 + aac, faststart).

    ``aspect`` optionally reframes the output ('16:9', '9:16', '1:1') with a
    smart center-crop; None renders at the timeline's own resolution.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_render_command(timeline, out_path, aspect)
    logger.info("rendering %s (%s)", out_path.name, aspect or timeline.aspect)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError(
            f"ffmpeg failed (exit {result.returncode}): {result.stderr.strip()[-800:]}"
        )
    return out_path


def render_thumbnail(clip: Clip, out_path: str | Path, width: int = 640) -> Path:
    """Extract a thumbnail (jpeg/png by extension) from the middle of a clip."""
    if not Path(clip.src).exists():
        raise ValidationError(f"Clip {clip.clip_id!r}: source {clip.src} missing.")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    midpoint = clip.in_point + (clip.out_point - clip.in_point) / 2.0
    result = subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            _f(midpoint),
            "-i",
            clip.src,
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            "-q:v",
            "2",
            str(out_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RenderError(
            f"thumbnail failed (exit {result.returncode}): "
            f"{result.stderr.strip()[-400:]}"
        )
    return out_path
