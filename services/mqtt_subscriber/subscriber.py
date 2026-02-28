import os
import json
import logging
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import paho.mqtt.client as mqtt
import requests
import toml

# ── Config ────────────────────────────────────────────────────────────────────
config_path = Path("/app/config.toml")
if not config_path.exists():
    config_path = Path(__file__).parent.parent.parent / "config.toml"
config = toml.load(config_path)

sub_cfg = config.get("subscriber", {})
# Topics live under [subscriber.topics.*] in the new config structure
topic_mappings = sub_cfg.get("topics", config.get("mqtt_topics", {}))

MQTT_BROKER = sub_cfg.get("broker", "localhost")
MQTT_PORT = int(sub_cfg.get("port", 1883))
CLIENT_ID = sub_cfg.get("client_id", "smartfield-subscriber")
MQTT_QOS = int(sub_cfg.get("qos", 1))
SMARTFIELDS_URL = sub_cfg.get("smartfields_url", "http://smartfields:2188/initiate_pipeline")
RECONNECT_MAX_DELAY = int(sub_cfg.get("reconnect_max_delay_seconds", 60))

# ── Logging ───────────────────────────────────────────────────────────────────
_log_dir = "/var/log/smartfield"
Path(_log_dir).mkdir(parents=True, exist_ok=True)
_log_level = sub_cfg.get("log_level", "INFO").upper()
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"{_log_dir}/mqtt_subscriber.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("mqtt_subscriber")


# ── Health check HTTP server (port 8080) ─────────────────────────────────────
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # suppress default access log noise


def _start_health_server() -> None:
    server = HTTPServer(("0.0.0.0", 8080), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="health-server")
    thread.start()
    logger.info("Health server listening on :8080")


# ── MQTT callbacks ────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("Connected to MQTT broker %s:%d", MQTT_BROKER, MQTT_PORT)
        for topic in topic_mappings:
            client.subscribe(topic, qos=MQTT_QOS)
            logger.info("Subscribed to topic: %s", topic)
    else:
        logger.error("MQTT connect failed with result code %d", rc)


def on_disconnect(client, userdata, rc, properties=None, reason=None):
    if rc != 0:
        logger.warning("Unexpected MQTT disconnect (rc=%d) — will reconnect", rc)


def on_message(client, userdata, msg):
    topic = msg.topic
    try:
        mapping = topic_mappings.get(topic)
        if not mapping:
            logger.warning("Message on unrecognized topic: %s", topic)
            return

        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)
        logger.info("Event on %s:\n%s", topic, json.dumps(data, indent=2))

        lat = mapping["lat"]
        lon = mapping["lon"]
        camid = mapping["camid"]

        response = requests.post(
            SMARTFIELDS_URL,
            params={"lat": lat, "lon": lon, "camid": camid},
            timeout=10,
        )

        if response.status_code == 200:
            logger.info("Pipeline triggered for %s at (%s, %s)", camid, lat, lon)
        else:
            logger.error(
                "Pipeline trigger failed: %d — %s", response.status_code, response.text
            )

    except Exception as e:
        logger.exception("Error processing message on %s: %s", topic, e)


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    _start_health_server()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    # Exponential backoff reconnect loop
    delay = 1
    while True:
        try:
            logger.info("Connecting to MQTT broker %s:%d ...", MQTT_BROKER, MQTT_PORT)
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            client.loop_forever()
            # loop_forever exits only on explicit disconnect
            break
        except Exception as e:
            logger.error("MQTT connection error: %s — retrying in %ds", e, delay)
            time.sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_DELAY)


if __name__ == "__main__":
    main()
