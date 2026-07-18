'use client';

import { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import {
  CircleNotchIcon,
  FilmStripIcon,
  PauseIcon,
  PlayIcon,
} from '@phosphor-icons/react/dist/ssr';
import { type Phase, type Shot } from '@/lib/project-state';
import { cn } from '@/lib/shadcn/utils';

function formatTime(seconds: number): string {
  const s = Math.max(0, seconds);
  const m = Math.floor(s / 60);
  const rest = Math.floor(s % 60);
  return `${m}:${String(rest).padStart(2, '0')}`;
}

const STATUS_BADGES: Record<Shot['status'], { label: string; className: string }> = {
  planned: { label: 'Planned', className: 'border-zinc-500/40 bg-zinc-500/15 text-zinc-300' },
  still: { label: 'Storyboard', className: 'border-sky-500/40 bg-sky-500/15 text-sky-300' },
  rendering: {
    label: 'Rendering',
    className: 'border-amber-500/40 bg-amber-500/15 text-amber-300',
  },
  ready: { label: 'Ready', className: 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300' },
  replacing: {
    label: 'Replacing',
    className: 'border-fuchsia-500/40 bg-fuchsia-500/15 text-fuchsia-300',
  },
};

interface PreviewPlayerProps {
  shot: Shot | null;
  phase: Phase;
  highlightActive: boolean;
  /** Called with the absolute timeline position (shot.start + video time). */
  onTimeUpdate: (seconds: number) => void;
  onEnded: () => void;
}

export function PreviewPlayer({
  shot,
  phase,
  highlightActive,
  onTimeUpdate,
  onEnded,
}: PreviewPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [localTime, setLocalTime] = useState(0);

  const shotDuration = shot ? shot.end - shot.start : 0;
  const hasVideo = Boolean(shot?.video_url);

  // Reload the element when the clip changes; keep rolling if we were playing.
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !shot?.video_url) return;
    video.load();
    setLocalTime(0);
    if (isPlaying) {
      video.play().catch(() => setIsPlaying(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shot?.id, shot?.video_url]);

  const togglePlay = () => {
    const video = videoRef.current;
    if (!video || !hasVideo) return;
    if (isPlaying) {
      video.pause();
      setIsPlaying(false);
    } else {
      video.play().catch(() => undefined);
      setIsPlaying(true);
    }
  };

  const handleTimeUpdate = () => {
    const video = videoRef.current;
    if (!video || !shot) return;
    const t = video.currentTime;
    // A source clip may run longer than its shot — clamp to the shot's slot on the timeline.
    if (t >= shotDuration) {
      video.pause();
      setLocalTime(shotDuration);
      onTimeUpdate(shot.end);
      onEnded();
      return;
    }
    setLocalTime(t);
    onTimeUpdate(shot.start + t);
  };

  const badge = shot ? STATUS_BADGES[shot.status] : null;

  return (
    <motion.div
      animate={
        highlightActive
          ? { boxShadow: '0 0 0 2px rgba(251, 191, 36, 0.7)' }
          : { boxShadow: '0 0 0 1px rgba(255, 255, 255, 0.08)' }
      }
      className="relative aspect-video max-h-full w-full max-w-4xl overflow-hidden rounded-lg bg-zinc-900"
    >
      {/* media */}
      {hasVideo ? (
        <video
          ref={videoRef}
          src={shot?.video_url ?? undefined}
          poster={shot?.still_url ?? undefined}
          playsInline
          muted
          preload="auto"
          onTimeUpdate={handleTimeUpdate}
          onEnded={onEnded}
          onPause={() => setIsPlaying(false)}
          className="h-full w-full object-cover"
        />
      ) : shot?.still_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={shot.still_url}
          alt={shot.prompt}
          className="h-full w-full object-cover opacity-90"
        />
      ) : (
        <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-zinc-600">
          <FilmStripIcon className="size-10" />
          <p className="font-mono text-[11px] tracking-widest uppercase">
            {phase === 'brainstorm' ? 'Talk to start a project' : 'Waiting for footage'}
          </p>
        </div>
      )}

      {/* busy overlays */}
      {(shot?.status === 'rendering' || shot?.status === 'replacing') && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/45">
          <div
            className={cn(
              'flex items-center gap-2 rounded-full border px-3 py-1.5 font-mono text-[11px] font-bold tracking-widest uppercase',
              shot.status === 'rendering'
                ? 'border-amber-500/50 bg-zinc-950/80 text-amber-300'
                : 'border-fuchsia-500/50 bg-zinc-950/80 text-fuchsia-300'
            )}
          >
            <CircleNotchIcon className="size-3.5 animate-spin" />
            {shot.status === 'rendering' ? 'Rendering shot' : 'Replacing segment'}
          </div>
        </div>
      )}

      {/* top overlays */}
      {shot && badge && (
        <div className="absolute inset-x-0 top-0 flex items-start justify-between p-3">
          <span className="rounded bg-zinc-950/70 px-2 py-1 font-mono text-[10px] tracking-widest text-zinc-300 uppercase">
            {shot.id} · {formatTime(shot.start)}–{formatTime(shot.end)}
          </span>
          <span
            className={cn(
              'rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold tracking-widest uppercase',
              badge.className
            )}
          >
            {badge.label}
          </span>
        </div>
      )}

      {/* dialogue caption */}
      {shot?.dialogue && (
        <div className="pointer-events-none absolute inset-x-0 bottom-12 flex justify-center px-6">
          <p className="rounded bg-zinc-950/70 px-3 py-1 text-center text-sm text-zinc-100 italic">
            &ldquo;{shot.dialogue}&rdquo;
          </p>
        </div>
      )}

      {/* transport bar */}
      <div className="absolute inset-x-0 bottom-0 flex h-10 items-center gap-3 bg-gradient-to-t from-zinc-950/90 to-transparent px-3">
        <button
          type="button"
          onClick={togglePlay}
          disabled={!hasVideo}
          aria-label={isPlaying ? 'Pause' : 'Play'}
          className={cn(
            'flex size-7 items-center justify-center rounded-full bg-white/10 text-zinc-100 transition-colors hover:bg-white/20',
            !hasVideo && 'cursor-not-allowed opacity-40'
          )}
        >
          {isPlaying ? (
            <PauseIcon weight="fill" className="size-3.5" />
          ) : (
            <PlayIcon weight="fill" className="size-3.5" />
          )}
        </button>
        <span className="font-mono text-[11px] text-zinc-300 tabular-nums">
          {formatTime((shot?.start ?? 0) + localTime)} / {formatTime(shot?.end ?? 0)}
        </span>
        {shot && (
          <span className="ml-auto hidden truncate font-mono text-[10px] text-zinc-500 sm:block sm:max-w-[50%]">
            {shot.prompt}
          </span>
        )}
      </div>
    </motion.div>
  );
}
