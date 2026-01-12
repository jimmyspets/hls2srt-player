import httpx
import pytest

import app.main as main_module
from app.main import app, DEFAULT_HLS_URL, DEFAULT_TOTAL_LENGTH


@pytest.fixture(autouse=True)
async def reset_stream_state() -> None:
    """Reset stream state between tests."""
    # Use clear_stream to safely cancel any running tasks
    await main_module.stream_state.clear_stream()
    
    # Reset to default values using update_stream
    await main_module.stream_state.update_stream(
        hls_url=DEFAULT_HLS_URL,
        variants=[],
        audio_tracks=[],
        total_length=DEFAULT_TOTAL_LENGTH,
        is_vod=True,
        media_url=None,
    )


@pytest.mark.anyio
async def test_root() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "hls2srt-player" in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "expected_state", "expected_position"),
    [
        ("/status", "playing", 1234.5),
        ("/play", "playing", 1234.5),
        ("/pause", "paused", 1234.5),
        ("/stop", "stopped", 0.0),
        ("/skip/forward/10", "playing", 1244.5),
        ("/skip/backward/10", "playing", 1224.5),
        ("/jump/from-start/60", "playing", 60.0),
        ("/jump/from-end/60", "playing", 5340.0),
    ],
)
async def test_status_endpoints(
    endpoint: str, expected_state: str, expected_position: float
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(endpoint)

    assert response.status_code == 200

    payload = response.json()

    assert payload["buffer_status"] == "ok"
    assert payload["state"] == expected_state
    assert payload["current_position"] == expected_position
    assert payload["buffer_length"] == 3600.0
    assert payload["total_length"] == 5400.0
    assert payload["hls_url"] == DEFAULT_HLS_URL
    assert payload["variants"] == []
    assert payload["audio_tracks"] == []


@pytest.mark.anyio
async def test_set_stream_updates_status(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_m3u8_text(url: str) -> str:
        if url.endswith("stream.m3u8"):
            return """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",LANGUAGE="en",URI="audio/eng.m3u8",DEFAULT=YES
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
low/playlist.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720
mid/playlist.m3u8
"""
        return """#EXTM3U
#EXT-X-VERSION:3
#EXTINF:6.0,
seg-1.ts
#EXTINF:5.0,
seg-2.ts
#EXTINF:4.0,
seg-3.ts
#EXT-X-ENDLIST
"""

    monkeypatch.setattr(main_module, "fetch_m3u8_text", fake_fetch_m3u8_text)
    new_url = "https://example.com/test/stream.m3u8"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/stream", json={"hls_url": new_url})

    assert response.status_code == 200
    payload = response.json()
    assert payload["hls_url"] == new_url
    assert payload["total_length"] == 15.0
    assert payload["variants"] == [
        {
            "bandwidth": 800000,
            "resolution": "640x360",
            "uri": "https://example.com/test/low/playlist.m3u8",
        },
        {
            "bandwidth": 2000000,
            "resolution": "1280x720",
            "uri": "https://example.com/test/mid/playlist.m3u8",
        },
    ]
    assert payload["audio_tracks"] == [
        {
            "name": "English",
            "language": "en",
            "group_id": "audio",
            "uri": "https://example.com/test/audio/eng.m3u8",
            "default": True,
        }
    ]


@pytest.mark.anyio
async def test_clear_stream_resets_state() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/stream/clear")

    assert response.status_code == 200
    payload = response.json()
    assert payload["hls_url"] == ""
    assert payload["variants"] == []
    assert payload["audio_tracks"] == []
    assert payload["total_length"] == 0.0
    assert payload["state"] == "stopped"
