'use client';

import { useMemo, useReducer } from 'react';
import { TokenSource } from 'livekit-client';
import { useSession, useSessionContext } from '@livekit/components-react';
import { AgentSessionProvider } from '@/components/agents-ui/agent-session-provider';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { SetupScreen } from '@/components/studio/setup-screen';
import { StudioShell } from '@/components/studio/studio-shell';
import {
  INITIAL_PROJECT_STATE,
  ProjectStateContext,
  type ProjectStore,
  projectStateReducer,
  useLiveKitStateSync,
} from '@/lib/project-state';

interface StudioAppProps {
  /** True only when LiveKit env is configured. Otherwise we show the setup
   *  screen — never a simulated studio (SPEC §9.5, no fake product). */
  liveEnabled: boolean;
  /** Registered agent name for explicit dispatch (agent/src/agent.py). */
  agentName?: string;
}

export function StudioApp({ liveEnabled, agentName }: StudioAppProps) {
  if (!liveEnabled) {
    return <SetupScreen />;
  }
  return <LiveStudio agentName={agentName} />;
}

function LiveStudio({ agentName }: { agentName?: string }) {
  const session = useSession(
    TokenSource.endpoint('/api/token'),
    agentName ? { agentName } : undefined
  );

  return (
    <AgentSessionProvider session={session}>
      <StudioStateBridge />
      <StartAudioButton
        label="Enable audio"
        className="fixed bottom-52 left-1/2 z-[80] -translate-x-1/2"
      />
    </AgentSessionProvider>
  );
}

function StudioStateBridge() {
  const [state, dispatch] = useReducer(projectStateReducer, INITIAL_PROJECT_STATE);
  const session = useSessionContext();

  // The agent pushes `state_update` over the LiveKit data channel / RPC.
  useLiveKitStateSync(session.room, dispatch, true);

  const store = useMemo<ProjectStore>(() => ({ state, dispatch }), [state]);

  return (
    <ProjectStateContext.Provider value={store}>
      <StudioShell />
    </ProjectStateContext.Provider>
  );
}
