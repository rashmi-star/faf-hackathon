import Link from 'next/link';

export function Footer() {
  return (
    <footer className="mx-auto w-full max-w-6xl px-5 pt-20 pb-10 md:px-10">
      <div className="flex flex-col gap-10 border-b border-white/10 pb-12 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="font-mono text-xs font-bold tracking-[0.35em] text-white/80 uppercase">
            Director FAL
          </p>
          <p className="mt-3 text-3xl font-extrabold tracking-tight text-white md:text-4xl">
            The editor you talk to.
          </p>
        </div>
        <Link
          href="/studio"
          className="self-start rounded-full bg-[color:var(--ld-accent)] px-7 py-3.5 text-sm font-bold tracking-wide text-black uppercase transition-transform hover:scale-[1.04] active:scale-[0.98] md:self-auto"
        >
          Enter Studio
        </Link>
      </div>
      <div className="flex flex-col gap-2 pt-6 font-mono text-[11px] text-white/35 md:flex-row md:justify-between">
        <span>Built in 72 hours for the fal × Sequoia Video Hackathon</span>
        <span>July 2026 · all media generated with fal + ElevenLabs</span>
      </div>
    </footer>
  );
}
