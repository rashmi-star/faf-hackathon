'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { FilmSlateIcon } from '@phosphor-icons/react/dist/ssr';
import { PreviewPlayer } from '@/components/studio/preview-player';
import { RightPanel } from '@/components/studio/right-panel';
import { TalkOrb } from '@/components/studio/talk-orb';
import { Timeline } from '@/components/studio/timeline';
import { type Phase, type Shot, useProjectState } from '@/lib/project-state';
import { cn } from '@/lib/shadcn/utils';

const PHASES: Phase[] = ['brainstorm', 'characters', 'scene', 'generating', 'review', 'exporting'];

function PhaseStepper({ phase }: { phase: Phase }) {
  const activeIndex = PHASES.indexOf(phase);

  return (
    <ol className="hidden items-center gap-1.5 lg:flex">
      {PHASES.map((p, i) => (
        <li key={p} className="flex items-center gap-1.5">
          {i > 0 && <span className="h-px w-3 bg-zinc-700" />}
          <span
            className={cn(
              'font-mono text-[10px] tracking-widest uppercase transition-colors',
              i < activeIndex && 'text-zinc-500',
              i === activeIndex && 'text-amber-300',
              i > activeIndex && 'text-zinc-700'
            )}
          >
            {p}
          </span>
        </li>
      ))}
    </ol>
  );
}

function StudioHeader() {
  const { state } = useProjectState();

  return (
    <header className="flex h-11 shrink-0 items-center gap-3 border-b border-white/10 bg-zinc-950 px-3 md:px-4">
      <Link href="/" className="flex items-center gap-2 text-zinc-100 hover:text-white">
        <FilmSlateIcon weight="fill" className="size-4 text-amber-300" />
        <span className="font-mono text-xs font-bold tracking-widest uppercase">Director FAL</span>
      </Link>
      <span className="h-4 w-px bg-zinc-800" />
      <span className="hidden truncate text-xs text-zinc-400 sm:block md:max-w-72">
        {state.story?.logline || 'Untitled Project'}
      </span>
      <div className="ml-auto flex items-center gap-4">
        <PhaseStepper phase={state.phase} />
        <span className="flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-bold tracking-widest text-emerald-300 uppercase">
          <span className="size-1.5 animate-pulse rounded-full bg-emerald-400" />
          Live
        </span>
      </div>
    </header>
  );
}

export function StudioShell() {
  const { state } = useProjectState();
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState(0);

  const shots = state.shots;
  const selectedShot: Shot | null = shots.find((s) => s.id === selectedShotId) ?? shots[0] ?? null;
  const music = state.timeline?.music;
  const musicUrl = music?.src.includes('/agent/media-cache/')
    ? `/api/media/${encodeURIComponent(music.src.split('/').at(-1) ?? '')}`
    : music?.src;

  // Keep the playhead parked at the selected shot's start when nothing is playing yet.
  useEffect(() => {
    if (selectedShot && (playhead < selectedShot.start || playhead > selectedShot.end)) {
      setPlayhead(selectedShot.start);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedShot?.id]);

  const handleSelectShot = useCallback((id: string) => {
    setSelectedShotId(id);
  }, []);

  // Auto-advance through the assembled timeline when a shot finishes.
  const handleShotEnded = useCallback(() => {
    if (!selectedShot) return;
    const idx = shots.findIndex((s) => s.id === selectedShot.id);
    const next = shots[idx + 1];
    if (next?.video_url) {
      setSelectedShotId(next.id);
      setPlayhead(next.start);
    }
  }, [selectedShot, shots]);

  return (
    <div className="dark fixed inset-0 z-[60] flex flex-col overflow-hidden bg-zinc-950 font-sans text-zinc-100">
      <StudioHeader />

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        {/* preview */}
        <div className="relative flex min-h-0 flex-1 items-center justify-center bg-black p-2 md:p-6">
          <PreviewPlayer
            shot={selectedShot}
            phase={state.phase}
            highlightActive={state.highlight !== null}
            musicUrl={musicUrl}
            musicGainDb={music?.gain_db}
            onTimeUpdate={setPlayhead}
            onEnded={handleShotEnded}
          />
        </div>

        {/* right panel */}
        <RightPanel className="h-60 w-full shrink-0 border-t border-white/10 md:h-auto md:w-80 md:border-t-0 md:border-l" />
      </div>

      <Timeline
        shots={shots}
        highlight={state.highlight}
        playhead={playhead}
        selectedShotId={selectedShot?.id ?? null}
        onSelectShot={handleSelectShot}
      />

      <TalkOrb />
    </div>
  );
}
