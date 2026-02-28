import logging
import sys
import os
import toml
import threading
import subprocess
import datetime
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

# Load configuration
config_path = Path("/app/config.toml")
if not config_path.exists():
    config_path = Path(__file__).parent.parent.parent / "config.toml"
config = toml.load(config_path)
wildwings_config = config["wildwings"]

# Setup logging (stdout + mounted volume file)
_log_dir = "/var/log/smartfield"
Path(_log_dir).mkdir(parents=True, exist_ok=True)
_log_level = wildwings_config.get("log_level", "INFO").upper()
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{_log_dir}/wildwings.log", mode='a'),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("wildwings")

# ── Global mission state ───────────────────────────────────────────────────────
mission_lock = threading.Lock()
mission_thread: threading.Thread | None = None
stop_mission_flag = threading.Event()
current_process: subprocess.Popen | None = None
is_running: bool = False
mission_lat: float | None = None
mission_lon: float | None = None


def run_mission_background() -> None:
    """Execute controller.py directly as a Python subprocess (no bash wrapper)."""
    global stop_mission_flag, current_process, is_running, mission_lat, mission_lon

    with mission_lock:
        if is_running:
            logger.warning("Mission already running")
            return
        is_running = True
        stop_mission_flag.clear()

    mission_success = False

    try:
        if stop_mission_flag.is_set():
            logger.info("Mission stopped before execution")
            return

        logger.info("Starting WildWings mission")

        # Create timestamped output directory (previously done by launch.sh)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"/app/mission/mission_record_{timestamp}"
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        controller_path = Path("/app/controller.py")
        if not controller_path.exists():
            raise FileNotFoundError(f"controller.py not found at {controller_path}")

        # Build argument list — matches controller.py's sys.argv interface
        cmd = [sys.executable, str(controller_path), output_dir]
        if mission_lat is not None and mission_lon is not None:
            cmd += [str(mission_lat), str(mission_lon)]
            logger.info("Mission coordinates: lat=%s lon=%s", mission_lat, mission_lon)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        log_file_path = Path(f"{_log_dir}/wildwings.log")
        with open(log_file_path, "a") as log_file:
            with mission_lock:
                current_process = subprocess.Popen(
                    cmd,
                    cwd="/app",
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=env,
                )

        logger.info("Mission subprocess started (PID %d)", current_process.pid)

        # Wait for completion, checking stop flag periodically
        while True:
            try:
                current_process.wait(timeout=1)
                break
            except subprocess.TimeoutExpired:
                if stop_mission_flag.is_set():
                    logger.info("Stop signal received — terminating mission")
                    with mission_lock:
                        if current_process:
                            current_process.terminate()
                    break

        with mission_lock:
            if current_process:
                return_code = current_process.returncode
                if return_code is None:
                    # Process was terminated
                    return_code = current_process.wait()

                logger.info("Mission process exited with return code: %d", return_code)
                mission_success = return_code == 0
                if not mission_success:
                    logger.error("Mission failed with return code: %d", return_code)

    except Exception as e:
        logger.error("Mission failed: %s", e)
        mission_success = False
    finally:
        with mission_lock:
            if current_process:
                try:
                    if current_process.poll() is None:
                        logger.info("Terminating process...")
                        current_process.terminate()
                        try:
                            current_process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            logger.warning("Process did not terminate — forcing kill")
                            current_process.kill()
                            current_process.wait(timeout=2)
                except Exception as cleanup_error:
                    logger.error("Error during process cleanup: %s", cleanup_error)

            is_running = False
            current_process = None
            stop_mission_flag.clear()

        # Brief wait for drone connection resources to release
        logger.info("Waiting for connection cleanup (%ds)...",
                    wildwings_config.get("drone_disconnect_wait_seconds", 5))
        time.sleep(wildwings_config.get("drone_disconnect_wait_seconds", 5))

        if mission_success:
            logger.info("Mission thread finished")
        else:
            logger.error("Mission thread finished with errors")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("WildWings service starting up")
    yield
    logger.info("WildWings service shutting down")

    global mission_thread, stop_mission_flag, current_process, is_running

    with mission_lock:
        if mission_thread and mission_thread.is_alive():
            logger.info("Stopping running mission during shutdown")
            stop_mission_flag.set()

            if current_process:
                try:
                    current_process.terminate()
                    current_process.wait(timeout=5)
                    logger.info("Process terminated gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("Process didn't terminate — forcing kill")
                    current_process.kill()
                    try:
                        current_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logger.error("Process could not be killed")
                except Exception as e:
                    logger.error("Error terminating process: %s", e)

    if mission_thread:
        mission_thread.join(timeout=10.0)

    is_running = False


app = FastAPI(
    title="WildWings Service",
    description="WildWings wildlife monitoring service",
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
    return {"message": "WildWings Service", "status": "running"}


@app.post("/start_mission")
async def start_mission(
    lat: float = Query(None, description="Optional latitude coordinate"),
    lon: float = Query(None, description="Optional longitude coordinate"),
):
    logger.info("Start mission: lat=%s lon=%s", lat, lon)

    global mission_thread, stop_mission_flag, is_running, mission_lat, mission_lon

    with mission_lock:
        if (mission_thread and mission_thread.is_alive()) or is_running:
            logger.warning("Mission request rejected — already running")
            raise HTTPException(status_code=409, detail="Mission is currently running")

        mission_lat = lat
        mission_lon = lon

    stop_mission_flag.clear()
    mission_thread = threading.Thread(
        target=run_mission_background,
        name="WildWings-Mission",
        daemon=False,
    )
    mission_thread.start()

    logger.info("WildWings mission started")
    response: dict = {"status": "success", "message": "WildWings mission started"}
    if lat is not None:
        response["lat"] = lat
    if lon is not None:
        response["lon"] = lon
    return response


@app.post("/stop_mission")
async def stop_mission():
    logger.info("Stop mission requested")

    global mission_thread, stop_mission_flag, current_process, is_running

    with mission_lock:
        if not (mission_thread and mission_thread.is_alive()) and not is_running:
            return {"status": "success", "message": "No mission currently running", "was_running": False}

    try:
        stop_mission_flag.set()

        with mission_lock:
            if current_process:
                try:
                    current_process.terminate()
                    current_process.wait(timeout=5)
                    logger.info("Process terminated gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("Process didn't terminate — forcing kill")
                    current_process.kill()
                    try:
                        current_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logger.error("Process could not be killed")
                except Exception as e:
                    logger.error("Error terminating process: %s", e)

        if mission_thread and mission_thread.is_alive():
            mission_thread.join(timeout=10)

        with mission_lock:
            is_running = False

        return {"status": "success", "message": "Mission stopped", "was_running": True}

    except Exception as e:
        logger.error("Failed to stop mission: %s", e)
        with mission_lock:
            is_running = False
            stop_mission_flag.set()
        raise HTTPException(status_code=500, detail=f"Error stopping mission: {e}")


@app.get("/mission_status")
async def mission_status():
    with mission_lock:
        alive = mission_thread.is_alive() if mission_thread else False
        if alive:
            status = "stopping" if stop_mission_flag.is_set() else "running"
        else:
            status = "idle"

        return {
            "status": status,
            "thread_alive": alive,
            "stop_requested": stop_mission_flag.is_set(),
            "is_running": is_running,
        }


@app.get("/logs")
async def get_logs(lines: int = 100):
    try:
        log_file_path = Path(f"{_log_dir}/wildwings.log")
        if not log_file_path.exists():
            return {"logs": ["Log file not found"], "total_lines": 0}

        with open(log_file_path) as f:
            all_lines = f.readlines()

        recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return {
            "logs": [line.strip() for line in recent if line.strip()],
            "total_lines": len(all_lines),
        }
    except Exception as e:
        logger.error("Failed to read logs: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {e}")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=wildwings_config["host"],
        port=wildwings_config["port"],
        access_log=True,
    )
