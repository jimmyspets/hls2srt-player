import httpx
import pytest

import app.main as main_module
from app.main import app, DEFAULT_HLS_URL


@pytest.fixture(autouse=True)
def reset_hls_url() -> None:
    main_module.CURRENT_HLS_URL = DEFAULT_HLS_URL


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


@pytest.mark.anyio
async def test_set_stream_updates_status() -> None:
    new_url = "https://example.com/test/stream.m3u8"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/stream", json={"hls_url": new_url})

    assert response.status_code == 200
    assert response.json()["hls_url"] == new_url
