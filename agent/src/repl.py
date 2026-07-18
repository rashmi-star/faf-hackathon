"""Keyless dev REPL for the Director FAL edit engine.

Drives the REAL engine (:mod:`engine.ops` + :mod:`engine.render`) against the
bundled placeholder clip, with no LiveKit room and no API keys. This is a
developer/testing tool — NOT part of the shipped product (SPEC section 9.5).
It exists so the full timeline-edit surface can be exercised and a real mp4
produced before any keys exist.

    uv run python -m src.repl              # interactive
    uv run python -m src.repl --script demo  # canned sequence -> real render

Interactive commands mirror the agent's edit tools 1:1. Type ``help``.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from engine import ops as engine_ops
from engine.render import probe_media, render
from engine.timeline import Clip, Timeline, ValidationError
from state import STATE, apply_edit

# The one asset every dev machine has, no keys required.
PLACEHOLDER = (
    Path(__file__).resolve().parent.parent.parent
    / "frontend"
    / "public"
    / "placeholders"
    / "hero-video-bg.mp4"
)
OUT_DIR = Path(__file__).resolve().parent.parent / "test-output"


def _seed_timeline() -> None:
    """Start from two clips cut out of the placeholder video."""
    src = str(PLACEHOLDER)
    info = probe_media(src)
    span = min(4.0, info.duration / 2)
    STATE.timeline = Timeline(
        fps=30,
        resolution=(1280, 720),
        aspect="16:9",
        clips=[
            Clip(clip_id="c1", src=src, in_point=0.0, out_point=span),
            Clip(clip_id="c2", src=src, in_point=span, out_point=span * 2),
        ],
    )


# command name -> (engine op, arg converters). Each op returns (Timeline, entry).
_OPS: dict[str, tuple] = {
    "split": (engine_ops.split_clip, [float]),
    "trim": (engine_ops.trim, [str, float, float]),
    "reorder": (engine_ops.reorder, [str, int]),
    "delete": (engine_ops.delete_clip, [str]),
    "speed": (engine_ops.set_speed, [str, float]),
    "transition": (engine_ops.add_transition, [str, float]),
    "text": (engine_ops.add_text, [str, float, float, str]),
    "untext": (engine_ops.remove_text, [str]),
    "captions": (engine_ops.add_captions, None),  # freeform, handled inline
    "gain": (engine_ops.set_gain, [float]),
    "reframe": (engine_ops.reframe, [str]),
}


def _apply(op, *args) -> None:
    new_timeline, entry = op(STATE.timeline, *args)
    apply_edit(new_timeline, entry)
    print(f"  ✓ {entry.summary}")


def _print_state() -> None:
    tl = STATE.timeline
    print(f"  timeline {tl.aspect} {tl.resolution[0]}x{tl.resolution[1]} "
          f"{tl.duration:.2f}s, {len(tl.clips)} clips, {len(tl.texts)} texts, "
          f"music={'yes' if tl.music else 'no'}")
    for clip, start in zip(tl.clips, tl.clip_start_times()):
        print(f"    {clip.clip_id}: {start:.2f}-{start + clip.duration:.2f}s "
              f"(src {clip.in_point:.2f}-{clip.out_point:.2f}, {clip.speed}x)")


def _do_render(name: str = "repl-demo") -> Path:
    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"{name}.mp4"
    print(f"  rendering {out} ...")
    render(STATE.timeline, out)
    info = probe_media(str(out))
    print(f"  ✓ rendered {out.name}: {info.width}x{info.height} {info.duration:.2f}s")
    return out


HELP = """commands (mirror the agent edit tools):
  split <at>                 split the clip under <at> seconds
  trim <clip> <in> <out>     trim a clip's source range
  reorder <clip> <index>     move a clip to a new position
  delete <clip>              remove a clip
  speed <clip> <x>           set clip speed (0.25..4.0)
  transition <clip> <dur>    crossfade into a clip
  text "words" <s> <e> <preset>   add overlay (preset: title|lower-third|caption)
  untext <text_id>           remove a text overlay
  gain <db>                  set music gain
  reframe 16:9|9:16|1:1      change aspect (center-crop)
  state                      print the timeline
  render [name]              render a real mp4 to test-output/
  help / quit"""


def _dispatch(line: str) -> bool:
    """Run one command line. Returns False to exit."""
    try:
        parts = shlex.split(line)
    except ValueError as err:
        print(f"  ! {err}")
        return True
    if not parts:
        return True
    cmd, args = parts[0], parts[1:]

    if cmd in ("quit", "exit", "q"):
        return False
    if cmd == "help":
        print(HELP)
        return True
    if cmd == "state":
        _print_state()
        return True
    if cmd == "render":
        _do_render(args[0] if args else "repl-demo")
        return True
    if cmd not in _OPS:
        print(f"  ! unknown command '{cmd}' (try help)")
        return True

    op, converters = _OPS[cmd]
    try:
        if converters is None:  # captions: "text" start end, repeatable pairs
            phrases = [(args[i], float(args[i + 1]), float(args[i + 2]))
                       for i in range(0, len(args), 3)]
            _apply(op, phrases)
        else:
            typed = [conv(a) for conv, a in zip(converters, args)]
            _apply(op, *typed)
    except ValidationError as err:
        print(f"  ! rejected: {err}")
    except (ValueError, IndexError):
        print(f"  ! bad args for '{cmd}' (try help)")
    return True


DEMO_SCRIPT = [
    "state",
    "split 2.0",
    "trim c1 0.0 1.5",
    "speed c2 1.5",
    'text "DIRECTOR FAL" 0.0 2.0 title',
    'text "the editor you talk to" 0.5 3.0 lower-third',
    "reframe 16:9",
    "state",
    "render repl-demo",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Director FAL engine REPL (keyless)")
    parser.add_argument("--script", choices=["demo"], help="run a canned sequence")
    args = parser.parse_args(argv)

    if not PLACEHOLDER.exists():
        print(f"placeholder video not found: {PLACEHOLDER}", file=sys.stderr)
        return 1

    _seed_timeline()
    print(f"Director FAL engine REPL — seeded from {PLACEHOLDER.name}")

    if args.script == "demo":
        for line in DEMO_SCRIPT:
            print(f"> {line}")
            _dispatch(line)
        print("demo complete.")
        return 0

    print("type 'help' for commands, 'quit' to exit.")
    try:
        while True:
            try:
                line = input("director> ")
            except EOFError:
                break
            if not _dispatch(line):
                break
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
