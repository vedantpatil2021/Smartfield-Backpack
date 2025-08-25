import os
import json
import logging
import paho.mqtt.client as mqtt
import requests
import toml
from pathlib import Path

config_path = Path("/app/config.toml")
if not config_path.exists():
    config_path = Path(__file__).parent.parent.parent / "config.toml"
config = toml.load(config_path)

sub_cfg = config.get("subscriber", {})
topic_mappings = config.get("mqtt_topics", {})

MQTT_BROKER = sub_cfg.get("broker", "localhost")
MQTT_PORT = int(sub_cfg.get("port", 1883))
CLIENT_ID = sub_cfg.get("client_id", "ckn_event_subscriber")
SMARTFIELDS_API = sub_cfg.get("smartfields_url", "http://smartfields:2188/initiate_process")
MQTT_QOS = int(sub_cfg.get("qos", 1))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(sub_cfg["logfile_path"]),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("mqtt_subscriber")

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info("Connected to MQTT broker.")
        for topic in topic_mappings.keys():
            logger.info(f"Subscribing to topic: {topic}")
            client.subscribe(topic, qos=MQTT_QOS)
    else:
        logger.error("Failed to connect with result code %d", rc)

def on_message(client, userdata, msg):
    topic = msg.topic
    try:
        mapping = topic_mappings.get(topic)
        if not mapping:
            logger.warning(f"Received message on unrecognized topic: {topic}")
            return

        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)

        logger.info(f"Received event from topic {topic}:\n{json.dumps(data, indent=2)}")

        lat = mapping["lat"]
        lon = mapping["lon"]
        camid = mapping["camid"]

        response = requests.get(
            SMARTFIELDS_API,
            params={"lat": lat, "lon": lon, "camid": camid},
            timeout=10
        )

        if response.status_code == 200:
            logger.info(f"Triggered SmartFields pipeline for {camid} at ({lat}, {lon})")
        else:
            logger.error(f"Failed to trigger SmartFields pipeline: {response.status_code}, {response.text}")

    except Exception as e:
        logger.exception(f"Error processing message on topic {topic}: {e}")

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=CLIENT_ID)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except Exception as e:
        logger.exception(f"Could not connect to MQTT broker: {e}")
        return

    client.loop_forever()

if __name__ == "__main__":
    main()