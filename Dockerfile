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

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

EXPOSE 8000 9000

CMD ["bash", "-lc", "uvicorn app.main:app --host 0.0.0.0 --port ${HTTP_PORT:-8000}"]
