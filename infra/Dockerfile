# Runtime image for the complete OracleAI stack.
# The same image is used by API, Telegram bot, Celery worker and Beat so that
# every process runs identical application, LLM-agent and local-engine code.
# Frontend bundles are built in a separate Node stage and copied into the Python image.
FROM node:22.19.0-bookworm-slim AS frontend-builder
WORKDIR /opt/oracle
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit
COPY miniapp ./miniapp
COPY scripts/build_frontend.mjs ./scripts/build_frontend.mjs
RUN npm run build:frontend

FROM python:3.12-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/opt/oracle/data \
    PYTHONPATH=/opt/oracle

# Native libraries required by WeasyPrint, Pillow, OpenCV/ONNX and timezone data.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
        libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
        libffi8 shared-mime-info \
        libjpeg62-turbo zlib1g \
        libgl1 libglib2.0-0 \
        fonts-dejavu-core \
        gcc g++ libc6-dev pkg-config \
        curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/oracle

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code and every resource referenced at runtime. In particular,
# models/ is required by the palm-line ONNX and MediaPipe adapters, while web/
# is served by FastAPI as the public landing/SEO surface.
COPY app ./app
COPY miniapp ./miniapp
COPY --from=frontend-builder /opt/oracle/miniapp/dist ./miniapp/dist
COPY admin ./admin
COPY web ./web
COPY models ./models
COPY prompts ./prompts
COPY scripts ./scripts
COPY alembic ./alembic
COPY docs ./docs
COPY data ./data
COPY .github ./.github
COPY Makefile ./Makefile
COPY .env.example .env.production.example ./
COPY alembic.ini ./

RUN useradd --create-home --uid 10001 oracle \
    && mkdir -p /opt/oracle/data \
    && chown -R oracle:oracle /opt/oracle
USER oracle

# Keep the default command useful for the simplest local deployment.
CMD ["python", "-m", "app.bot.main"]
