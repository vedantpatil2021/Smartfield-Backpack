import json
import csv
from pathlib import Path
import time

def run(drone,lat_sample=None, long_sample=None):
    mission_dir = Path(__file__).parent
    config_path = mission_dir / "config.json"
    csv_path = mission_dir / "data.csv"
    
    waypoints = []
    height = 25
    
    try:
        with open(csv_path, 'r') as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                if len(row) >= 2:
                    lat_val = float(row[0])
                    lon_val = float(row[1])
                    waypoints.append((lat_val, lon_val))
    except Exception as e:
        raise Exception(f"Failed to read coordinates from CSV: {e}")
    
    if not waypoints:
        raise Exception("No valid coordinates found in data.csv")
        
    try:
        print("=== INITIALIZING DRONE ===")
        print("=== CONNECTING TO DRONE ===")
        drone.connect()
        print("Connected successfully")
        
        print("=== WAITING FOR GPS STABILIZATION ===")
        time.sleep(10)

        print("=== SETTING UP IMAGE MODE ===")
        drone.camera.media.setup_photo()
        
        print("=== CHECKING GPS STATUS ===")
        coordinates = drone.get_drone_coordinates()
        if not coordinates or coordinates[0] == 0.0 or coordinates[1] == 0.0:
            raise Exception("GPS coordinates not available - drone may not have GPS lock")
        
        print(f"Current GPS coordinates: Lat={coordinates[0]:.6f}, Lon={coordinates[1]:.6f}, Alt={coordinates[2]:.2f}m")
        
        print("=== INITIATING TAKEOFF ===")
        drone.piloting.takeoff()
        print("✓ Takeoff completed")
        
        print("=== STABILIZING AFTER TAKEOFF ===")
        time.sleep(5)
        
        print(f"=== STARTING ORTHOMOSAIC MISSION ===")
        print(f"Total waypoints: {len(waypoints)} at {height}m altitude")
        
        for i, (lat, lon) in enumerate(waypoints):
            print(f"=== WAYPOINT {i+1}/{len(waypoints)} ===")
            print(f"Target: Lat={lat:.6f}, Lon={lon:.6f}, Alt={height}m")
            
            try:
                drone.piloting.move_to(
                    lat=float(lat), 
                    lon=float(lon), 
                    alt=height, 
                    orientation_mode="NONE", 
                    heading=0, 
                    wait=True
                )
                print("Navigation completed successfully")
                
            except AssertionError as e:
                print(f"Navigation with wait=True failed: {e}")
                print("Attempting navigation without waiting...")
                
                drone.piloting.move_to(
                    lat=float(lat), 
                    lon=float(lon), 
                    alt=height, 
                    orientation_mode="NONE", 
                    heading=0, 
                    wait=False
                )
                print("Navigation command sent (not waiting for completion)")
                time.sleep(3)
            
            print("=== CAPTURING IMAGE ===")
            try:
                drone.camera.media.take_photo()
                print("✓ Image captured")
            except Exception as e:
                print(f"Photo capture failed: {e}")
            
            time.sleep(2)
        
        print("=== RETURNING TO HOME ===")
        drone.rth.setup_rth()
        drone.rth.return_to_home()
        print("✓ Returning to home position")
        
        print("=== ORTHOMOSAIC MISSION COMPLETED SUCCESSFULLY ===")
        
    except Exception as e:
        print(f"Orthomosaic mission failed: {e}")
        return False
        
    finally:
        if drone:
            try:
                print("=== DISCONNECTING FROM DRONE ===")
                drone.disconnect()
                print("Disconnected successfully")
            except Exception as e:
                print(f"Disconnect warning: {e}")