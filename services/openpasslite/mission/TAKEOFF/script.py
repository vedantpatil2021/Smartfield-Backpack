import time

def run(drone, lat=None, long=None):
    """
    Execute takeoff mission.
    Note: drone.connect() is already called in main.py
    Note: drone.disconnect() is handled by main.py
    """
    try:
        drone.piloting.takeoff()
        time.sleep(8)

    except Exception as e:
        print(f"Takeoff mission failed: {e}")
        raise
