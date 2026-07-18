'use client';

import { useMemo, useReducer } from 'react';
import { TokenSource } from 'livekit-client';
import { useSession, useSessionContext } from '@livekit/components-react';
import { AgentSessionProvider } from '@/components/agents-ui/agent-session-provider';
import { StartAudioButton } from '@/components/agents-ui/start-audio-button';
import { StudioShell } from '@/components/studio/studio-shell';
import {
  INITIAL_PROJECT_STATE,
  ProjectStateContext,
  type ProjectStore,
  projectStateReducer,
  useLiveKitStateSync,
  useMockDirector,
} from '@/lib/project-state';

interface StudioAppProps {
  /** True when LiveKit env vars are configured — otherwise the mock director runs. */
  liveEnabled: boolean;
  /** Registered agent name for explicit dispatch (agent/src/agent.py). */
  agentName?: string;
}

export function StudioApp({ liveEnabled, agentName }: StudioAppProps) {
  const session = useSession(
    TokenSource.endpoint('/api/token'),
    agentName ? { agentName } : undefined
  );

  return (
    <AgentSessionProvider session={session}>
      <StudioStateBridge liveEnabled={liveEnabled} />
      {liveEnabled && (
        <StartAudioButton
          label="Enable audio"
          className="fixed bottom-52 left-1/2 z-[80] -translate-x-1/2"
        />
      )}
    </AgentSessionProvider>
  );
}

function StudioStateBridge({ liveEnabled }: StudioAppProps) {
  const [state, dispatch] = useReducer(projectStateReducer, INITIAL_PROJECT_STATE);
  const session = useSessionContext();

  // Source (a): agent pushes `state_update` over the LiveKit data channel / RPC.
  useLiveKitStateSync(liveEnabled ? session.room : undefined, dispatch, liveEnabled);
  // Source (b): scripted golden path when there is no backend.
  const mockAgentState = useMockDirector(!liveEnabled, dispatch);

  const store = useMemo<ProjectStore>(
    () => ({ state, dispatch, mode: liveEnabled ? 'live' : 'mock', mockAgentState }),
    [state, liveEnabled, mockAgentState]
  );

  return (
    <ProjectStateContext.Provider value={store}>
      <StudioShell />
    </ProjectStateContext.Provider>
  );
}
