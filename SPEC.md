# Director FAL — Build Spec (single source of truth)

> The video editor you talk to. Voice-directed AI video creation and editing.
> Built for the fal x Sequoia 72-Hour Video Hackathon (Developer Track), July 17-19, 2026.
> Working name: **Director FAL** (alt considered: Falsetto). Tagline: "The editor you talk to."

## 0. Non-negotiable context

- **Deadline:** submission Sunday July 19, 9:00 AM PT (repo + max 3-minute demo video).
- **Judging:** technical execution 35%, creativity 25%, user value 25%, demo 15%.
- **Scope law:** ONE happy path, demoed in a desktop browser (Chrome). Mobile is shown via
  responsive layout at iPhone 15 Pro Max viewport in devtools. No auth, no accounts, no
  multi-project, no undo stack, no edge-case handling. If it does not appear in the
  3-minute demo, it does not get built.
- **Hackathon rule — new work only:** all shipped code/assets must be created during the
  hackathon. Anything adapted from prior work (see §8 asset provenance) is a temporary
  placeholder and MUST be regenerated via fal/ElevenLabs before submission.

## 1. The product in one paragraph

You open the studio and talk. The agent brainstorms a story with you, generates your
characters (images you approve), locks the scene, then produces a 20-30 second video.
You watch it, then direct changes with your voice: "around 15 seconds, she should say
'I really love you' instead, and he's happy about it." The timeline highlights the
segment instantly, the agent re-renders that segment (new ElevenLabs line + fal lipsync/
regen), and the fix drops into place. Say "export" and you get every format: 16:9
YouTube, 9:16 Reels/Shorts, 1:1, plus an 8s loop. Positioning: this scales to full
films; the demo shows 20-30 seconds.

## 2. Golden-path flow (this IS the demo script)

1. **Landing page** (cinematic, animated) → click "Enter Studio" (no auth).
2. Studio opens: editor-style UI. Agent greets by voice: "What are we making today?"
3. **Brainstorm:** user talks through an idea; agent riffs, they agree on a story
   (demo story: a couple at the Golden Gate Bridge; she says "I really hate you"
   angrily; he is heartbroken).
4. **Characters:** agent generates 2 character portraits (fal image model), shows them
   as cards; user approves by voice. Agent stores a character sheet (appearance +
   personality) used in every later generation for consistency.
5. **Scene:** agent confirms scenery ("golden hour, Golden Gate Bridge, cinematic").
6. **Generate:** agent creates a shot plan (3-4 shots ≈ 20-30s total), renders
   storyboard stills instantly, then renders video clips in the background while
   narrating progress; assembles the timeline.
7. **Voice edit (the magic moment):** user: "Around 15 seconds — change 'I really hate
   you' to 'I really love you', and he's very happy." → timeline segment highlights
   INSTANTLY → agent regenerates: new ElevenLabs line + lipsync (or segment re-render
   with the happy expression) → updated clip swaps in.
8. **Export:** user says "export" → fal ffmpeg compose emits 16:9 / 9:16 / 1:1 (+ 8s
   loop). Download cards appear.
9. Live transcript of the whole conversation is visible throughout.

## 3. Architecture

```
frontend/   Next.js (base: livekit-examples/agent-starter-react)
agent/      Python LiveKit agent (base: livekit-examples/agent-starter-python)
```

- **Transport:** LiveKit Cloud (free Build tier). Browser joins a room; the Python
  agent joins the same room. Frontend mints tokens via its API route.
- **Voice pipeline (agent/):** LiveKit AgentSession — STT (Deepgram or ElevenLabs
  Scribe) → LLM (fal OpenRouter, tool calling) → TTS (ElevenLabs Flash v2.5,
  user's Pro key). Async function tools keep the agent talking during renders.
- **Agent → UI sync:** LiveKit RPC / data messages. The agent pushes `state_update`
  events (timeline JSON, highlights, character cards, render status, export links).
  Frontend is a pure renderer of that state. Frontend may also send RPC (e.g. playhead
  position) but voice is the primary input.
- **Media:** all generation via fal (`fal_client`, queue API + polling). ElevenLabs
  REST for TTS lines, music, SFX. fal CDN is file storage; no DB — a single in-memory
  project state in the agent process, mirrored to `project_state.json` for crash
  recovery.

## 4. Project state (the one data structure)

```jsonc
{
  "phase": "brainstorm | characters | scene | generating | review | exporting",
  "story": {"logline": "...", "scene": "...", "style": "cinematic ..."},
  "characters": [
    {"id": "her", "name": "...", "sheet": "appearance + personality prompt",
     "image_url": "...", "approved": true}
  ],
  "shots": [
    {"id": "s1", "start": 0.0, "end": 8.0, "prompt": "...", "dialogue": null,
     "still_url": "...", "video_url": "...",
     "status": "planned | still | rendering | ready | replacing"}
  ],
  "highlight": {"start": 15.0, "end": 20.0} ,   // or null
  "exports": [{"format": "16:9", "url": "..."}],
  "transcript": [{"role": "user|agent", "text": "...", "ts": 0}]
}
```

## 5. Agent tools (LLM function-calling surface)

| Tool | What it does |
|---|---|
| `set_story(logline, scene, style)` | lock brainstorm result, advance phase |
| `create_character(name, sheet)` | fal image gen portrait → character card in UI |
| `plan_shots(shots[])` | write shot plan, render stills for all (fast image model) |
| `render_all()` | async: video-gen each shot (image-to-video from its still), narrate progress, assemble timeline |
| `highlight(start, end)` | instant UI highlight of a time range |
| `replace_segment(shot_id, new_prompt?, new_dialogue?)` | async: re-render one shot; if only dialogue changed, prefer ElevenLabs TTS + fal lipsync on existing clip |
| `export(formats[])` | fal ffmpeg compose → 16:9, 9:16, 1:1, loop |
| `show_status()` | speak current render queue state |

Rules: every tool immediately emits `state_update`. Long tools are async with spoken
progress. The agent never renders video without the user having approved the
storyboard/characters (preview-before-spend).

## 6. fal model plan (finalize in first pipeline session once FAL_KEY works)

- Stills/characters: `fal-ai/flux/schnell` (speed) or `flux-2` (quality) — test both.
- Video: image-to-video, candidates: Kling (quality), Seedance/LTX turbo (speed).
  Pick ONE after a 3-prompt bake-off; budget ~$100 total, so demo assets get
  pre-generated and cached.
- Lipsync: `fal-ai/sync-lipsync` (Sync Labs 2.0).
- Assembly/exports: `fal-ai/ffmpeg-api/compose` (+ `merge-audio-video`).
- Upscale (only if time): Topaz.
- **Mock mode:** when `FAL_KEY` is absent or `MOCK_MEDIA=1`, every media call returns
  bundled placeholder assets instantly, so UI/voice dev never blocks on credits.

## 7. Frontend spec

**Landing (`/`)** — cinematic and animated; the bar is "video people should love it":
full-bleed background video hero, bold typography, 3D tilt cards (film-frame styled),
smooth scroll (lenis), sections: hero → "how it works" (3 beats: Talk. Watch. Ship.) →
live demo teaser (3-5s clip) → footer. CTA: "Enter Studio" → `/studio`.

**Studio (`/studio`)** — looks like real editing software (dark, pro):
- Center: video preview player.
- Bottom: timeline strip with time ruler, shot blocks (color by status), playhead,
  highlight overlay (flashes on `highlight`).
- Right panel: transcript (live) + character cards + export cards.
- Floating: mic/talk orb with audio-level visualization, agent state
  (listening/thinking/speaking), captions of agent speech.
- Responsive breakpoint tuned for iPhone 15 Pro Max width (~430px): preview stacks,
  timeline scrolls horizontally, orb bottom-center.

## 8. Asset provenance (hackathon compliance)

Placeholder art may be adapted from `/Users/anirudh/Desktop/stripe-hack` (own prior
work) ONLY during development. Before submission: regenerate all landing imagery/video
via fal (great story: "every pixel on our landing page is fal-generated") and delete
the placeholders. Track them in `frontend/PLACEHOLDERS.md`.

## 9. Env vars

```
# agent/.env.local          # frontend/.env.local
LIVEKIT_URL=                LIVEKIT_URL=
LIVEKIT_API_KEY=            LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=         LIVEKIT_API_SECRET=
ANTHROPIC_API_KEY=
ELEVENLABS_API_KEY=
FAL_KEY=
DEEPGRAM_API_KEY=           # or use ElevenLabs Scribe STT
MOCK_MEDIA=1                # dev default until keys arrive
```

## 9.5 NO FAKE PRODUCT (hard rule, added Jul 18)

The shipped experience is REAL ONLY. Anyone cloning the repo runs the actual
product or is told plainly what's missing — never a simulation.

- `/studio` has exactly one mode: a real LiveKit session driving the real agent.
  If required env is missing, render an honest **setup screen** (which vars are
  missing, copy-paste .env.local blocks, run commands) — NOT a mock studio.
- The scripted golden-path content and any keyword/mock "brain" live ONLY in
  test harnesses (`scripts/state_demo.py`, agent REPL, pytest) — never reachable
  from the website UI. No "demo mode" buttons in the product.
- `MOCK_MEDIA` in the agent is a dev/test switch, OFF by default, documented as
  dev-only. Default behavior with keys present = real fal/ElevenLabs calls.
- The typed-direction input stays — but it feeds the REAL agent session (text
  chat to the same brain), not a mock.

## 10. Character Reference Sheets (first-class feature)

When the director casts a character it produces a CHARACTER SHEET, not a lone
portrait — modeled on professional animation/film character bibles (user-provided
references: photoreal investigator sheet, stylized "Nimble Quillwright" sheet):

- **Sheet contents:** identity block (name, role, age, personality, core theme),
  turnaround (front / 3-4 / side / back), expression grid (6-8 emotions),
  color palette swatches, 1-2 detail crops (wardrobe/prop), silhouette, notes.
- **Generation:** fal image model with a consistent seed/reference chain; the sheet
  IS the consistency backbone — every shot render passes the character's sheet
  image(s) + sheet text as reference so faces/wardrobe hold across shots.
  (Sponsor-aligned: fal publicly pushes character sheets as production assets.)
- **Studio UI:** Cast tab renders sheets like a pro reference document (tabs or
  expandable card: turnaround strip, expression grid, palette chips, notes),
  typography clean and editorial — never a bare image dump.
- **Mock mode:** one pre-built sheet layout per character using placeholder art.
- **Export:** sheets are downloadable artifacts alongside the film (judges love
  inspectable intermediates).

**Landing showcase card:** one 3D-tilt card featuring a looping character-action
video with small reference-sheet thumbnails beside it ("Cast characters that stay
consistent — the director keeps a bible for every face"). Dev placeholder:
`/placeholders/reference-character-video.mp4` (third-party, MUST be replaced with
our own fal-generated clip before submission — see PLACEHOLDERS.md).

## 11. Milestones

- **M1 Scaffold (tonight):** repo, frontend base builds, agent base runs, studio UI
  shell with mock state, landing v1.
- **M2 Voice loop:** talk to agent in browser, transcript streams, `highlight` works
  end-to-end (the instant-highlight moment).
- **M3 Pipeline:** real fal + ElevenLabs calls behind the tools; character → stills →
  video → assemble; lipsync replace; exports.
- **M4 Polish + demo:** landing polish, regenerate placeholder art via fal, record the
  3-minute demo, README for judges, submit by Sat night buffer (NOT Sunday 8:59).
