# scripts/

Developer utilities. None of these require cloud keys.

## `state_demo.py` — prove live mode with zero cloud keys

Drives the studio frontend's **live** LiveKit path end-to-end on your laptop:
a local `livekit-server` replaces LiveKit Cloud, and this script replaces the
Python agent — it joins the browser's room and replays the SPEC §2 golden path
(same timings and payloads as the frontend mock director) on the
`state_update` data topic.

No FAL, Anthropic, ElevenLabs, or Deepgram keys. No LiveKit Cloud account.

### 1. Install and start a local LiveKit server

```sh
brew install livekit
livekit-server --dev
```

`--dev` listens on `ws://localhost:7880` with the fixed credentials
`devkey` / `secret`. Leave it running.

### 2. Point the frontend at it

Create (or edit) `frontend/.env.local`:

```sh
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
```

Important: `MOCK_MEDIA` must be **unset** (or not `1`) — `MOCK_MEDIA=1` forces
the studio into mock mode and it will ignore LiveKit entirely.

Then start the frontend:

```sh
cd frontend && pnpm install && pnpm dev
```

### 3. Connect the browser

Open <http://localhost:3000/studio> and click the talk orb ("Tap to talk").
Allow microphone access (the mic is only used to establish the session; this
demo never listens to it). The browser mints a token via `/api/token` and
joins a fresh `voice_assistant_room_*` room on your local server.

### 4. Run the demo script

From the repo root (reuses the agent's Python environment):

```sh
cd agent && uv sync && cd ..          # first time only
uv run --project agent python scripts/state_demo.py
```

The script polls the local server until the browser's room exists, joins it as
an agent-kind participant, and plays the ~80-second golden path. Useful flags:

| Flag | Effect |
|---|---|
| `--speed 2` | play twice as fast (any float) |
| `--loop` | replay forever, like the landing-page mock loop |
| `--room NAME` | skip discovery and join/create a specific room |
| `--url` / `--api-key` / `--api-secret` | override the `livekit-server --dev` defaults (also read from `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET`) |

### What you should see

In the studio tab, in order:

1. Transcript streams the brainstorm ("What are we making today?" …).
2. Character cards for Maya and James appear, then flip to approved.
3. Four shot blocks land on the timeline and progress
   `planned → still → rendering → ready`, stills filling in one by one.
4. The magic moment: the 15–20s timeline range highlights instantly, shot 3
   flips to `replacing`, then returns `ready` with the new line.
5. Export cards for 16:9, 9:16, 1:1, and loop appear.

The talk orb also tracks the director's listening / thinking / speaking states
and captions each spoken line.

### Troubleshooting

- **"LiveKit server not reachable"** — `livekit-server --dev` isn't running
  (or `LIVEKIT_URL` points somewhere else).
- **"Waiting for a browser room" forever** — the studio tab isn't connected:
  make sure you clicked the orb and that `frontend/.env.local` has the three
  LiveKit values above (restart `pnpm dev` after editing it).
- **Studio shows the mock director instead of connecting** — `MOCK_MEDIA=1`
  is set, or the LiveKit env vars are missing; live mode requires all three.

## `fetch_fonts.sh`

Downloads the Inter typeface (OFL) into `agent/assets/fonts/` for burned-in
text rendering by the edit engine. Idempotent; see the script header.
