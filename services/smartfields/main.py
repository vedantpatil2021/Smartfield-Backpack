import json
import logging
import os
import shutil
import sys
import time
import toml
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import aiohttp
import uvicorn

# ── Config ─────────────────────────────────────────────────────────────────────
config_path = Path("/app/config.toml")
if not config_path.exists():
    config_path = Path(__file__).parent.parent.parent / "config.toml"
config = toml.load(config_path)
smartfields_config = config["smartfields"]

# ── Log paths (from [logging] in config.toml) ─────────────────────────────────
_log_cfg      = config.get("logging", {})
_log_dir      = Path(_log_cfg.get("dir",          "/var/log/smartfield"))
_missions_dir = Path(_log_cfg.get("missions_dir", str(_log_dir / "missions")))
_max_missions: int = _log_cfg.get("max_missions", 100)
_log_dir.mkdir(parents=True, exist_ok=True)
_missions_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=smartfields_config.get("log_level", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_log_dir / "smartfields.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("smartfields")

# ── Pipeline tuning ────────────────────────────────────────────────────────────
_step_delay: int = smartfields_config.get("inter_step_delay_seconds", 5)

# ── Singleton aiohttp session ──────────────────────────────────────────────────
_http: aiohttp.ClientSession | None = None


def get_session() -> aiohttp.ClientSession:
    global _http
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return _http


async def close_session() -> None:
    global _http
    if _http and not _http.closed:
        await _http.close()


# ── Global pipeline state ──────────────────────────────────────────────────────
pipeline_lock: asyncio.Lock
pipeline_stop_event: asyncio.Event

_lat:   Optional[float] = None
_lon:   Optional[float] = None
_model: Optional[str]   = None
_camid: Optional[str]   = None
pipeline_running: bool = False
pipeline_task: Optional[asyncio.Task] = None


# ── Mission logger ─────────────────────────────────────────────────────────────
def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class MissionLogger:
    """Writes per-mission pipeline.log and meta.json to a timestamped directory."""

    def __init__(self, mission_id: str, camid: str, lat: float, lon: float, model: Optional[str]):
        self.id   = mission_id
        self._dir = _missions_dir / mission_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._fh  = open(self._dir / "pipeline.log", "w")
        self._t0  = time.monotonic()
        self._meta: dict = {
            "id":             mission_id,
            "started_at":     _utcnow(),
            "ended_at":       None,
            "duration_s":     None,
            "status":         "running",
            "location":       {"lat": lat, "lon": lon, "camid": camid},
            "model":          model,
            "steps":          [],
            "failure_reason": None,
        }
        self._flush_meta()
        self.write(
            f"Mission started · {camid} · ({lat:.6f}, {lon:.6f})"
            + (f" · model: {model}" if model else "")
        )

    def write(self, msg: str) -> None:
        self._fh.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self._fh.flush()

    def step_start(self, idx: int, total: int, name: str) -> None:
        self.write(f"Step {idx + 1}/{total} → {name} initiated")
        self._meta["steps"].append(
            {"name": name, "status": "running", "started_at": _utcnow(), "duration_s": None}
        )
        self._flush_meta()

    def step_end(self, status: str, duration_s: int) -> None:
        step = self._meta["steps"][-1]
        step["status"]     = status
        step["duration_s"] = duration_s
        icon = {"ok": "✓", "timeout": "✗", "stopped": "■", "failed": "✗"}.get(status, "⚠")
        m, s = divmod(duration_s, 60)
        self.write(f"  {icon} {step['name']} {status} ({m}m {s:02d}s)")
        self._flush_meta()

    def close(self, status: str, failure_reason: Optional[str] = None) -> None:
        elapsed = round(time.monotonic() - self._t0)
        self._meta.update(
            ended_at=_utcnow(), duration_s=elapsed,
            status=status, failure_reason=failure_reason,
        )
        self._flush_meta()
        m, s = divmod(elapsed, 60)
        self.write(f"{'✓' if status == 'success' else '✗'} Mission {status}  (total: {m}m {s:02d}s)")
        self._fh.close()

    def _flush_meta(self) -> None:
        with open(self._dir / "meta.json", "w") as f:
            json.dump(self._meta, f, indent=2)


def _cleanup_old_missions() -> None:
    """Delete oldest mission folders when count reaches _max_missions."""
    dirs = sorted(p for p in _missions_dir.iterdir() if p.is_dir())
    while len(dirs) >= _max_missions:
        shutil.rmtree(dirs.pop(0), ignore_errors=True)


# ── Service helpers ────────────────────────────────────────────────────────────
def get_services() -> dict:
    return {
        "openpasslite": os.environ.get("OPENPASSLITE_URL", "http://localhost:2177"),
        "wildwings":    os.environ.get("WILDWINGS_URL",    "http://localhost:2199"),
    }


async def call_service(
    services: dict, service_name: str, endpoint: str, mission_name: Optional[str] = None,
) -> bool:
    url, params = f"{services[service_name]}{endpoint}", {}
    if service_name == "openpasslite" and endpoint == "/start_mission":
        params = {"name": mission_name, "lat": _lat, "long": _lon}
    elif service_name == "wildwings" and endpoint == "/start_mission":
        params = {"lat": _lat, "lon": _lon}
        if _model:
            params["model"] = _model
    try:
        async with get_session().post(url, params=params) as r:
            status, body = r.status, await r.text()
        logger.info("POST %s%s → %d", service_name, endpoint, status)
        if status != 200:
            logger.warning("%s response: %s", service_name, body)
        return status == 200
    except asyncio.TimeoutError:
        logger.error("Timeout calling %s%s", service_name, endpoint)
        return False
    except Exception as exc:
        logger.error("Error calling %s%s: %s", service_name, endpoint, exc)
        return False


async def wait_for_idle(status_url: str, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pipeline_stop_event.is_set():
            return False
        try:
            async with get_session().get(status_url) as r:
                r.raise_for_status()
                if (await r.json()).get("status") == "idle":
                    return True
        except Exception:
            pass
        await asyncio.sleep(2)
    logger.error("Timeout waiting for %s", status_url)
    return False


async def inter_step_pause(mission: MissionLogger) -> bool:
    mission.write(f"  ─── {_step_delay}s pause ───")
    for _ in range(_step_delay):
        if pipeline_stop_event.is_set():
            return False
        await asyncio.sleep(1)
    return True


# ── Pipeline ───────────────────────────────────────────────────────────────────
async def execute_pipeline() -> bool:
    global pipeline_running

    async with pipeline_lock:
        if pipeline_running:
            return False
        pipeline_running = True
        pipeline_stop_event.clear()

    _cleanup_old_missions()
    mission_id = (
        f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        f"_{(_camid or 'unknown').replace('/', '_')}"
    )
    mission: Optional[MissionLogger] = None
    success, failure_reason = False, None

    try:
        mission = MissionLogger(mission_id, _camid or "", _lat, _lon, _model)
        logger.info("Pipeline starting — mission=%s", mission_id)
        services = get_services()

        opl_timeout = config.get("openpasslite", {}).get("mission_timeout_seconds", 180)
        ww_timeout  = config.get("wildwings",    {}).get("mission_duration_seconds", 25) + 30

        flow = [
            ("openpasslite", "/start_mission", "LTT",  f"{services['openpasslite']}/mission_status", opl_timeout),
            ("wildwings",    "/start_mission",  None,   f"{services['wildwings']}/mission_status",    ww_timeout),
            ("openpasslite", "/start_mission", "RTB",  f"{services['openpasslite']}/mission_status", opl_timeout),
        ]

        for idx, (service, endpoint, script, status_url, timeout) in enumerate(flow):
            if pipeline_stop_event.is_set():
                failure_reason = "stop_requested"
                return False

            label = script or "WildWings"
            mission.step_start(idx, len(flow), label)
            step_t0 = time.monotonic()

            if not await call_service(services, service, endpoint, script):
                dur = round(time.monotonic() - step_t0)
                mission.step_end("failed", dur)
                if idx == 1:
                    mission.write("  ⚠ continuing to RTB")
                    continue
                failure_reason = f"{label}_start_failed"
                return False

            if not await wait_for_idle(status_url, timeout=timeout):
                dur = round(time.monotonic() - step_t0)
                step_status = "stopped" if pipeline_stop_event.is_set() else "timeout"
                mission.step_end(step_status, dur)
                if idx == 1:
                    mission.write("  ⚠ continuing to RTB")
                    continue
                failure_reason = f"{label}_{step_status}"
                return False

            mission.step_end("ok", round(time.monotonic() - step_t0))

            if idx < len(flow) - 1:
                if not await inter_step_pause(mission):
                    failure_reason = f"stop_during_pause_after_{label}"
                    return False

        success = True
        return True

    except Exception as exc:
        logger.error("Pipeline error: %s", exc)
        failure_reason = str(exc)
        return False
    finally:
        if mission:
            final_status = "success" if success else (
                "stopped" if pipeline_stop_event.is_set() else "failed"
            )
            mission.close(final_status, failure_reason)
        async with pipeline_lock:
            pipeline_running = False
            pipeline_stop_event.clear()


# ── App lifespan ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline_lock, pipeline_stop_event
    pipeline_lock = asyncio.Lock()
    pipeline_stop_event = asyncio.Event()
    logger.info("SmartFields service starting")
    yield
    logger.info("SmartFields service shutting down")
    global pipeline_running, pipeline_task
    async with pipeline_lock:
        if pipeline_running:
            pipeline_stop_event.set()
            if pipeline_task and not pipeline_task.done():
                try:
                    pipeline_task.cancel()
                    await pipeline_task
                except (asyncio.CancelledError, Exception):
                    pass
    await close_session()


# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SmartFields Service",
    description="SmartFields agricultural monitoring service",
    version="1.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(_static_dir), html=True), name="ui")


# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "SmartFields Service", "status": "running", "ui": "/ui"}


@app.post("/initiate_pipeline")
async def initiate_pipeline(
    lat:   float         = Query(...,  description="Latitude"),
    lon:   float         = Query(...,  description="Longitude"),
    camid: Optional[str] = Query(None, description="Camera trap ID"),
    model: Optional[str] = Query(None, description="Detection model (e.g. yolov5su)"),
):
    global _lat, _lon, _model, _camid, pipeline_task
    async with pipeline_lock:
        if pipeline_running:
            raise HTTPException(status_code=409, detail="Pipeline is currently running")
    _lat, _lon, _model, _camid = lat, lon, model, camid
    logger.info("Pipeline initiated: lat=%s lon=%s camid=%s model=%s", lat, lon, camid, model)
    pipeline_task = asyncio.create_task(execute_pipeline())
    return {"status": "pipeline_started", "coordinates": {"lat": lat, "lon": lon},
            "camera_id": camid, "model": model}


@app.get("/config/defaults")
async def config_defaults():
    """UI defaults sourced directly from config.toml — single source of truth."""
    topics = config.get("subscriber", {}).get("topics", {})
    first  = next(iter(topics.values()), {})
    return {
        "lat":    first.get("lat",   0.0),
        "lon":    first.get("lon",   0.0),
        "camid":  first.get("camid", ""),
        "models": config.get("wildwings", {}).get("models", ["yolov5su"]),
    }


@app.get("/status")
async def status():
    """Aggregated status: pipeline state + downstream service health."""
    services = get_services()

    async def probe(name: str, url: str) -> tuple[str, bool]:
        try:
            async with get_session().get(
                f"{url}/healthz", timeout=aiohttp.ClientTimeout(total=2)
            ) as r:
                return name, r.status == 200
        except Exception:
            return name, False

    results = await asyncio.gather(*[probe(n, u) for n, u in services.items()])
    async with pipeline_lock:
        return {
            "pipeline_running": pipeline_running,
            "status":           "running" if pipeline_running else "idle",
            "stop_requested":   pipeline_stop_event.is_set(),
            "coordinates":      {"lat": _lat, "lon": _lon} if _lat is not None else None,
            "services":         dict(results),
        }


@app.post("/stop_pipeline")
async def stop_pipeline():
    global pipeline_task
    async with pipeline_lock:
        if not pipeline_running:
            return {"status": "already_stopped", "pipeline_running": False}
        pipeline_stop_event.set()
        logger.info("Stop signal sent")
    services = get_services()
    stopped, failed = [], []
    for name, base_url in services.items():
        try:
            async with get_session().post(
                f"{base_url}/stop_mission", timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                (stopped if r.status == 200 else failed).append(name)
        except Exception:
            failed.append(name)
    if pipeline_task and not pipeline_task.done():
        pipeline_task.cancel()
        try:
            await pipeline_task
        except asyncio.CancelledError:
            pass
    logger.info("Pipeline stopped. ok=%s failed=%s", stopped, failed)
    return {"status": "stopped", "pipeline_running": False,
            "stopped_services": stopped, "failed_services": failed}


@app.get("/missions")
async def list_missions():
    """List all mission metadata, newest first."""
    if not _missions_dir.exists():
        return []
    missions = []
    for meta_file in sorted(_missions_dir.glob("*/meta.json"), reverse=True):
        try:
            missions.append(json.loads(meta_file.read_text()))
        except Exception:
            pass
    return missions


@app.get("/missions/{mission_id}/log", response_class=PlainTextResponse)
async def mission_log(mission_id: str):
    if ".." in mission_id or "/" in mission_id:
        raise HTTPException(status_code=400, detail="Invalid mission ID")
    log_file = _missions_dir / mission_id / "pipeline.log"
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Mission not found")
    return log_file.read_text()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=smartfields_config["host"],
        port=smartfields_config["port"],
        access_log=True,
    )
