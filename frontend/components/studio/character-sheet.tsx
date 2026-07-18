'use client';

import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  CaretDownIcon,
  CheckCircleIcon,
  CircleNotchIcon,
  FilmStripIcon,
} from '@phosphor-icons/react/dist/ssr';
import { type Character } from '@/lib/project-state';
import { cn } from '@/lib/shadcn/utils';

// Canonical labels for the media the director generates (agent/src/media.py).
// Used positionally; anything beyond the known set falls back to a numbered
// label so the sheet never shows an unlabeled thumbnail.
const EXPRESSION_LABELS = ['neutral', 'happy', 'sad', 'angry'];
const TURNAROUND_LABELS = ['front', '3/4', 'side', 'back'];

function labelAt(labels: string[], i: number, prefix: string): string {
  return labels[i] ?? `${prefix} ${String(i + 1).padStart(2, '0')}`;
}

// ---------------------------------------------------------------------------
// Building blocks
// ---------------------------------------------------------------------------

/** An image that degrades to a neutral film-strip tile instead of a broken slot. */
function SheetImage({ src, alt, className }: { src: string; alt: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div className={cn('flex items-center justify-center bg-zinc-900 text-zinc-700', className)}>
        <FilmStripIcon className="size-4" />
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => setFailed(true)}
      className={cn('object-cover', className)}
    />
  );
}

/** Mono section header with a hairline rule — the reference-document motif. */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[9px] font-bold tracking-widest text-zinc-500 uppercase">
        {children}
      </span>
      <span className="h-px flex-1 bg-white/10" />
    </div>
  );
}

function ApprovalPill({ approved }: { approved: boolean }) {
  return (
    <span
      className={cn(
        'flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 font-mono text-[8px] font-bold tracking-widest uppercase',
        approved
          ? 'border-emerald-500/50 bg-emerald-950/60 text-emerald-300'
          : 'border-amber-500/50 bg-amber-950/60 text-amber-300'
      )}
    >
      {approved ? (
        <CheckCircleIcon weight="fill" className="size-2.5" />
      ) : (
        <CircleNotchIcon className="size-2.5 animate-spin" />
      )}
      {approved ? 'Approved' : 'Pending'}
    </span>
  );
}

/** Four L-shaped ticks that frame the hero portrait like a film reference plate. */
function FrameTicks() {
  const corners = [
    'top-1.5 left-1.5 border-t border-l',
    'top-1.5 right-1.5 border-t border-r',
    'bottom-1.5 left-1.5 border-b border-l',
    'bottom-1.5 right-1.5 border-b border-r',
  ];
  return (
    <>
      {corners.map((pos) => (
        <span
          key={pos}
          className={cn('pointer-events-none absolute size-2.5 border-amber-300/70', pos)}
        />
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Sheet
// ---------------------------------------------------------------------------

export function CharacterSheet({
  character,
  expanded,
  onToggle,
}: {
  character: Character;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { name, sheet, image_url, role, age, approved } = character;
  const personality = character.personality ?? [];
  const palette = character.palette ?? [];
  const expressions = character.expression_urls ?? [];
  const turnaround = character.turnaround_urls ?? [];
  const notes = character.notes ?? [];
  const identity = [role, age].filter(Boolean).join(' · ');

  return (
    <div className="overflow-hidden rounded-lg border border-white/10 bg-zinc-900/60">
      {/* header — always visible, toggles the sheet */}
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2.5 p-2 text-left transition-colors hover:bg-white/[0.03]"
      >
        <SheetImage
          src={image_url}
          alt={name}
          className="size-10 shrink-0 rounded border border-white/10"
        />
        <div className="min-w-0 flex-1">
          <p className="truncate font-sans text-sm font-semibold text-zinc-100">{name}</p>
          {identity && (
            <p className="truncate font-mono text-[9px] tracking-widest text-zinc-500 uppercase">
              {identity}
            </p>
          )}
        </div>
        <ApprovalPill approved={approved} />
        <CaretDownIcon
          className={cn(
            'size-3.5 shrink-0 text-zinc-500 transition-transform duration-200',
            expanded && 'rotate-180'
          )}
        />
      </button>

      {/* body — the full reference sheet */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeInOut' as const }}
            className="overflow-hidden"
          >
            <div className="space-y-3 border-t border-white/10 px-2.5 pt-2.5 pb-3">
              {/* hero portrait */}
              <div className="relative overflow-hidden rounded-md">
                <SheetImage
                  src={image_url}
                  alt={`${name} portrait`}
                  className="aspect-[4/5] w-full"
                />
                <FrameTicks />
                <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/85 to-transparent px-2 pt-6 pb-1.5">
                  <span className="font-mono text-[8px] tracking-widest text-white/70 uppercase">
                    {character.id}
                  </span>
                  <span className="font-mono text-[8px] tracking-widest text-white/60 uppercase">
                    Reference Sheet
                  </span>
                </div>
              </div>

              {/* personality */}
              {personality.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {personality.map((trait) => (
                    <span
                      key={trait}
                      className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 font-mono text-[9px] tracking-wide text-zinc-300"
                    >
                      {trait}
                    </span>
                  ))}
                </div>
              )}

              {/* sheet text */}
              {sheet && (
                <div className="space-y-1.5">
                  <SectionLabel>Sheet</SectionLabel>
                  <p className="text-[11px] leading-relaxed text-zinc-400">{sheet}</p>
                </div>
              )}

              {/* expression grid */}
              {expressions.length > 0 && (
                <div className="space-y-1.5">
                  <SectionLabel>Expressions</SectionLabel>
                  <div className="grid grid-cols-4 gap-1">
                    {expressions.map((url, i) => (
                      <figure key={`${url}-${i}`} className="space-y-0.5">
                        <SheetImage
                          src={url}
                          alt={labelAt(EXPRESSION_LABELS, i, 'view')}
                          className="aspect-square w-full rounded border border-white/10"
                        />
                        <figcaption className="text-center font-mono text-[7px] tracking-widest text-zinc-500 uppercase">
                          {labelAt(EXPRESSION_LABELS, i, 'view')}
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                </div>
              )}

              {/* turnaround strip */}
              {turnaround.length > 0 && (
                <div className="space-y-1.5">
                  <SectionLabel>Turnaround</SectionLabel>
                  <div className="flex gap-1 overflow-x-auto pb-1 [scrollbar-color:rgba(255,255,255,0.2)_transparent] [scrollbar-width:thin]">
                    {turnaround.map((url, i) => (
                      <figure key={`${url}-${i}`} className="shrink-0 space-y-0.5">
                        <SheetImage
                          src={url}
                          alt={labelAt(TURNAROUND_LABELS, i, 'view')}
                          className="h-16 w-12 rounded border border-white/10"
                        />
                        <figcaption className="text-center font-mono text-[7px] tracking-widest text-zinc-500 uppercase">
                          {labelAt(TURNAROUND_LABELS, i, 'view')}
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                </div>
              )}

              {/* color palette */}
              {palette.length > 0 && (
                <div className="space-y-1.5">
                  <SectionLabel>Palette</SectionLabel>
                  <div className="flex flex-wrap gap-1.5">
                    {palette.map((hex, i) => (
                      <div key={`${hex}-${i}`} className="flex flex-col items-center gap-1">
                        <span
                          className="size-7 rounded border border-white/15"
                          style={{ backgroundColor: hex }}
                        />
                        <span className="font-mono text-[7px] tracking-wider text-zinc-500 uppercase">
                          {hex}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* notes */}
              {notes.length > 0 && (
                <div className="space-y-1.5">
                  <SectionLabel>Notes</SectionLabel>
                  <ul className="space-y-1">
                    {notes.map((note, i) => (
                      <li
                        key={i}
                        className="flex gap-1.5 text-[11px] leading-relaxed text-zinc-400"
                      >
                        <span className="mt-1.5 size-1 shrink-0 rounded-full bg-amber-300/70" />
                        <span>{note}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
