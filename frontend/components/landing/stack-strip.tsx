'use client';

import { Reveal } from '@/components/landing/reveal';

const STACK = ['fal', 'ElevenLabs', 'LiveKit'];

export function StackStrip() {
  return (
    <section className="border-y border-white/10 bg-[#0d0d0f]">
      <Reveal className="mx-auto flex w-full max-w-6xl flex-col items-center gap-5 px-5 py-14 text-center md:py-16">
        <p className="font-mono text-[11px] tracking-[0.35em] text-white/40 uppercase">Built on</p>
        <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 md:gap-x-8">
          {STACK.map((name, i) => (
            <span key={name} className="flex items-center gap-5 md:gap-8">
              {i > 0 && (
                <span aria-hidden className="size-1.5 rounded-full bg-[color:var(--ld-accent)]" />
              )}
              <span className="text-2xl font-bold tracking-tight text-white/85 md:text-4xl">
                {name}
              </span>
            </span>
          ))}
        </div>
        <p className="max-w-md font-mono text-xs leading-relaxed text-white/35">
          Every frame, every voice line, every export — generated live through the stack above.
        </p>
      </Reveal>
    </section>
  );
}
