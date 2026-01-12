from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, HttpUrl
import os

app = FastAPI(title="hls2srt-player")

DEFAULT_HLS_URL = os.getenv(
    "HLS_URL",
    "https://edge.waoplay.com/live/encoder03/2026-01-12_15.21.54/ori/master.m3u8",
)
CURRENT_HLS_URL = DEFAULT_HLS_URL


class StatusResponse(BaseModel):
    current_position: float
    buffer_length: float
    total_length: float
    buffer_status: str
    state: str
    hls_url: str


class HlsUrlRequest(BaseModel):
    hls_url: HttpUrl


def build_dummy_status(
    *,
    current_position: float = 1234.5,
    buffer_length: float = 3600.0,
    total_length: float = 5400.0,
    buffer_status: str = "ok",
    state: str = "playing",
    hls_url: str | None = None,
) -> StatusResponse:
    return StatusResponse(
        current_position=current_position,
        buffer_length=buffer_length,
        total_length=total_length,
        buffer_status=buffer_status,
        state=state,
        hls_url=hls_url or CURRENT_HLS_URL,
    )


def render_homepage() -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>hls2srt-player</title>
    <link
      rel="icon"
      href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0%25' stop-color='%23f59e0b'/%3E%3Cstop offset='100%25' stop-color='%23f97316'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='64' height='64' rx='14' fill='%230f172a'/%3E%3Cpath d='M18 20h28v6H18zM18 30h18v6H18zM18 40h10v6H18z' fill='url(%23g)'/%3E%3C/svg%3E"
    >
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
          <div class="controls">
            <button type="button" id="set-url">Set stream</button>
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
    CURRENT_HLS_URL = str(payload.hls_url)
    return build_dummy_status()


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
