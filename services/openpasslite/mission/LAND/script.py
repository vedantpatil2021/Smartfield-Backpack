import json
import csv
from pathlib import Path
import time

def run(drone, lat=None, long=None):
    mission_dir = Path(__file__).parent
    config_path = mission_dir / "config.json"
    csv_path = mission_dir / "data.csv"
        
    try:
        drone.connect()
        drone.piloting.land()
        drone.disconnect()

    except Exception as e:
        print(f"Takeoff mission failed: {e}")
        raise