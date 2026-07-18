'use client';

import { useEffect, useState } from 'react';
import { Track } from 'livekit-client';
import { AnimatePresence, motion } from 'motion/react';
import {
  type AgentState,
  useAgent,
  useMultibandTrackVolume,
  useSessionContext,
  useSessionMessages,
  useTrackToggle,
} from '@livekit/components-react';
import { MicrophoneSlashIcon } from '@phosphor-icons/react/dist/ssr';
import { useProjectState } from '@/lib/project-state';
import { cn } from '@/lib/shadcn/utils';

const BAR_COUNT = 7;

const STATE_LABELS: Partial<Record<AgentState, string>> = {
  disconnected: 'Tap to talk',
  connecting: 'Connecting',
  'pre-connect-buffering': 'Listening',
  initializing: 'Warming up',
  idle: 'Tap to talk',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
  failed: 'Agent unavailable',
};

/** Fake audio levels for mock mode — a sine/noise blend that looks like speech. */
function useMockBands(active: boolean): number[] {
  const [bands, setBands] = useState<number[]>(() => new Array(BAR_COUNT).fill(0));

  useEffect(() => {
    if (!active) {
      setBands(new Array(BAR_COUNT).fill(0));
      return;
    }
    let raf: number;
    const start = performance.now();
    const tick = (now: number) => {
      const e = (now - start) / 1000;
      setBands(
        Array.from({ length: BAR_COUNT }, (_, i) => {
          const wave = Math.abs(Math.sin(e * (2.6 + i * 0.9) + i * 1.3));
          const envelope = 0.35 + 0.65 * Math.abs(Math.sin(e * 1.8 + 0.5));
          return wave * envelope;
        })
      );
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active]);

  return bands;
}

function OrbBars({ bands, active }: { bands: number[]; active: boolean }) {
  return (
    <div className="flex h-6 items-center gap-[3px]">
      {bands.map((band, i) => (
        <div
          key={i}
          className={cn(
            'w-[3px] rounded-full bg-white transition-[height] duration-75',
            !active && 'opacity-60'
          )}
          style={{ height: `${Math.max(15, Math.min(100, band * 100))}%` }}
        />
      ))}
    </div>
  );
}

export function TalkOrb() {
  const { state, mode, mockAgentState } = useProjectState();
  const session = useSessionContext();
  const agent = useAgent();
  const { messages } = useSessionMessages(session);
  const micToggle = useTrackToggle({ source: Track.Source.Microphone });
  const [mockMicEnabled, setMockMicEnabled] = useState(true);

  const agentState: AgentState = mode === 'live' ? agent.state : mockAgentState;
  const isSpeaking = agentState === 'speaking';
  const micEnabled = mode === 'live' ? micToggle.enabled : mockMicEnabled;

  // Visualize agent speech when speaking, otherwise the user's mic level.
  const liveBands = useMultibandTrackVolume(
    isSpeaking ? agent.microphoneTrack : session.local.microphoneTrack,
    { bands: BAR_COUNT, loPass: 100, hiPass: 200 }
  );
  const mockBands = useMockBands(mode === 'mock' && isSpeaking);
  const bands = mode === 'live' ? liveBands : mockBands;

  const caption =
    mode === 'live'
      ? [...messages].reverse().find((m) => !m.from?.isLocal)?.message
      : [...state.transcript].reverse().find((t) => t.role === 'agent')?.text;

  const handleClick = async () => {
    if (mode === 'mock') {
      setMockMicEnabled((v) => !v);
      return;
    }
    if (!session.isConnected) {
      await session.start({
        tracks: {
          microphone: { enabled: true },
          camera: { enabled: false },
          screenShare: { enabled: false },
        },
      });
      return;
    }
    await micToggle.toggle();
  };

  return (
    <div className="pointer-events-none fixed bottom-[10.5rem] left-1/2 z-[70] flex -translate-x-1/2 flex-col items-center gap-2 md:right-8 md:bottom-[12.5rem] md:left-auto md:translate-x-0 md:items-end">
      {/* captions of agent speech */}
      <AnimatePresence>
        {isSpeaking && caption && (
          <motion.div
            key="caption"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.25, ease: 'easeOut' as const }}
            className="max-w-[19rem] rounded-xl border border-white/10 bg-zinc-900/95 px-3 py-2 shadow-xl backdrop-blur"
          >
            <p className="mb-0.5 font-mono text-[9px] font-bold tracking-widest text-amber-300 uppercase">
              Director
            </p>
            <p className="text-xs leading-relaxed text-zinc-200">{caption}</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* the orb */}
      <motion.button
        type="button"
        onClick={handleClick}
        aria-label={micEnabled ? 'Mute microphone' : 'Unmute microphone'}
        animate={
          isSpeaking
            ? { scale: [1, 1.06, 1] }
            : agentState === 'listening'
              ? { scale: [1, 1.02, 1] }
              : { scale: 1 }
        }
        transition={{
          duration: isSpeaking ? 0.9 : 2.4,
          repeat: Infinity,
          ease: 'easeInOut' as const,
        }}
        className={cn(
          'pointer-events-auto relative flex size-16 items-center justify-center rounded-full shadow-2xl transition-colors',
          'bg-gradient-to-br from-amber-400 via-orange-500 to-rose-600',
          agentState === 'thinking' && 'from-sky-400 via-indigo-500 to-violet-600'
        )}
      >
        {/* state ring */}
        <span
          className={cn(
            'absolute -inset-1 rounded-full border-2',
            isSpeaking && 'animate-ping border-amber-300/60',
            agentState === 'listening' && 'animate-pulse border-white/30',
            agentState === 'thinking' && 'animate-spin border-sky-300/60 border-t-transparent',
            !['speaking', 'listening', 'thinking'].includes(agentState) && 'border-white/15'
          )}
        />
        <span className="absolute inset-1 rounded-full bg-zinc-950/35" />
        <span className="relative">
          {micEnabled ? (
            <OrbBars bands={bands} active={isSpeaking} />
          ) : (
            <MicrophoneSlashIcon weight="fill" className="size-6 text-white" />
          )}
        </span>
      </motion.button>

      {/* state label */}
      <span className="rounded-full bg-zinc-950/80 px-2.5 py-0.5 font-mono text-[9px] font-bold tracking-widest text-zinc-300 uppercase">
        {micEnabled ? (STATE_LABELS[agentState] ?? agentState) : 'Muted'}
      </span>
    </div>
  );
}
