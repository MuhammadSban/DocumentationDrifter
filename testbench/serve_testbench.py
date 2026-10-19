# serves the dedicated test bench dashboard and runs the existing CLI in owned subprocesses

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = Path(__file__).resolve().parent / "frontend"
RUN_ID = re.compile(r"\d{8}-\d{6}-\d{6}-(?:local|smoke|live)\Z")
RAILWAY = "https://documentationdrifter-production.up.railway.app"


class RunRequest(BaseModel):
    # accepts runner options rather than commands or paths supplied by a browser
    model_config = ConfigDict(extra="forbid")
    mode: Literal["local", "smoke", "live"] = "local"
    url: str = RAILWAY
    console_url: str = ""
    show_known_failures: bool = False

    @field_validator("url", "console_url")
    @classmethod
    def valid_url(cls, value):
        value = value.strip()
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use an http(s) URL without credentials, a query or a fragment")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("The URL port is invalid") from exc
        return value.rstrip("/")

    @model_validator(mode="after")
    def compatible_options(self):
        if self.mode != "local" and not self.url:
            raise ValueError("A hosted API URL is required")
        if self.console_url and self.mode != "live":
            raise ValueError("A deployed console URL is available only in Live mode")
        if self.show_known_failures and self.mode == "smoke":
            raise ValueError("Smoke mode does not run the known frontend defects")
        return self


class Bench:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.results = self.root / "testbench/results/bench"
        self.results.mkdir(parents=True, exist_ok=True)
        self.logs = self.root / "testbench/results/dashboard"
        self.lock = threading.RLock()
        self.job = None
        self.process = None
        self.worker = None
        self.closing = False

    def read_run(self, run_id):
        # resolves one known report folder without exposing arbitrary workspace files
        if not RUN_ID.fullmatch(run_id):
            raise HTTPException(404, "Run not found")
        folder = (self.results / run_id).resolve()
        if not folder.is_relative_to(self.results.resolve()):
            raise HTTPException(404, "Run not found")
        try:
            data = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
            if not isinstance(data.get("cases"), list) or not isinstance(data.get("counts"), dict):
                raise ValueError("Invalid summary")
        except (OSError, ValueError, TypeError, AttributeError):
            raise HTTPException(404, "Run summary is unavailable") from None
        artifacts = {name: f"/artifacts/{run_id}/{name}" for name in ("report.html", "results.xml", "summary.json", "console.txt") if (folder / name).is_file()}
        return {**data, "id": run_id, "artifacts": artifacts}

    def history(self):
        runs = []
        for folder in sorted(self.results.iterdir(), reverse=True):
            if not RUN_ID.fullmatch(folder.name):
                continue
            try:
                run = self.read_run(folder.name)
            except HTTPException:
                continue
            run["case_count"] = len(run.pop("cases"))
            runs.append(run)
        return runs

    def snapshot(self, offset=0):
        with self.lock:
            if self.job is None:
                return {"job": None, "log": "", "offset": 0}
            data = {key: value for key, value in self.job.items() if key not in {"output", "output_start", "monotonic"}}
            data["elapsed_seconds"] = round(time.monotonic() - self.job["monotonic"], 1) if data["status"] == "running" else data["elapsed_seconds"]
            output = self.job["output"]
            start = self.job["output_start"]
            offset = max(0, min(offset - start, len(output)))
            return {"job": data, "log": output[offset:], "offset": start + len(output)}

    def start(self, options):
        with self.lock:
            if self.closing:
                raise HTTPException(503, "The dashboard is shutting down")
            if self.job and self.job["status"] == "running":
                raise HTTPException(409, "A test run is already in progress")
            command = [sys.executable, str(self.root / "testbench/run_testbench.py"), "--mode", options.mode]
            if options.mode != "local":
                command.extend(["--url", options.url])
            if options.console_url:
                command.extend(["--console-url", options.console_url])
            if options.show_known_failures:
                command.append("--show-known-failures")
            self.logs.mkdir(parents=True, exist_ok=True)
            job_id = uuid.uuid4().hex
            log_path = self.logs / f"{job_id}.log"
            job_temp = self.logs / f"{job_id}-tmp"
            job_temp.mkdir()
            try:
                self.process = subprocess.Popen(
                    command, cwd=self.root,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTEST_DEBUG_TEMPROOT": str(job_temp)},
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    start_new_session=os.name != "nt",
                )
            except OSError:
                raise HTTPException(503, "Could not start the runner; check your Python environment") from None
            self.job = {
                "id": job_id, "mode": options.mode, "status": "running",
                "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "elapsed_seconds": 0, "exit_code": None, "run_id": None,
                "command": subprocess.list2cmdline(command), "output": "", "output_start": 0,
                "monotonic": time.monotonic(), "cancel_requested": False,
            }
            self.worker = threading.Thread(target=self._watch, args=(self.process, self.job, log_path), daemon=True)
            self.worker.start()
            return self.snapshot()

    def _watch(self, process, job, log_path):
        # retains the full log on disk while keeping the browser's live tail bounded
        try:
            with log_path.open("w", encoding="utf-8") as log:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    with self.lock:
                        job["output"] += line
                        if len(job["output"]) > 2_000_000:
                            removed = len(job["output"]) - 2_000_000
                            job["output"] = job["output"][removed:]
                            job["output_start"] += removed
                        if line.startswith("Evidence folder: "):
                            folder = Path(line.removeprefix("Evidence folder: ").strip()).resolve()
                            if folder.parent == self.results.resolve() and RUN_ID.fullmatch(folder.name):
                                job["run_id"] = folder.name
            code = process.wait()
        except (OSError, ValueError) as exc:
            with self.lock:
                job["output"] += f"\nDashboard log error: {exc}\n"
            self._terminate(process)
            code = process.poll() if process.poll() is not None else 1
        finally:
            if process.stdout:
                process.stdout.close()
        with self.lock:
            job["elapsed_seconds"] = round(time.monotonic() - job["monotonic"], 1)
            job["exit_code"] = code
            job["status"] = "cancelled" if job["cancel_requested"] else "completed" if code == 0 else "failed"

    def _terminate(self, process):
        # closes only the runner process tree owned by this dashboard
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def cancel(self):
        with self.lock:
            if not self.job or self.job["status"] != "running":
                raise HTTPException(409, "There is no active run")
            self.job["cancel_requested"] = True
            process = self.process
        self._terminate(process)
        return self.snapshot()

    def close(self):
        with self.lock:
            self.closing = True
            active = self.job and self.job["status"] == "running"
        if active:
            try:
                self.cancel()
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
        if self.worker:
            self.worker.join(timeout=5)


def create_app(bench=None):
    bench = bench or Bench()

    @asynccontextmanager
    async def lifespan(app):
        yield
        bench.close()

    app = FastAPI(title="DocumentationDrifter Test Bench", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        # requires matching browser origins before starting or cancelling local processes
        if request.method == "POST":
            origin = request.headers.get("origin")
            expected = str(request.base_url).rstrip("/")
            if origin and origin.rstrip("/") != expected:
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "Use the dashboard's own browser tab"}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")

    @app.get("/api/config")
    def config():
        return {"project": "DocumentationDrifter", "python": sys.version.split()[0], "default_url": RAILWAY}

    @app.get("/api/runs")
    def history():
        return {"runs": bench.history()}

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        return bench.read_run(run_id)

    @app.get("/api/job")
    def state(offset: int = 0):
        return bench.snapshot(offset)

    @app.post("/api/runs", status_code=202)
    def start(options: RunRequest):
        return bench.start(options)

    @app.post("/api/job/cancel")
    def cancel():
        return bench.cancel()

    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
    app.mount("/artifacts", StaticFiles(directory=bench.results), name="artifacts")
    return app


def main():
    parser = argparse.ArgumentParser(description="Open the dedicated local test bench dashboard")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    import uvicorn

    print(f"\nTest bench: http://127.0.0.1:{args.port}\nPress Ctrl+C to stop.\n", flush=True)
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
