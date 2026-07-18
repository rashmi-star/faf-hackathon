# frontend/ structure map (for builders)

Base: `livekit-examples/agent-starter-react` — Next.js 15 App Router, React 19, TypeScript strict, Tailwind CSS v4.

## Build / dev commands

- Package manager: **pnpm 9.15.9** (declared in `package.json#packageManager`).
- IMPORTANT: the global `pnpm` shim on this machine is a broken corepack shim. Use
  **`npx -y pnpm@9.15.9 <cmd>`** instead. The build that passed:
  - `cd frontend && npx -y pnpm@9.15.9 build`
- Other scripts: `dev` (next dev --turbopack), `lint`, `format`.

## Routing (app/)

- `app/page.tsx` — the ONLY page today. Server component; loads `AppConfig` via
  `getAppConfig()` and renders `<App/>` (the LiveKit session UI). Per SPEC this
  becomes the landing page; studio goes to a new `app/studio/page.tsx`.
- `app/layout.tsx` — root layout. Loads fonts (Google `Public_Sans` as
  `--font-public-sans`, local CommitMono OTFs from `fonts/` as
  `--font-commit-mono`), injects accent-color CSS from `AppConfig`, wraps
  everything in `ThemeProvider` (next-themes, class strategy, system default),
  renders a fixed LiveKit header + floating `ThemeToggle`. Imports
  `styles/globals.css`.
- `app/api/token/route.ts` — POST endpoint minting LiveKit access tokens with
  `livekit-server-sdk` from `LIVEKIT_URL` / `LIVEKIT_API_KEY` /
  `LIVEKIT_API_SECRET` (frontend/.env.local). Random room
  `voice_assistant_room_<n>` + identity `voice_assistant_user_<n>`; accepts
  optional `room_config` body (agent dispatch). NOTE: throws in production
  builds by design ("insecure route" guard at top of POST) — fine for dev/demo.
- `app/opengraph-image.tsx` — OG image.

## LiveKit session UI (the existing voice app)

Flow: `app/page.tsx` → `components/app/app.tsx` → `components/app/view-controller.tsx`.

- `components/app/app.tsx` (client) — creates `useSession(TokenSource.endpoint('/api/token'))`,
  wraps children in `AgentSessionProvider`, mounts `StartAudioButton`, sonner
  `Toaster`, debug + error hooks. Session state via `useSessionContext()` from
  `@livekit/components-react`.
- `components/app/view-controller.tsx` — AnimatePresence switch: disconnected →
  `WelcomeView` (start-call button), connected → `AgentSessionView_01`.
- `components/app/welcome-view.tsx` — pre-connect screen.
- `components/agents-ui/` — LiveKit "agents-ui" kit: `agent-session-provider.tsx`
  (context), `agent-chat-transcript.tsx` (live transcript), `agent-control-bar.tsx`
  (mic/camera/screen/chat controls), `agent-track-*`, 5 audio visualizers
  (bar/wave/grid/radial/aura), `start-audio-button.tsx`.
- `components/agents-ui/blocks/agent-session-view-01/` — the full in-session
  layout block (tile view + visualizer + transcript + control bar). Good source
  to mine for the Studio page.
- `components/ai-elements/` — conversation/message/shimmer primitives used by the transcript.
- `components/ui/` — shadcn-style primitives (button, select, tooltip, sonner, …).
- `hooks/agents-ui/` — visualizer + control-bar hooks; `hooks/useAgentErrors.tsx`,
  `hooks/useDebug.ts`.

## Config & utils

- `app-config.ts` — `AppConfig` interface + `APP_CONFIG_DEFAULTS` (page title,
  start button text, accent colors, visualizer options, optional `agentName`
  from `AGENT_NAME` env). Edit this for branding (Director FAL title etc.).
- `lib/utils.ts` — `getAppConfig()` (defaults or LiveKit sandbox remote config),
  `getStyles()` (accent → `--primary` CSS), `getSandboxTokenSource()`.
- `lib/shadcn/utils.ts` — `cn()` (clsx + tailwind-merge).

## Styling / theme system

- Tailwind CSS **v4** (CSS-first: no tailwind.config; tokens in
  `styles/globals.css` via `@theme inline`). shadcn-style oklch color variables
  in `:root` + `.dark`; dark mode via `.dark` class (next-themes), custom
  variant `@custom-variant dark (&:is(.dark *))`.
- Fonts: `--font-sans` = Public Sans, `--font-mono` = CommitMono. `--primary`
  is overridden at runtime from `AppConfig.accent` / `accentDark`.
- `tw-animate-css` is imported; `motion` (motion/react) is used throughout the
  starter — prefer `import { motion } from 'motion/react'`. `framer-motion` and
  `lenis` are installed for the landing page. Gotcha: motion v12 types are
  strict about `ease` — use literal consts (e.g. `ease: 'linear' as const`) or
  typed cubic-bezier arrays, not widened strings.

## Static assets

- `public/` — LiveKit logos, favicon. `public/placeholders/` — temporary landing
  assets (see PLACEHOLDERS.md; must be regenerated via fal before submission).
- `frontend/reference-landing/` — scratch reference components copied verbatim
  from prior work (tilt-3d, glass-card, hero). NOT imported by the app; adapt,
  don't import (they reference paths/deps that don't exist here).

## Env (frontend/.env.local)

`LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` (see SPEC §9).
