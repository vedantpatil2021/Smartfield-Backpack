import cv2
import time
import queue
import olympe
from SoftwarePilot import SoftwarePilot
from ultralytics import YOLO
import navigation as navigation
import sys
import json
import time
import csv
import os
import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/wildwings.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Check if running in Docker
IN_DOCKER = os.environ.get('IN_DOCKER', 'false').lower() == 'true' or os.path.exists('/.dockerenv')

# User-defined mission parameters
DURATION = 25  # duration in seconds

# Retrieve the filename from command-line arguments
if len(sys.argv) < 2:
    logger.error("Usage: python controller.py <output_directory>")
    sys.exit(1)

output_directory = sys.argv[1]
logger.info(f"Output directory: {output_directory}")

# Ensure output directory exists with proper permissions
try:
    os.makedirs(output_directory, exist_ok=True)
    os.chmod(output_directory, 0o755)
except Exception as e:
    logger.error(f"Failed to create output directory: {e}")
    sys.exit(1)

# Define CSV file path to store telemetry data
csv_file_path = os.path.join(output_directory, 'telemetry_log.csv')

# Create images subdirectory
images_dir = os.path.join(output_directory, 'images')
try:
    os.makedirs(images_dir, exist_ok=True)
    os.chmod(images_dir, 0o755)
    logger.info(f"Created images directory: {images_dir}")
except Exception as e:
    logger.error(f"Failed to create images directory: {e}")

# Ensure the CSV file has a header row
if not os.path.exists(csv_file_path):
    try:
        with open(csv_file_path, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["timestamp", "x", "y", "z", "move_x", "move_y", "move_z", "frame"])
        os.chmod(csv_file_path, 0o644)
        logger.info("Created telemetry CSV file")
    except Exception as e:
        logger.error(f"Failed to create CSV file: {e}")

class Tracker:
    def __init__(self, drone, model):
        self.drone = drone
        self.media = drone.camera.media
        self.model = model
        self.frame = None
        self.FPS = 1/60
        self.FPS_MS = int(self.FPS * 1000)
        logger.info("Tracker initialized")

    def track(self):
        logger.info("Starting tracking loop")
        frame_count = 0
        
        while self.media.running:
            yuv_frame = None
            try:
                yuv_frame = self.media.frame_queue.get(timeout=0.1)
                self.media.frame_counter += 1
                frame_count += 1

                if (self.media.frame_counter % 40) == 0:
                    logger.info(f"Processing frame {self.media.frame_counter}")
                    
                    # Get frame info
                    info = yuv_frame.info()
                    height, width = (
                        info["raw"]["frame"]["info"]["height"],
                        info["raw"]["frame"]["info"]["width"],
                    )

                    # Convert YUV to BGR
                    cv2_cvt_color_flag = {
                        olympe.VDEF_I420: cv2.COLOR_YUV2BGR_I420,
                        olympe.VDEF_NV12: cv2.COLOR_YUV2BGR_NV12,
                    }[yuv_frame.format()]

                    cv2frame = cv2.cvtColor(yuv_frame.as_ndarray(), cv2_cvt_color_flag)

                    # Get navigation action
                    x_direction, y_direction, z_direction = navigation.get_next_action(
                        cv2frame, self.model, images_dir, self.media.frame_counter
                    )

                    # Get and save telemetry
                    try:
                        telemetry = drone.get_drone_coordinates()
                        timestamp = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')
                        
                        with open(csv_file_path, mode='a', newline='') as file:
                            writer = csv.writer(file)
                            writer.writerow([timestamp, telemetry[0], telemetry[1], telemetry[2], 
                                           x_direction, y_direction, z_direction, self.media.frame_counter])
                        
                        logger.debug(f"Telemetry saved for frame {self.media.frame_counter}")
                    except Exception as e:
                        logger.error(f"Failed to save telemetry: {e}")

                    # Uncomment to enable drone movement
                    logger.info(f"Coodinate/Direction : {x_direction, y_direction, z_direction, 0}")
                    self.drone.piloting.move_by(x_direction, y_direction, z_direction, 0)

                if yuv_frame is not None:
                    yuv_frame.unref()
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing frame: {e}")
                if yuv_frame is not None:
                    yuv_frame.unref()
                continue

        logger.info(f"Tracking loop ended. Processed {frame_count} frames")

# Main execution
try:
    time.sleep(3)
    # Setup drone
    logger.info("Setting up drone connection")
    sp = SoftwarePilot()

    # Load YOLO model
    logger.info("Loading YOLO model")
    model = YOLO('yolov5su')

    # Connect to drone (drone should be flying from TAKEOFF mission)
    drone = sp.setup_drone("parrot_anafi", 1, "None")
    drone.connect()
    logger.info("=" * 60)
    logger.info("Drone connected")
    logger.info("=" * 60)

    # Wait for stabilization
    time.sleep(3)

    # Create tracker
    tracker = Tracker(drone, model)

    # Setup and start recording
    logger.info("=" * 60)
    logger.info("Starting recording")
    logger.info("=" * 60)
    drone.camera.media.setup_recording()
    drone.camera.media.start_recording()

    time.sleep(5)

    # Start stream with tracking
    logger.info("=" * 60)
    logger.info("Starting video stream")
    logger.info("=" * 60)
    drone.camera.media.setup_stream(yuv_frame_processing=tracker.track)
    drone.camera.media.start_stream()

    # Setup OpenCV window (only if not in Docker or if display is available)
    if not IN_DOCKER or os.environ.get('DISPLAY'):
        try:
            cv2.namedWindow('tracking', cv2.WINDOW_KEEPRATIO)
            cv2.resizeWindow('tracking', 500, 500)
            cv2.moveWindow('tracking', 0, 0)
            logger.info("OpenCV window created")
        except Exception as e:
            logger.warning(f"Could not create OpenCV window (running headless): {e}")

    # Run for specified duration
    logger.info(f"Running mission for {DURATION} seconds")
    time.sleep(DURATION)

    # Stop stream
    logger.info("=" * 60)
    logger.info("Stopping stream")
    logger.info("=" * 60)
    drone.camera.media.stop_stream()

    # Stop recording
    logger.info("=" * 60)
    logger.info("Stopping recording")
    logger.info("=" * 60)
    drone.camera.media.stop_recording()

    # Disconnect
    logger.info("=" * 60)
    logger.info("Disconnecting drone")
    logger.info("=" * 60)
    drone.disconnect()
    time.sleep(15)
    logger.info("=" * 60)
    logger.info("Mission Completed")
    logger.info("=" * 60)
    
except Exception as e:
    logger.error(f"Mission failed with error: {e}", exc_info=True)
    cv2.destroyAllWindows()
    sys.exit(1)
finally:
    cv2.destroyAllWindows()