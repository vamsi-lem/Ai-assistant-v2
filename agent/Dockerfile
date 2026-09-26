# Agent image. Built by LiveKit Cloud (lk agent create), Fly.io (fly deploy)
# or any container host; docs/DEPLOY.md covers both.
#
# The agent is a long-running worker, not a web server. It opens an outbound
# connection to LiveKit and waits for calls. It needs no public URL, no port,
# and no health check. Do not attach a public port or domain to it.
#
# This is also the fix for the Windows-only resampler crash: the LiveKit native
# library is stable on Linux, which is what this image is.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src ./src

# Pull the voice-activity and turn-detector model files into the image at
# build time. Without this the first call of every fresh deploy would spend
# its opening seconds downloading them, with the lead already on the line.
# No credentials are needed for this step; config skips its env check when it
# sees this subcommand.
RUN python -m src.main download-files

# `start` is production mode. `dev` is for a laptop.
CMD ["python", "-m", "src.main", "start"]
