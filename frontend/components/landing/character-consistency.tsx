'use client';

import { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { IdentificationCard, Images } from '@phosphor-icons/react';
import { Reveal } from '@/components/landing/reveal';
import { Tilt3D } from '@/components/landing/tilt-3d';

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

interface Sheet {
  /** Reference index, e.g. "01". */
  ref: string;
  /** Sheet section name, e.g. "Turnaround". */
  name: string;
  /** Short descriptor of what the section holds. */
  note: string;
  /** Placeholder still standing in for the sheet thumbnail. */
  image: string;
}

// Stand-in thumbnails for the reference-sheet sections (turnaround / expressions /
// wardrobe). These are placeholder JPGs — swapped for real sheet crops once the
// character pipeline lands (see PLACEHOLDERS.md).
const SHEETS: readonly Sheet[] = [
  {
    ref: '01',
    name: 'Turnaround',
    note: 'Front · 3/4 · side',
    image: '/placeholders/hero-kingdom-left.jpg',
  },
  {
    ref: '02',
    name: 'Expressions',
    note: '6 emotions',
    image: '/placeholders/hero-modern-left.jpg',
  },
  {
    ref: '03',
    name: 'Wardrobe',
    note: 'Detail crops',
    image: '/placeholders/hero-rock-left.jpg',
  },
];

// Locked character palette — real swatches, the way a film character bible pins
// its colors so wardrobe and grade never drift between shots.
const PALETTE = ['#e8b34b', '#c76b4a', '#3f4a63', '#e9e2d3', '#1b1b20'];

/**
 * Landing showcase for the character-consistency feature (SPEC §10).
 * A large 3D-tilt film-frame card plays the looping character-action clip, with
 * a "reference sheet" sidebar (turnaround / expression / wardrobe thumbnails +
 * locked palette) beside it — the pitch being that the director keeps a bible
 * for every face so shot 12 looks like shot 1.
 */
export function CharacterConsistency() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [videoFailed, setVideoFailed] = useState(false);

  // Match the hero: force play on mount so Safari Low-Power-Mode still loops,
  // and fall back to the poster still if it refuses.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = true;
    video.play().catch(() => {
      // Autoplay blocked — poster fallback stays visible.
    });
  }, []);

  return (
    <section
      id="characters"
      className="relative mx-auto w-full max-w-6xl px-5 py-24 md:px-10 md:py-32"
    >
      <Reveal>
        <p className="font-mono text-xs tracking-[0.35em] text-white/40 uppercase">
          Character consistency
        </p>
        <h2 className="mt-4 max-w-3xl text-4xl font-extrabold tracking-tight text-white md:text-6xl">
          Cast characters that stay{' '}
          <span className="text-[color:var(--ld-accent)]">consistent</span>.
        </h2>
        <p className="mt-4 max-w-xl text-base text-white/60 md:text-lg">
          The director keeps a reference sheet for every face — so shot 12 looks like shot 1.
        </p>
      </Reveal>

      <div className="mt-12 grid grid-cols-1 items-center gap-8 md:mt-16 lg:grid-cols-12 lg:gap-10">
        {/* Film-frame video card */}
        <motion.div
          className="lg:col-span-7"
          initial={{ opacity: 0, y: 34, scale: 0.985 }}
          whileInView={{ opacity: 1, y: 0, scale: 1 }}
          viewport={{ once: true, amount: 0.25 }}
          transition={{ duration: 0.85, ease: EASE }}
        >
          <Tilt3D max={6} className="h-full">
            <div className="flex h-full overflow-hidden rounded-2xl border border-white/10 bg-[color:var(--ld-surface)] shadow-[0_24px_60px_-24px_rgba(0,0,0,0.8)]">
              <div aria-hidden className="ld-rail w-4 shrink-0 sm:w-5" />
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex items-center justify-between px-4 pt-4 pb-3 font-mono text-[10px] tracking-[0.25em] text-white/45 uppercase">
                  <span>Reel 01 · Her</span>
                  <span className="flex items-center gap-1.5 text-[color:var(--ld-accent)]">
                    <span
                      aria-hidden
                      className="ld-rec-dot size-1.5 rounded-full bg-[color:var(--ld-accent)]"
                    />
                    Live take
                  </span>
                </div>

                <div className="bg-black px-1.5">
                  <div className="relative aspect-square w-full overflow-hidden rounded-sm">
                    {/* Poster still underneath so blocked autoplay / a failed load
                        degrades to a static frame instead of a black box. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src="/placeholders/reference-character-poster.jpg"
                      alt=""
                      className="absolute inset-0 h-full w-full object-cover"
                    />
                    {/*
                      THIRD-PARTY DEV PLACEHOLDER — reference-character-video.mp4 is
                      NOT our asset (downloaded from x.com/yokohara_h). It MUST be
                      replaced with a fal-generated character clip before submission.
                      Tracked in frontend/PLACEHOLDERS.md; do not ship as-is.
                    */}
                    {!videoFailed && (
                      <video
                        ref={videoRef}
                        src="/placeholders/reference-character-video.mp4"
                        poster="/placeholders/reference-character-poster.jpg"
                        autoPlay
                        loop
                        muted
                        playsInline
                        controls={false}
                        disablePictureInPicture
                        preload="metadata"
                        onError={() => setVideoFailed(true)}
                        className="pointer-events-none absolute inset-0 h-full w-full object-cover"
                      />
                    )}
                    {/* Cinematic vignette + timecode HUD */}
                    <div
                      aria-hidden
                      className="pointer-events-none absolute inset-0"
                      style={{
                        background:
                          'radial-gradient(120% 90% at 50% 40%, transparent 55%, rgba(6,6,8,0.55) 100%)',
                      }}
                    />
                    <div className="pointer-events-none absolute inset-x-3 bottom-3 flex items-center justify-between font-mono text-[10px] tracking-[0.2em] text-white/70 uppercase">
                      <span className="rounded-sm bg-black/45 px-1.5 py-0.5 backdrop-blur-sm">
                        Shot 12
                      </span>
                      <span className="rounded-sm bg-black/45 px-1.5 py-0.5 tabular-nums backdrop-blur-sm">
                        00:12:04
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex flex-1 flex-col gap-1.5 px-4 pt-4 pb-5">
                  <p className="font-mono text-[10px] tracking-[0.25em] text-[color:var(--ld-accent)] uppercase">
                    Shot 12 · matches shot 01
                  </p>
                  <p className="text-sm leading-relaxed text-white/60">
                    The same generated face, wardrobe, and palette carried across every render.
                  </p>
                </div>
              </div>
              <div aria-hidden className="ld-rail w-4 shrink-0 sm:w-5" />
            </div>
          </Tilt3D>
        </motion.div>

        {/* Reference-sheet sidebar */}
        <div className="lg:col-span-5">
          <Reveal delay={0.1}>
            <div className="flex items-center gap-2.5">
              <IdentificationCard
                weight="duotone"
                className="size-5 text-[color:var(--ld-accent)]"
                aria-hidden
              />
              <p className="font-mono text-xs tracking-[0.3em] text-white/55 uppercase">
                Reference sheet — Her
              </p>
            </div>
            <p className="mt-4 max-w-md text-sm leading-relaxed text-white/55 md:text-base">
              Every face gets a bible the director casts from — turnaround, expression grid,
              wardrobe crops, and a locked palette — passed into each shot so the look never drifts.
            </p>
          </Reveal>

          <div className="mt-6 grid grid-cols-3 gap-3">
            {SHEETS.map((sheet, i) => (
              <Reveal key={sheet.ref} delay={0.16 + i * 0.08}>
                <figure className="overflow-hidden rounded-lg border border-white/10 bg-black">
                  <div className="relative aspect-square w-full">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={sheet.image}
                      alt=""
                      loading="lazy"
                      className="absolute inset-0 h-full w-full object-cover"
                    />
                    <span className="absolute top-1.5 left-1.5 rounded-sm bg-black/55 px-1 py-0.5 font-mono text-[9px] tracking-[0.15em] text-white/75 uppercase backdrop-blur-sm">
                      Ref {sheet.ref}
                    </span>
                  </div>
                  <figcaption className="px-2 py-2">
                    <p className="text-xs font-semibold tracking-tight text-white/90">
                      {sheet.name}
                    </p>
                    <p className="mt-0.5 font-mono text-[10px] tracking-wide text-white/40">
                      {sheet.note}
                    </p>
                  </figcaption>
                </figure>
              </Reveal>
            ))}
          </div>

          <Reveal delay={0.42}>
            <div className="mt-5 flex items-center gap-3">
              <span className="font-mono text-[10px] tracking-[0.25em] text-white/40 uppercase">
                Palette
              </span>
              <div className="flex items-center gap-1.5">
                {PALETTE.map((hex) => (
                  <span
                    key={hex}
                    className="size-4 rounded-sm border border-white/10"
                    style={{ backgroundColor: hex }}
                    title={hex}
                  />
                ))}
              </div>
            </div>
          </Reveal>

          <Reveal delay={0.5}>
            <div className="mt-6 flex items-start gap-3 border-l-2 border-[color:var(--ld-accent)] pl-4">
              <Images
                weight="duotone"
                className="mt-0.5 size-4 shrink-0 text-[color:var(--ld-accent)]"
                aria-hidden
              />
              <p className="text-sm leading-relaxed text-white/70">
                One locked sheet, referenced on every generation — so a face cast in shot 1 still
                reads as the same person twelve shots later.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
