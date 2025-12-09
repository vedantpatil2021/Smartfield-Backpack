import logging
import toml
import threading
import subprocess
import os
import time
import sys
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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(wildwings_config["logfile_path"], mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("wildwings")

# Global mission state with thread safety
mission_lock = threading.Lock()
mission_thread = None
stop_mission_flag = threading.Event()
current_process = None
is_running = False
mission_lat = None
mission_lon = None

def run_mission_background():
    """Execute mission in background thread"""
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

        # Create mission directory
        mission_dir = Path("/app/mission")
        mission_dir.mkdir(exist_ok=True)

        # Execute launch.sh script
        script_path = Path("/app/launch.sh")
        if not script_path.exists():
            raise FileNotFoundError(f"Launch script not found: {script_path}")

        os.chmod(script_path, 0o755)

        # Run the launch script
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'

        # Add lat/lon to environment if provided
        if mission_lat is not None:
            env['MISSION_LAT'] = str(mission_lat)
            logger.info(f"Setting MISSION_LAT={mission_lat}")
        if mission_lon is not None:
            env['MISSION_LON'] = str(mission_lon)
            logger.info(f"Setting MISSION_LON={mission_lon}")

        with mission_lock:
            current_process = subprocess.Popen(
                ["bash", str(script_path)],
                cwd="/app",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                env=env
            )

        logger.info("Mission subprocess started successfully")

        # Stream output
        for line in iter(current_process.stdout.readline, ''):
            if stop_mission_flag.is_set():
                logger.info("Stop signal received, terminating mission")
                with mission_lock:
                    if current_process:
                        current_process.terminate()
                mission_success = False
                break

            if line.strip():
                logger.info(f"Mission output: {line.strip()}")

        with mission_lock:
            if current_process:
                current_process.wait()
                return_code = current_process.returncode
                logger.info(f"Mission process exited with return code: {return_code}")

                if return_code != 0:
                    logger.error(f"Mission failed with return code: {return_code}")
                    mission_success = False
                else:
                    logger.info("Mission completed successfully")
                    mission_success = True

    except Exception as e:
        logger.error(f"Mission failed: {str(e)}")
        mission_success = False
    finally:
        # Cleanup process
        with mission_lock:
            if current_process:
                try:
                    if current_process.poll() is None:
                        logger.info("Terminating process...")
                        current_process.terminate()
                        try:
                            current_process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            logger.warning("Process did not terminate, forcing kill...")
                            current_process.kill()
                            current_process.wait(timeout=2)
                    logger.info("Process cleanup completed")
                except Exception as cleanup_error:
                    logger.error(f"Error during process cleanup: {cleanup_error}")

            is_running = False
            current_process = None
            stop_mission_flag.clear()

        # Wait for connection cleanup
        logger.info("Waiting for connection cleanup (5 seconds)...")
        time.sleep(5)

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
                    logger.warning("Process didn't terminate gracefully, forcing kill")
                    current_process.kill()
                    try:
                        current_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logger.error("Process couldn't be killed")
                except Exception as e:
                    logger.error(f"Error terminating process: {e}")

    if mission_thread:
        mission_thread.join(timeout=10.0)

    is_running = False

app = FastAPI(
    title="WildWings Service",
    description="WildWings wildlife monitoring service",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[wildwings_config["cors_origin"]],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "WildWings Service", "status": "running"}

@app.post("/start_mission")
async def start_mission(
    lat: float = Query(None, description="Optional latitude coordinate"),
    lon: float = Query(None, description="Optional longitude coordinate")
):
    logger.info(f"Start mission endpoint accessed with lat={lat}, lon={lon}")

    global mission_thread, stop_mission_flag, is_running, mission_lat, mission_lon

    with mission_lock:
        if mission_thread and mission_thread.is_alive():
            logger.warning("Mission request rejected - mission already running")
            raise HTTPException(status_code=409, detail="Mission is currently running")

        if is_running:
            logger.warning("Mission request rejected - mission state indicates running")
            raise HTTPException(status_code=409, detail="Mission is currently running")

        # Store lat/lon for the mission
        mission_lat = lat
        mission_lon = lon

    try:
        stop_mission_flag.clear()
        mission_thread = threading.Thread(
            target=run_mission_background,
            name="WildWings-Mission",
            daemon=False
        )
        mission_thread.start()

        logger.info("WildWings mission started successfully")
        response = {
            "status": "success",
            "message": "WildWings mission started"
        }
        if lat is not None:
            response["lat"] = lat
        if lon is not None:
            response["lon"] = lon
        return response

    except Exception as e:
        logger.error(f"Failed to start mission: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start mission: {str(e)}")

@app.post("/stop_mission")
async def stop_mission():
    logger.info("Stop mission endpoint accessed")

    global mission_thread, stop_mission_flag, current_process, is_running

    with mission_lock:
        if not mission_thread or not mission_thread.is_alive():
            if not is_running:
                logger.info("No mission currently running")
                return {
                    "status": "success",
                    "message": "No mission currently running",
                    "was_running": False
                }

    try:
        stop_mission_flag.set()
        logger.info("Stop mission flag set")

        # Terminate the process
        with mission_lock:
            if current_process:
                logger.info("Terminating current process")
                try:
                    current_process.terminate()
                    current_process.wait(timeout=5)
                    logger.info("Process terminated gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("Process didn't terminate gracefully, forcing kill")
                    current_process.kill()
                    try:
                        current_process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        logger.error("Process couldn't be killed")
                except Exception as e:
                    logger.error(f"Error terminating process: {e}")

        # Wait for mission thread
        if mission_thread and mission_thread.is_alive():
            logger.info("Waiting for mission thread to finish")
            mission_thread.join(timeout=10)

        with mission_lock:
            is_running = False

        logger.info("Mission stopped successfully")
        return {
            "status": "success",
            "message": "Mission stopped successfully",
            "was_running": True
        }

    except Exception as e:
        logger.error(f"Failed to stop mission: {str(e)}")
        with mission_lock:
            is_running = False
            stop_mission_flag.set()
        raise HTTPException(status_code=500, detail=f"Error stopping mission: {str(e)}")

@app.get("/mission_status")
async def mission_status():
    global mission_thread, stop_mission_flag, is_running

    with mission_lock:
        if mission_thread and mission_thread.is_alive():
            status = "running"
            if stop_mission_flag.is_set():
                status = "stopping"
        else:
            status = "idle"

        thread_alive = mission_thread.is_alive() if mission_thread else False
        stop_requested = stop_mission_flag.is_set()
        running_state = is_running

    return {
        "status": status,
        "thread_alive": thread_alive,
        "stop_requested": stop_requested,
        "is_running": running_state
    }

@app.get("/logs")
async def get_logs(lines: int = 100):
    logger.info(f"Logs endpoint accessed - requesting {lines} lines")

    try:
        log_file_path = wildwings_config["logfile_path"]

        if not Path(log_file_path).exists():
            logger.warning(f"Log file not found at: {log_file_path}")
            return {"logs": ["Log file not found"], "total_lines": 0}

        with open(log_file_path, 'r') as f:
            all_lines = f.readlines()

        recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        file_logs = [line.strip() for line in recent_lines if line.strip()]

        logger.info(f"Returning {len(file_logs)} log lines")
        return {"logs": file_logs, "total_lines": len(all_lines)}

    except Exception as e:
        logger.error(f"Failed to read logs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=wildwings_config["host"],
        port=wildwings_config["port"],
        reload=wildwings_config["debug"],
        access_log=True
    )
