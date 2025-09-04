import json
import time
import csv
import os
from pathlib import Path

def run(drone, lat=None, long=None):
    """Main landing mission entry point"""
    mission_dir = Path(__file__).parent
    config_path = mission_dir / "config.json"
    csv_path = mission_dir / "data.csv"

    try:
        print("=== INITIALIZING DRONE ===")
        print("=== CONNECTING TO DRONE ===")
        drone.connect()
        time.sleep(3)
        print("=== SETTING UP RETURN TO HOME ===")
        drone.rth.setup_rth()
        print("=== RETURNING BACK HOME ===")
        drone.rth.return_to_home()
        print("=== MISSION COMPLETED SUCCESSFULLY ===")
        time.sleep(3)
        print("=== DISCONNECTING FROM DRONE ===")
        drone.disconnect()
        
    except Exception as e:
        print(f"Landing mission failed: {e}")
        raise