FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install GStreamer runtime and common plugins.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    gstreamer1.0-tools \
    gstreamer1.0-libav \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    jq \
    nano \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Placeholder: application code will be added later.
CMD ["bash", "-lc", "echo 'hls2srt-player image built. App not added yet.' && sleep infinity"]
