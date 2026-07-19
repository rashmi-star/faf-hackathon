'use client';

import { type Dispatch, createContext, useContext, useEffect } from 'react';
import {
  type DataPacket_Kind,
  type RemoteParticipant,
  type Room,
  RoomEvent,
  type RpcInvocationData,
} from 'livekit-client';

// ---------------------------------------------------------------------------
// SPEC §4 — the one data structure
// ---------------------------------------------------------------------------

export type Phase = 'brainstorm' | 'characters' | 'scene' | 'generating' | 'review' | 'exporting';

export type ShotStatus = 'planned' | 'still' | 'rendering' | 'ready' | 'replacing';

export interface Story {
  logline: string;
  scene: string;
  style: string;
}

export interface Character {
  id: string;
  name: string;
  sheet: string;
  image_url: string;
  approved: boolean;
  // Reference-sheet fields (SPEC §10). Present when the agent generates a full
  // character bible; the Cast tab degrades gracefully when they are empty.
  role?: string;
  age?: string;
  personality?: string[];
  palette?: string[];
  turnaround_urls?: string[];
  expression_urls?: string[];
  notes?: string[];
}

export interface Shot {
  id: string;
  start: number;
  end: number;
  prompt: string;
  dialogue: string | null;
  still_url: string | null;
  video_url: string | null;
  status: ShotStatus;
}

export interface Highlight {
  start: number;
  end: number;
}

export interface ExportItem {
  format: string;
  url: string;
}

export interface TranscriptEntry {
  role: 'user' | 'agent';
  text: string;
  ts: number;
}

export interface ProjectState {
  phase: Phase;
  story: Story | null;
  characters: Character[];
  shots: Shot[];
  highlight: Highlight | null;
  exports: ExportItem[];
  transcript: TranscriptEntry[];
  /** Assembled master cut, published by the agent after render_all/replace_segment. */
  timeline_url?: string;
  /** Public music source published by the agent for browser preview. */
  music_url?: string;
  timeline?: {
    duration: number;
    music: { src: string; gain_db: number; duck_under_dialogue: boolean } | null;
  };
}

export const INITIAL_PROJECT_STATE: ProjectState = {
  phase: 'brainstorm',
  story: null,
  characters: [],
  shots: [],
  highlight: null,
  exports: [],
  transcript: [],
};

// ---------------------------------------------------------------------------
// Store (reducer + context)
// ---------------------------------------------------------------------------

export type ProjectAction =
  | { type: 'merge'; patch: Partial<ProjectState> }
  | { type: 'apply'; fn: (state: ProjectState) => Partial<ProjectState> }
  | { type: 'reset' };

export function projectStateReducer(state: ProjectState, action: ProjectAction): ProjectState {
  switch (action.type) {
    case 'merge':
      return { ...state, ...action.patch };
    case 'apply':
      return { ...state, ...action.fn(state) };
    case 'reset':
      return INITIAL_PROJECT_STATE;
  }
}

export interface ProjectStore {
  state: ProjectState;
  dispatch: Dispatch<ProjectAction>;
}

export const ProjectStateContext = createContext<ProjectStore | null>(null);

export function useProjectState(): ProjectStore {
  const ctx = useContext(ProjectStateContext);
  if (!ctx) {
    throw new Error('useProjectState must be used within a ProjectStateContext.Provider');
  }
  return ctx;
}

// ---------------------------------------------------------------------------
// Source (a): LiveKit data-channel / RPC listener for `state_update`
// ---------------------------------------------------------------------------

export const STATE_UPDATE_TOPIC = 'state_update';

export function useLiveKitStateSync(
  room: Room | undefined,
  dispatch: Dispatch<ProjectAction>,
  enabled: boolean
) {
  useEffect(() => {
    if (!enabled || !room) return;

    const decoder = new TextDecoder();
    const applyPayload = (raw: string) => {
      try {
        dispatch({ type: 'merge', patch: JSON.parse(raw) as Partial<ProjectState> });
      } catch (error) {
        console.error('Failed to parse state_update payload', error);
      }
    };

    const onData = (
      payload: Uint8Array,
      _participant?: RemoteParticipant,
      _kind?: DataPacket_Kind,
      topic?: string
    ) => {
      if (topic !== STATE_UPDATE_TOPIC) return;
      applyPayload(decoder.decode(payload));
    };

    room.on(RoomEvent.DataReceived, onData);
    try {
      room.registerRpcMethod(STATE_UPDATE_TOPIC, async (data: RpcInvocationData) => {
        applyPayload(data.payload);
        return 'ok';
      });
    } catch {
      // already registered (hot reload) — data channel listener still active
    }

    return () => {
      room.off(RoomEvent.DataReceived, onData);
      try {
        room.unregisterRpcMethod(STATE_UPDATE_TOPIC);
      } catch {
        // room already torn down
      }
    };
  }, [room, dispatch, enabled]);
}
