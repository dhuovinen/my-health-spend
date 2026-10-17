# One image for every Release 1 service (app, worker, vault, setup, migrate); the `test` stage adds the suite.
FROM python:3.12-slim AS runtime
# Tesseract reads photos and scanned PDFs in the application tier (ADR-029, MHS_OCR_ENGINE=tesseract).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /srv/mhs
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY schema ./schema
COPY samples ./samples
RUN uv sync --frozen --no-dev \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin mhs \
    && mkdir -p /srv/objects /backups && chown mhs:mhs /srv/objects /backups
USER 10001
EXPOSE 3063

FROM runtime AS test
USER root
RUN uv sync --frozen
COPY tests ./tests
COPY tools ./tools
USER 10001
CMD ["pytest", "-q"]
