"""Local, single-user teaching server. Run: python server/app.py"""
import atexit
import copy
import math
import os
import random
import threading
import time
from pathlib import Path

# Set before loading the OpenMP runtime. Users can override OMP_NUM_THREADS.
os.environ.setdefault("OMP_NUM_THREADS", str(min(8, os.cpu_count() or 1)))
os.environ.setdefault("OMP_DYNAMIC", "FALSE")

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
try:
    from .native import Native, Simulation, BACKENDS
except ImportError:
    from native import Native, Simulation, BACKENDS

WEB = Path(__file__).resolve().parents[1] / "web"
app = Flask(__name__, static_folder=str(WEB), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
native = Native()
lock = threading.RLock()  # Never let two requests mutate the same native handle.
simulation = Simulation(native, 64, "cpu")
job = {"status": "idle", "rows": [], "progress": 0, "message": "Ready to benchmark"}
atexit.register(lambda: simulation.close())


def body():
    data = request.get_json()
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer from {low} to {high}")
    return value


def number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be a finite number from {low} to {high}")
    return value


def settings(data, sim):
    ambient = number(data.get("ambient", sim.ambient), "ambient", 10, 45)
    threshold = number(data.get("threshold", sim.threshold), "threshold", 30, 120)
    tiled = data.get("tiled", sim.tiled)
    if type(tiled) is not bool:
        raise ValueError("tiled must be true or false")
    return ambient, threshold, tiled


def selection(data, n):
    if "indices" in data and "rectangle" in data:
        raise ValueError("Send indices OR rectangle")
    if "rectangle" in data:
        rect = data["rectangle"]
        if not isinstance(rect, dict) or set(rect) != {"r0", "c0", "r1", "c1"}:
            raise ValueError("rectangle requires r0, c0, r1, c1 (inclusive)")
        r0, c0, r1, c1 = [integer(rect[k], k, 0, n - 1) for k in ("r0", "c0", "r1", "c1")]
        if r0 > r1 or c0 > c1:
            raise ValueError("Rectangle bounds must be ordered")
        return [r * n + c for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
    indices = data.get("indices")
    if not isinstance(indices, list) or not 1 <= len(indices) <= n * n:
        raise ValueError("Select at least one cell, up to N*N indices")
    return sorted({integer(i, "cell index", 0, n * n - 1) for i in indices})


def ensure_idle():
    if job["status"] == "running":
        raise RuntimeError("Benchmark is running. Live changes are paused until it finishes.")


@app.errorhandler(Exception)
def error(exc):
    if isinstance(exc, HTTPException):
        return jsonify(error=exc.description), exc.code
    if isinstance(exc, ValueError):
        return jsonify(error=str(exc)), 400
    if isinstance(exc, RuntimeError):
        return jsonify(error=str(exc)), 409
    app.logger.exception("Unexpected server error")
    return jsonify(error="Unexpected server error; see the terminal."), 500


@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/benchmark-page")
def benchmark_page():
    return send_from_directory(WEB, "benchmark.html")


@app.get("/info")
def info():
    return jsonify(native.info())


@app.post("/init")
def initialize():
    global simulation
    data = body()
    size = integer(data.get("size", 64), "size", 64, 512)
    backend = data.get("backend", "cpu")
    if size not in (64, 128, 256, 512) or not isinstance(backend, str) or backend not in BACKENDS:
        raise ValueError("Choose size 64/128/256/512 and backend cpu/openmp/cuda")
    with lock:
        ensure_idle()
        config = settings(data, simulation)
        replacement = Simulation(native, size, backend)
        try:
            replacement.configure(*config)
        except Exception:
            replacement.close()
            raise
        old, simulation = simulation, replacement
        old.close()
        return jsonify(ok=True)


@app.post("/step")
def step():
    data = body()
    count = integer(data.get("n", 1), "n", 0, 100)
    with lock:
        ensure_idle()
        if any(k in data for k in ("ambient", "threshold", "tiled")):
            simulation.configure(*settings(data, simulation))
        if count:
            simulation.step(count)
        return jsonify(stats=simulation.stats())


@app.get("/frame")
def frame():
    with lock:
        return jsonify(simulation.frame())


@app.post("/modify")
def modify():
    data = body()
    with lock:
        ensure_idle()
        indices = selection(data, simulation.size)
        values = data.get("values")
        limits = {"temperature": (-100, 500), "workload": (0, 100),
                  "cooling": (0, 100), "delta": (-100, 100)}
        if not isinstance(values, dict) or not values or not set(values) <= limits.keys():
            raise ValueError("values must contain temperature, workload, cooling and/or delta")
        values = {k: number(v, k, *limits[k]) for k, v in values.items()}
        simulation.modify(indices, values)
        return jsonify(updated=len(indices), stats=simulation.stats())


@app.post("/preset")
def preset():
    data = body()
    name = data.get("name")
    if name not in ("normal", "hot-aisle", "cooling-failure", "cooling-boost", "random-spikes"):
        raise ValueError("Unknown preset")
    with lock:
        ensure_idle()
        n = simulation.size
        # A selection takes precedence; otherwise use the central quarter.
        indices = selection(data, n) if "indices" in data or "rectangle" in data else [
            r * n + c for r in range(n // 4, 3 * n // 4) for c in range(n // 4, 3 * n // 4)]
        if name == "normal":
            indices = list(range(n * n))
            simulation.modify(indices, {"temperature": 25, "workload": 50, "cooling": 50})
        elif name == "hot-aisle":
            simulation.modify(indices, {"workload": 100, "cooling": 5})
        elif name == "cooling-failure":
            simulation.modify(indices, {"cooling": 0})
        elif name == "cooling-boost":
            simulation.modify(indices, {"cooling": 100})
        else:
            indices = random.Random(2026 + simulation.stats()["step"]).sample(
                range(n * n), max(1, n * n // 50))
            simulation.modify(indices, {"temperature": 95, "workload": 100, "cooling": 10})
        return jsonify(indices=indices, stats=simulation.stats())


def benchmark_worker(sizes, steps, tiled):
    """Fresh state per backend; warm-up/setup/transfers are outside timing."""
    available = ["cpu", "openmp"] + (["cuda"] if native.info()["cuda_available"] else [])
    total, completed = len(sizes) * len(available), 0
    try:
        for n in sizes:
            runs = {}
            for backend in available:
                with lock:
                    job["message"] = f"{n} × {n} · {backend.upper()} · {steps} steps"
                # Warm up kernels, thread team and caches, then discard that state.
                with Simulation(native, n, backend) as warm:
                    warm.configure(tiled=tiled)
                    warm.step(5)
                with Simulation(native, n, backend) as sim:
                    sim.configure(tiled=tiled)
                    # Stress both hotspot classification and throttling, identically.
                    center = [r * n + c for r in range(n // 4, n // 2)
                              for c in range(n // 4, n // 2)]
                    sim.modify(center, {"temperature": 90, "workload": 95, "cooling": 10})
                    start = time.perf_counter()
                    sim.step(steps)
                    wall_ms = (time.perf_counter() - start) * 1000 / steps
                    stats = sim.stats()  # Tiny CUDA result transfer is outside timing.
                    runs[backend] = {"ms": wall_ms, "compute_ms": stats["milliseconds"], "stats": stats}
                completed += 1
                with lock:
                    job["progress"] = round(completed / total * 100)
            reference = runs["cpu"]["stats"]
            errors = {b: abs(v["stats"]["maximum"] - reference["maximum"]) for b, v in runs.items()}
            verified = all(error <= 0.001 for error in errors.values())
            row = {"size": n, "runs": runs, "verified": verified,
                   "max_temperature_errors": errors,
                   "speedups": {b: runs["cpu"]["ms"] / v["ms"] for b, v in runs.items()}}
            with lock:
                job["rows"].append(row)
        with lock:
            job.update(status="done", progress=100,
                       message="Finished. See the results verification below.")
    except Exception as exc:
        app.logger.exception("Benchmark failed")
        with lock:
            job.update(status="error", message=str(exc))


@app.route("/benchmark", methods=["GET", "POST"])
def benchmark():
    global job
    if request.method == "GET":
        with lock:
            return jsonify(copy.deepcopy(job))
    data = body()
    steps = integer(data.get("steps", 100), "steps", 1, 1000)
    sizes = data.get("sizes", [128, 256, 512, 1024, 2048])
    if not isinstance(sizes, list) or not sizes or len(sizes) > 5:
        raise ValueError("sizes must be a nonempty list of up to five benchmark sizes")
    for n in sizes:
        integer(n, "benchmark size", 128, 2048)
        if n not in (128, 256, 512, 1024, 2048):
            raise ValueError("Benchmark sizes: 128, 256, 512, 1024, 2048")
    tiled = data.get("tiled", False)
    if type(tiled) is not bool:
        raise ValueError("tiled must be true or false")
    with lock:
        ensure_idle()
        job = {"status": "running", "rows": [], "progress": 0, "message": "Warming up…",
               "steps": steps, "tiled": tiled, "info": native.info()}
        threading.Thread(target=benchmark_worker, args=(sorted(set(sizes)), steps, tiled), daemon=True).start()
        return jsonify(copy.deepcopy(job)), 202


if __name__ == "__main__":
    print("Open http://127.0.0.1:5000 · Ctrl+C to stop")
    app.run(host="127.0.0.1", port=5000, threaded=True, debug=False)
