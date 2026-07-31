# QueryTrace — CPU-only image. Embeddings run on ONNX Runtime via fastembed
# (Fase 5 Etapa A) — no torch in the image anymore.
FROM python:3.11-slim

# Model caches live at fixed paths (outside any $HOME) so the build-time
# download is what the runtime user reads — no cache copying needed.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed_cache \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the ONNX embedding model and the tiktoken encoding at build
# time so the container serves its first request without a cold-start download.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')"
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

COPY src/ src/
COPY frontend/ frontend/
COPY corpora/ corpora/
COPY artifacts/ artifacts/

# Non-root user; needs ownership of the model caches downloaded above
# (huggingface_hub takes lock files inside the cache dir even on reads).
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /opt/fastembed_cache /opt/tiktoken_cache /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",8000)}/health')" || exit 1

CMD uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
