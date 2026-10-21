# syntax=docker/dockerfile:1
# One Dockerfile for all 15 services. Each service is still its own image:
#   docker build --build-arg SERVICE=incident -t drukrescue-incident .
FROM python:3.12-slim

ARG SERVICE
RUN test -n "$SERVICE" || (echo "Pass --build-arg SERVICE=<name>" && exit 1)

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    SERVICE_NAME=${SERVICE}

WORKDIR /srv

# Dependencies first (better layer caching): shared template + service extras.
COPY libs/common /tmp/common
COPY services/${SERVICE}/requirements.txt /tmp/requirements.txt
# The cache mount is shared by all 15 builds, so each package is downloaded once (and never ends up in the image).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /tmp/common -r /tmp/requirements.txt && rm -rf /tmp/common /tmp/requirements.txt

COPY services/${SERVICE}/app ./app

# Run as an unprivileged user (Kubernetes also enforces runAsNonRoot + read-only root FS).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--timeout-graceful-shutdown", "20"]
