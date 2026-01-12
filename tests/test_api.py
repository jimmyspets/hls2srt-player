import httpx
import pytest

from app.main import app

@pytest.mark.anyio
async def test_root() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "hls2srt-player is running"}


@pytest.mark.anyio
async def test_status() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/status")

    assert response.status_code == 200

    payload = response.json()

    assert payload["buffer_status"] == "ok"
    assert payload["state"] == "playing"
    assert payload["current_position"] == 1234.5
    assert payload["buffer_length"] == 3600.0
    assert payload["total_length"] == 5400.0
