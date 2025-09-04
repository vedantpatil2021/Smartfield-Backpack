import logging
import toml
import threading
import subprocess
import datetime
import os
import time
import json
import asyncio
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from pathlib import Path

config_path = Path("/app/config.toml")
if not config_path.exists():
    config_path = Path(__file__).parent.parent.parent / "config.toml"
config = toml.load(config_path)
wildwings_config = config["wildwings"]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(wildwings_config["logfile_path"]),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("wildwings")

logs: List[str] = []
is_running = False
current_process = None

def run_mission():
    global logs, is_running, current_process
    try:
        is_running = True
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"missions/mission_record_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs("logs", exist_ok=True)
        
        logs.append(f"Starting mission at {timestamp}")
        logger.info(f"Starting mission with output directory: {output_dir}")
        
        current_process = subprocess.Popen(
            ["conda", "run", "-n", "wildwing", "python", "controller.py", output_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        for line in current_process.stdout:
            if current_process.poll() is None or line:
                log_entry = line.strip()
                if log_entry:  # Only add non-empty lines
                    logs.append(log_entry)
                    logger.info(f"Mission log: {log_entry}")
            else:
                break
        
        current_process.wait()
        logs.append("Mission completed")
        logger.info("Mission completed successfully")
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logs.append(error_msg)
        logger.error(f"Mission failed: {str(e)}")
    finally:
        is_running = False
        current_process = None

async def log_stream_generator():
    yield f"data: {json.dumps({'message': 'Mission started', 'status': 'running'})}\n\n"
    
    last_log_count = 0
    while is_running or last_log_count < len(logs):
        current_log_count = len(logs)
        if current_log_count > last_log_count:
            new_logs = logs[last_log_count:current_log_count]
            for log in new_logs:
                yield f"data: {json.dumps({'log': log, 'status': 'running' if is_running else 'completed'})}\n\n"
            last_log_count = current_log_count
        
        await asyncio.sleep(0.5)
    
    yield f"data: {json.dumps({'message': 'Mission completed', 'status': 'completed'})}\n\n"

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("WildWings service starting up")
    yield
    logger.info("WildWings service shutting down")
    global current_process, is_running
    if current_process and is_running:
        logger.info("Terminating running mission during shutdown")
        current_process.terminate()
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

@app.post("/start")
async def start_mission():
    logger.info("Start mission endpoint accessed")
    
    global logs, is_running
    
    if is_running:
        async def error_stream():
            yield f"data: {json.dumps({'error': 'Mission already running'})}\n\n"
        
        return StreamingResponse(
            error_stream(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
            }
        )
    
    logs.clear()
    threading.Thread(target=run_mission, name="WildWings-Mission").start()
    
    return StreamingResponse(
        log_stream_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
        }
    )

@app.post("/stop_mission")
async def stop_mission():
    logger.info("Stop mission endpoint accessed")
    
    global is_running, current_process
    
    if not is_running:
        logger.error("No mission currently running")
        raise HTTPException(status_code=400, detail="No mission running")
    
    if current_process:
        try:
            current_process.terminate()
            logs.append("Mission stopped by user")
            is_running = False
            logger.info("Mission stopped by user request")
            
            return {
                "message": "Mission stopped", 
                "status": "stopped"
            }
        except Exception as e:
            logger.error(f"Failed to stop mission: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to stop mission: {str(e)}")
    else:
        logger.error("No process to terminate")
        raise HTTPException(status_code=400, detail="No process to terminate")

@app.get("/mission_status")
async def mission_status():
    global is_running, logs
    
    status = "running" if is_running else "idle"
    recent_logs = logs[-10:] if len(logs) > 10 else logs
    
    return {
        "status": status,
        "is_running": is_running,
        "total_logs": len(logs),
        "recent_logs": recent_logs
    }

@app.get("/logs")
async def get_logs():
    return {
        "logs": logs,
        "total_count": len(logs),
        "is_running": is_running
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=wildwings_config["host"],
        port=wildwings_config["port"],
        reload=wildwings_config["debug"],
        access_log=True
    )