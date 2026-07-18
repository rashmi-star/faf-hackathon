'use client';

import { useEffect } from 'react';
import type Lenis from 'lenis';

/**
 * Lenis smooth-scroll wrapper for the landing page. Loaded dynamically so a
 * missing/broken dependency degrades to native scrolling instead of crashing.
 * Companion CSS lives in styles/globals.css (html.lenis rules).
 */
export function SmoothScroll({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    let lenis: Lenis | undefined;
    let raf = 0;
    let cancelled = false;

    import('lenis')
      .then(({ default: LenisCtor }) => {
        if (cancelled) return;
        lenis = new LenisCtor({ lerp: 0.11, anchors: true });
        const loop = (time: number) => {
          lenis?.raf(time);
          raf = requestAnimationFrame(loop);
        };
        raf = requestAnimationFrame(loop);
      })
      .catch(() => {
        // lenis unavailable — native scrolling still works.
      });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      lenis?.destroy();
    };
  }, []);

  return <>{children}</>;
}
