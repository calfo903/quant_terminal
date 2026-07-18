"""Lightweight in-process operational metrics (standard 5.2).

No external dependency (Prometheus client not required). Exposes a
Prometheus-compatible text exposition via get_text() and a snapshot() dict
for JSON scrapers. All updates are thread-safe.
"""
import os
import platform
import threading
import time
from collections import defaultdict

_start_time = time.time()
_lock = threading.Lock()

_req_total = 0
_req_errors = 0
_req_lat_sum = 0.0
_req_lat_count = 0
_status = defaultdict(int)
_methods = defaultdict(int)
_counters = defaultdict(int)


def record_request(latency: float, status_code: int, method: str = "GET") -> None:
    global _req_total, _req_errors, _req_lat_sum, _req_lat_count
    with _lock:
        _req_total += 1
        _methods[method] += 1
        _status[status_code] += 1
        if status_code >= 500:
            _req_errors += 1
        _req_lat_sum += latency
        _req_lat_count += 1


def inc(name: str, n: int = 1) -> None:
    with _lock:
        _counters[name] += n


def snapshot() -> dict:
    with _lock:
        return {
            "uptime_seconds": round(time.time() - _start_time, 3),
            "requests_total": _req_total,
            "request_errors_total": _req_errors,
            "request_latency_seconds_sum": round(_req_lat_sum, 3),
            "request_latency_seconds_count": _req_lat_count,
            "requests_by_status": dict(_status),
            "requests_by_method": dict(_methods),
            "counters": dict(_counters),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        }


def get_text() -> str:
    """Prometheus exposition format (subset)."""
    s = snapshot()
    lines = []
    lines.append("# HELP quant_uptime_seconds Process uptime in seconds")
    lines.append("# TYPE quant_uptime_seconds gauge")
    lines.append(f"quant_uptime_seconds {s['uptime_seconds']}")
    lines.append("# HELP quant_requests_total Total HTTP requests")
    lines.append("# TYPE quant_requests_total counter")
    lines.append(f"quant_requests_total {s['requests_total']}")
    lines.append("# HELP quant_request_errors_total Total 5xx responses")
    lines.append("# TYPE quant_request_errors_total counter")
    lines.append(f"quant_request_errors_total {s['request_errors_total']}")
    lines.append("# HELP quant_request_latency_seconds HTTP request latency")
    lines.append("# TYPE quant_request_latency_seconds histogram")
    lines.append(f"quant_request_latency_seconds_sum {s['request_latency_seconds_sum']}")
    lines.append(f"quant_request_latency_seconds_count {s['request_latency_seconds_count']}")
    for code, v in s["requests_by_status"].items():
        lines.append(f'quant_requests_by_status{{code="{code}"}} {v}')
    for method, v in s["requests_by_method"].items():
        lines.append(f'quant_requests_by_method{{method="{method}"}} {v}')
    for name, v in s["counters"].items():
        lines.append(f"# HELP quant_{name} custom counter ({name})")
        lines.append(f"# TYPE quant_{name} counter")
        lines.append(f"quant_{name} {v}")
    return "\n".join(lines) + "\n"


def reset() -> None:
    """Zero all counters. Used by tests and by process restarts."""
    global _req_total, _req_errors, _req_lat_sum, _req_lat_count
    with _lock:
        _req_total = 0
        _req_errors = 0
        _req_lat_sum = 0.0
        _req_lat_count = 0
        _status.clear()
        _methods.clear()
        _counters.clear()
