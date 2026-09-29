# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

FROM python:3.13-slim-bookworm AS base
COPY --from=uv /uv /uvx /usr/local/bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/cache/uv \
    SCIENCE_AGENT_DATA_DIR=/data \
    HF_HOME=/cache/huggingface \
    DOCLING_CACHE_DIR=/cache/docling \
    XDG_CACHE_HOME=/cache
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app \
    && mkdir -p /app /data /cache \
    && chown app:app /app /data /cache
WORKDIR /app
ENV UV_HTTP_TIMEOUT=120 UV_CONCURRENT_DOWNLOADS=8

# A small environment for updating the lock before the application is built.
FROM base AS resolver
COPY deploy/toolbox.sh /usr/local/bin/toolbox
USER app
ENTRYPOINT ["/bin/sh", "/usr/local/bin/toolbox", "python"]
CMD ["uv", "lock"]

FROM base AS dependencies
COPY deploy/python/pyproject.toml deploy/python/uv.lock ./
RUN --mount=type=cache,target=/cache/uv \
    uv sync --locked --no-install-project --no-dev --extra web --extra rag
# RapidOCR downloads both model weights and its character dictionary into this
# package directory. Redirect the entire asset directory to the writable cache.
RUN mkdir -p /cache/docling \
    && mv /usr/local/lib/python3.13/site-packages/rapidocr/models /cache/docling/rapidocr \
    && ln -s /cache/docling/rapidocr /usr/local/lib/python3.13/site-packages/rapidocr/models \
    && chown -R app:app /cache
COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/cache/uv \
    uv sync --locked --no-dev --extra web --extra rag --no-editable

FROM dependencies AS tools
RUN --mount=type=cache,target=/cache/uv \
    uv sync --locked --extra web --extra rag --extra dev
COPY tests ./tests
COPY examples ./examples
COPY deploy ./deploy
COPY deploy/toolbox.sh /usr/local/bin/toolbox
RUN chown -R app:app /app
USER app
ENTRYPOINT ["/bin/sh", "/usr/local/bin/toolbox", "python"]
CMD ["pytest", "-q"]

FROM dependencies AS runtime
USER app
EXPOSE 8000
CMD ["uvicorn", "science_agent_web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "25"]
