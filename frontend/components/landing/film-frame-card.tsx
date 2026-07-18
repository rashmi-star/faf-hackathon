import { cn } from '@/lib/shadcn/utils';

interface FilmFrameCardProps {
  /** Frame number, e.g. "01". */
  kicker: string;
  /** Beat name, e.g. "TALK". */
  name: string;
  title: string;
  body: string;
  /** Two stills, stacked like consecutive frames on a strip. */
  images: readonly [string, string];
  className?: string;
}

/**
 * A 35mm film-strip card (adapted from reference-landing/glass-card.tsx):
 * sprocket-hole rails down both edges, two stacked frames, and a
 * contact-sheet caption underneath.
 */
export function FilmFrameCard({
  kicker,
  name,
  title,
  body,
  images,
  className,
}: FilmFrameCardProps) {
  return (
    <div
      className={cn(
        'flex overflow-hidden rounded-2xl border border-white/10 bg-[color:var(--ld-surface)]',
        'shadow-[0_24px_60px_-24px_rgba(0,0,0,0.8)]',
        className
      )}
    >
      <div aria-hidden className="ld-rail w-4 shrink-0 sm:w-5" />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between px-4 pt-4 pb-3 font-mono text-[10px] tracking-[0.25em] text-white/45 uppercase">
          <span>Frame {kicker}</span>
          <span className="text-[color:var(--ld-accent)]">{name}</span>
        </div>
        <div className="flex flex-col gap-1.5 bg-black px-1.5 py-1.5">
          {images.map((src) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={src}
              src={src}
              alt=""
              loading="lazy"
              className="aspect-video w-full rounded-sm object-cover"
            />
          ))}
        </div>
        <div className="flex flex-1 flex-col gap-2 px-4 pt-4 pb-5">
          <h3 className="text-lg font-bold tracking-tight text-white">{title}</h3>
          <p className="text-sm leading-relaxed text-white/60">{body}</p>
        </div>
      </div>
      <div aria-hidden className="ld-rail w-4 shrink-0 sm:w-5" />
    </div>
  );
}
