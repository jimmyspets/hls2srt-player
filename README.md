# hls2srt-player

`hls2srt-player` is a Dockerized, GStreamer-based player that accepts an HLS
(`.m3u8`) URL, buffers it for long-term playback, and outputs a remuxed
(MPEG-TS, no transcoding) stream over SRT. Control and monitoring are exposed
via an async FastAPI-based HTTP API and a built-in web GUI.

The project is designed for automation and easy integration with tools such as
Bitfocus Companion.

## Features

- Accepts direct `.m3u8` URLs (HLS)
- Supports VOD, event-style, and live HLS streams
- Selectable video variant / bitrate
- Selectable audio track (single-track initially)
- Long buffering (target up to 1 hour, disk-backed)
- Buffer survives pause and seeking
- Remux-only playback (no transcoding)
- MPEG-TS output over SRT
- Async FastAPI control API
- Built-in web GUI for URL and stream selection
- One player instance per container

## Buffering behavior

- Buffer size is a target, not a hard limit
- Buffering continues while paused
- If the network stalls, playback stalls
- For live streams, total length equals the sliding window duration

## API (overview)

All control endpoints return the same status JSON.

### Status JSON

```json
{
  "current_position": 1234.5,
  "buffer_length": 3600,
  "total_length": 5400,
  "buffer_status": "ok",
  "state": "playing",
  "hls_url": "https://edge.waoplay.com/live/encoder03/2026-01-12_15.21.54/ori/master.m3u8"
}
```

### Control endpoints (GET)

- `/status`
- `/play`
- `/pause`
- `/stop`
- `/skip/forward/{seconds}`
- `/skip/backward/{seconds}`
- `/jump/from-start/{seconds}`
- `/jump/from-end/{seconds}`

### Stream endpoints (POST)

- `/stream` with JSON body `{"hls_url": "https://.../master.m3u8"}`

## Docker

The entire project runs inside a single Docker container.

Exposed ports:
- HTTP API / Web GUI (FastAPI): `8000` (default, configurable)
- SRT output: `9000` (default, configurable)

## Tech stack

- Python 3.12+
- FastAPI (async)
- GStreamer
- Docker

## Getting started

This repo now includes a minimal FastAPI app stub and tests. The runtime and
API will evolve inside a Docker image that bundles GStreamer and the app.

### Prerequisites

- Docker 24+ (or compatible)
- A reachable HLS `.m3u8` URL to test with

### Quick start (once the image exists)

```bash
docker build -t hls2srt-player .
docker run --rm -p 8000:8000 -p 9000:9000 \
  -e HLS_URL="https://edge.waoplay.com/live/encoder03/2026-01-12_15.21.54/ori/master.m3u8" \
  -e SRT_LISTEN_PORT=9000 \
  -e HTTP_PORT=8000 \
  hls2srt-player
```

Or with Docker Compose:

```bash
docker compose up --build
```

### Local development (current)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Note: When working inside the Docker/Dev Container environment, do not create
or use a `.venv`; install dependencies directly in the container.

Visit `http://localhost:8000/` for a hello page and `/status` for dummy data.

### Tests (current)

```bash
pytest
```

### Project layout (current)

- `app/`: FastAPI app stub (`/` and `/status`)
- `tests/`: API tests
- `requirements.txt`: Python dependencies (runtime + tests)

### GStreamer installation (Docker)

The Docker image installs GStreamer and common plugins from Debian packages.
See `Dockerfile` for the exact list.

### VS Code Dev Container

If you are developing in a Dev Container, `.devcontainer/` is configured to
build from the main `Dockerfile` so it uses the same GStreamer setup. In VS
Code:

1. Open the repo.
2. Run “Dev Containers: Reopen in Container”.

The container will provide a consistent GStreamer runtime for development.

### Configuration (environment)

Planned configuration knobs (subject to change as implementation lands):

- `HLS_URL`: Source HLS `.m3u8` URL (optional if set via API/UI)
- `HTTP_PORT`: FastAPI port (default `8000`)
- `SRT_LISTEN_PORT`: SRT output port (default `9000`)
- `BUFFER_TARGET_SECONDS`: Target buffer size (default `3600`)
- `HLS_VARIANT`: Variant index or bitrate selector (optional)
- `AUDIO_TRACK`: Audio track index (optional)

### Development workflow (planned)

The project is intended to run in Docker to ensure GStreamer availability and
consistent plugin versions. A typical workflow will look like this:

1. Build the image locally.
2. Run the container with ports exposed.
3. Use the API or web UI to load a stream and control playback.

Once the code is in place, this section will include:

- `make dev` or `docker compose up` examples
- Local API docs via `/docs`
- UI usage notes

### API usage

The FastAPI server exposes control endpoints listed above. Example:

```bash
curl http://localhost:8000/status
curl http://localhost:8000/play
```

### Web UI

The web UI is served from the FastAPI app at `http://localhost:8000/`.
Use it to input a stream URL, select variants, and monitor buffer status.

## License

This project is licensed under the MIT License.

Note: This project uses GStreamer, which is licensed under the LGPL.
Users are responsible for ensuring that any installed GStreamer plugins and
codecs comply with their local laws and licensing requirements.
