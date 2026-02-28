import logging
import sys
import os
import toml
import asyncio
from typing import Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import aiohttp
import uvicorn

# Load configuration
config_path = Path("/app/config.toml")
if not config_path.exists():
    config_path = Path(__file__).parent.parent.parent / "config.toml"
config = toml.load(config_path)
smartfields_config = config["smartfields"]

# Setup logging (JSON to stdout + file on the mounted volume)
_log_dir = "/var/log/smartfield"
Path(_log_dir).mkdir(parents=True, exist_ok=True)
_log_level = smartfields_config.get("log_level", "INFO").upper()
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{_log_dir}/smartfields.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("smartfields")

# ── Singleton aiohttp session ──────────────────────────────────────────────────
_session: aiohttp.ClientSession | None = None


def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return _session


async def close_session() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()


# ── Global pipeline state ──────────────────────────────────────────────────────
# Initialized in lifespan() — not usable before startup
pipeline_lock: asyncio.Lock
pipeline_stop_event: asyncio.Event

lat: Optional[float] = None
lon: Optional[float] = None
pipeline_running: bool = False
pipeline_task: Optional[asyncio.Task] = None


def get_services() -> dict:
    """Return service base URLs, resolved from NODE_IP env var (K3s) or localhost."""
    node_ip = os.environ.get("NODE_IP", "localhost")
    opl_url = os.environ.get("OPENPASSLITE_URL", f"http://{node_ip}:2177")
    ww_url = os.environ.get("WILDWINGS_URL", f"http://{node_ip}:2199")
    return {
        "openpasslite": opl_url,
        "wildwings": ww_url,
    }


async def call_service(
    services: dict,
    service_name: str,
    endpoint: str,
    mission_name: Optional[str] = None,
) -> bool:
    """POST to a service endpoint, reusing the shared aiohttp session."""
    url = f"{services[service_name]}{endpoint}"
    params: dict = {}

    if service_name == "openpasslite" and endpoint == "/start_mission":
        params = {"name": mission_name, "lat": lat, "long": lon}
    elif service_name == "wildwings" and endpoint == "/start_mission":
        params = {"lat": lat, "lon": lon}

    try:
        async with get_session().post(url, params=params) as response:
            status_code = response.status
            response_text = await response.text()
        logger.info("Called %s%s — status: %d", service_name, endpoint, status_code)
        if status_code != 200:
            logger.warning("Service %s response: %s", service_name, response_text)
        return status_code == 200
    except asyncio.TimeoutError:
        logger.error("Timeout calling %s%s", service_name, endpoint)
        return False
    except Exception as e:
        logger.error("Error calling %s%s: %s", service_name, endpoint, e)
        return False


async def wait_for_completion(status_url: str, timeout: int = 180) -> bool:
    """Poll a service's /mission_status endpoint until it reports 'idle'."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if pipeline_stop_event.is_set():
            return False
        try:
            async with get_session().get(status_url) as r:
                r.raise_for_status()
                data = await r.json()
                if data.get("status") == "idle":
                    return True
        except Exception:
            pass
        await asyncio.sleep(2)
    logger.error("Timeout waiting for %s to become idle", status_url)
    return False


async def execute_pipeline() -> bool:
    """Execute the mission pipeline: LTT → WildWings → RTB."""
    global pipeline_running, pipeline_stop_event

    async with pipeline_lock:
        if pipeline_running:
            logger.warning("Pipeline already running")
            return False
        pipeline_running = True
        pipeline_stop_event.clear()

    try:
        logger.info("Starting pipeline execution")
        services = get_services()
        logger.info("Using services: %s", services)

        mission_timeout = config.get("openpasslite", {}).get("mission_timeout_seconds", 180)

        flow = [
            ("openpasslite", "/start_mission", "LTT", f"{services['openpasslite']}/mission_status"),
            ("wildwings",    "/start_mission", None,  f"{services['wildwings']}/mission_status"),
            ("openpasslite", "/start_mission", "RTB", f"{services['openpasslite']}/mission_status"),
        ]

        for idx, (service, endpoint, mission_name, status_url) in enumerate(flow):
            if pipeline_stop_event.is_set():
                logger.info("Pipeline stop requested, aborting")
                return False

            logger.info("Starting %s%s  mission=%s", service, endpoint, mission_name)

            if not await call_service(services, service, endpoint, mission_name):
                logger.error("Failed to start %s", service)
                if idx == 0:
                    return False
                elif idx == 1:
                    logger.warning("WildWings failed — continuing to RTB")
                    continue
                return False

            if not await wait_for_completion(status_url, timeout=mission_timeout):
                logger.error("%s mission %s failed or timed out", service, mission_name)
                if idx == 0:
                    return False
                elif idx == 1:
                    logger.warning("WildWings timed out — continuing to RTB")
                    continue
                return False

            logger.info("%s mission %s completed", service, mission_name)

            # Brief pause between steps (skip after LTT to keep drone flying)
            wait_secs = 3 if (service == "openpasslite" and mission_name == "LTT") else 10
            for _ in range(wait_secs):
                if pipeline_stop_event.is_set():
                    return False
                await asyncio.sleep(1)

        logger.info("Pipeline completed successfully")
        return True

    except Exception as e:
        logger.error("Pipeline execution error: %s", e)
        return False
    finally:
        async with pipeline_lock:
            pipeline_running = False
            pipeline_stop_event.clear()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline_lock, pipeline_stop_event
    pipeline_lock = asyncio.Lock()
    pipeline_stop_event = asyncio.Event()
    logger.info("SmartFields service starting up")
    yield
    logger.info("SmartFields service shutting down")

    global pipeline_running, pipeline_task
    async with pipeline_lock:
        if pipeline_running:
            logger.info("Stopping pipeline during shutdown")
            pipeline_stop_event.set()
            if pipeline_task and not pipeline_task.done():
                try:
                    pipeline_task.cancel()
                    await pipeline_task
                except asyncio.CancelledError:
                    logger.info("Pipeline task cancelled during shutdown")
                except Exception as e:
                    logger.error("Error during pipeline shutdown: %s", e)

    await close_session()


app = FastAPI(
    title="SmartFields Service",
    description="SmartFields agricultural monitoring service",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "SmartFields Service", "status": "running"}


@app.post("/initiate_pipeline")
async def initiate_pipeline(
    lat: float = Query(..., description="Latitude coordinate"),
    lon: float = Query(..., description="Longitude coordinate"),
    camid: Optional[str] = Query(None, description="Camera trap ID"),
):
    """Initiate the mission pipeline with the given coordinates."""
    global pipeline_running, pipeline_task

    async with pipeline_lock:
        if pipeline_running:
            logger.warning("Pipeline request rejected — already running")
            raise HTTPException(status_code=409, detail="Pipeline is currently running")

    # Store coordinates for use inside execute_pipeline
    globals()["lat"] = lat
    globals()["lon"] = lon

    logger.info("Pipeline initiated: lat=%s lon=%s camid=%s", lat, lon, camid)
    pipeline_task = asyncio.create_task(execute_pipeline())

    return {
        "message": f"Pipeline started for coordinates ({lat}, {lon})",
        "status": "pipeline_started",
        "coordinates": {"lat": lat, "lon": lon},
        "camera_id": camid,
    }


@app.get("/pipeline_status")
async def pipeline_status():
    async with pipeline_lock:
        return {
            "pipeline_running": pipeline_running,
            "coordinates": {"lat": lat, "lon": lon} if lat and lon else None,
            "status": "running" if pipeline_running else "idle",
            "stop_requested": pipeline_stop_event.is_set(),
        }


@app.get("/health")
async def health_check():
    try:
        services = get_services()
        async with pipeline_lock:
            return {
                "status": "healthy",
                "pipeline_running": pipeline_running,
                "services_configured": list(services.keys()),
                "service": "smartfields",
            }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        raise HTTPException(status_code=503, detail="Service unhealthy")


@app.post("/stop_pipeline")
async def stop_pipeline():
    global pipeline_running, pipeline_task

    async with pipeline_lock:
        if not pipeline_running:
            return {
                "message": "Pipeline is not currently running",
                "status": "already_stopped",
                "pipeline_running": False,
            }
        pipeline_stop_event.set()
        logger.info("Pipeline stop signal sent")

    # Ask each downstream service to stop its mission
    services = get_services()
    stopped_services, failed_services = [], []
    for service_name, base_url in services.items():
        try:
            async with get_session().post(
                f"{base_url}/stop_mission",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    stopped_services.append(service_name)
                    logger.info("Stopped %s", service_name)
                else:
                    failed_services.append(service_name)
                    logger.warning("Failed to stop %s: %d", service_name, response.status)
        except Exception as e:
            failed_services.append(service_name)
            logger.warning("Error stopping %s: %s", service_name, e)

    if pipeline_task and not pipeline_task.done():
        pipeline_task.cancel()
        try:
            await pipeline_task
        except asyncio.CancelledError:
            logger.info("Pipeline task cancelled")

    return {
        "message": f"Pipeline stopped. Contacted: {stopped_services + failed_services}",
        "stopped_services": stopped_services,
        "failed_services": failed_services,
        "pipeline_running": False,
        "status": "stopped",
    }


@app.get("/logs", response_class=HTMLResponse)
async def view_logs():
    try:
        log_file = Path(f"{_log_dir}/smartfields.log")
        if log_file.exists():
            with open(log_file) as f:
                content = f.read()
            return f"<pre>{content}</pre>"
        return "<pre>No logs yet</pre>"
    except Exception as e:
        logger.error("Error reading logs: %s", e)
        return f"<pre>Error reading logs: {e}</pre>"


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=smartfields_config["host"],
        port=smartfields_config["port"],
        access_log=True,
    )
