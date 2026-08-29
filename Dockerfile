FROM python:3.12.14-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY pyproject.toml requirements.lock README.md ./
COPY src ./src

RUN pip wheel --no-cache-dir --wheel-dir /wheels --constraint requirements.lock .

FROM python:3.12.14-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579 AS runtime

ARG VCS_REF=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="RootLens" \
      org.opencontainers.image.description="Graph-grounded incident diagnosis and guarded remediation" \
      org.opencontainers.image.source="https://github.com/raman-gatech/RootLens" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --gid 10001 rootlens \
    && useradd --uid 10001 --gid rootlens --no-create-home --home-dir /nonexistent rootlens

WORKDIR /app

COPY --from=builder /wheels /wheels

RUN pip install --no-cache-dir --no-index --find-links=/wheels rootlens==1.0.1 \
    && rm -rf /wheels

COPY --chown=rootlens:rootlens migrations ./migrations
COPY --chown=rootlens:rootlens alembic.ini ./

USER rootlens

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"]

CMD ["uvicorn", "rootlens.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]
