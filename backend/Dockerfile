# ==========================================================================
# Backend Dockerfile — Face Surveillance
# ==========================================================================

FROM python:3.11-slim

ARG USE_GPU=false

WORKDIR /app

# --------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# --------------------------------------------------------------------------
# System dependencies
# --------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    curl \
    ffmpeg \
    git \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# --------------------------------------------------------------------------
# Copy requirements first (better Docker cache)
# --------------------------------------------------------------------------
COPY requirements.txt .

# --------------------------------------------------------------------------
# Upgrade pip
# --------------------------------------------------------------------------
RUN pip install --upgrade pip setuptools wheel

# --------------------------------------------------------------------------
# Install requirements except onnxruntime
# --------------------------------------------------------------------------
RUN grep -vE "onnxruntime|onnxruntime-gpu" requirements.txt > /tmp/requirements.txt && \
    pip install -r /tmp/requirements.txt

# --------------------------------------------------------------------------
# Install ONNX Runtime
# --------------------------------------------------------------------------
RUN if [ "$USE_GPU" = "true" ]; then \
        echo "Installing onnxruntime-gpu..." && \
        pip install onnxruntime-gpu>=1.17.0; \
    else \
        echo "Installing onnxruntime CPU..." && \
        pip install onnxruntime>=1.17.0; \
    fi

# --------------------------------------------------------------------------
# Copy app source
# --------------------------------------------------------------------------
COPY . .

# --------------------------------------------------------------------------
# Create snapshot directory
# --------------------------------------------------------------------------
RUN mkdir -p /app/snapshots

# --------------------------------------------------------------------------
# Healthcheck
# --------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
CMD curl -f http://localhost:8000/api/settings/health || exit 1

# --------------------------------------------------------------------------
# Expose FastAPI port
# --------------------------------------------------------------------------
EXPOSE 8000

# --------------------------------------------------------------------------
# Run app
# --------------------------------------------------------------------------
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]