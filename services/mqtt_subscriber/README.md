# TODO: Add content of this ReadMe into the main ReadMe file 

# Smart Field MQTT Subscriber

This service listens to camera trap event messages published via MQTT and triggers drone missions based on each camera’s GPS location.

## What's this all about?

In the field, multiple Raspberry Pi-based backpack camera traps detect wildlife activity. Each Pi publishes events (like new images captured) to its own MQTT topic.

This service subscribes to those MQTT topics, maps each topic to a specific **GPS location**, and then calls the drone pipeline (`initiate_process`) with the correct coordinates. That way, a drone knows *exactly* where to fly next.

---

## How it Works

1. Each Raspberry Pi publishes to a **unique MQTT topic**, like:
pi/001/event1
pi/002/event2

2. This subscriber listens to all of them and uses a mapping config to determine:
- Which Pi sent the event
- What its latitude & longitude is
- Which camera ID is associated

3. Once an event is received, it automatically triggers the `/initiate_process` API of the **smartfields** service with the right GPS data.