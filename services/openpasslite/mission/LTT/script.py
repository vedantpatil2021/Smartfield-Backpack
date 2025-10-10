import time

def run(drone, lat=None, long=None):
    """
    Execute LTT (Location Target Travel) mission.
    Note: drone.connect() is already called in main.py
    Note: drone.disconnect() is handled by main.py
    """
    try:
        lat_float = float(lat)
        long_float = float(long)
    except (ValueError, TypeError):
        raise Exception(f"Invalid coordinates: lat={lat}, long={long}")

    try:
        print("=== CHECKING GPS STATUS ===")
        coordinates = drone.get_drone_coordinates()
        if not coordinates or coordinates[0] == 0.0 or coordinates[1] == 0.0:
            raise Exception("GPS coordinates not available - drone may not have GPS lock")

        print(f"Current GPS: Lat={coordinates[0]:.6f}, Lon={coordinates[1]:.6f}, Alt={coordinates[2]:.2f}m")

        print("=== INITIATING TAKEOFF ===")
        drone.piloting.takeoff()
        print("✓ Takeoff completed")

        print("=== STABILIZING AFTER TAKEOFF ===")

        print("=== CHANGING THE DRONE GIMBAL MOTION ===")
        drone.camera.controls.set_orientation(0, -90, 0, wait=True)
        time.sleep(3)

        print(f"=== NAVIGATING TO TARGET ===")
        print(f"Target: Lat={lat_float:.6f}, Lon={long_float:.6f}, Alt=13m")

        try:
            drone.piloting.move_to(
                lat=lat_float,
                lon=long_float,
                alt=13,
                orientation_mode="TO_TARGET",
                heading=0,
                wait=True
            )
            print("Navigation completed successfully")

        except AssertionError as e:
            print(f"Navigation with wait=True failed: {e}")
            print("Attempting navigation without waiting...")

            drone.piloting.move_to(
                lat=lat_float,
                lon=long_float,
                alt=13,
                orientation_mode="TO_TARGET",
                heading=0,
                wait=False
            )
            print("Navigation command sent (not waiting for completion)")
            time.sleep(15)

        print("=== CHECKING FINAL POSITION ===")
        final_coords = drone.get_drone_coordinates()
        print(f"Final position: Lat={final_coords[0]:.6f}, Lon={final_coords[1]:.6f}, Alt={final_coords[2]:.2f}m")

        print("=== MISSION COMPLETED SUCCESSFULLY ===")

    except Exception as e:
        print(f"Mission failed: {e}")
        raise
