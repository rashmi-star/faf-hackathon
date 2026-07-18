'use client';

import { useEffect, useRef, useState } from 'react';
import { useSessionContext, useSessionMessages } from '@livekit/components-react';
import {
  ChatTextIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  DownloadSimpleIcon,
  ExportIcon,
  UsersIcon,
} from '@phosphor-icons/react/dist/ssr';
import { type ExportItem, type TranscriptEntry, useProjectState } from '@/lib/project-state';
import { cn } from '@/lib/shadcn/utils';

type TabId = 'transcript' | 'cast' | 'exports';

function formatTs(ts: number): string {
  if (ts > 1e10) {
    // epoch milliseconds from a live session message
    return new Date(ts).toLocaleTimeString(undefined, { timeStyle: 'short' });
  }
  const m = Math.floor(ts / 60);
  const s = Math.floor(ts % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ---------------------------------------------------------------------------
// Transcript
// ---------------------------------------------------------------------------

function TranscriptTab({ entries }: { entries: TranscriptEntry[] }) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  if (entries.length === 0) {
    return (
      <EmptyState icon={<ChatTextIcon className="size-6" />} label="Conversation appears here" />
    );
  }

  return (
    <div
      ref={scrollRef}
      className="h-full space-y-3 overflow-y-auto p-3 [scrollbar-color:rgba(255,255,255,0.2)_transparent] [scrollbar-width:thin]"
    >
      {entries.map((entry, i) => (
        <div key={i} className="flex flex-col gap-0.5">
          <div className="flex items-baseline gap-2">
            <span
              className={cn(
                'font-mono text-[9px] font-bold tracking-widest uppercase',
                entry.role === 'agent' ? 'text-amber-300' : 'text-sky-300'
              )}
            >
              {entry.role === 'agent' ? 'Director' : 'You'}
            </span>
            <span className="font-mono text-[9px] text-zinc-600 tabular-nums">
              {formatTs(entry.ts)}
            </span>
          </div>
          <p className="text-xs leading-relaxed text-zinc-300">{entry.text}</p>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cast (character cards)
// ---------------------------------------------------------------------------

function CastTab() {
  const { state } = useProjectState();

  if (state.characters.length === 0) {
    return <EmptyState icon={<UsersIcon className="size-6" />} label="Characters appear here" />;
  }

  return (
    <div className="grid h-full grid-cols-2 content-start gap-3 overflow-y-auto p-3 [scrollbar-color:rgba(255,255,255,0.2)_transparent] [scrollbar-width:thin]">
      {state.characters.map((character) => (
        <div
          key={character.id}
          className="overflow-hidden rounded-lg border border-white/10 bg-zinc-900"
        >
          <div className="relative aspect-[3/4]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={character.image_url}
              alt={character.name}
              className="h-full w-full object-cover"
            />
            <span
              className={cn(
                'absolute right-1.5 bottom-1.5 flex items-center gap-1 rounded-full border px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-widest uppercase backdrop-blur',
                character.approved
                  ? 'border-emerald-500/50 bg-emerald-950/70 text-emerald-300'
                  : 'border-amber-500/50 bg-amber-950/70 text-amber-300'
              )}
            >
              {character.approved ? (
                <CheckCircleIcon weight="fill" className="size-3" />
              ) : (
                <CircleNotchIcon className="size-3 animate-spin" />
              )}
              {character.approved ? 'Approved' : 'Pending'}
            </span>
          </div>
          <div className="space-y-0.5 p-2">
            <p className="text-xs font-semibold text-zinc-100">{character.name}</p>
            <p className="line-clamp-2 text-[10px] leading-snug text-zinc-500">{character.sheet}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

const EXPORT_META: Record<string, { name: string; dims: string; ratio: number }> = {
  '16:9': { name: 'YouTube', dims: '1920 × 1080', ratio: 16 / 9 },
  '9:16': { name: 'Reels · Shorts', dims: '1080 × 1920', ratio: 9 / 16 },
  '1:1': { name: 'Square', dims: '1080 × 1080', ratio: 1 },
  loop: { name: '8s Loop', dims: '1920 × 1080', ratio: 16 / 9 },
};

function ExportCard({ item }: { item: ExportItem }) {
  const meta = EXPORT_META[item.format] ?? { name: item.format, dims: '', ratio: 16 / 9 };
  const glyphHeight = 22;
  const glyphWidth = Math.min(36, Math.round(glyphHeight * meta.ratio));

  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/10 bg-zinc-900 p-2.5">
      <div className="flex size-10 shrink-0 items-center justify-center rounded bg-zinc-800">
        <div
          className="rounded-[2px] border border-zinc-400"
          style={{ width: glyphWidth, height: meta.ratio < 1 ? 28 : glyphHeight }}
        />
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-mono text-xs font-bold tracking-wider text-zinc-100 uppercase">
          {item.format}
        </p>
        <p className="truncate text-[10px] text-zinc-500">
          {meta.name}
          {meta.dims && ` · ${meta.dims}`}
        </p>
      </div>
      <a
        href={item.url}
        download
        className="flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 font-mono text-[10px] font-bold tracking-widest text-emerald-300 uppercase transition-colors hover:bg-emerald-500/20"
      >
        <DownloadSimpleIcon className="size-3.5" />
        Get
      </a>
    </div>
  );
}

function ExportsTab() {
  const { state } = useProjectState();

  if (state.exports.length === 0) {
    return (
      <EmptyState
        icon={<ExportIcon className="size-6" />}
        label="Say “export” when you love the cut"
      />
    );
  }

  return (
    <div className="h-full space-y-2 overflow-y-auto p-3 [scrollbar-color:rgba(255,255,255,0.2)_transparent] [scrollbar-width:thin]">
      {state.exports.map((item) => (
        <ExportCard key={item.format} item={item} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel chrome
// ---------------------------------------------------------------------------

function EmptyState({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-zinc-600">
      {icon}
      <p className="text-center font-mono text-[10px] tracking-widest uppercase">{label}</p>
    </div>
  );
}

export function RightPanel({ className }: { className?: string }) {
  const { state } = useProjectState();
  const session = useSessionContext();
  const { messages } = useSessionMessages(session);
  const [tab, setTab] = useState<TabId>('transcript');

  // The transcript is the live session transcription stream.
  const entries: TranscriptEntry[] = messages.map((m) => ({
    role: m.from?.isLocal ? 'user' : 'agent',
    text: m.message,
    ts: m.timestamp,
  }));

  // Auto-surface new content as the agent produces it (demo magic).
  const charCount = state.characters.length;
  const exportCount = state.exports.length;
  const prevChars = useRef(0);
  const prevExports = useRef(0);

  useEffect(() => {
    if (charCount > prevChars.current) setTab('cast');
    prevChars.current = charCount;
  }, [charCount]);

  useEffect(() => {
    if (exportCount > prevExports.current) setTab('exports');
    prevExports.current = exportCount;
  }, [exportCount]);

  const tabs: Array<{ id: TabId; label: string; icon: React.ReactNode; count: number }> = [
    {
      id: 'transcript',
      label: 'Transcript',
      icon: <ChatTextIcon className="size-3.5" />,
      count: entries.length,
    },
    { id: 'cast', label: 'Cast', icon: <UsersIcon className="size-3.5" />, count: charCount },
    {
      id: 'exports',
      label: 'Exports',
      icon: <ExportIcon className="size-3.5" />,
      count: exportCount,
    },
  ];

  return (
    <aside className={cn('flex min-h-0 flex-col bg-zinc-950', className)}>
      <div className="flex h-9 shrink-0 items-stretch border-b border-white/10">
        {tabs.map(({ id, label, icon, count }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              'flex flex-1 items-center justify-center gap-1.5 border-b-2 font-mono text-[10px] font-bold tracking-widest uppercase transition-colors',
              tab === id
                ? 'border-amber-300 text-zinc-100'
                : 'border-transparent text-zinc-500 hover:text-zinc-300'
            )}
          >
            {icon}
            <span className="hidden sm:inline">{label}</span>
            {count > 0 && (
              <span className="rounded-full bg-white/10 px-1.5 text-[9px] text-zinc-300 tabular-nums">
                {count}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1">
        {tab === 'transcript' && <TranscriptTab entries={entries} />}
        {tab === 'cast' && <CastTab />}
        {tab === 'exports' && <ExportsTab />}
      </div>
    </aside>
  );
}
