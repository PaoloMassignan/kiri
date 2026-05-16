FROM python:3.11-slim

# build tools needed by sentence-transformers (tokenizers Rust extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install dependencies before copying source so layer is cached
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir -e .

# copy source
COPY src/ src/

# sentence-transformers model cache stays inside the volume mount so it
# survives container restarts
ENV SENTENCE_TRANSFORMERS_HOME=/workspace/.kiri/models
ENV PYTHONPATH=/app
ENV WORKSPACE=/workspace

EXPOSE 8765

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

# gateway serve binds to 127.0.0.1 — correct for local dev but not for Docker
# (port forwarding needs 0.0.0.0 inside the container; the docker-compose.yml
# restricts the host-side binding to 127.0.0.1:8765 so the LAN is never exposed).
CMD ["python", "-m", "uvicorn", "src.main:create_gateway_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8765"]
