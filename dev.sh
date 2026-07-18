#!/usr/bin/env bash
# Director FAL — start the whole product locally with one command.
# Runs three processes: livekit-server (transport), the director agent, and the
# web app. Ctrl-C stops all three. Everything is localhost; no database, no cloud.
set -euo pipefail
cd "$(dirname "$0")"

info() { printf '\033[1;36m[dev]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[dev]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[dev]\033[0m %s\n' "$*" >&2; exit 1; }

# --- preflight -------------------------------------------------------------
command -v ffmpeg         >/dev/null || die "ffmpeg not found (brew install ffmpeg)"
command -v uv             >/dev/null || die "uv not found (https://docs.astral.sh/uv/)"
command -v livekit-server >/dev/null || die "livekit-server not found (brew install livekit)"

[ -f agent/.env.local ]    || warn "agent/.env.local missing — copy agent/.env.example and add keys"
[ -f frontend/.env.local ] || warn "frontend/.env.local missing — copy frontend/.env.example"

# pick a package manager for the frontend
if command -v pnpm >/dev/null; then WEB_PM="pnpm"; elif command -v npm >/dev/null; then WEB_PM="npm"; else die "need pnpm or npm"; fi

pids=()
cleanup() { info "shutting down..."; for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

# --- 1) livekit-server (dev mode: devkey/secret, no account) ---------------
info "starting livekit-server --dev (ws://localhost:7880)"
livekit-server --dev >/tmp/director-livekit.log 2>&1 &
pids+=($!)
sleep 1

# --- 2) the director agent -------------------------------------------------
info "starting director agent"
( cd agent && uv run python src/agent.py dev ) &
pids+=($!)

# --- 3) the web app --------------------------------------------------------
info "starting web app -> http://localhost:3000"
( cd frontend && "$WEB_PM" run dev ) &
pids+=($!)

info "all three running. open http://localhost:3000 and press the talk orb."
info "livekit logs: /tmp/director-livekit.log   |   Ctrl-C to stop everything"
wait
