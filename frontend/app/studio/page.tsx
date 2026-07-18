import { StudioApp } from '@/components/studio/studio-app';

export default function StudioPage() {
  // Mock mode is the default whenever LiveKit is not configured (SPEC §6 mock mode).
  const liveEnabled =
    Boolean(
      process.env.LIVEKIT_URL && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET
    ) && process.env.MOCK_MEDIA !== '1';

  // Explicit dispatch: must match the registered name in agent/src/agent.py.
  const agentName = process.env.AGENT_NAME || 'my-agent';

  return <StudioApp liveEnabled={liveEnabled} agentName={agentName} />;
}
