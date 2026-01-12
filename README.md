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
  "state": "playing"
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

## License

This project is licensed under the MIT License.

Note: This project uses GStreamer, which is licensed under the LGPL.
Users are responsible for ensuring that any installed GStreamer plugins and
codecs comply with their local laws and licensing requirements.
