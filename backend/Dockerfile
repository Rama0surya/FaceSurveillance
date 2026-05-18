# ==========================================================================
# Backend Dockerfile — Face Surveillance
# ==========================================================================
# Supports optional GPU acceleration via build argument.
#
# CPU build (default):
#   docker build -t face-backend .
#
# GPU build (requires NVIDIA Container Toolkit on host):
#   docker build --build-arg USE_GPU=true -t face-backend-gpu .
# ==========================================================================

FROM python:3.11-slim

ARG USE_GPU=false

WORKDIR /app

# System dependencies for OpenCV, DeepFace, ffmpeg, and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .

# Install all requirements EXCEPT onnxruntime variants (handled below)
RUN pip install --no-cache-dir $(grep -vE "onnxruntime" requirements.txt)

# Conditional onnxruntime install: GPU or CPU
RUN if [ "$USE_GPU" = "true" ]; then \
        echo "Installing onnxruntime-gpu for CUDA support..." && \
        pip install --no-cache-dir onnxruntime-gpu>=1.17.0; \
    else \
        echo "Installing onnxruntime (CPU only)..." && \
        pip install --no-cache-dir onnxruntime>=1.17.0; \
    fi

# Copy application code
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
