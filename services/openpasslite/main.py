import logging
import toml
import threading
import importlib
import time
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from pathlib import Path
from AnafiController import AnafiController

# Load configuration
config_path = Path("/app/config.toml")
if not config_path.exists():
    config_path = Path(__file__).parent.parent.parent / "config.toml"
config = toml.load(config_path)
openpasslite_config = config["openpasslite"]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(openpasslite_config["logfile_path"]),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("openpasslite")

# Global mission state with thread safety
mission_lock = threading.Lock()
mission_thread = None
stop_mission_flag = threading.Event()
current_drone = None

def run_mission_background(mission_name: str, lat: Optional[str], long: Optional[str]):
    """Execute mission in background thread"""
    global stop_mission_flag, current_drone
    drone = None
    mission_success = False

    try:
        if stop_mission_flag.is_set():
            logger.info(f"Mission {mission_name} stopped before execution")
            return

        logger.info(f"Starting mission: {mission_name}")
        mission_module = importlib.import_module(f"mission.{mission_name}.script")

        drone = AnafiController(connection_type=1)
        with mission_lock:
            current_drone = drone

        drone.connect()
        logger.info("=" * 60)
        logger.info(f"Drone connected for mission {mission_name}")
        logger.info("=" * 60)

        if hasattr(mission_module, 'run'):
            logger.info(f"Executing mission {mission_name}")
            mission_module.run(drone, lat, long)
            mission_success = True
            logger.info(f"Mission {mission_name} completed successfully")
        else:
            raise Exception(f"'run(drone)' not defined in mission.{mission_name}")

    except Exception as e:
        logger.error(f"Mission {mission_name} failed: {str(e)}")
        mission_success = False
    finally:
        with mission_lock:
            if drone:
                try:
                    logger.info(f"Disconnecting drone for mission {mission_name}")
                    drone.disconnect()
                    logger.info("=" * 60)
                    logger.info("Drone disconnected successfully")
                    logger.info("=" * 60)
                except Exception as disconnect_error:
                    logger.error(f"Error disconnecting drone: {str(disconnect_error)}")
                finally:
                    del drone

            current_drone = None

        stop_mission_flag.clear()

        # Wait for full resource cleanup before next service can connect
        logger.info("Waiting for connection resources to fully release...")
        time.sleep(15)  # Increased cleanup time

        if mission_success:
            logger.info(f"Mission {mission_name} thread finished")
        else:
            logger.error(f"Mission {mission_name} thread finished with errors")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("OpenPassLite service starting up")
    yield
    logger.info("OpenPassLite service shutting down")

    global mission_thread, stop_mission_flag, current_drone

    with mission_lock:
        if mission_thread and mission_thread.is_alive():
            logger.info("Stopping running mission during shutdown")
            stop_mission_flag.set()

        if current_drone:
            try:
                current_drone.disconnect()
                logger.info("Forced drone disconnection during shutdown")
            except Exception as e:
                logger.error(f"Error during forced drone disconnection: {str(e)}")

    if mission_thread and mission_thread.is_alive():
        mission_thread.join(timeout=5.0)

app = FastAPI(
    title="OpenPassLite Service",
    description="OpenPassLite drone control service",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[openpasslite_config["cors_origin"]],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "OpenPassLite Service", "status": "running"}

@app.post("/start_mission")
async def start_mission(name: str, lat: Optional[str] = None, long: Optional[str] = None):
    logger.info(f"Start mission endpoint accessed - Mission: {name}")

    global mission_thread, stop_mission_flag

    if not name:
        logger.error("Mission name is required")
        raise HTTPException(status_code=400, detail="Mission name is required")

    with mission_lock:
        if mission_thread and mission_thread.is_alive():
            logger.error("Mission already running")
            raise HTTPException(status_code=400, detail="Mission already running")

        try:
            stop_mission_flag.clear()
            mission_thread = threading.Thread(
                target=run_mission_background,
                args=(name, lat, long),
                name=f"Mission-{name}",
                daemon=False
            )
            mission_thread.start()

            logger.info(f"Mission {name} started successfully")
            return {
                "status": "success",
                "message": f"Mission '{name}' started",
                "mission_name": name,
                "coordinates": {"lat": lat, "long": long} if lat and long else None
            }

        except Exception as e:
            logger.error(f"Failed to start mission {name}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to start mission: {str(e)}")

@app.post("/stop_mission")
async def stop_mission():
    logger.info("Stop mission endpoint accessed")

    global mission_thread, stop_mission_flag, current_drone

    with mission_lock:
        if not mission_thread or not mission_thread.is_alive():
            logger.error("No mission currently running")
            raise HTTPException(status_code=400, detail="No mission currently running")

        try:
            stop_mission_flag.set()

            if current_drone:
                try:
                    current_drone.disconnect()
                    logger.info("Drone disconnected to stop mission")
                except Exception as disconnect_error:
                    logger.warning(f"Could not disconnect drone during stop: {str(disconnect_error)}")

            logger.info("Mission stop signal sent")
            return {
                "status": "success",
                "message": "Mission stop requested"
            }

        except Exception as e:
            logger.error(f"Failed to stop mission: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to stop mission: {str(e)}")

@app.get("/mission_status")
async def mission_status():
    global mission_thread, stop_mission_flag, current_drone

    with mission_lock:
        if mission_thread and mission_thread.is_alive():
            status = "running"
            if stop_mission_flag.is_set():
                status = "stopping"
        else:
            status = "idle"

        return {
            "status": status,
            "thread_alive": mission_thread.is_alive() if mission_thread else False,
            "stop_requested": stop_mission_flag.is_set(),
            "drone_connected": current_drone is not None
        }

@app.get("/logs")
async def get_logs(lines: int = 100):
    logger.info(f"Logs endpoint accessed - requesting {lines} lines")

    try:
        log_file_path = openpasslite_config["logfile_path"]

        if not Path(log_file_path).exists():
            logger.warning(f"Log file not found at: {log_file_path}")
            return {"logs": ["Log file not found"], "total_lines": 0}

        with open(log_file_path, 'r') as f:
            all_lines = f.readlines()

        recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        logs = [line.strip() for line in recent_lines if line.strip()]

        logger.info(f"Returning {len(logs)} log lines")
        return {"logs": logs, "total_lines": len(all_lines)}

    except Exception as e:
        logger.error(f"Failed to read logs: {str(e)}")
        return {"logs": [f"Error reading logs: {str(e)}"], "total_lines": 0}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=openpasslite_config["host"],
        port=openpasslite_config["port"],
        reload=openpasslite_config["debug"],
        access_log=True
    )
