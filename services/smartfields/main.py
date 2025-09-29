import logging
import toml
import time
import aiohttp
import threading
import asyncio
import os
from typing import Optional, Dict, List, Tuple
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import uvicorn
from pathlib import Path

config_path = Path("/app/config.toml")
if not config_path.exists():
    config_path = Path(__file__).parent.parent.parent / "config.toml"
config = toml.load(config_path)
smartfields_config = config["smartfields"]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(smartfields_config["logfile_path"]),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("smartfields")

# Global state with thread safety
pipeline_lock = threading.Lock()
lat = None
lon = None
pipeline_running = False
pipeline_stop_event = asyncio.Event()
pipeline_task = None

def get_services():
    return {
        "openpasslite": os.getenv("OPENPASSLITE_URL", "openpasslite:2177"),
        "wildwings": os.getenv("WILDWINGS_URL", "wildwings:2199")
    }

async def call_service(services: Dict[str, str], service_name: str, endpoint: str, mission_name: Optional[str] = None) -> bool:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        try:
            url = f"http://{services[service_name]}{endpoint}"

            if service_name == "openpasslite" and endpoint == "/start_mission":
                params = {
                    'name': mission_name,
                    'lat': lat,
                    'long': lon  # Note: openpasslite expects 'long' not 'lon'
                }
                async with session.post(url, params=params) as response:
                    status_code = response.status
                    response_text = await response.text()
            else:
                async with session.post(url) as response:
                    status_code = response.status
                    response_text = await response.text()

            logger.info(f"Called {service_name}{endpoint} - Status: {status_code}")
            if status_code != 200:
                logger.warning(f"Service {service_name} response: {response_text}")
            return status_code == 200
        except asyncio.TimeoutError:
            logger.error(f"Timeout calling {service_name}{endpoint}")
            return False
        except Exception as e:
            logger.error(f"Error calling {service_name}{endpoint}: {e}")
            return False

def get_log_paths():
    """Get log paths from config or use defaults"""
    try:
        # Try to get from config first
        base_log_dir = Path(smartfields_config.get("log_directory", "logs"))
        return {
            "openpasslite": base_log_dir / "openpasslite.log",
            "wildwings": base_log_dir / "wildwings.log"
        }
    except Exception:
        # Fallback to relative paths
        return {
            "openpasslite": Path("logs/openpasslite.log"),
            "wildwings": Path("logs/wildwings.log")
        }

async def wait_for_completion(services: Dict[str, str], service_name: str, mission_name: str) -> bool:
    logger.info(f"Waiting for {service_name} mission {mission_name} to complete...")

    log_paths = get_log_paths()

    if service_name not in log_paths:
        logger.error(f"No log path configured for service: {service_name}")
        return False

    log_file_path = log_paths[service_name]
    completion_pattern = f"Mission {mission_name} thread finished"

    try:
        initial_size = log_file_path.stat().st_size if log_file_path.exists() else 0
    except Exception as e:
        logger.error(f"Error accessing log file {log_file_path}: {e}")
        return False

    start_time = time.time()
    timeout = 180
    max_wait_for_log = 30  # Wait max 30 seconds for log file to appear

    # Wait for log file to appear
    log_wait_start = time.time()
    while not log_file_path.exists():
        if pipeline_stop_event.is_set():
            logger.info(f"Pipeline stop requested during log wait for {service_name}")
            return False

        if time.time() - log_wait_start > max_wait_for_log:
            logger.error(f"Log file {log_file_path} did not appear within {max_wait_for_log} seconds")
            return False

        await asyncio.sleep(2)

    while not pipeline_stop_event.is_set():
        try:
            current_size = log_file_path.stat().st_size

            if current_size > initial_size:
                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(initial_size)
                    new_content = f.read()

                    if completion_pattern in new_content:
                        logger.info(f"{service_name} mission {mission_name} completed successfully")
                        return True

                    mission_failure_patterns = [
                        f"Mission {mission_name} failed:",
                        f"Mission failed:",
                        f"ERROR - Mission {mission_name}",
                        f"FAILED - Mission {mission_name}"
                    ]
                    for pattern in mission_failure_patterns:
                        if pattern in new_content:
                            logger.error(f"{service_name} mission {mission_name} failed")
                            return False

                initial_size = current_size

            if time.time() - start_time > timeout:
                logger.error(f"Timeout waiting for {service_name} mission {mission_name} to complete")
                return False

        except Exception as e:
            logger.warning(f"Error reading log file for {service_name}: {e}")

        await asyncio.sleep(2)

    logger.info(f"Pipeline stop requested while waiting for {service_name}")
    return False

async def execute_pipeline() -> bool:
    global pipeline_running, pipeline_stop_event

    with pipeline_lock:
        if pipeline_running:
            logger.warning("Pipeline already running")
            return False
        pipeline_running = True
        pipeline_stop_event.clear()

    try:
        logger.info("Starting pipeline execution")

        services = get_services()
        logger.info(f"Using services: {services}")

        # pipeline flow with retry mechanism
        flow: List[Tuple[str, str, Optional[str], int]] = [
            # ("openpasslite", "/start_mission", "TAKEOFF", 2),  # service, endpoint, mission, max_retries
            ("wildwings", "/start_mission", None, 1),
            # ("openpasslite", "/start_mission", "LAND", 2)
        ]

        for service, endpoint, mission_name, max_retries in flow:
            if pipeline_stop_event.is_set():
                logger.info("Pipeline stop requested, aborting execution")
                return False

            logger.info(f"Starting {service}{endpoint} with mission: {mission_name}")

            # Retry logic for service calls
            service_success = False
            for attempt in range(max_retries + 1):
                if pipeline_stop_event.is_set():
                    logger.info("Pipeline stop requested during service call")
                    return False

                if await call_service(services, service, endpoint, mission_name):
                    service_success = True
                    break
                else:
                    if attempt < max_retries:
                        logger.warning(f"Service {service} failed, retrying ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(5)
                    else:
                        logger.error(f"Service {service} failed after {max_retries + 1} attempts")

            if not service_success:
                logger.error(f"Failed to start {service} after all retries")
                return False

            # Wait for completion with stop check
            if not await wait_for_completion(services, service, mission_name):
                logger.error(f"{service} mission {mission_name} failed or was stopped")
                return False

            logger.info(f"{service} mission {mission_name} completed successfully")

            # Interruptible wait between missions
            logger.info("Waiting 30 seconds before next mission...")
            for _ in range(30):
                if pipeline_stop_event.is_set():
                    logger.info("Pipeline stop requested during inter-mission wait")
                    return False
                await asyncio.sleep(1)

        logger.info("Pipeline completed successfully")
        return True

    except Exception as e:
        logger.error(f"Pipeline execution error: {e}")
        return False
    finally:
        with pipeline_lock:
            pipeline_running = False
            pipeline_stop_event.clear()

async def run_pipeline_async():
    """Run pipeline asynchronously"""
    return await execute_pipeline()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SmartFields service starting up")
    yield
    logger.info("SmartFields service shutting down")

    global pipeline_running, pipeline_stop_event, pipeline_task
    with pipeline_lock:
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
                    logger.error(f"Error during pipeline shutdown: {e}")

app = FastAPI(
    title="SmartFields Service",
    description="SmartFields agricultural monitoring service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[smartfields_config["cors_origin"]],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "SmartFields Service", "status": "running"}

@app.post("/initiate_pipeline")
async def initiate_process(
    lat: float = Query(..., description="Latitude coordinate"),
    lon: float = Query(..., description="Longitude coordinate"),
    camid: Optional[str] = Query(None, description="Camera trap ID")
):
    global pipeline_running, pipeline_task

    logger.info(f"Process initiation requested - lat: {lat}, lon: {lon}, camid: {camid}")

    with pipeline_lock:
        if pipeline_running:
            logger.warning('Pipeline request rejected - pipeline already running')
            raise HTTPException(
                status_code=409,
                detail="Pipeline is currently running. Please wait for it to complete."
            )

    try:
        float(lat)
        float(lon)
    except ValueError:
        logger.error(f'Invalid coordinates: lat={lat}, lon={lon}')
        raise HTTPException(
            status_code=400,
            detail="lat and lon must be valid numbers"
        )

    globals()['lat'] = lat
    globals()['lon'] = lon

    logger.info(f'Process initiated with camera_id: {camid} and coordinates: lat={lat}, lon={lon}')

    logger.info('Starting pipeline execution')
    pipeline_task = asyncio.create_task(run_pipeline_async())

    return {
        "message": f"Process initiated with coordinates: {lat},{lon}. Pipeline started.",
        "status": "pipeline_started",
        "coordinates": {"lat": lat, "lon": lon},
        "camera_id": camid
    }

@app.get("/logs", response_class=HTMLResponse)
async def view_logs():
    try:
        log_file = Path(smartfields_config["logfile_path"])
        if log_file.exists():
            with open(log_file, 'r') as f:
                content = f.read()
            return f'<pre>{content}</pre>'
        else:
            return '<pre>No logs yet</pre>'
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        return f'<pre>Error reading logs: {e}</pre>'

@app.get("/pipeline_status")
async def pipeline_status():
    with pipeline_lock:
        return {
            "pipeline_running": pipeline_running,
            "coordinates": {"lat": lat, "lon": lon} if lat and lon else None,
            "status": "running" if pipeline_running else "idle",
            "stop_requested": pipeline_stop_event.is_set()
        }

@app.get("/health")
async def health_check():
    try:
        services = get_services()

        with pipeline_lock:
            return {
                "status": "healthy",
                "pipeline_running": pipeline_running,
                "services_configured": list(services.keys()),
                "service": "smartfields"
            }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

@app.post("/stop_pipeline")
async def stop_pipeline():
    global pipeline_running, pipeline_stop_event, pipeline_task
    logger.info("Stop pipeline endpoint accessed")

    with pipeline_lock:
        if not pipeline_running:
            logger.info("Pipeline is not currently running")
            return {
                "message": "Pipeline is not currently running",
                "status": "already_stopped",
                "pipeline_running": False
            }

        # Stop the pipeline
        pipeline_stop_event.set()
        logger.info("Pipeline stop signal sent")

    # Get services and attempt to stop them
    services = get_services()
    stopped_services = []
    failed_services = []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        for service_name, service_url in services.items():
            try:
                url = f"http://{service_url}/stop_mission"
                async with session.post(url) as response:
                    if response.status == 200:
                        stopped_services.append(service_name)
                        logger.info(f'Successfully stopped {service_name}')
                    else:
                        failed_services.append(service_name)
                        logger.warning(f'Failed to stop {service_name}: {response.status}')
            except Exception as e:
                failed_services.append(service_name)
                logger.warning(f'Error stopping {service_name}: {e}')

    # Cancel the pipeline task if it exists
    if pipeline_task and not pipeline_task.done():
        pipeline_task.cancel()
        try:
            await pipeline_task
        except asyncio.CancelledError:
            logger.info("Pipeline task cancelled successfully")

    return {
        "message": f"Pipeline stopped. Services contacted: {', '.join(stopped_services + failed_services)}",
        "stopped_services": stopped_services,
        "failed_services": failed_services,
        "pipeline_running": False,
        "status": "stopped"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=smartfields_config["host"],
        port=smartfields_config["port"],
        reload=smartfields_config["debug"],
        access_log=True
    )