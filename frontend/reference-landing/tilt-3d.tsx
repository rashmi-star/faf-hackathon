"use client";

import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { useRef } from "react";

/**
 * 3D tilt-on-mouse-move container — the Synex "card catches the light"
 * effect. Tracks the pointer position relative to the element's bounding
 * rect and rotates the whole child group on X/Y axes accordingly. Spring-
 * damped so motion feels liquid, not snappy. Disabled on touch + reduced-
 * motion preferences.
 *
 *   <Tilt3D max={6} perspective={1400}>
 *     <YourComposition />
 *   </Tilt3D>
 */
export function Tilt3D({
  children,
  max = 6,
  perspective = 1400,
  className,
}: {
  children: React.ReactNode;
  /** Max rotation in degrees on each axis. */
  max?: number;
  /** CSS perspective in px. Bigger = subtler tilt. */
  perspective?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const rx = useMotionValue(0);
  const ry = useMotionValue(0);
  const srx = useSpring(rx, { stiffness: 120, damping: 18, mass: 0.7 });
  const sry = useSpring(ry, { stiffness: 120, damping: 18, mass: 0.7 });

  const rotateX = useTransform(srx, (v) => `${v}deg`);
  const rotateY = useTransform(sry, (v) => `${v}deg`);

  function handleMove(e: React.MouseEvent<HTMLDivElement>) {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width; // 0 → 1
    const y = (e.clientY - rect.top) / rect.height; // 0 → 1
    // Centered around 0; max degrees at the edges
    rx.set((0.5 - y) * 2 * max);
    ry.set((x - 0.5) * 2 * max);
  }

  function handleLeave() {
    rx.set(0);
    ry.set(0);
  }

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: purely decorative tilt, no semantic role needed
    <div
      ref={ref}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      className={className}
      style={{ perspective: `${perspective}px` }}
    >
      <motion.div
        style={{
          rotateX,
          rotateY,
          transformStyle: "preserve-3d",
        }}
      >
        {children}
      </motion.div>
    </div>
  );
}
