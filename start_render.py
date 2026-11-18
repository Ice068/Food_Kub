"""Run and supervise Food Kub's web and API processes on one Render service."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
LOCAL_BACKEND = "http://127.0.0.1:8000"


class StartupError(RuntimeError):
    pass


def wait_for_backend(url: str, process: subprocess.Popen | None,
                     stopping: threading.Event, timeout: float = 120) -> bool:
    """Wait for the catalog, not merely an open TCP port or an imported app."""
    deadline = time.monotonic() + timeout
    last_failure = "not ready"
    while not stopping.is_set():
        if process is not None and process.poll() is not None:
            raise StartupError(
                f"Backend exited with code {process.returncode}. "
                "Check its traceback above, including Firebase credentials and Firestore access."
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise StartupError(f"Backend catalog did not become ready ({last_failure}).")
        try:
            with urlopen(f"{url}/api/menu", timeout=min(3, remaining)) as response:
                if response.status == 200 and isinstance(json.load(response), list):
                    return not stopping.is_set()
                last_failure = "invalid catalog response"
        except HTTPError as exc:
            last_failure = f"HTTP {exc.code}"
        except (URLError, OSError, ValueError) as exc:
            # Exception messages can contain URLs or credentials; report only the type.
            last_failure = type(exc).__name__
        stopping.wait(min(0.5, max(0, deadline - time.monotonic())))
    return False


def stop_processes(processes: list[tuple[str, subprocess.Popen]]) -> None:
    """Stop both children on shutdown or failure, with a bounded grace period."""
    for _, process in reversed(processes):
        if process.poll() is None:
            try:
                process.terminate()
            except OSError as exc:
                print(f"Child termination failed ({type(exc).__name__}); continuing cleanup.",
                      file=sys.stderr, flush=True)
    deadline = time.monotonic() + 8
    for _, process in reversed(processes):
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired) as exc:
                print(f"Child cleanup failed ({type(exc).__name__}); continuing cleanup.",
                      file=sys.stderr, flush=True)


def run(stopping: threading.Event) -> int:
    processes: list[tuple[str, subprocess.Popen]] = []
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    demo = environment.get("FOOD_KUB_DEMO") == "1"
    backend_url = environment.get("FOOD_KUB_BACKEND_URL", LOCAL_BACKEND).rstrip("/")
    local_backend = backend_url in (LOCAL_BACKEND, "http://localhost:8000")
    if local_backend:
        backend_url = LOCAL_BACKEND
    environment["FOOD_KUB_BACKEND_URL"] = backend_url

    def launch(name: str, directory: str, host: str, port: int) -> subprocess.Popen:
        print(f"Starting Food_Kub {name} on {host}:{port}...", flush=True)
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", host,
             "--port", str(port), "--workers", "1"],
            cwd=ROOT / directory, env=environment,
        )
        processes.append((name, process))
        return process

    try:
        port = int(environment.get("PORT", "8001"))
        if not 1 <= port <= 65535 or (not demo and local_backend and port == 8000):
            raise StartupError("PORT must be a valid public port distinct from backend port 8000.")
        if not demo:
            backend = launch("Backend API", "blackend_py", "127.0.0.1", 8000) if local_backend else None
            print("Waiting for the backend catalog to become ready...", flush=True)
            if not wait_for_backend(backend_url, backend, stopping):
                return 0
            print("Backend catalog is ready.", flush=True)
        else:
            print("Explicit demo mode: using local SQLite; Firebase backend is disabled.", flush=True)
        if stopping.is_set():
            return 0
        launch("Frontend Web", "front_py", "0.0.0.0", port)
        while not stopping.is_set():
            for name, process in processes:
                if process.poll() is not None:
                    raise StartupError(f"{name} exited with code {process.returncode}; stopping the service.")
            stopping.wait(0.5)
        return 0
    except StartupError as exc:
        print(f"Food_Kub startup failed: {exc}", file=sys.stderr, flush=True)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Food_Kub launcher failed ({type(exc).__name__}). Check PORT and runtime configuration.",
              file=sys.stderr, flush=True)
        return 1
    finally:
        stop_processes(processes)


def main() -> int:
    stopping = threading.Event()

    def handle_stop(signum, frame):
        stopping.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, handle_stop)
    return run(stopping)


if __name__ == "__main__":
    sys.exit(main())
