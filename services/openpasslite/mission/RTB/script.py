import time

def run(drone, lat=None, long=None):
    """
    Execute RTB (Return to Base) mission.
    Note: drone.connect() is already called in main.py
    Note: drone.disconnect() is handled by main.py
    """
    try:
        print("=== SETTING UP RETURN TO HOME ===")
        drone.rth.setup_rth()

        print("=== RETURNING BACK HOME ===")
        drone.rth.return_to_home()

        print("=== MISSION COMPLETED SUCCESSFULLY ===")
        time.sleep(3)

    except Exception as e:
        print(f"RTB mission failed: {e}")
        raise
