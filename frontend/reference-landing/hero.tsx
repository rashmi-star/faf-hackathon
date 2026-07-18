"use client";

import { motion, useScroll, useTransform } from "framer-motion";
import { useEffect, useRef } from "react";
import { Magnetic } from "@/components/motion/magnetic";
import { Button } from "@/components/ui/button";
import { WaitlistPill } from "@/components/waitlist-pill";

/**
 * Cinematic single-image hero — exactly one viewport tall.
 *
 *   Layers (back → front):
 *     - Full-bleed painted nature scene with slow Ken Burns drift
 *     - Soft vignette anchored on the left so the white serif headline reads
 *     - Cherry blossom petals raining across the viewport
 *     - Left-anchored center column: eyebrow + headline + subhead + magnetic CTAs
 */
export function Hero() {
  const ref = useRef<HTMLElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const imageY = useTransform(scrollYProgress, [0, 1], ["0%", "18%"]);

  // iOS Safari sometimes suppresses autoplay even with all the right attributes
  // (Low Power Mode is a common culprit). Force-play the video programmatically
  // on mount so the play-button overlay never appears on mobile.
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = true; // ensure muted is on the DOM element, not just JSX
    const tryPlay = () =>
      v.play().catch(() => {
        /* user gesture required — fine */
      });
    tryPlay();
    // Retry on the first user interaction in case Low Power Mode blocked autoplay
    const onFirstTouch = () => {
      tryPlay();
      window.removeEventListener("touchstart", onFirstTouch);
      window.removeEventListener("click", onFirstTouch);
    };
    window.addEventListener("touchstart", onFirstTouch, { passive: true });
    window.addEventListener("click", onFirstTouch);
    return () => {
      window.removeEventListener("touchstart", onFirstTouch);
      window.removeEventListener("click", onFirstTouch);
    };
  }, []);

  return (
    <section
      ref={ref}
      className="relative flex h-screen min-h-[640px] w-full flex-col justify-center overflow-hidden bg-[#9bb8c8]"
    >
      {/* Full-bleed looping video background with subtle parallax drift on scroll.
          Muted + autoplay + playsInline is required for mobile Safari to actually
          loop without user gesture. Video carries its own motion so we don't need
          the old Ken Burns animation. */}
      <motion.div aria-hidden className="absolute inset-0 z-0" style={{ y: imageY }}>
        <video
          ref={videoRef}
          autoPlay
          loop
          muted
          playsInline
          controls={false}
          disablePictureInPicture
          disableRemotePlayback
          preload="auto"
          poster="/images/hero-video-poster.jpg"
          className="pointer-events-none absolute inset-0 h-full w-full object-cover"
          // Legacy mobile browser attributes — set via spread to bypass React's type checker
          {...({
            "webkit-playsinline": "true",
            "x5-playsinline": "true",
          } as Record<string, string>)}
        >
          <source src="/images/hero-video-bg.mp4" type="video/mp4" />
        </video>
      </motion.div>

      {/* Left-side vignette so the white serif headline pops against the bright sky */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-[2]"
        style={{
          background:
            "linear-gradient(95deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.35) 28%, rgba(0,0,0,0.1) 52%, transparent 72%), linear-gradient(180deg, rgba(0,0,0,0.3) 0%, transparent 22%, transparent 65%, rgba(0,0,0,0.4) 100%)",
        }}
      />

      {/* Foreground content — left-anchored so the headline doesn't overlap the tree.
          Plain div (not motion.div) — a MotionValue in style here was suppressing
          child framer animations, leaving the headline stuck at opacity:0. The
          section is h-screen so it scrolls off-viewport on its own; no fade needed. */}
      <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-col items-start px-6 text-left md:px-12 lg:px-20">
        {/* Hero text rendered without framer initial-opacity: a MotionValue on
            the parent (style={{ opacity }} from useTransform) was preventing
            children's initial→animate transitions from progressing, leaving
            text stuck at opacity:0. CSS animation handles fade-in instead. */}
        <p
          className="eyebrow hero-fade-in"
          style={{ color: "rgba(255,255,255,0.85)", animationDelay: "0.3s" }}
        >
          Memory reimagined
        </p>

        <h1
          className="headline mt-6 max-w-4xl text-[clamp(40px,6.5vw,92px)] leading-[1.02] hero-fade-in"
          style={{
            color: "#ffffff",
            textShadow: "0 2px 28px rgba(0,0,0,0.55)",
            animationDelay: "0.5s",
          }}
        >
          <span className="block" style={{ opacity: 0.92 }}>
            Step inside
          </span>
          <span className="block italic">a memory you can walk through.</span>
        </h1>

        <p
          className="mt-8 max-w-xl text-balance text-base md:text-lg hero-fade-in"
          style={{
            color: "rgba(255,255,255,0.9)",
            textShadow: "0 1px 14px rgba(0,0,0,0.55)",
            animationDelay: "0.85s",
          }}
        >
          Upload one photograph. Walk into it in 3D. Hear the voice of someone you loved play softly
          from inside the room.
        </p>

        <div
          className="mt-8 flex flex-wrap items-center gap-3 hero-fade-in"
          style={{ animationDelay: "1.05s" }}
        >
          <Magnetic radius={140} strength={0.4}>
            <Button href="/create" size="lg" variant="primary">
              Bring a memory to life
            </Button>
          </Magnetic>
          <Magnetic radius={120} strength={0.3}>
            <Button href="#how-it-works" size="lg" variant="secondary">
              See how it works
            </Button>
          </Magnetic>
        </div>

        <div className="hero-fade-in" style={{ animationDelay: "1.3s" }}>
          <WaitlistPill />
        </div>
      </div>
    </section>
  );
}
