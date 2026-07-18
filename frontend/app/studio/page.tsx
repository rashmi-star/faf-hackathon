import { StudioApp } from '@/components/studio/studio-app';

export default function StudioPage() {
  // Real-only (SPEC §9.5). With LiveKit configured we open a real session;
  // without it we show an honest setup screen — never a simulated studio.
  const liveEnabled = Boolean(
    process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET
  );

  // Explicit dispatch: must match the registered name in agent/src/agent.py.
  const agentName = process.env.AGENT_NAME || 'my-agent';

  return <StudioApp liveEnabled={liveEnabled} agentName={agentName} />;
}
