'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { motion, useScroll, useTransform } from 'motion/react';

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const fade = (delay: number) => ({
  initial: { opacity: 0, y: 26 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.9, delay, ease: EASE },
});

/**
 * Full-bleed background-video hero. The poster image sits underneath the
 * video, so blocked autoplay or a failed video load degrades to a static
 * cinematic still. Subtle parallax drift on scroll.
 */
export function Hero() {
  const sectionRef = useRef<HTMLElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [videoFailed, setVideoFailed] = useState(false);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ['start start', 'end start'],
  });
  const mediaY = useTransform(scrollYProgress, [0, 1], ['0%', '16%']);

  // Safari (Low Power Mode) sometimes ignores the autoplay attribute — force
  // play on mount; the poster layer covers us if it still refuses.
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
      ref={sectionRef}
      className="relative flex h-svh min-h-[640px] w-full flex-col overflow-hidden"
    >
      {/* Background media with parallax drift */}
      <motion.div aria-hidden className="absolute inset-0 z-0" style={{ y: mediaY }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/placeholders/hero-video-poster.jpg"
          alt=""
          className="absolute inset-0 h-full w-full scale-105 object-cover"
        />
        {!videoFailed && (
          <video
            ref={videoRef}
            src="/placeholders/hero-video-bg.mp4"
            poster="/placeholders/hero-video-poster.jpg"
            autoPlay
            loop
            muted
            playsInline
            controls={false}
            disablePictureInPicture
            preload="auto"
            onError={() => setVideoFailed(true)}
            className="pointer-events-none absolute inset-0 h-full w-full scale-105 object-cover"
          />
        )}
      </motion.div>

      {/* Cinematic vignette so the type reads against bright footage */}
      <div
        aria-hidden
        className="absolute inset-0 z-[1]"
        style={{
          background:
            'linear-gradient(100deg, rgba(6,6,8,0.82) 0%, rgba(6,6,8,0.55) 34%, rgba(6,6,8,0.15) 60%, transparent 78%), linear-gradient(180deg, rgba(6,6,8,0.55) 0%, transparent 24%, transparent 58%, rgba(10,10,12,0.94) 100%)',
        }}
      />

      {/* Landing nav */}
      <header className="absolute inset-x-0 top-0 z-20 flex items-center justify-between px-5 py-5 md:px-10 md:py-7">
        <motion.p
          {...fade(0.15)}
          className="font-mono text-xs font-bold tracking-[0.35em] text-white/90 uppercase"
        >
          Director FAL
        </motion.p>
        <motion.div {...fade(0.25)}>
          <Link
            href="/studio"
            className="rounded-full border border-white/25 bg-white/5 px-5 py-2 font-mono text-xs tracking-[0.2em] text-white uppercase backdrop-blur-md transition-colors hover:border-white/60 hover:bg-white/15"
          >
            Enter Studio
          </Link>
        </motion.div>
      </header>

      {/* Copy block, poster-style bottom-left */}
      <div className="relative z-10 mx-auto flex w-full max-w-6xl flex-1 flex-col justify-end px-5 pb-24 md:px-10 md:pb-28">
        <motion.p
          {...fade(0.35)}
          className="flex items-center gap-2.5 font-mono text-[11px] tracking-[0.3em] text-white/70 uppercase"
        >
          <span aria-hidden className="ld-rec-dot size-2 rounded-full bg-red-500" />
          Voice-directed video creation
        </motion.p>
        <motion.h1
          {...fade(0.5)}
          className="mt-5 text-[clamp(3.25rem,9vw,8rem)] leading-[0.95] font-extrabold tracking-[-0.03em] text-white"
        >
          Director FAL
        </motion.h1>
        <motion.p
          {...fade(0.65)}
          className="mt-2 text-[clamp(1.6rem,4.5vw,3.5rem)] leading-tight font-extralight tracking-tight text-white/90 italic"
        >
          The editor you talk to.
        </motion.p>
        <motion.p
          {...fade(0.8)}
          className="mt-6 max-w-xl text-base leading-relaxed text-white/70 md:text-lg"
        >
          Pitch a story, cast your characters, and watch the film assemble itself. Then direct every
          re-shoot out loud — the timeline listens.
        </motion.p>
        <motion.div {...fade(0.95)} className="mt-9 flex flex-wrap items-center gap-3.5">
          <Link
            href="/studio"
            className="rounded-full bg-[color:var(--ld-accent)] px-7 py-3.5 text-sm font-bold tracking-wide text-black uppercase transition-transform hover:scale-[1.04] active:scale-[0.98]"
          >
            Enter Studio
          </Link>
          <a
            href="#how-it-works"
            className="rounded-full border border-white/25 px-7 py-3.5 text-sm font-semibold tracking-wide text-white/90 uppercase backdrop-blur-md transition-colors hover:border-white/60"
          >
            See how it works
          </a>
        </motion.div>
      </div>

      {/* Scroll cue */}
      <div
        aria-hidden
        className="absolute bottom-7 left-1/2 z-10 hidden -translate-x-1/2 flex-col items-center gap-2 md:flex"
      >
        <span className="font-mono text-[10px] tracking-[0.3em] text-white/45 uppercase">
          Scroll
        </span>
        <span className="ld-scroll-line h-8 w-px bg-white/45" />
      </div>
    </section>
  );
}
