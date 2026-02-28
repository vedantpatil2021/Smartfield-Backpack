import time

def run(drone, lat=None, long=None):
    """
    Execute landing mission.
    Note: drone.connect() is already called in main.py
    Note: drone.disconnect() is handled by main.py
    """
    try:
        drone.piloting.land()
        time.sleep(5)

    except Exception as e:
        print(f"Landing mission failed: {e}")
        raise
