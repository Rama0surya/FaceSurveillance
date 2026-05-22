#!/usr/bin/env python3
"""
MJPEG Stream Stress Test for Face Surveillance Dashboard.

Opens N concurrent HTTP connections to /api/stream/video/{camera_id}
and measures: frame rate, bytes received, connection stability.

Usage:
    pip install aiohttp

    # 30 clients, 60 seconds
    python mjpeg_stress_test.py --url http://localhost:8000 --cameras cam1 cam2 --clients 30 --duration 60
"""

import argparse
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

try:
    import aiohttp
except ImportError:
    print("ERROR: 'aiohttp' package required. Install with: pip install aiohttp")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("mjpeg-stress")


@dataclass
class ClientResult:
    """Result from a single MJPEG client."""
    client_id: int = 0
    camera_id: str = ""
    frames: int = 0
    fps: float = 0.0
    mb_received: float = 0.0
    duration_s: float = 0.0
    error: str = ""


@dataclass
class AggregateStats:
    """Aggregate statistics across all clients."""
    connected: int = 0
    total_clients: int = 0
    results: list = field(default_factory=list)
    errors: list = field(default_factory=list)


async def mjpeg_client(
    session: aiohttp.ClientSession,
    url: str,
    client_id: int,
    camera_id: str,
    duration: float,
    stats: AggregateStats,
):
    """Single MJPEG client — consume frames for `duration` seconds."""
    frame_count = 0
    bytes_received = 0
    start = time.time()
    result = ClientResult(client_id=client_id, camera_id=camera_id)

    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=None, connect=10)
        ) as resp:
            if resp.status != 200:
                result.error = f"HTTP {resp.status}"
                stats.errors.append(f"Client {client_id}: HTTP {resp.status}")
                stats.results.append(result)
                return

            stats.connected += 1
            logger.debug("Client %d connected to %s", client_id, url)

            buffer = b""

            async for chunk in resp.content.iter_any():
                elapsed = time.time() - start
                if elapsed > duration:
                    break

                buffer += chunk
                bytes_received += len(chunk)

                # Count JPEG frames by looking for JPEG SOI marker (0xFF 0xD8)
                while b"\xff\xd8" in buffer:
                    soi = buffer.index(b"\xff\xd8")
                    # Find JPEG EOI marker (0xFF 0xD9)
                    eoi_pos = buffer.find(b"\xff\xd9", soi + 2)
                    if eoi_pos == -1:
                        break  # incomplete frame — wait for more data
                    frame_count += 1
                    buffer = buffer[eoi_pos + 2:]

                # Prevent buffer from growing unbounded
                if len(buffer) > 10 * 1024 * 1024:  # 10 MB safety cap
                    buffer = buffer[-1024 * 1024:]  # keep last 1 MB

    except asyncio.TimeoutError:
        result.error = "timeout"
    except aiohttp.ClientError as e:
        result.error = f"{type(e).__name__}: {e}"
        stats.errors.append(f"Client {client_id}: {result.error}")
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        stats.errors.append(f"Client {client_id}: {result.error}")

    elapsed = time.time() - start
    result.frames = frame_count
    result.fps = round(frame_count / max(elapsed, 0.1), 1)
    result.mb_received = round(bytes_received / 1e6, 2)
    result.duration_s = round(elapsed, 1)
    stats.results.append(result)


async def run_mjpeg_stress(
    base_url: str,
    camera_ids: list,
    num_clients: int,
    duration: float,
):
    """Run the MJPEG stress test."""
    stats = AggregateStats(total_clients=num_clients)

    connector = aiohttp.TCPConnector(limit=num_clients + 10, force_close=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for i in range(num_clients):
            cam_id = camera_ids[i % len(camera_ids)]
            url = f"{base_url}/api/stream/video/{cam_id}"
            tasks.append(
                mjpeg_client(session, url, i, cam_id, duration, stats)
            )

        logger.info(
            "Starting %d MJPEG clients across %d cameras for %.0fs ...",
            num_clients, len(camera_ids), duration,
        )
        await asyncio.gather(*tasks, return_exceptions=True)

    return stats


def build_summary(stats: AggregateStats) -> dict:
    """Build a summary report from aggregate stats."""
    all_fps = [r.fps for r in stats.results if r.fps > 0]
    all_frames = [r.frames for r in stats.results]
    total_mb = sum(r.mb_received for r in stats.results)

    # Per-camera breakdown
    camera_stats = {}
    for r in stats.results:
        if r.camera_id not in camera_stats:
            camera_stats[r.camera_id] = {"clients": 0, "fps_values": [], "frames": 0}
        camera_stats[r.camera_id]["clients"] += 1
        camera_stats[r.camera_id]["fps_values"].append(r.fps)
        camera_stats[r.camera_id]["frames"] += r.frames

    per_camera = {}
    for cam_id, cs in camera_stats.items():
        fps_vals = cs["fps_values"]
        per_camera[cam_id] = {
            "clients": cs["clients"],
            "avg_fps": round(sum(fps_vals) / max(len(fps_vals), 1), 1),
            "min_fps": round(min(fps_vals), 1) if fps_vals else 0,
            "total_frames": cs["frames"],
        }

    return {
        "total_clients": stats.total_clients,
        "connected": stats.connected,
        "connection_rate_pct": round(
            stats.connected / max(stats.total_clients, 1) * 100, 1
        ),
        "total_frames": sum(all_frames),
        "avg_fps": round(sum(all_fps) / max(len(all_fps), 1), 1) if all_fps else 0,
        "min_fps": round(min(all_fps), 1) if all_fps else 0,
        "max_fps": round(max(all_fps), 1) if all_fps else 0,
        "total_data_mb": round(total_mb, 2),
        "per_camera": per_camera,
        "errors_sample": stats.errors[:10],
    }


def main():
    parser = argparse.ArgumentParser(
        description="MJPEG Stream Stress Test for Face Surveillance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python mjpeg_stress_test.py --clients 30 --duration 60
  python mjpeg_stress_test.py --url http://192.168.1.100:8000 --cameras cam1 cam2 --clients 50 --duration 300
        """,
    )
    parser.add_argument("--url", default="http://localhost:8000",
                        help="Backend base URL (default: http://localhost:8000)")
    parser.add_argument("--cameras", nargs="+", default=["cam1"],
                        help="Camera IDs to distribute clients across")
    parser.add_argument("--clients", type=int, default=30,
                        help="Number of concurrent MJPEG clients (default: 30)")
    parser.add_argument("--duration", type=float, default=60,
                        help="Test duration in seconds (default: 60)")
    parser.add_argument("--output", default="mjpeg_stress_results.json",
                        help="Output file for results JSON")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  MJPEG STREAM STRESS TEST")
    print(f"  Target: {args.url}")
    print(f"  Cameras: {args.cameras}")
    print(f"  Clients: {args.clients}")
    print(f"  Duration: {args.duration}s")
    print(f"{'='*60}\n")

    stats = asyncio.run(run_mjpeg_stress(
        args.url, args.cameras, args.clients, args.duration
    ))

    summary = build_summary(stats)

    print(f"\n{'='*60}")
    print(f"  MJPEG STRESS TEST RESULTS")
    print(f"{'='*60}")
    print(json.dumps(summary, indent=2))
    print(f"{'='*60}")

    # Pass/fail
    avg_fps = summary["avg_fps"]
    min_fps = summary["min_fps"]
    conn_rate = summary["connection_rate_pct"]

    passed = True
    if avg_fps < 2:
        print(f"\n  FAIL: avg FPS {avg_fps} < 2")
        passed = False
    if min_fps < 1 and summary["connected"] > 0:
        print(f"  WARNING: min FPS {min_fps} < 1")
    if conn_rate < 80:
        print(f"\n  FAIL: connection rate {conn_rate}% < 80%")
        passed = False

    if passed:
        print(f"\n  RESULT: PASS (avg={avg_fps} FPS, connections={conn_rate}%)")
    else:
        print(f"\n  RESULT: FAIL")

    with open(args.output, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Results saved to: {args.output}\n")


if __name__ == "__main__":
    main()
