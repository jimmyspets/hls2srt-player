from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="hls2srt-player")


class StatusResponse(BaseModel):
    current_position: float
    buffer_length: float
    total_length: float
    buffer_status: str
    state: str


def build_dummy_status() -> StatusResponse:
    return StatusResponse(
        current_position=1234.5,
        buffer_length=3600.0,
        total_length=5400.0,
        buffer_status="ok",
        state="playing",
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "hls2srt-player is running"}


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    return build_dummy_status()
