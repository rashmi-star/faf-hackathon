'use client';

import { useRef } from 'react';
import { motion, useMotionTemplate, useMotionValue, useSpring, useTransform } from 'motion/react';

interface Tilt3DProps {
  children: React.ReactNode;
  /** Max rotation in degrees on each axis. */
  max?: number;
  /** CSS perspective in px. Bigger = subtler tilt. */
  perspective?: number;
  className?: string;
}

/**
 * Pointer-tracking 3D tilt container (adapted from reference-landing/tilt-3d.tsx).
 * Rotates its child group toward the cursor with spring damping, plus a glare
 * sheen that follows the pointer so the film-frame cards catch the light.
 * Inert on touch devices (mouse events only).
 */
export function Tilt3D({ children, max = 7, perspective = 1100, className }: Tilt3DProps) {
  const ref = useRef<HTMLDivElement>(null);
  const rx = useMotionValue(0);
  const ry = useMotionValue(0);
  const glareX = useMotionValue(50);
  const glareY = useMotionValue(35);
  const springRx = useSpring(rx, { stiffness: 140, damping: 18, mass: 0.6 });
  const springRy = useSpring(ry, { stiffness: 140, damping: 18, mass: 0.6 });

  const rotateX = useTransform(springRx, (v) => `${v}deg`);
  const rotateY = useTransform(springRy, (v) => `${v}deg`);
  const glare = useMotionTemplate`radial-gradient(420px circle at ${glareX}% ${glareY}%, rgba(255, 255, 255, 0.1), transparent 65%)`;

  function handleMove(e: React.MouseEvent<HTMLDivElement>) {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width; // 0 → 1
    const y = (e.clientY - rect.top) / rect.height; // 0 → 1
    rx.set((0.5 - y) * 2 * max);
    ry.set((x - 0.5) * 2 * max);
    glareX.set(x * 100);
    glareY.set(y * 100);
  }

  function handleLeave() {
    rx.set(0);
    ry.set(0);
  }

  return (
    <div
      ref={ref}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      className={className}
      style={{ perspective: `${perspective}px` }}
    >
      <motion.div
        className="relative h-full"
        style={{ rotateX, rotateY, transformStyle: 'preserve-3d' }}
      >
        {children}
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-2xl"
          style={{ background: glare }}
        />
      </motion.div>
    </div>
  );
}
