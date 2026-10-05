"""Tiny Prometheus-format metrics (no external dependency)."""
import threading

_lock = threading.Lock()
_requests = {}
_duration = {"sum": 0.0, "count": 0}
_orders_created = 0


def observe_request(method, path, status, seconds):
    with _lock:
        key = (method, path, str(status))
        _requests[key] = _requests.get(key, 0) + 1
        _duration["sum"] += seconds
        _duration["count"] += 1


def order_created():
    global _orders_created
    with _lock:
        _orders_created += 1


def render(version):
    lines = [
        "# HELP restaurant_app_info Application version info",
        "# TYPE restaurant_app_info gauge",
        'restaurant_app_info{version="%s"} 1' % version,
        "# HELP restaurant_http_requests_total Total HTTP requests",
        "# TYPE restaurant_http_requests_total counter",
    ]
    with _lock:
        for (method, path, status), value in sorted(_requests.items()):
            lines.append(
                'restaurant_http_requests_total{method="%s",path="%s",status="%s"} %d'
                % (method, path, status, value)
            )
        lines += [
            "# HELP restaurant_http_request_duration_seconds Request duration",
            "# TYPE restaurant_http_request_duration_seconds summary",
            "restaurant_http_request_duration_seconds_sum %f" % _duration["sum"],
            "restaurant_http_request_duration_seconds_count %d" % _duration["count"],
            "# HELP restaurant_orders_created_total Orders created",
            "# TYPE restaurant_orders_created_total counter",
            "restaurant_orders_created_total %d" % _orders_created,
        ]
    return "\n".join(lines) + "\n"
