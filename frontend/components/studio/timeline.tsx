'use client';

import { AnimatePresence, motion } from 'motion/react';
import { type Highlight, type Shot, type ShotStatus } from '@/lib/project-state';
import { cn } from '@/lib/shadcn/utils';

/** Pixels per second on the timeline. */
const PPS = 44;
const MIN_DURATION = 30;

const STATUS_STYLES: Record<ShotStatus, string> = {
  planned: 'border-dashed border-zinc-600/60 bg-zinc-800/60 text-zinc-400',
  still: 'border-sky-500/50 bg-sky-950/70 text-sky-200',
  rendering: 'border-amber-500/60 bg-amber-950/60 text-amber-200',
  ready: 'border-emerald-500/50 bg-emerald-950/50 text-emerald-200',
  replacing: 'border-fuchsia-500/60 bg-fuchsia-950/60 text-fuchsia-200',
};

const LEGEND: Array<{ status: ShotStatus; dot: string }> = [
  { status: 'planned', dot: 'bg-zinc-500' },
  { status: 'still', dot: 'bg-sky-400' },
  { status: 'rendering', dot: 'bg-amber-400' },
  { status: 'ready', dot: 'bg-emerald-400' },
  { status: 'replacing', dot: 'bg-fuchsia-400' },
];

function formatTick(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function ShotBlock({
  shot,
  selected,
  onSelect,
}: {
  shot: Shot;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  const busy = shot.status === 'rendering' || shot.status === 'replacing';

  return (
    <motion.button
      type="button"
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      onClick={() => onSelect(shot.id)}
      title={shot.prompt}
      style={{ left: shot.start * PPS, width: (shot.end - shot.start) * PPS }}
      className={cn(
        'absolute top-1 bottom-1 overflow-hidden rounded-md border text-left transition-colors',
        STATUS_STYLES[shot.status],
        busy && 'animate-pulse',
        selected && 'ring-2 ring-white/70'
      )}
    >
      {shot.still_url && (
        <div
          aria-hidden
          className="absolute inset-0 bg-cover bg-center opacity-35"
          style={{ backgroundImage: `url(${shot.still_url})` }}
        />
      )}
      <div className="relative flex h-full flex-col justify-between p-1.5">
        <span className="font-mono text-[10px] font-bold tracking-widest uppercase">{shot.id}</span>
        <span className="truncate text-[10px] leading-tight opacity-80">
          {shot.dialogue ? `“${shot.dialogue}”` : shot.prompt}
        </span>
      </div>
    </motion.button>
  );
}

interface TimelineProps {
  shots: Shot[];
  highlight: Highlight | null;
  playhead: number;
  selectedShotId: string | null;
  onSelectShot: (id: string) => void;
}

export function Timeline({
  shots,
  highlight,
  playhead,
  selectedShotId,
  onSelectShot,
}: TimelineProps) {
  const duration = Math.max(MIN_DURATION, ...shots.map((s) => s.end));
  const width = duration * PPS;
  const ticks = Array.from({ length: duration + 1 }, (_, i) => i);

  return (
    <section className="shrink-0 border-t border-white/10 bg-zinc-950">
      {/* header row */}
      <div className="flex h-7 items-center gap-4 px-3 md:px-4">
        <span className="font-mono text-[10px] font-bold tracking-widest text-zinc-400 uppercase">
          Timeline
        </span>
        <span className="font-mono text-[10px] text-zinc-600 tabular-nums">
          {formatTick(Math.round(playhead))} / {formatTick(duration)}
        </span>
        <div className="ml-auto hidden items-center gap-3 md:flex">
          {LEGEND.map(({ status, dot }) => (
            <span key={status} className="flex items-center gap-1.5">
              <span className={cn('size-1.5 rounded-full', dot)} />
              <span className="font-mono text-[9px] tracking-widest text-zinc-500 uppercase">
                {status}
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* scrollable ruler + track */}
      <div className="overflow-x-auto pb-2 [scrollbar-color:rgba(255,255,255,0.2)_transparent] [scrollbar-width:thin]">
        <div className="relative px-3 md:px-4" style={{ width: width + 32 }}>
          {/* ruler */}
          <div className="relative h-5 border-b border-white/10" style={{ width }}>
            {ticks.map((t) => (
              <div key={t} className="absolute bottom-0" style={{ left: t * PPS }}>
                <div className={cn('w-px bg-zinc-700', t % 5 === 0 ? 'h-2.5' : 'h-1.5')} />
                {t % 5 === 0 && (
                  <span className="absolute bottom-3 left-0 font-mono text-[9px] text-zinc-500 tabular-nums">
                    {formatTick(t)}
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* track */}
          <div className="relative h-16 md:h-20" style={{ width }}>
            {shots.length === 0 && (
              <div className="absolute inset-1 flex items-center rounded-md border border-dashed border-zinc-800 px-4">
                <span className="font-mono text-[10px] tracking-widest text-zinc-600 uppercase">
                  Shot plan will appear here
                </span>
              </div>
            )}

            {shots.map((shot) => (
              <ShotBlock
                key={shot.id}
                shot={shot}
                selected={shot.id === selectedShotId}
                onSelect={onSelectShot}
              />
            ))}

            {/* highlight overlay — flashes while a highlight is set */}
            <AnimatePresence>
              {highlight && (
                <motion.div
                  key="highlight"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: [0.9, 0.25, 0.85, 0.35, 0.7] }}
                  exit={{ opacity: 0 }}
                  transition={{
                    duration: 1.1,
                    repeat: Infinity,
                    repeatType: 'reverse' as const,
                    ease: 'easeInOut' as const,
                  }}
                  style={{
                    left: highlight.start * PPS,
                    width: (highlight.end - highlight.start) * PPS,
                  }}
                  className="pointer-events-none absolute top-0 bottom-0 z-10 rounded-sm border-x-2 border-amber-400 bg-amber-400/25"
                />
              )}
            </AnimatePresence>

            {/* playhead */}
            <div
              className="pointer-events-none absolute -top-5 bottom-0 z-20"
              style={{ left: playhead * PPS }}
            >
              <div className="absolute top-0 left-1/2 size-2 -translate-x-1/2 rotate-45 rounded-[1px] bg-red-500" />
              <div className="absolute top-1 bottom-0 left-1/2 w-px -translate-x-1/2 bg-red-500" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
