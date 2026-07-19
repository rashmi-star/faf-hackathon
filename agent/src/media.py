"""Media layer for Director FAL (SPEC section 6).

Two implementations behind one interface:

- MockMedia: default when MOCK_MEDIA=1 or FAL_KEY is missing. Returns bundled
  placeholder URLs (served by the Next.js frontend) with small fake delays so
  UI/voice development never blocks on credits.
- FalMedia: real calls via fal_client (flux schnell stills/portraits,
  image-to-video shots, sync-lipsync dialogue replacement, ffmpeg-api/compose
  assemble + exports) and the ElevenLabs REST API for dialogue lines.

FalMedia is code-complete but UNTESTED WITHOUT KEYS: exact request/response
shapes for the fal endpoints must be confirmed against fal.ai/models once
FAL_KEY works (first pipeline session, per SPEC).
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
import itertools
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("director.media")

# --- fal model ids (SPEC section 6) ----------------------------------------
FAL_STILL_MODEL = "fal-ai/flux/schnell"  # or "fal-ai/flux-2" for quality
# Pick ONE video model after the 3-prompt bake-off (SPEC section 6). Candidates:
#   "fal-ai/kling-video/v2.1/standard/image-to-video"   (quality)
#   "fal-ai/bytedance/seedance/v1/lite/image-to-video"  (speed)
#   "fal-ai/ltx-video-13b-distilled/image-to-video"     (speed)
FAL_VIDEO_MODEL = "fal-ai/kling-video/v2.1/standard/image-to-video"
FAL_LIPSYNC_MODEL = "fal-ai/sync-lipsync/v2"  # Sync Labs 2.0
FAL_COMPOSE_MODEL = "fal-ai/ffmpeg-api/compose"
FAL_MUSIC_MODEL = "fal-ai/stable-audio"  # text-to-audio music bed

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
ELEVENLABS_TTS_MODEL = "eleven_flash_v2_5"
# single dialogue voice for the demo happy path (Rachel); override per deploy
DIALOGUE_VOICE_ID = os.getenv("DIALOGUE_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

EXPORT_SPECS: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "loop": (1920, 1080),  # 8s loop, 16:9
}
LOOP_DURATION_S = 8.0

# --- character reference sheets (SPEC section 10) --------------------------
# The four expressions the real backend renders per character, in order. The
# studio Cast tab labels its expression grid positionally against this list.
SHEET_EXPRESSIONS = ("neutral", "happy", "sad", "angry")

# Cinematic base palette used to backfill swatches when few colors are named in
# the sheet text, so every real sheet carries 5 chips.
_BASE_PALETTE = ["#14141A", "#C9A227", "#8C3B2B", "#3E5C6B", "#E8DCC4"]

# Color words a sheet prompt might mention -> a filmic hex, so the palette is
# actually derived from the character description rather than fabricated.
_COLOR_WORDS: dict[str, str] = {
    "black": "#111114",
    "white": "#F5F1E6",
    "ivory": "#F0E9D6",
    "red": "#B23A2E",
    "crimson": "#8C2C22",
    "blue": "#2E4A63",
    "navy": "#1C2B3A",
    "green": "#3B5E4A",
    "emerald": "#2F6E52",
    "gold": "#C9A227",
    "amber": "#D8973C",
    "brown": "#5A3E2B",
    "grey": "#6B6B6E",
    "gray": "#6B6B6E",
    "charcoal": "#2A2A2E",
    "silver": "#B8BCC0",
    "purple": "#4E3A5E",
    "violet": "#5B4A78",
    "pink": "#C97F86",
    "orange": "#C86A2E",
    "teal": "#2C5B5B",
    "yellow": "#D8C33C",
    "beige": "#D8C7A8",
    "tan": "#C2A878",
}


@dataclass
class CharacterSheetResult:
    """What :meth:`Media.create_character` returns — the media half of a sheet.

    ``role``/``age``/``personality`` are caller metadata passed straight through
    (never invented by the media layer). ``expression_urls``/``palette``/
    ``notes`` are the generated reference material and are only populated by the
    real backend; the mock leaves them empty so the UI degrades to a portrait
    card (SPEC section 9.5). ``turnaround_urls`` is reserved and stays empty for
    now (kept cost-aware — the expression grid is the consistency backbone).
    """

    image_url: str
    expression_urls: list[str] = field(default_factory=list)
    turnaround_urls: list[str] = field(default_factory=list)
    palette: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    role: str = ""
    age: str = ""
    personality: list[str] = field(default_factory=list)


def derive_palette(*texts: str) -> list[str]:
    """Five hex swatches: colors named in the sheet first, cinematic base after."""
    blob = " ".join(texts).lower()
    found: list[str] = []
    for word, hex_code in _COLOR_WORDS.items():
        if word in blob and hex_code not in found:
            found.append(hex_code)
    for hex_code in _BASE_PALETTE:
        if len(found) >= 5:
            break
        if hex_code not in found:
            found.append(hex_code)
    return found[:5]


def sheet_notes(name: str) -> list[str]:
    """Two short production notes tying downstream renders to the sheet."""
    return [
        f"Reuse this sheet as {name}'s reference on every shot so the face and "
        "wardrobe hold.",
        "Match key light and eyeline to the hero portrait when re-rendering.",
    ]


class Media(abc.ABC):
    """One interface for all generation. clips are (video_url, duration_s) pairs."""

    @abc.abstractmethod
    async def portrait(self, name: str, sheet: str, style: str) -> str: ...

    @abc.abstractmethod
    async def create_character(
        self,
        name: str,
        sheet: str,
        style: str,
        *,
        role: str = "",
        age: str = "",
        personality: list[str] | None = None,
    ) -> CharacterSheetResult: ...

    @abc.abstractmethod
    async def still(self, prompt: str, style: str) -> str: ...

    @abc.abstractmethod
    async def shot_video(self, still_url: str, prompt: str, duration: float) -> str: ...

    @abc.abstractmethod
    async def dialogue_audio(self, text: str, voice_id: str) -> str: ...

    @abc.abstractmethod
    async def lipsync(self, video_url: str, audio_url: str) -> str: ...

    @abc.abstractmethod
    async def music(self, prompt: str, duration: float) -> str: ...

    @abc.abstractmethod
    async def assemble(self, clips: list[tuple[str, float]]) -> str: ...

    @abc.abstractmethod
    async def export(self, timeline_url: str, fmt: str) -> str: ...

    @abc.abstractmethod
    async def publish_file(self, path: str | Path) -> str:
        """Publish a local render and return a browser-accessible URL."""
        ...


# ---------------------------------------------------------------------------
# URL -> local path resolution (for the local ffmpeg edit engine)

MEDIA_CACHE_DIR = Path(__file__).resolve().parent.parent / "media-cache"
_PUBLIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "public"


async def resolve_local(url: str) -> str:
    """Local filesystem path for a media URL, so the ffmpeg engine can read it.

    Three cases: an existing local path passes through untouched; a mock
    placeholder URL maps onto ``frontend/public``; anything else (fal CDN)
    is downloaded once into ``agent/media-cache`` keyed by URL hash.
    """
    if not url:
        raise ValueError("Cannot resolve an empty media url.")
    parsed = urlparse(url)
    if parsed.scheme in ("", "file"):
        return parsed.path or url
    base = os.getenv("MOCK_ASSET_BASE_URL", "http://localhost:3000")
    if url.startswith(f"{base}/"):
        candidate = _PUBLIC_DIR / url[len(base) + 1 :]
        if candidate.exists():
            return str(candidate)
    suffix = Path(parsed.path).suffix or ".bin"
    target = MEDIA_CACHE_DIR / (hashlib.sha256(url.encode()).hexdigest()[:16] + suffix)
    if not target.exists():
        MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        target.write_bytes(resp.content)
        logger.info("cached %s -> %s", url, target.name)
    return str(target)


# ---------------------------------------------------------------------------
# Mock implementation


class MockMedia(Media):
    """Instant placeholder assets from frontend/public/placeholders."""

    def __init__(self) -> None:
        base = os.getenv("MOCK_ASSET_BASE_URL", "http://localhost:3000")
        p = f"{base}/placeholders"
        self._portraits = itertools.cycle(
            [f"{p}/hero-modern-left.jpg", f"{p}/hero-modern-right.jpg"]
        )
        self._stills = itertools.cycle(
            [
                f"{p}/hero-kingdom-left.jpg",
                f"{p}/hero-kingdom-right.jpg",
                f"{p}/hero-rock-left.jpg",
                f"{p}/hero-rock-right.jpg",
                f"{p}/branch-left.jpg",
                f"{p}/branch-right.jpg",
            ]
        )
        self._video = f"{p}/hero-video-bg.mp4"
        self._poster = f"{p}/hero-video-poster.jpg"

    async def portrait(self, name: str, sheet: str, style: str) -> str:
        await asyncio.sleep(0.8)
        return next(self._portraits)

    async def create_character(
        self,
        name: str,
        sheet: str,
        style: str,
        *,
        role: str = "",
        age: str = "",
        personality: list[str] | None = None,
    ) -> CharacterSheetResult:
        # No fabricated reference sheet (SPEC section 9.5): only a placeholder
        # portrait plus the real caller metadata. expression_urls/palette/notes
        # stay EMPTY so the studio Cast tab degrades to a clean portrait card.
        url = await self.portrait(name, sheet, style)
        return CharacterSheetResult(
            image_url=url,
            role=role,
            age=age,
            personality=list(personality or []),
        )

    async def still(self, prompt: str, style: str) -> str:
        await asyncio.sleep(0.4)
        return next(self._stills)

    async def shot_video(self, still_url: str, prompt: str, duration: float) -> str:
        await asyncio.sleep(2.0)  # fake render time so progress speech is visible
        return self._video

    async def dialogue_audio(self, text: str, voice_id: str) -> str:
        await asyncio.sleep(0.5)
        return self._video  # no bundled audio asset; url is never played in mock

    async def lipsync(self, video_url: str, audio_url: str) -> str:
        await asyncio.sleep(1.5)
        return self._video

    async def music(self, prompt: str, duration: float) -> str:
        """Synthesize a quiet placeholder tone bed with ffmpeg (cached, keyless)."""
        from engine.render import ffmpeg_bin  # local import: engine is optional here

        path = MEDIA_CACHE_DIR / "mock-music.wav"
        if not path.exists():
            MEDIA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            seconds = max(8.0, min(duration, 30.0))
            await asyncio.to_thread(
                _run_checked,
                [
                    ffmpeg_bin(),
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    f"sine=frequency=220:sample_rate=48000:duration={seconds:g}",
                    "-af",
                    "volume=0.4,tremolo=f=0.5:d=0.6",
                    "-c:a",
                    "pcm_s16le",
                    str(path),
                ],
            )
        return str(path)

    async def assemble(self, clips: list[tuple[str, float]]) -> str:
        await asyncio.sleep(1.0)
        return self._video

    async def export(self, timeline_url: str, fmt: str) -> str:
        await asyncio.sleep(0.8)
        return self._video

    async def publish_file(self, path: str | Path) -> str:
        return str(path)


def _run_checked(command: list[str]) -> None:
    """Run a subprocess and raise with the stderr tail on failure."""
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"{command[0]} failed (exit {result.returncode}): "
            f"{result.stderr.strip()[-400:]}"
        )


# ---------------------------------------------------------------------------
# Real implementation (fal + ElevenLabs REST) — UNTESTED WITHOUT KEYS


class FalMedia(Media):
    def __init__(self) -> None:
        if not os.getenv("FAL_KEY"):
            raise RuntimeError(
                "FAL_KEY is not set. Set FAL_KEY in agent/.env.local for real "
                "media generation, or set MOCK_MEDIA=1 to use placeholders."
            )
        # imported lazily so MockMedia works without the key configured at all
        import fal_client

        self._fal = fal_client

    @staticmethod
    def _video_url(result: dict) -> str:
        """Extract a video URL from the slightly varying fal result shapes."""
        video = result.get("video")
        if isinstance(video, dict) and video.get("url"):
            return video["url"]
        if result.get("video_url"):
            return result["video_url"]
        raise RuntimeError(f"fal result had no video url: {list(result.keys())}")

    async def portrait(self, name: str, sheet: str, style: str) -> str:
        result = await self._fal.subscribe_async(
            FAL_STILL_MODEL,
            arguments={
                "prompt": (
                    f"cinematic character portrait of {name}. {sheet}. {style}. "
                    "centered, shallow depth of field, film still"
                ),
                "image_size": "portrait_4_3",
                "num_images": 1,
            },
        )
        return result["images"][0]["url"]

    async def _expression(
        self, name: str, sheet: str, style: str, emotion: str, seed: int
    ) -> str:
        """One expression frame, seeded to hold the face across the grid.

        flux/schnell is text-to-image, so consistency comes from reusing the
        exact appearance sheet plus a fixed per-character seed while only the
        emotion phrase changes. (A true image-reference chain — flux redux /
        IP-adapter — is the upgrade path once the video model is locked.)
        """
        result = await self._fal.subscribe_async(
            FAL_STILL_MODEL,
            arguments={
                "prompt": (
                    f"character reference of {name}, {emotion} facial expression. "
                    f"{sheet}. {style}. head and shoulders, neutral grey studio "
                    "backdrop, consistent face and wardrobe, film still"
                ),
                "image_size": "square_hd",
                "num_images": 1,
                "seed": seed,
            },
        )
        return result["images"][0]["url"]

    async def create_character(
        self,
        name: str,
        sheet: str,
        style: str,
        *,
        role: str = "",
        age: str = "",
        personality: list[str] | None = None,
    ) -> CharacterSheetResult:
        """Full reference sheet: hero portrait + 4-emotion expression grid.

        Cost-aware — one portrait plus four flux/schnell frames per character,
        rendered concurrently and sharing a seed for face consistency. The
        palette is derived from the sheet text; notes are pipeline guidance.
        """
        portrait_url = await self.portrait(name, sheet, style)
        seed = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)
        expression_urls = list(
            await asyncio.gather(
                *(
                    self._expression(name, sheet, style, emotion, seed)
                    for emotion in SHEET_EXPRESSIONS
                )
            )
        )
        return CharacterSheetResult(
            image_url=portrait_url,
            expression_urls=expression_urls,
            palette=derive_palette(sheet, style),
            notes=sheet_notes(name),
            role=role,
            age=age,
            personality=list(personality or []),
        )

    async def still(self, prompt: str, style: str) -> str:
        result = await self._fal.subscribe_async(
            FAL_STILL_MODEL,
            arguments={
                "prompt": f"{prompt}. {style}. cinematic film still",
                "image_size": "landscape_16_9",
                "num_images": 1,
            },
        )
        return result["images"][0]["url"]

    async def shot_video(self, still_url: str, prompt: str, duration: float) -> str:
        # UNTESTED: argument names vary per video model — confirm on fal.ai/models
        # (Kling takes duration as a string enum "5" | "10").
        result = await self._fal.subscribe_async(
            FAL_VIDEO_MODEL,
            arguments={
                "prompt": prompt,
                "image_url": still_url,
                "duration": "5" if duration <= 5 else "10",
            },
        )
        return self._video_url(result)

    async def dialogue_audio(self, text: str, voice_id: str) -> str:
        api_key = os.getenv("ELEVENLABS_API_KEY") or os.getenv("ELEVEN_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is not set — cannot generate dialogue lines."
            )
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                ELEVENLABS_TTS_URL.format(voice_id=voice_id),
                params={"output_format": "mp3_44100_128"},
                headers={"xi-api-key": api_key},
                json={"text": text, "model_id": ELEVENLABS_TTS_MODEL},
            )
            resp.raise_for_status()
        # fal CDN is our file storage (SPEC section 3)
        return await self._fal.upload_async(resp.content, "audio/mpeg", "dialogue.mp3")

    async def lipsync(self, video_url: str, audio_url: str) -> str:
        # UNTESTED: confirm arguments on fal.ai/models/fal-ai/sync-lipsync
        result = await self._fal.subscribe_async(
            FAL_LIPSYNC_MODEL,
            arguments={
                "video_url": video_url,
                "audio_url": audio_url,
                "sync_mode": "cut_off",
            },
        )
        return self._video_url(result)

    async def music(self, prompt: str, duration: float) -> str:
        # UNTESTED: confirm arguments on fal.ai/models/fal-ai/stable-audio
        result = await self._fal.subscribe_async(
            FAL_MUSIC_MODEL,
            arguments={
                "prompt": prompt,
                "seconds_total": int(max(8.0, min(duration, 47.0))),
            },
        )
        audio = result.get("audio_file") or result.get("audio") or {}
        if isinstance(audio, dict) and audio.get("url"):
            return audio["url"]
        raise RuntimeError(f"fal result had no audio url: {list(result.keys())}")

    async def assemble(self, clips: list[tuple[str, float]]) -> str:
        # UNTESTED: compose track/keyframe schema — confirm on
        # fal.ai/models/fal-ai/ffmpeg-api/compose (timestamps in milliseconds).
        keyframes = []
        t_ms = 0
        for url, duration_s in clips:
            d_ms = int(duration_s * 1000)
            keyframes.append({"url": url, "timestamp": t_ms, "duration": d_ms})
            t_ms += d_ms
        result = await self._fal.subscribe_async(
            FAL_COMPOSE_MODEL,
            arguments={
                "tracks": [{"id": "main", "type": "video", "keyframes": keyframes}]
            },
        )
        return self._video_url(result)

    async def export(self, timeline_url: str, fmt: str) -> str:
        # UNTESTED: aspect handling via compose resolution args — confirm schema.
        width, height = EXPORT_SPECS.get(fmt, EXPORT_SPECS["16:9"])
        keyframe: dict = {"url": timeline_url, "timestamp": 0}
        if fmt == "loop":
            keyframe["duration"] = int(LOOP_DURATION_S * 1000)
        result = await self._fal.subscribe_async(
            FAL_COMPOSE_MODEL,
            arguments={
                "tracks": [{"id": "main", "type": "video", "keyframes": [keyframe]}],
                "width": width,
                "height": height,
            },
        )
        return self._video_url(result)

    async def publish_file(self, path: str | Path) -> str:
        return await self._fal.upload_file_async(Path(path))


# ---------------------------------------------------------------------------

_media: Media | None = None


def get_media() -> Media:
    """Mock when MOCK_MEDIA=1 or FAL_KEY is missing; real fal otherwise."""
    global _media
    if _media is None:
        if os.getenv("MOCK_MEDIA") == "1" or not os.getenv("FAL_KEY"):
            logger.info("media backend: MockMedia (placeholders)")
            _media = MockMedia()
        else:
            logger.info("media backend: FalMedia (real generation)")
            _media = FalMedia()
    return _media
