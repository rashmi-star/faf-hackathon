import { cn } from "@/lib/utils";

export function GlassCard({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("glass rounded-[var(--radius-lg)] p-8", className)}>{children}</div>;
}
