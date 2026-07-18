'use client';

import { type Dispatch, createContext, useContext, useEffect, useState } from 'react';
import {
  type DataPacket_Kind,
  type RemoteParticipant,
  type Room,
  RoomEvent,
  type RpcInvocationData,
} from 'livekit-client';
import type { AgentState } from '@livekit/components-react';

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

export type StudioMode = 'live' | 'mock';

export interface ProjectStore {
  state: ProjectState;
  dispatch: Dispatch<ProjectAction>;
  mode: StudioMode;
  /** Agent state driven by the mock director. In live mode, read useAgent() instead. */
  mockAgentState: AgentState;
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

// ---------------------------------------------------------------------------
// Source (b): mock director — walks the golden path on a timer (SPEC §2)
// ---------------------------------------------------------------------------

const P = '/placeholders';
const MOCK_VIDEO = `${P}/hero-video-bg.mp4`;

const MOCK_STORY: Story = {
  logline: 'A couple at the Golden Gate Bridge — one line changes everything.',
  scene: 'Golden hour at the Golden Gate Bridge, wind off the bay',
  style: 'cinematic 35mm, warm backlight, shallow depth of field',
};

const MOCK_CHARACTERS: Character[] = [
  {
    id: 'her',
    name: 'Maya',
    sheet: 'Late 20s, windswept dark hair, denim jacket. Fierce, wounded, decisive.',
    image_url: `${P}/hero-modern-left.jpg`,
    approved: false,
  },
  {
    id: 'him',
    name: 'James',
    sheet: 'Early 30s, wool coat, open face. Earnest, easily broken, wears his heart.',
    image_url: `${P}/hero-modern-right.jpg`,
    approved: false,
  },
];

const MOCK_SHOTS: Shot[] = [
  {
    id: 's1',
    start: 0,
    end: 7,
    prompt: 'Wide establishing: golden hour, Golden Gate Bridge, couple silhouetted at the rail',
    dialogue: null,
    still_url: null,
    video_url: null,
    status: 'planned',
  },
  {
    id: 's2',
    start: 7,
    end: 13,
    prompt: 'Close on Maya, wind in her hair, jaw set, bay glittering behind',
    dialogue: null,
    still_url: null,
    video_url: null,
    status: 'planned',
  },
  {
    id: 's3',
    start: 13,
    end: 20,
    prompt: 'Two-shot at the rail: Maya turns and delivers the line, James takes it',
    dialogue: 'I really hate you.',
    still_url: null,
    video_url: null,
    status: 'planned',
  },
  {
    id: 's4',
    start: 20,
    end: 26,
    prompt: 'James alone at the rail, heartbroken, city lights flickering on',
    dialogue: null,
    still_url: null,
    video_url: null,
    status: 'planned',
  },
];

const MOCK_STILLS: Record<string, string> = {
  s1: `${P}/hero-kingdom-left.jpg`,
  s2: `${P}/hero-modern-left.jpg`,
  s3: `${P}/hero-modern-right.jpg`,
  s4: `${P}/hero-rock-right.jpg`,
};

const MOCK_EXPORTS: ExportItem[] = [
  { format: '16:9', url: MOCK_VIDEO },
  { format: '9:16', url: MOCK_VIDEO },
  { format: '1:1', url: MOCK_VIDEO },
  { format: 'loop', url: MOCK_VIDEO },
];

interface MockStep {
  /** ms after the previous step */
  delay: number;
  agentState?: AgentState;
  apply?: (state: ProjectState, ts: number) => Partial<ProjectState>;
}

function say(role: TranscriptEntry['role'], text: string) {
  return (state: ProjectState, ts: number): Partial<ProjectState> => ({
    transcript: [...state.transcript, { role, text, ts }],
  });
}

function patchShot(id: string, patch: Partial<Shot>) {
  return (state: ProjectState): Partial<ProjectState> => ({
    shots: state.shots.map((shot) => (shot.id === id ? { ...shot, ...patch } : shot)),
  });
}

export const MOCK_SCRIPT: MockStep[] = [
  // brainstorm
  { delay: 1200, agentState: 'speaking', apply: say('agent', 'What are we making today?') },
  { delay: 2400, agentState: 'listening' },
  {
    delay: 1400,
    apply: say(
      'user',
      'A couple at the Golden Gate Bridge at sunset. She tells him she hates him — and it breaks his heart.'
    ),
  },
  { delay: 700, agentState: 'thinking' },
  {
    delay: 1400,
    agentState: 'speaking',
    apply: say(
      'agent',
      'Love it. Golden hour, wind off the bay, one brutal line. Sketching your leads now.'
    ),
  },
  { delay: 400, apply: () => ({ phase: 'characters', story: MOCK_STORY }) },
  // characters appear
  { delay: 1800, apply: () => ({ characters: MOCK_CHARACTERS }) },
  { delay: 1200, apply: say('agent', 'Meet Maya and James. Should I lock them in?') },
  { delay: 2200, agentState: 'listening' },
  { delay: 1300, apply: say('user', 'Yes — they are perfect.') },
  { delay: 800, agentState: 'thinking' },
  {
    delay: 900,
    agentState: 'speaking',
    apply: (state) => ({
      phase: 'scene',
      characters: state.characters.map((c) => ({ ...c, approved: true })),
    }),
  },
  {
    delay: 200,
    apply: say('agent', 'Locked. Scene: golden hour on the Golden Gate Bridge, cinematic 35mm.'),
  },
  // shot plan
  { delay: 2200, apply: () => ({ phase: 'generating', shots: MOCK_SHOTS }) },
  {
    delay: 300,
    agentState: 'speaking',
    apply: say('agent', 'Here is the shot plan — four shots, twenty-six seconds. Boarding it now.'),
  },
  // stills
  { delay: 1500, apply: patchShot('s1', { status: 'still', still_url: MOCK_STILLS.s1 }) },
  { delay: 700, apply: patchShot('s2', { status: 'still', still_url: MOCK_STILLS.s2 }) },
  { delay: 700, apply: patchShot('s3', { status: 'still', still_url: MOCK_STILLS.s3 }) },
  { delay: 700, apply: patchShot('s4', { status: 'still', still_url: MOCK_STILLS.s4 }) },
  {
    delay: 1000,
    agentState: 'speaking',
    apply: say('agent', 'Storyboard is up. Rendering all four shots — talk to me while I work.'),
  },
  // renders
  { delay: 800, apply: patchShot('s1', { status: 'rendering' }) },
  { delay: 600, apply: patchShot('s2', { status: 'rendering' }) },
  { delay: 600, apply: patchShot('s3', { status: 'rendering' }) },
  { delay: 600, apply: patchShot('s4', { status: 'rendering' }) },
  { delay: 2600, apply: patchShot('s1', { status: 'ready', video_url: MOCK_VIDEO }) },
  { delay: 2200, apply: patchShot('s2', { status: 'ready', video_url: MOCK_VIDEO }) },
  { delay: 2000, apply: patchShot('s3', { status: 'ready', video_url: MOCK_VIDEO }) },
  { delay: 2200, apply: patchShot('s4', { status: 'ready', video_url: MOCK_VIDEO }) },
  { delay: 900, apply: () => ({ phase: 'review' }) },
  {
    delay: 200,
    agentState: 'speaking',
    apply: say('agent', 'First cut is assembled — twenty-six seconds. Take a look.'),
  },
  // the magic moment: voice edit
  { delay: 3200, agentState: 'listening' },
  {
    delay: 2400,
    apply: say(
      'user',
      "Around 15 seconds — change 'I really hate you' to 'I really love you', and he's very happy about it."
    ),
  },
  { delay: 700, apply: () => ({ highlight: { start: 15, end: 20 } }) },
  {
    delay: 300,
    agentState: 'speaking',
    apply: say('agent', 'Got it — re-cutting that beat with the new line.'),
  },
  { delay: 500, apply: patchShot('s3', { status: 'replacing' }) },
  {
    delay: 3800,
    apply: patchShot('s3', {
      status: 'ready',
      dialogue: 'I really love you.',
      video_url: MOCK_VIDEO,
    }),
  },
  { delay: 300, apply: () => ({ highlight: null }) },
  {
    delay: 300,
    agentState: 'speaking',
    apply: say('agent', 'Done — new line, new reaction, dropped straight into place.'),
  },
  // export
  { delay: 2600, agentState: 'listening' },
  { delay: 1600, apply: say('user', 'Export it.') },
  { delay: 800, agentState: 'thinking' },
  { delay: 600, apply: () => ({ phase: 'exporting' }) },
  { delay: 300, agentState: 'speaking', apply: say('agent', 'Exporting every format now.') },
  { delay: 2600, apply: () => ({ exports: MOCK_EXPORTS }) },
  {
    delay: 400,
    agentState: 'speaking',
    apply: say('agent', 'All formats ready — YouTube, Reels, square, and a loop. That is a wrap.'),
  },
  { delay: 3000, agentState: 'listening' },
  // hold on the finished project, then loop
  { delay: 12000 },
];

/**
 * Runs the scripted golden path against the store on a timer. Loops forever.
 * Returns the simulated agent state for the talk orb.
 */
export function useMockDirector(enabled: boolean, dispatch: Dispatch<ProjectAction>): AgentState {
  const [agentState, setAgentState] = useState<AgentState>('connecting');

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let index = 0;
    let elapsed = 0;
    setAgentState('initializing');

    const runStep = () => {
      if (cancelled) return;
      const step = MOCK_SCRIPT[index];
      elapsed += step.delay;
      if (step.agentState) setAgentState(step.agentState);
      if (step.apply) {
        const apply = step.apply;
        const ts = Math.round(elapsed / 1000);
        dispatch({ type: 'apply', fn: (state) => apply(state, ts) });
      }
      index += 1;
      if (index >= MOCK_SCRIPT.length) {
        index = 0;
        elapsed = 0;
        dispatch({ type: 'reset' });
      }
      timer = setTimeout(runStep, MOCK_SCRIPT[index].delay);
    };

    timer = setTimeout(runStep, MOCK_SCRIPT[0].delay);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [enabled, dispatch]);

  return agentState;
}
