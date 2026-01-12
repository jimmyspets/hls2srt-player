from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl
import os
import asyncio
from urllib.parse import urljoin

import httpx

app = FastAPI(title="hls2srt-player")

DEFAULT_HLS_URL = os.getenv(
    "HLS_URL",
    "https://edge.waoplay.com/live/encoder03/2026-01-12_15.21.54/ori/master.m3u8",
)
CURRENT_HLS_URL = DEFAULT_HLS_URL
CURRENT_VARIANTS: list["Variant"] = []
CURRENT_AUDIO_TRACKS: list["AudioTrack"] = []
CURRENT_TOTAL_LENGTH = 5400.0
CURRENT_IS_VOD = True
CURRENT_MEDIA_URL: str | None = None
CURRENT_POLL_TASK: asyncio.Task | None = None


class StatusResponse(BaseModel):
    current_position: float
    buffer_length: float
    total_length: float
    buffer_status: str
    state: str
    hls_url: str
    variants: list["Variant"]
    audio_tracks: list["AudioTrack"]


class Variant(BaseModel):
    bandwidth: int | None
    resolution: str | None
    uri: str


class AudioTrack(BaseModel):
    name: str | None
    language: str | None
    group_id: str | None
    uri: str | None
    default: bool | None


class HlsUrlRequest(BaseModel):
    hls_url: HttpUrl


def build_dummy_status(
    *,
    current_position: float = 1234.5,
    buffer_length: float = 3600.0,
    total_length: float | None = None,
    buffer_status: str = "ok",
    state: str = "playing",
    hls_url: str | None = None,
    variants: list["Variant"] | None = None,
    audio_tracks: list["AudioTrack"] | None = None,
) -> StatusResponse:
    return StatusResponse(
        current_position=current_position,
        buffer_length=buffer_length,
        total_length=total_length if total_length is not None else CURRENT_TOTAL_LENGTH,
        buffer_status=buffer_status,
        state=state,
        hls_url=CURRENT_HLS_URL if hls_url is None else hls_url,
        variants=variants if variants is not None else CURRENT_VARIANTS,
        audio_tracks=audio_tracks if audio_tracks is not None else CURRENT_AUDIO_TRACKS,
    )


def split_attribute_pairs(raw: str) -> list[str]:
    pairs = []
    current = []
    in_quotes = False
    for char in raw:
        if char == "\"":
            in_quotes = not in_quotes
            current.append(char)
            continue
        if char == "," and not in_quotes:
            pairs.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        pairs.append("".join(current).strip())
    return pairs


def parse_attribute_list(raw: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for pair in split_attribute_pairs(raw):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        value = value.strip()
        if value.startswith("\"") and value.endswith("\""):
            value = value[1:-1]
        attributes[key.strip()] = value
    return attributes


def parse_m3u8(master_text: str, base_url: str) -> tuple[list["Variant"], list["AudioTrack"]]:
    variants: list[Variant] = []
    audio_tracks: list[AudioTrack] = []
    pending_stream_info: dict[str, str] | None = None

    for raw_line in master_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-STREAM-INF:"):
            attributes = parse_attribute_list(line.split(":", 1)[1])
            pending_stream_info = attributes
            continue
        if line.startswith("#EXT-X-MEDIA:"):
            attributes = parse_attribute_list(line.split(":", 1)[1])
            if attributes.get("TYPE") != "AUDIO":
                continue
            uri = attributes.get("URI")
            audio_tracks.append(
                AudioTrack(
                    name=attributes.get("NAME"),
                    language=attributes.get("LANGUAGE"),
                    group_id=attributes.get("GROUP-ID"),
                    uri=urljoin(base_url, uri) if uri else None,
                    default=(attributes.get("DEFAULT") == "YES")
                    if "DEFAULT" in attributes
                    else None,
                )
            )
            continue
        if line.startswith("#"):
            continue
        if pending_stream_info is not None:
            bandwidth = pending_stream_info.get("BANDWIDTH")
            resolution = pending_stream_info.get("RESOLUTION")
            variants.append(
                Variant(
                    bandwidth=int(bandwidth) if bandwidth and bandwidth.isdigit() else None,
                    resolution=resolution,
                    uri=urljoin(base_url, line),
                )
            )
            pending_stream_info = None

    return variants, audio_tracks


def parse_media_playlist(text: str) -> tuple[float, bool]:
    total_length = 0.0
    is_vod = False
    playlist_type = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-PLAYLIST-TYPE:"):
            playlist_type = line.split(":", 1)[1].strip()
            continue
        if line.startswith("#EXTINF:"):
            duration_part = line.split(":", 1)[1].split(",", 1)[0].strip()
            try:
                total_length += float(duration_part)
            except ValueError:
                continue
            continue
        if line.startswith("#EXT-X-ENDLIST"):
            is_vod = True

    if playlist_type == "VOD":
        is_vod = True

    return total_length, is_vod


async def fetch_m3u8_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


async def load_stream_metadata(
    url: str,
) -> tuple[list["Variant"], list["AudioTrack"], float, bool, str | None]:
    text = await fetch_m3u8_text(url)
    variants, audio_tracks = parse_m3u8(text, url)
    media_url = None
    total_length = CURRENT_TOTAL_LENGTH
    is_vod = True

    if variants:
        selected = max(variants, key=lambda variant: variant.bandwidth or 0)
        media_url = selected.uri
    else:
        media_url = url

    if media_url:
        media_text = await fetch_m3u8_text(media_url)
        total_length, is_vod = parse_media_playlist(media_text)

    return variants, audio_tracks, total_length, is_vod, media_url


async def poll_media_playlist(url: str) -> None:
    global CURRENT_TOTAL_LENGTH
    global CURRENT_IS_VOD
    try:
        while True:
            try:
                media_text = await fetch_m3u8_text(url)
                total_length, is_vod = parse_media_playlist(media_text)
                CURRENT_TOTAL_LENGTH = total_length
                CURRENT_IS_VOD = is_vod
                if is_vod:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        return


def render_homepage() -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>hls2srt-player</title>
    <style>
      :root {{
        --bg: #0f172a;
        --bg-accent: #1e293b;
        --panel: rgba(255, 255, 255, 0.08);
        --text: #f8fafc;
        --muted: #cbd5f5;
        --accent: #f59e0b;
        --accent-strong: #f97316;
      }}

      * {{
        box-sizing: border-box;
      }}

      body {{
        margin: 0;
        font-family: "Trebuchet MS", "Segoe UI", sans-serif;
        background: radial-gradient(circle at top left, #0f172a, #020617 55%);
        color: var(--text);
        min-height: 100vh;
      }}

      header {{
        padding: 32px 24px 16px;
        text-align: center;
      }}

      header h1 {{
        margin: 0 0 8px;
        font-size: clamp(2rem, 5vw, 3.2rem);
        letter-spacing: 0.02em;
      }}

      header p {{
        margin: 0;
        color: var(--muted);
      }}

      main {{
        max-width: 960px;
        margin: 0 auto;
        padding: 16px 24px 48px;
        display: grid;
        gap: 20px;
      }}

      section {{
        background: var(--panel);
        border: 1px solid rgba(148, 163, 184, 0.25);
        border-radius: 16px;
        padding: 20px;
        backdrop-filter: blur(6px);
      }}

      .grid {{
        display: grid;
        gap: 16px;
      }}

      .two-col {{
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      }}

      input[type="text"] {{
        width: 100%;
        padding: 12px 14px;
        border-radius: 10px;
        border: 1px solid rgba(148, 163, 184, 0.4);
        background: rgba(15, 23, 42, 0.7);
        color: var(--text);
      }}

      button {{
        cursor: pointer;
        border: none;
        border-radius: 999px;
        padding: 10px 16px;
        font-weight: 600;
        background: linear-gradient(135deg, var(--accent), var(--accent-strong));
        color: #1f2937;
        transition: transform 0.2s ease, filter 0.2s ease;
      }}

      button.secondary {{
        background: rgba(255, 255, 255, 0.1);
        color: var(--text);
        border: 1px solid rgba(148, 163, 184, 0.4);
      }}

      button.state-active {{
        background: linear-gradient(135deg, #22c55e, #16a34a);
        color: #0f172a;
      }}

      button:hover {{
        transform: translateY(-1px);
        filter: brightness(1.05);
      }}

      pre {{
        background: rgba(15, 23, 42, 0.7);
        padding: 12px;
        border-radius: 12px;
        overflow-x: auto;
      }}

      .controls {{
        display: flex;
        flex-direction: column;
        gap: 12px;
      }}

      .controls-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: center;
      }}

      .seek-row {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 16px;
      }}

      .seek-group {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        padding: 10px 12px;
        border-radius: 14px;
        background: rgba(15, 23, 42, 0.4);
        border: 1px solid rgba(148, 163, 184, 0.2);
      }}

      .seek-label {{
        width: 100%;
        font-size: 0.85rem;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }}

      .chip {{
        padding: 8px 14px;
        border-radius: 999px;
      }}

      .jump-input {{
        max-width: 220px;
      }}

      .status-line {{
        color: var(--muted);
        font-size: 0.95rem;
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>hls2srt-player</h1>
      <p>Buffered HLS playback with SRT output. Demo UI for the control API.</p>
    </header>
    <main>
      <section class="grid">
        <div>
          <h2>Stream source</h2>
          <p class="status-line">Default test stream for early development.</p>
        </div>
        <div class="grid two-col">
          <input type="text" id="hls-url" value="{DEFAULT_HLS_URL}" />
          <div class="controls-row">
            <button type="button" id="set-url">Set stream</button>
            <button type="button" id="clear-url" class="secondary">Remove stream</button>
          </div>
        </div>
      </section>

      <section class="grid">
        <div>
          <h2>Playback controls</h2>
          <p class="status-line">These endpoints return dummy data until GStreamer is wired up.</p>
        </div>
        <div class="controls">
          <div class="controls-row">
            <button data-endpoint="/play" data-state="playing">Play</button>
            <button data-endpoint="/pause" data-state="paused" class="secondary">Pause</button>
            <button data-endpoint="/stop" data-state="stopped" class="secondary">Stop</button>
          </div>
          <div class="seek-row">
            <div class="seek-group">
              <div class="seek-label">Back</div>
              <button data-endpoint="/skip/backward/300" class="secondary chip">5m</button>
              <button data-endpoint="/skip/backward/30" class="secondary chip">30s</button>
              <button data-endpoint="/skip/backward/5" class="secondary chip">5s</button>
            </div>
            <div class="seek-group">
              <div class="seek-label">Forward</div>
              <button data-endpoint="/skip/forward/5" class="secondary chip">5s</button>
              <button data-endpoint="/skip/forward/30" class="secondary chip">30s</button>
              <button data-endpoint="/skip/forward/300" class="secondary chip">5m</button>
            </div>
          </div>
          <div class="controls-row">
            <input
              type="text"
              id="jump-seconds"
              class="jump-input"
              value="60"
              inputmode="numeric"
              placeholder="seconds | mm:ss | hh:mm:ss"
            />
            <label class="status-line">
              <input type="checkbox" id="jump-from-end" />
              From end
            </label>
            <button type="button" id="jump-button" class="secondary">Jump</button>
          </div>
        </div>
      </section>

      <section class="grid">
        <div>
          <h2>Status</h2>
          <p class="status-line">Latest response from the status endpoint.</p>
        </div>
        <pre id="status-json">Loading...</pre>
      </section>
    </main>

    <script>
      const statusEl = document.getElementById("status-json");
      const urlInput = document.getElementById("hls-url");
      const setButton = document.getElementById("set-url");
      const clearButton = document.getElementById("clear-url");
      const jumpButton = document.getElementById("jump-button");
      const jumpSecondsInput = document.getElementById("jump-seconds");
      const jumpFromEndInput = document.getElementById("jump-from-end");

      function updateState(state) {{
        document.querySelectorAll("[data-state]").forEach((button) => {{
          if (button.dataset.state === state) {{
            button.classList.add("state-active");
          }} else {{
            button.classList.remove("state-active");
          }}
        }});
      }}

      async function fetchStatus(endpoint = "/status") {{
        const response = await fetch(endpoint);
        const data = await response.json();
        statusEl.textContent = JSON.stringify(data, null, 2);
        updateState(data.state);
      }}

      document.querySelectorAll("[data-endpoint]").forEach((button) => {{
        button.addEventListener("click", () => fetchStatus(button.dataset.endpoint));
      }});

      function parseDurationToSeconds(value) {{
        const trimmed = value.trim();
        if (!trimmed) {{
          return NaN;
        }}

        if (trimmed.includes(":")) {{
          const parts = trimmed.split(":").map((part) => part.trim());
          if (parts.some((part) => part === "" || Number.isNaN(Number(part)))) {{
            return NaN;
          }}
          if (parts.length === 3) {{
            const [hours, minutes, seconds] = parts.map(Number);
            return hours * 3600 + minutes * 60 + seconds;
          }}
          if (parts.length === 2) {{
            const [minutes, seconds] = parts.map(Number);
            return minutes * 60 + seconds;
          }}
          return NaN;
        }}

        const seconds = Number.parseFloat(trimmed);
        return Number.isNaN(seconds) ? NaN : seconds;
      }}

      jumpButton.addEventListener("click", async () => {{
        const seconds = parseDurationToSeconds(jumpSecondsInput.value);
        if (Number.isNaN(seconds) || seconds < 0) {{
          return;
        }}
        const endpoint = jumpFromEndInput.checked
          ? `/jump/from-end/${{seconds}}`
          : `/jump/from-start/${{seconds}}`;
        await fetchStatus(endpoint);
      }});

      setButton.addEventListener("click", async () => {{
        const response = await fetch("/stream", {{
          method: "POST",
          headers: {{
            "Content-Type": "application/json",
          }},
          body: JSON.stringify({{ hls_url: urlInput.value }}),
        }});

        if (response.ok) {{
          const data = await response.json();
          statusEl.textContent = JSON.stringify(data, null, 2);
        }}
      }});

      clearButton.addEventListener("click", async () => {{
        const response = await fetch("/stream/clear", {{
          method: "POST",
        }});
        if (response.ok) {{
          const data = await response.json();
          statusEl.textContent = JSON.stringify(data, null, 2);
          urlInput.value = "{DEFAULT_HLS_URL}";
        }}
      }});

      fetchStatus();
      setInterval(fetchStatus, 1000);
    </script>
  </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return render_homepage()


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    return build_dummy_status()


@app.post("/stream", response_model=StatusResponse)
async def set_stream(payload: HlsUrlRequest) -> StatusResponse:
    global CURRENT_HLS_URL
    global CURRENT_VARIANTS
    global CURRENT_AUDIO_TRACKS
    global CURRENT_TOTAL_LENGTH
    global CURRENT_IS_VOD
    global CURRENT_MEDIA_URL
    global CURRENT_POLL_TASK
    CURRENT_HLS_URL = str(payload.hls_url)
    if CURRENT_POLL_TASK and not CURRENT_POLL_TASK.done():
        CURRENT_POLL_TASK.cancel()
        CURRENT_POLL_TASK = None
    try:
        variants, audio_tracks, total_length, is_vod, media_url = await load_stream_metadata(
            CURRENT_HLS_URL
        )
    except (httpx.HTTPError, ValueError):
        variants = []
        audio_tracks = []
        total_length = CURRENT_TOTAL_LENGTH
        is_vod = True
        media_url = None
    CURRENT_VARIANTS = variants
    CURRENT_AUDIO_TRACKS = audio_tracks
    CURRENT_TOTAL_LENGTH = total_length
    CURRENT_IS_VOD = is_vod
    CURRENT_MEDIA_URL = media_url
    if not is_vod and media_url:
        CURRENT_POLL_TASK = asyncio.create_task(poll_media_playlist(media_url))
    return build_dummy_status()


@app.post("/stream/clear", response_model=StatusResponse)
async def clear_stream() -> StatusResponse:
    global CURRENT_HLS_URL
    global CURRENT_VARIANTS
    global CURRENT_AUDIO_TRACKS
    global CURRENT_TOTAL_LENGTH
    global CURRENT_IS_VOD
    global CURRENT_MEDIA_URL
    global CURRENT_POLL_TASK

    if CURRENT_POLL_TASK:
        if not CURRENT_POLL_TASK.done():
            CURRENT_POLL_TASK.cancel()
        CURRENT_POLL_TASK = None

    CURRENT_HLS_URL = ""
    CURRENT_VARIANTS = []
    CURRENT_AUDIO_TRACKS = []
    CURRENT_TOTAL_LENGTH = 0.0
    CURRENT_IS_VOD = True
    CURRENT_MEDIA_URL = None

    return build_dummy_status(
        current_position=0.0,
        buffer_length=0.0,
        total_length=0.0,
        buffer_status="empty",
        state="stopped",
        hls_url="",
        variants=[],
        audio_tracks=[],
    )


@app.get("/play", response_model=StatusResponse)
async def play() -> StatusResponse:
    return build_dummy_status(state="playing")


@app.get("/pause", response_model=StatusResponse)
async def pause() -> StatusResponse:
    return build_dummy_status(state="paused")


@app.get("/stop", response_model=StatusResponse)
async def stop() -> StatusResponse:
    return build_dummy_status(state="stopped", current_position=0.0)


@app.get("/skip/forward/{seconds}", response_model=StatusResponse)
async def skip_forward(seconds: float) -> StatusResponse:
    base_position = 1234.5
    return build_dummy_status(current_position=base_position + seconds)


@app.get("/skip/backward/{seconds}", response_model=StatusResponse)
async def skip_backward(seconds: float) -> StatusResponse:
    base_position = 1234.5
    return build_dummy_status(current_position=max(0.0, base_position - seconds))


@app.get("/jump/from-start/{seconds}", response_model=StatusResponse)
async def jump_from_start(seconds: float) -> StatusResponse:
    total_length = 5400.0
    return build_dummy_status(current_position=min(seconds, total_length))


@app.get("/jump/from-end/{seconds}", response_model=StatusResponse)
async def jump_from_end(seconds: float) -> StatusResponse:
    total_length = 5400.0
    return build_dummy_status(current_position=max(0.0, total_length - seconds))
