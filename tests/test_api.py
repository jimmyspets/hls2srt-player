import asyncio
import httpx
import pytest

import app.main as main_module
from app.main import (
    DEFAULT_HLS_URL,
    app,
    cancel_poll_task,
    fetch_m3u8_text,
    load_stream_metadata,
    parse_attribute_list,
    parse_m3u8,
    parse_media_playlist,
    poll_media_playlist,
)


@pytest.fixture(autouse=True)
def reset_hls_url() -> None:
    main_module.CURRENT_HLS_URL = DEFAULT_HLS_URL
    main_module.CURRENT_VARIANTS = []
    main_module.CURRENT_AUDIO_TRACKS = []
    main_module.CURRENT_TOTAL_LENGTH = 5400.0
    main_module.CURRENT_IS_VOD = True
    main_module.CURRENT_MEDIA_URL = None
    if main_module.CURRENT_POLL_TASK and not main_module.CURRENT_POLL_TASK.done():
        main_module.CURRENT_POLL_TASK.cancel()


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


def test_parse_attribute_list_skips_invalid_pairs() -> None:
    raw = 'BANDWIDTH=800000,NAME="Main",BROKEN'
    parsed = parse_attribute_list(raw)
    assert parsed == {"BANDWIDTH": "800000", "NAME": "Main"}


def test_parse_m3u8_ignores_non_audio_media() -> None:
    text = """#EXTM3U
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English",URI="sub/eng.m3u8"

#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360
low/playlist.m3u8
"""
    variants, audio_tracks = parse_m3u8(text, "https://example.com/master.m3u8")

    assert len(variants) == 1
    assert audio_tracks == []


def test_parse_media_playlist_handles_invalid_duration_and_vod() -> None:
    text = """#EXTM3U
#EXT-X-VERSION:3

#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:bad,
seg-1.ts
#EXTINF:5.0,
seg-2.ts
"""
    total_length, is_vod = parse_media_playlist(text)

    assert total_length == 5.0
    assert is_vod is True


@pytest.mark.anyio
async def test_poll_media_playlist_stops_on_vod(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    async def fake_fetch(_: str) -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.HTTPError("boom")
        return """#EXTM3U
#EXTINF:6.0,
seg-1.ts
#EXT-X-ENDLIST
"""

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(main_module, "fetch_m3u8_text", fake_fetch)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    await poll_media_playlist("https://example.com/media.m3u8")
    assert main_module.CURRENT_TOTAL_LENGTH == 6.0
    assert main_module.CURRENT_IS_VOD is True


@pytest.mark.anyio
async def test_cancel_poll_task_cancels_running_task() -> None:
    async def sleepy() -> None:
        await asyncio.sleep(10)

    main_module.CURRENT_POLL_TASK = asyncio.create_task(sleepy())
    await cancel_poll_task()
    assert main_module.CURRENT_POLL_TASK is None


@pytest.mark.anyio
async def test_lifespan_shutdown_cancels_poll_task() -> None:
    async def sleepy() -> None:
        await asyncio.sleep(10)

    main_module.CURRENT_POLL_TASK = asyncio.create_task(sleepy())
    async with app.router.lifespan_context(app):
        pass
    assert main_module.CURRENT_POLL_TASK is None


@pytest.mark.anyio
async def test_load_stream_metadata_uses_master_when_no_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    async def fake_fetch(url: str) -> str:
        if url.endswith("master.m3u8"):
            calls["count"] += 1
            if calls["count"] == 1:
                return """#EXTM3U
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="English",LANGUAGE="en",URI="audio/eng.m3u8"
"""
            return """#EXTM3U
#EXTINF:10.0,
seg-1.ts
#EXT-X-ENDLIST
"""
        return ""

    monkeypatch.setattr(main_module, "fetch_m3u8_text", fake_fetch)
    variants, audio_tracks, total_length, is_vod, media_url = await load_stream_metadata(
        "https://example.com/master.m3u8"
    )

    assert variants == []
    assert len(audio_tracks) == 1
    assert total_length == 10.0
    assert is_vod is True
    assert media_url == "https://example.com/master.m3u8"


@pytest.mark.anyio
async def test_set_stream_handles_fetch_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_load(_: str) -> tuple[list[main_module.Variant], list[main_module.AudioTrack], float, bool, str | None]:
        raise httpx.HTTPError("fail")

    monkeypatch.setattr(main_module, "load_stream_metadata", fail_load)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/stream", json={"hls_url": "https://bad.example/stream.m3u8"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["variants"] == []
    assert payload["audio_tracks"] == []


@pytest.mark.anyio
async def test_set_stream_starts_polling_for_live(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_load(_: str) -> tuple[list[main_module.Variant], list[main_module.AudioTrack], float, bool, str | None]:
        return [], [], 0.0, False, "https://example.com/live.m3u8"

    async def fake_poll(_: str) -> None:
        return None

    monkeypatch.setattr(main_module, "load_stream_metadata", fake_load)
    monkeypatch.setattr(main_module, "poll_media_playlist", fake_poll)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/stream", json={"hls_url": "https://example.com/master.m3u8"})

    assert response.status_code == 200
    assert main_module.CURRENT_POLL_TASK is not None
    await cancel_poll_task()


@pytest.mark.anyio
async def test_fetch_m3u8_text_uses_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, text: str) -> None:
            self.text = text

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str) -> FakeResponse:
            return FakeResponse(f"ok:{url}")

    monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeClient)
    result = await fetch_m3u8_text("https://example.com/master.m3u8")
    assert result == "ok:https://example.com/master.m3u8"


@pytest.mark.anyio
async def test_poll_media_playlist_cancellable(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_called = asyncio.Event()
    original_sleep = asyncio.sleep

    async def fake_fetch(_: str) -> str:
        return """#EXTM3U
#EXTINF:6.0,
seg-1.ts
"""

    async def fake_sleep(_: float) -> None:
        sleep_called.set()
        await original_sleep(0.1)

    monkeypatch.setattr(main_module, "fetch_m3u8_text", fake_fetch)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    task = asyncio.create_task(poll_media_playlist("https://example.com/live.m3u8"))
    await sleep_called.wait()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        # Task cancellation is expected in this test; ignore the exception.
        pass
