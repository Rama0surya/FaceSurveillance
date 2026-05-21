# ==========================================================================
# Backend Dockerfile — Face Surveillance (Raspberry Pi / aarch64)
# ==========================================================================
FROM python:3.11-slim

ARG USE_GPU=false

WORKDIR /app

# System deps — curl for healthcheck, build tools for C extensions
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    python3-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install torch CPU-only FIRST — prevents ultralytics/deepface
# from pulling in 1.8 GB of CUDA libs on a Pi with no GPU
RUN pip install --no-cache-dir \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

# Copy and install remaining requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Conditional onnxruntime: pinned exact versions
RUN if [ "$USE_GPU" = "true" ]; then \
        pip install --no-cache-dir onnxruntime-gpu==1.18.0; \
    else \
        pip install --no-cache-dir onnxruntime==1.18.0; \
    fi

# Non-root user for security
RUN useradd -m -u 1000 appuser

# Pre-create InsightFace model directory with correct ownership
# so the volume mount is writable by appuser at runtime
RUN mkdir -p /home/appuser/.insightface/models && \
    chown -R appuser:appuser /home/appuser/.insightface

# Set Ultralytics config dir to a writable location
ENV YOLO_CONFIG_DIR=/tmp/yolo

# Copy application code
COPY --chown=appuser:appuser . .

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]