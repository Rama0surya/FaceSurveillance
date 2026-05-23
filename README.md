# Face Surveillance Dashboard

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql)
![FastAPI](https://img.shields.io/badge/FastAPI-Production-009688?logo=fastapi)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)

> **Advanced AI-Powered CCTV Monitoring System.**  
> Transform any standard RTSP camera into a smart surveillance network with real-time demographic and emotion analytics.

## ✨ 6 Core AI Capabilities

1. **Real-Time Demographic Analysis** — Instantly identify faces, estimating **Age, Gender, and Emotion** directly from live camera feeds.
2. **AI Semantic Search (CLIP)** — Search captured faces using natural language descriptions (e.g. "man with glasses", "happy child") or image files (reverse face search).
3. **Automated Evidence Logging** — All detection events and face crop snapshots (with CLIP embeddings) are automatically persisted into the database.
4. **Universal Camera Integration** — Seamlessly connect any custom IP camera or NVR simply by pasting its **RTSP link**.
5. **1-Click Production Deployment** — Launch the entire stack (AI models, Backend, Frontend, MySQL database) instantly using a single `docker compose up` command.
6. **Enterprise-Grade Scalability** — Designed for heavy loads with GPU acceleration, multi-worker API support, and MediaMTX stream multiplexing.

---

## 🏗️ System Architecture

The system is fully self-contained using Docker, ensuring zero external dependencies and maximum data privacy. The entire architecture runs locally.

| Component      | Technology                                          |
|----------------|-----------------------------------------------------|
| **Frontend**   | React 18, Vite, TypeScript, Vanilla CSS             |
| **Backend**    | FastAPI, Python 3.11, WebSocket (Multi-Worker)      |
| **AI/ML Core** | YOLOv8 (Detect), ByteTrack (Track), InsightFace/DeepFace (Demographics), OpenCLIP (AI Search) |
| **Streaming**  | MediaMTX (RTSP Proxy)                               |
| **Database**   | MySQL 8.0 (Containerized) with vector indexing      |
| **Deployment** | Docker Compose, NVIDIA Container Toolkit (GPU)      |

---

## 📋 Prerequisites

- **Docker** Engine (v24.0+)
- **Docker Compose** (v2.20+)
- **NVIDIA GPU** & NVIDIA Container Toolkit (Optional, for AI GPU acceleration)

---

## 🚀 1-Click Deployment

Deployment is designed to be fully automated. The MySQL database will initialize its schema automatically on the first run using the provided initialization script.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Rama0surya/FaceSurveillance.git
   cd face-surveillance
   ```

2. **Prepare the Database Schema:**
   Ensure the database schema file `init.sql` is present in the root directory. Docker Compose will automatically mount and execute this script upon first database startup to create all tables (cameras, detections, snapshots, alerts, settings, etc.) with the correct CLIP embedding configurations.

3. **Deploy the stack:**
   ```bash
   # Standard CPU Deployment
   docker compose up -d --build

   # GPU-Accelerated Deployment (Requires NVIDIA Toolkit)
   docker compose build --build-arg USE_GPU=true backend
   docker compose up -d
   ```

4. **Access the Dashboard:**
   Open your browser and navigate to:
   - **Frontend Dashboard:** `http://localhost:5173`
   - **Backend API Docs:** `http://localhost:8000/docs`

---

## 📹 Custom Camera Integration (RTSP)

Integrating your own custom cameras is incredibly straightforward.

1. Find the RTSP URL of your IP Camera (e.g., `rtsp://admin:password@192.168.1.100:554/stream1`).
2. Open the Face Surveillance Dashboard.
3. Navigate to **Cameras** > **Add Camera**.
4. Give it a name and paste your **RTSP URL**.
5. Click **Start Stream**. The AI will immediately proxy the stream via MediaMTX, begin analyzing the feed, and log detections to the MySQL database.

---

## ⚡ Stress Testing & Load Simulation

The provided `docker-compose.yml` is explicitly configured with memory limits and a multi-worker FastAPI setup to accommodate stress testing. Here is how you can benchmark the system limits:

### 1. AI Tracking & Video Processing Stress Test (FFmpeg)
Simulate multiple high-resolution camera streams simultaneously to test the AI pipeline's multi-threading and GPU limitations:

```bash
# Terminal 1: Simulate Camera 1
ffmpeg -re -stream_loop -1 -i test_video.mp4 -c copy -f rtsp rtsp://localhost:8554/cam1

# Terminal 2: Simulate Camera 2
ffmpeg -re -stream_loop -1 -i test_video.mp4 -c copy -f rtsp rtsp://localhost:8554/cam2

# Terminal 3: Simulate Camera 3
ffmpeg -re -stream_loop -1 -i test_video.mp4 -c copy -f rtsp rtsp://localhost:8554/cam3
```
*Tip: Monitor GPU Usage using `watch nvidia-smi` or `nvtop` to observe VRAM allocation per RTSP stream.*

### 2. API & Database Stress Test (Locust)
Test the backend's ability to handle high-frequency database reads/writes and concurrent WebSocket connections.

1. Install Locust: 
   ```bash
   pip install locust
   ```
2. Create a `locustfile.py` to hit the heaviest endpoints:
   ```python
   from locust import HttpUser, task, between

   class APIUser(HttpUser):
       wait_time = between(0.5, 2)

       @task(3)
       def fetch_stats(self):
           self.client.get("/api/stats/today")

       @task(1)
       def fetch_detections(self):
           self.client.get("/api/detections?limit=100")
   ```
3. Run the stress test:
   ```bash
   locust -f locustfile.py --host=http://localhost:8000
   ```
4. Access the Locust dashboard at `http://localhost:8089` to simulate thousands of concurrent users hitting the MySQL database and API.
