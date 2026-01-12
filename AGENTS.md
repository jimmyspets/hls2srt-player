# Agent Instructions

## Project snapshot
- This repo is documentation-only for now; there is no application code yet.
- The goal is a Dockerized GStreamer + FastAPI service that buffers HLS and
  outputs SRT, plus a web UI.

## Where to look
- `README.md` is the source of truth for current behavior and intended scope.
- `Dockerfile` and `docker-compose.yml` describe the intended runtime.

## How to work here
- Keep changes minimal and aligned with the existing docs.
- If you add new files, update `README.md` to reflect them.
- Prefer Docker-centric workflows; avoid assuming local GStreamer installs.
- Use ASCII text unless the file already uses Unicode.

## Testing
- No automated tests exist yet. If you add code, propose a minimal test plan.

## Communication
- Call out assumptions explicitly, since many components are still planned.
- Avoid large speculative changes without asking first.
