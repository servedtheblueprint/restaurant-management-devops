import json
import logging
import os
import sys
import time

from flask import Flask, Response, jsonify, render_template, request

from . import metrics
from .db import close_db, get_db, init_db, seed_demo
from .routes import bp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_version():
    env = os.environ.get("APP_VERSION")
    if env:
        return env
    try:
        with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "dev"


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload)


def setup_logging(app):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    app.logger.handlers = [handler]
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False


def create_app(config=None):
    app = Flask(__name__)
    app.config["DB_PATH"] = os.environ.get("DB_PATH", "restaurant.db")
    app.config["VERSION"] = read_version()
    if config:
        app.config.update(config)

    if not app.config.get("TESTING"):
        setup_logging(app)

    init_db(app.config["DB_PATH"])
    if os.environ.get("SEED_DEMO") == "1":
        seed_demo(app.config["DB_PATH"])

    app.teardown_appcontext(close_db)
    app.register_blueprint(bp)

    @app.before_request
    def _start_timer():
        request.environ["_t0"] = time.perf_counter()

    @app.after_request
    def _record(response):
        elapsed = time.perf_counter() - request.environ.get("_t0", time.perf_counter())
        rule = request.url_rule.rule if request.url_rule else "unmatched"
        metrics.observe_request(request.method, rule, response.status_code, elapsed)
        if rule not in ("/metrics", "/health"):
            app.logger.info(
                "request",
                extra={"extra_fields": {
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round(elapsed * 1000, 2),
                }},
            )
        return response

    @app.get("/")
    def index():
        return render_template("index.html", version=app.config["VERSION"])

    @app.get("/health")
    def health():
        try:
            get_db().execute("SELECT 1").fetchone()
        except Exception:  # noqa: BLE001
            return jsonify(status="unhealthy"), 503
        return jsonify(status="ok", version=app.config["VERSION"])

    @app.get("/metrics")
    def prometheus_metrics():
        return Response(
            metrics.render(app.config["VERSION"]),
            mimetype="text/plain; version=0.0.4",
        )

    return app
