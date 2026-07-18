'use client';

import { Footer } from '@/components/landing/footer';
import { Hero } from '@/components/landing/hero';
import { HowItWorks } from '@/components/landing/how-it-works';
import { SmoothScroll } from '@/components/landing/smooth-scroll';
import { StackStrip } from '@/components/landing/stack-strip';

/**
 * Cinematic landing page (SPEC §7): video hero → “Talk. Watch. Ship.” →
 * stack strip → footer. Self-contained dark styling (see `.landing` tokens in
 * styles/globals.css) so it reads film-grade regardless of the app theme.
 */
export function LandingPage() {
  return (
    <SmoothScroll>
      <main className="landing relative min-h-screen overflow-x-clip">
        <div aria-hidden className="ld-grain pointer-events-none fixed inset-0 z-[60]" />
        <Hero />
        <HowItWorks />
        <StackStrip />
        <Footer />
      </main>
    </SmoothScroll>
  );
}
