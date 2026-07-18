"""Tests for the edit engine: ops validation plus real ffmpeg renders.

The render tests build a timeline from two short segments of the bundled
placeholder video, apply a full editorial pass (split, trim, reorder, speed,
title + caption, crossfade, music), render 16:9 and a 9:16 reframe into
``agent/test-output/``, and verify the output files with ffprobe. They are
marked ``render`` but run by default; deselect with ``-m 'not render'``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engine import ops
from engine.render import (
    build_render_command,
    ffmpeg_bin,
    probe_media,
    render,
    render_thumbnail,
)
from engine.timeline import Caption, Clip, Timeline, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_VIDEO = REPO_ROOT / "frontend" / "public" / "placeholders" / "hero-video-bg.mp4"
OUT_DIR = Path(__file__).resolve().parents[1] / "test-output"

DURATION_TOLERANCE_S = 0.35

needs_source = pytest.mark.skipif(
    not SOURCE_VIDEO.exists(), reason=f"placeholder video missing: {SOURCE_VIDEO}"
)


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def timeline() -> Timeline:
    """Two 3s segments of the placeholder video, 720p 30fps."""
    return Timeline(
        fps=30,
        resolution=(1280, 720),
        clips=[
            Clip(clip_id="a", src=str(SOURCE_VIDEO), in_point=0.0, out_point=3.0),
            Clip(clip_id="b", src=str(SOURCE_VIDEO), in_point=3.0, out_point=6.0),
        ],
    )


@pytest.fixture(scope="session")
def music_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 5s 440Hz sine generated via ffmpeg lavfi (the music-bed fixture)."""
    path = tmp_path_factory.mktemp("audio") / "sine.wav"
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=5",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def edited_timeline(timeline: Timeline, music: Path) -> Timeline:
    """Apply the full editorial pass the render tests exercise."""
    tl, _ = ops.split_clip(timeline, at=1.5)  # -> a(0-1.5), a-b(1.5-3), b
    tl, _ = ops.trim(tl, "b", new_in=3.0, new_out=5.0)  # b -> 2s
    tl, _ = ops.reorder(tl, "b", index=1)  # -> a, b, a-b
    tl, _ = ops.set_speed(tl, "a-b", speed=1.5)  # a-b -> 1s
    tl, _ = ops.add_transition(tl, "b", duration=0.5)  # a >< b crossfade
    tl, _ = ops.add_text(tl, "GOLDEN GATE", start=0.0, end=2.0, style_preset="title")
    tl, _ = ops.add_text(
        tl, "Director FAL", start=2.5, end=3.5, style_preset="lower-third"
    )
    tl, _ = ops.add_captions(
        tl, [{"text": "It's a wrap — 100% real", "start": 0.5, "end": 2.5}]
    )
    tl, _ = ops.set_music(tl, str(music), gain_db=-6.0, duck_under_dialogue=True)
    return tl


# --- ops: clip editing ------------------------------------------------------


def test_split_clip_midpoint(timeline: Timeline) -> None:
    tl, entry = ops.split_clip(timeline, at=1.5)
    assert [c.clip_id for c in tl.clips] == ["a", "a-b", "b"]
    assert (tl.clips[0].in_point, tl.clips[0].out_point) == (0.0, 1.5)
    assert (tl.clips[1].in_point, tl.clips[1].out_point) == (1.5, 3.0)
    assert tl.duration == pytest.approx(6.0)
    assert "Split 'a' at 1.5s" in entry.summary


def test_split_accounts_for_speed(timeline: Timeline) -> None:
    tl, _ = ops.set_speed(timeline, "a", speed=2.0)  # a plays 0-1.5 on timeline
    tl, _ = ops.split_clip(tl, at=1.0)  # 1.0s in -> 2.0s into the source
    assert tl.clips[0].out_point == pytest.approx(2.0)
    assert tl.clips[1].in_point == pytest.approx(2.0)
    assert tl.clips[1].speed == 2.0


def test_split_outside_program_raises(timeline: Timeline) -> None:
    with pytest.raises(ValidationError, match="No clip at 99"):
        ops.split_clip(timeline, at=99.0)


def test_split_at_existing_cut_raises(timeline: Timeline) -> None:
    with pytest.raises(ValidationError, match="cut point"):
        ops.split_clip(timeline, at=3.0)  # boundary between a and b


def test_trim_updates_window(timeline: Timeline) -> None:
    tl, entry = ops.trim(timeline, "b", new_in=3.0, new_out=5.0)
    clip = tl.get_clip("b")
    assert clip is not None and (clip.in_point, clip.out_point) == (3.0, 5.0)
    assert "Trimmed 'b'" in entry.summary


def test_trim_rejects_inverted_range(timeline: Timeline) -> None:
    with pytest.raises(ValidationError, match="end must be after start"):
        ops.trim(timeline, "a", new_in=2.0, new_out=1.0)
    with pytest.raises(ValidationError, match="start must be >= 0"):
        ops.trim(timeline, "a", new_in=-1.0, new_out=1.0)


def test_reorder_moves_clip(timeline: Timeline) -> None:
    tl, _ = ops.reorder(timeline, "b", index=0)
    assert [c.clip_id for c in tl.clips] == ["b", "a"]


def test_reorder_out_of_range_raises(timeline: Timeline) -> None:
    with pytest.raises(ValidationError, match="out of range"):
        ops.reorder(timeline, "a", index=5)


def test_reorder_to_front_drops_transition(timeline: Timeline) -> None:
    tl, _ = ops.add_transition(timeline, "b", duration=0.5)
    tl, _ = ops.reorder(tl, "b", index=0)
    assert tl.clips[0].transition_in is None


def test_delete_clip(timeline: Timeline) -> None:
    tl, entry = ops.delete_clip(timeline, "a")
    assert [c.clip_id for c in tl.clips] == ["b"]
    assert "1 clips remain" in entry.summary
    with pytest.raises(ValidationError, match="No clip 'zzz'"):
        ops.delete_clip(tl, "zzz")


def test_set_speed_bounds(timeline: Timeline) -> None:
    tl, _ = ops.set_speed(timeline, "a", speed=1.5)
    clip = tl.get_clip("a")
    assert clip is not None and clip.duration == pytest.approx(2.0)
    for bad in (0.0, -1.0, 8.0):
        with pytest.raises(ValidationError, match="Speed must be between"):
            ops.set_speed(timeline, "a", speed=bad)


def test_replace_clip_media(timeline: Timeline) -> None:
    tl, entry = ops.replace_clip_media(timeline, "a", "other.mp4", new_out=2.0)
    clip = tl.get_clip("a")
    assert clip is not None and clip.src == "other.mp4" and clip.out_point == 2.0
    assert "Replaced the media" in entry.summary


def test_insert_clip_appends_and_validates(timeline: Timeline) -> None:
    tl, _ = ops.insert_clip(timeline, str(SOURCE_VIDEO), 6.0, 8.0, clip_id="tail")
    assert [c.clip_id for c in tl.clips] == ["a", "b", "tail"]
    with pytest.raises(ValidationError, match="already exists"):
        ops.insert_clip(tl, str(SOURCE_VIDEO), 0.0, 1.0, clip_id="a")
    with pytest.raises(ValidationError, match="out of range"):
        ops.insert_clip(tl, str(SOURCE_VIDEO), 0.0, 1.0, index=9)


def test_add_transition_validation(timeline: Timeline) -> None:
    with pytest.raises(ValidationError, match="first clip"):
        ops.add_transition(timeline, "a", duration=0.5)
    with pytest.raises(ValidationError, match="longer than that"):
        ops.add_transition(timeline, "b", duration=3.5)
    tl, entry = ops.add_transition(timeline, "b", duration=0.5)
    clip = tl.get_clip("b")
    assert clip is not None and clip.transition_in is not None
    assert tl.duration == pytest.approx(5.5)  # 3 + 3 - 0.5 overlap
    assert "crossfade" in entry.summary


# --- ops: text, captions, music, reframe ------------------------------------


def test_text_lifecycle(timeline: Timeline) -> None:
    tl, _ = ops.add_text(timeline, "Hello", 0.0, 2.0, text_id="t1")
    tl, _ = ops.update_text(tl, "t1", text="Goodbye", end=3.0)
    overlay = tl.get_text("t1")
    assert overlay is not None and overlay.text == "Goodbye" and overlay.end == 3.0
    tl, entry = ops.remove_text(tl, "t1")
    assert tl.texts == [] and "Goodbye" in entry.summary


def test_text_validation(timeline: Timeline) -> None:
    with pytest.raises(ValidationError, match="style preset"):
        ops.add_text(timeline, "x", 0.0, 1.0, style_preset="banner")
    with pytest.raises(ValidationError, match="position"):
        ops.add_text(timeline, "x", 0.0, 1.0, position="middle-ish")
    with pytest.raises(ValidationError, match="end must be after start"):
        ops.add_text(timeline, "x", 2.0, 1.0)
    with pytest.raises(ValidationError, match="No text overlay 'nope'"):
        ops.update_text(timeline, "nope", text="x")


def test_add_captions_sorts_and_validates(timeline: Timeline) -> None:
    tl, entry = ops.add_captions(
        timeline,
        [
            {"text": "second", "start": 2.0, "end": 3.0},
            Caption(text="first", start=0.0, end=1.0),
        ],
    )
    assert [c.text for c in tl.captions] == ["first", "second"]
    assert "Added 2 captions" in entry.summary
    with pytest.raises(ValidationError, match="end must be after start"):
        ops.add_captions(timeline, [{"text": "bad", "start": 2.0, "end": 2.0}])


def test_music_and_gain(timeline: Timeline) -> None:
    with pytest.raises(ValidationError, match="No music"):
        ops.set_gain(timeline, -3.0)
    tl, _ = ops.set_music(timeline, "sine.wav", gain_db=-6.0)
    tl, entry = ops.set_gain(tl, -9.0)
    assert tl.music is not None and tl.music.gain_db == -9.0
    assert "-9 dB" in entry.summary


def test_reframe_variants(timeline: Timeline) -> None:
    for aspect, expected in (
        ("9:16", (720, 1280)),
        ("1:1", (720, 720)),
        ("16:9", (1280, 720)),
    ):
        tl, _ = ops.reframe(timeline, aspect)
        assert (tl.aspect, tl.resolution) == (aspect, expected)
    with pytest.raises(ValidationError, match="Unknown aspect"):
        ops.reframe(timeline, "4:3")


# --- model ------------------------------------------------------------------


def test_ops_never_mutate_input(timeline: Timeline) -> None:
    snapshot = timeline.to_json()
    ops.split_clip(timeline, at=1.5)
    ops.set_speed(timeline, "a", speed=2.0)
    ops.add_text(timeline, "x", 0.0, 1.0)
    ops.set_music(timeline, "sine.wav")
    assert timeline.to_json() == snapshot


def test_json_roundtrip(timeline: Timeline, tmp_path: Path) -> None:
    tl, _ = ops.add_transition(timeline, "b", duration=0.5)
    tl, _ = ops.add_text(tl, "Title", 0.0, 2.0, position="top")
    tl, _ = ops.add_captions(tl, [{"text": "hi", "start": 0.0, "end": 1.0}])
    tl, _ = ops.set_music(tl, "sine.wav", gain_db=-6.0, duck_under_dialogue=False)
    path = tmp_path / "timeline.json"
    tl.save(path)
    assert Timeline.load(path) == tl


# --- real renders -----------------------------------------------------------


@pytest.mark.render
@needs_source
def test_render_16x9_and_9x16_reframe(timeline: Timeline, music_wav: Path) -> None:
    tl = edited_timeline(timeline, music_wav)
    assert tl.duration == pytest.approx(4.0)  # 1.5 + 2 + 1 - 0.5 crossfade

    # the compiled command is deterministic
    assert build_render_command(tl, OUT_DIR / "x.mp4") == build_render_command(
        tl, OUT_DIR / "x.mp4"
    )

    for aspect, filename, expected_res in (
        ("16:9", "edit-16x9.mp4", (1280, 720)),
        ("9:16", "edit-9x16.mp4", (720, 1280)),
    ):
        out = render(tl, OUT_DIR / filename, aspect=aspect)
        assert out.exists() and out.stat().st_size > 0
        probe_media.cache_clear()  # file at this path changed on disk
        info = probe_media(str(out))
        assert info.has_video and info.has_audio, f"{aspect}: missing a stream"
        assert (info.width, info.height) == expected_res
        assert info.duration == pytest.approx(tl.duration, abs=DURATION_TOLERANCE_S)


@pytest.mark.render
@needs_source
def test_render_thumbnail(timeline: Timeline) -> None:
    clip = timeline.clips[0]
    out = render_thumbnail(clip, OUT_DIR / "thumb-a.jpg", width=640)
    probe_media.cache_clear()
    info = probe_media(str(out))
    assert info.has_video and info.width == 640 and info.height > 0
