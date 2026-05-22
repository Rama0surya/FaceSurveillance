#!/usr/bin/env python3
"""
WebSocket Stress Test for Face Surveillance Dashboard.

Simulates N concurrent WebSocket clients connecting to:
  - /ws/stream/{camera_id}  (detection events)
  - /ws/stats               (global stats)

Measures: connection success rate, message throughput, latency, disconnects.

Usage:
    pip install websockets

    # 50 clients, 60 seconds
    python ws_stress_test.py --url ws://localhost:8000 --cameras cam1 cam2 --clients 50 --duration 60

    # 200 clients, 5 minutes (heavy stress)
    python ws_stress_test.py --url ws://localhost:8000 --cameras cam1 cam2 cam3 --clients 200 --duration 300
"""

import argparse
import asyncio
import json
import logging
import statistics
import time
from dataclasses import dataclass, field

try:
    import websockets
except ImportError:
    print("ERROR: 'websockets' package required. Install with: pip install websockets")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("ws-stress")


@dataclass
class StressResult:
    """Aggregated stress test results."""
    total_connections: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    total_messages_received: int = 0
    disconnects: int = 0
    latencies_ms: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    def summary(self) -> dict:
        duration = self.end_time - self.start_time
        lat = self.latencies_ms

        if lat:
            sorted_lat = sorted(lat)
            p95_idx = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)
            latency_stats = {
                "avg": round(statistics.mean(lat), 1),
                "p50": round(statistics.median(lat), 1),
                "p95": round(sorted_lat[p95_idx], 1),
                "max": round(max(lat), 1),
                "samples": len(lat),
            }
        else:
            latency_stats = {"avg": 0, "p50": 0, "p95": 0, "max": 0, "samples": 0}

        return {
            "duration_s": round(duration, 1),
            "total_connections": self.total_connections,
            "successful": self.successful_connections,
            "failed": self.failed_connections,
            "success_rate_pct": round(
                self.successful_connections / max(self.total_connections, 1) * 100, 1
            ),
            "total_messages": self.total_messages_received,
            "msg_per_sec": round(
                self.total_messages_received / max(duration, 0.1), 1
            ),
            "disconnects": self.disconnects,
            "latency_ms": latency_stats,
            "errors_sample": self.errors[:10],
        }


async def ws_client(
    url: str,
    client_id: int,
    duration: float,
    result: StressResult,
    semaphore: asyncio.Semaphore,
):
    """Single WebSocket client — connect, receive messages for `duration` seconds."""
    async with semaphore:
        result.total_connections += 1
        try:
            async with websockets.connect(
                url, open_timeout=10, close_timeout=5, ping_interval=20
            ) as ws:
                result.successful_connections += 1
                logger.debug("Client %d connected to %s", client_id, url)

                deadline = time.time() + duration
                while time.time() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        recv_time = time.time()
                        result.total_messages_received += 1

                        # Try to extract timestamp for latency measurement
                        try:
                            data = json.loads(msg)
                            if "timestamp" in data:
                                from datetime import datetime
                                ts_str = data["timestamp"]
                                if ts_str.endswith("Z"):
                                    ts_str = ts_str[:-1] + "+00:00"
                                sent_time = datetime.fromisoformat(ts_str).timestamp()
                                latency = (recv_time - sent_time) * 1000
                                if 0 < latency < 60000:  # sanity check
                                    result.latencies_ms.append(latency)
                        except (json.JSONDecodeError, ValueError, KeyError):
                            pass

                    except asyncio.TimeoutError:
                        continue  # no message, keep waiting
                    except websockets.ConnectionClosed:
                        result.disconnects += 1
                        logger.debug("Client %d disconnected", client_id)
                        break

        except Exception as e:
            result.failed_connections += 1
            err_msg = f"Client {client_id}: {type(e).__name__}: {e}"
            result.errors.append(err_msg)
            logger.debug("Client %d failed: %s", client_id, e)


async def run_stress_test(
    base_url: str,
    camera_ids: list,
    num_clients: int,
    duration: float,
    include_stats: bool = True,
    max_concurrent: int = 100,
):
    """Run the WebSocket stress test."""
    result = StressResult()
    result.start_time = time.time()
    semaphore = asyncio.Semaphore(max_concurrent)

    tasks = []

    # Stream WebSocket clients (distributed across cameras)
    for i in range(num_clients):
        cam_id = camera_ids[i % len(camera_ids)]
        url = f"{base_url}/ws/stream/{cam_id}"
        tasks.append(ws_client(url, i, duration, result, semaphore))

    # Stats WebSocket clients (10% of total)
    stats_count = 0
    if include_stats:
        stats_count = max(1, num_clients // 10)
        for i in range(stats_count):
            url = f"{base_url}/ws/stats"
            tasks.append(ws_client(url, 10000 + i, duration, result, semaphore))

    logger.info(
        "Starting %d WebSocket clients (%d stream + %d stats) for %.0fs ...",
        len(tasks), num_clients, stats_count, duration,
    )

    await asyncio.gather(*tasks, return_exceptions=True)
    result.end_time = time.time()

    return result


def main():
    parser = argparse.ArgumentParser(
        description="WebSocket Stress Test for Face Surveillance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ws_stress_test.py --clients 50 --duration 60
  python ws_stress_test.py --url ws://192.168.1.100:8000 --cameras cam1 cam2 --clients 200 --duration 300
        """,
    )
    parser.add_argument("--url", default="ws://localhost:8000",
                        help="WebSocket base URL (default: ws://localhost:8000)")
    parser.add_argument("--cameras", nargs="+", default=["cam1"],
                        help="Camera IDs to distribute clients across")
    parser.add_argument("--clients", type=int, default=50,
                        help="Number of concurrent WS clients (default: 50)")
    parser.add_argument("--duration", type=float, default=60,
                        help="Test duration in seconds (default: 60)")
    parser.add_argument("--max-concurrent", type=int, default=100,
                        help="Max simultaneous connections (default: 100)")
    parser.add_argument("--no-stats", action="store_true",
                        help="Skip /ws/stats connections")
    parser.add_argument("--output", default="ws_stress_results.json",
                        help="Output file for results JSON")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  WebSocket STRESS TEST")
    print(f"  Target: {args.url}")
    print(f"  Cameras: {args.cameras}")
    print(f"  Clients: {args.clients} (+stats)")
    print(f"  Duration: {args.duration}s")
    print(f"{'='*60}\n")

    result = asyncio.run(run_stress_test(
        base_url=args.url,
        camera_ids=args.cameras,
        num_clients=args.clients,
        duration=args.duration,
        include_stats=not args.no_stats,
        max_concurrent=args.max_concurrent,
    ))

    summary = result.summary()

    print(f"\n{'='*60}")
    print(f"  WebSocket STRESS TEST RESULTS")
    print(f"{'='*60}")
    print(json.dumps(summary, indent=2))
    print(f"{'='*60}")

    # Determine pass/fail
    success_rate = summary["success_rate_pct"]
    if success_rate >= 95:
        print(f"\n  RESULT: PASS (success rate {success_rate}%)")
    else:
        print(f"\n  RESULT: FAIL (success rate {success_rate}% < 95%)")

    # Write results to file
    with open(args.output, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Results saved to: {args.output}\n")


if __name__ == "__main__":
    main()
