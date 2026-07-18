'use client';

import { FilmFrameCard } from '@/components/landing/film-frame-card';
import { Reveal } from '@/components/landing/reveal';
import { Tilt3D } from '@/components/landing/tilt-3d';

interface Beat {
  kicker: string;
  name: string;
  title: string;
  body: string;
  images: readonly [string, string];
}

const BEATS: Beat[] = [
  {
    kicker: '01',
    name: 'Talk',
    title: 'Pitch it out loud',
    body: 'Brainstorm with an agent that riffs back. Lock the logline, cast characters from generated portraits, and approve the storyboard — all in conversation.',
    images: ['/placeholders/branch-left.jpg', '/placeholders/branch-right.jpg'],
  },
  {
    kicker: '02',
    name: 'Watch',
    title: 'Watch the cut assemble',
    body: 'Stills land in seconds. Clips render in the background while the agent narrates progress, and every shot drops onto a live timeline.',
    images: ['/placeholders/hero-kingdom-left.jpg', '/placeholders/hero-kingdom-right.jpg'],
  },
  {
    kicker: '03',
    name: 'Ship',
    title: 'Direct the fix, then ship',
    body: '“Around 15 seconds, she says I love you instead.” The segment highlights, re-renders in place, and exports to 16:9, 9:16, and 1:1.',
    images: ['/placeholders/hero-modern-left.jpg', '/placeholders/hero-rock-right.jpg'],
  },
];

export function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="relative mx-auto w-full max-w-6xl px-5 py-24 md:px-10 md:py-32"
    >
      <Reveal>
        <p className="font-mono text-xs tracking-[0.35em] text-white/40 uppercase">How it works</p>
        <h2 className="mt-4 text-4xl font-extrabold tracking-tight text-white md:text-6xl">
          Talk. <span className="text-[color:var(--ld-accent)]">Watch.</span> Ship.
        </h2>
        <p className="mt-4 max-w-xl text-base text-white/60 md:text-lg">
          Three beats from idea to finished film — every one of them directed with your voice.
        </p>
      </Reveal>
      <div className="mt-12 grid grid-cols-1 gap-6 md:mt-16 md:grid-cols-3 md:gap-8">
        {BEATS.map((beat, i) => (
          <Reveal key={beat.name} delay={i * 0.12} className="h-full">
            <Tilt3D max={7} className="h-full">
              <FilmFrameCard {...beat} className="h-full" />
            </Tilt3D>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
