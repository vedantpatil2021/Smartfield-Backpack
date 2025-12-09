# Smart Backpack System for Animal Ecology

A field-deployable multimodal data infrastructure that integrates autonomous sensing, edge computing, and drone-based platforms to address critical data acquisition challenges in animal ecology research.

[![Software](https://img.shields.io/badge/category-Software-blue.svg)](https://github.com/)
[![Animal Ecology](https://img.shields.io/badge/category-Animal%20Ecology-green.svg)](https://github.com/)

### License
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## References

### Key Resources
- **Demo Video**: [System Operations and Autonomous Pipeline Execution](https://buckeyemailosu-my.sharepoint.com/:v:/g/personal/patil_343_buckeyemail_osu_edu/IQBnJR_YInoXRbbbfIbrRYj_AV5D1jZoJDbXNOzmpaFvDzY)
- **Parrot Olympe SDK**: [Drone Control Framework](https://github.com/KevynAngueira/SoftwarePilothttps://github.com/KevynAngueira/SoftwarePilot)
- **Docker Documentation**: [Container Deployment Guide](https://docs.docker.com/)
- **MQTT Protocol**: [IoT Messaging Standard](https://mqtt.org/)

### Key Terms
- **Camera-trap**: Edge-based machine learning system for real-time animal detection using motion-triggered image capture
- **UAS (Unmanned Aerial System)**: Autonomous drone platform for aerial video monitoring
- **Detection-to-Documentation Pipeline**: Automated workflow from ground-level detection to aerial observation
- **Edge Computing**: Local data processing at the point of collection without cloud dependency
- **Multimodal Data**: Synchronized datasets combining ground-level imagery with aerial videography

## Acknowledgements

*National Science Foundation (NSF) funded AI institute for Intelligent Cyberinfrastructure with Computational Learning in the Environment (ICICLE) (OAC 2112606)*

---

# Tutorials

## Getting Started with Smart Backpack Deployment

### Overview
This tutorial guides you through deploying the complete Smart Backpack system from camera-trap configuration to autonomous drone operations.

### Prerequisites

#### Hardware Requirements
- **Raspberry Pi 4B**: 64GB Storage, 4GB RAM minimum
- **Webcam**: USB-compatible camera for animal detection
- **WiFi Router**: Local network infrastructure
- **Power Station**: Portable power supply for field deployment
- **Parrot ANAFI Drone** (optional): For full autonomous pipeline

#### Software Requirements
- Docker Engine (v20.10+)
- Docker Compose (v2.0+)
- Python 3.9+
- Linux-based OS (tested on Ubuntu 20.04+)

### Step-by-Step Deployment

#### Step 1: Camera-Trap Configuration

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd smartfield
   ```

2. Navigate to the camera-trap configuration directory:
   ```bash
   cd ct-config
   ```

3. Edit `cameratrap-config.py` to set your controller IP:
   ```python
   controller_ip = 'http://icicle-ct1.local:8080'
   ```

4. Configure the camera-trap by running each section sequentially:

   **Health Check**:
   ```python
   response = requests.get(f'{controller_ip}/health')
   print(response.json())
   ```

   **System Startup**:
   ```python
   response = requests.post(f'{controller_ip}/startup', json={},
                           headers={'Content-Type': 'application/json'})
   ```

   **Configure Detection Parameters**:
   ```python
   payload = {
       "gpu": "false",
       "ckn_mqtt_broker": "192.168.0.122",  # Your MQTT broker IP
       "ct_version": "test",
       "mode": "demo",
       "min_seconds_between_images": "5",
       "model": "yolov5nu_ep120_bs32_lr0.001_0cfb1c03.pt",
       "inference_server": "false",
       "detection_thresholds": "{\"animal\": \"0.4\", \"image_store_save_threshold\": \"0\", \"image_store_reduce_save_threshold\": \"0\"}"
   }
   response = requests.post(f'{controller_ip}/configure', json=payload)
   ```

   **Start Detection**:
   Note: Run the file everytime when you comment and uncomment the piece of code. Dont run the entire file. Run every section of code one by one.
   ```python
   response = requests.post(f'{controller_ip}/run')
   ```

5. Run the configuration:
   ```bash
   python3 cameratrap-config.py
   ```

#### Step 2: System Installation

1. Create required directories:
   ```bash
   mkdir -p logs mission AnafiMedia
   ```

2. Configure system settings in `config.toml`:
   ```bash
   nano config.toml
   ```

   **IMPORTANT**: Update the camera-trap location coordinates precisely. The drone uses these coordinates to navigate to detection sites. Incorrect values will cause the drone to fly to the wrong location.

   ```toml
   # MQTT topic mapping for each Pi
   [mqtt_topics."cameratrap/events"]
   lat = 40.008278960212      # Replace with your camera-trap's exact latitude
   lon = -83.0175149068236    # Replace with your camera-trap's exact longitude
   camid = "pi-001"           # Unique identifier for this camera-trap
   ```

   Also update MQTT broker addresses, network settings, and service endpoints as needed.

3. Build and start services:
   ```bash
   docker-compose up -d
   ```

4. Verify deployment:
   ```bash
   docker-compose ps
   ```

#### Step 3: Verification

Check each service endpoint:
```bash
# OpenPassLite (Mission Planning)
curl http://localhost:2177/

# SmartField (Event Coordination)
curl http://localhost:2188/

# WildWings (Drone Control)
curl http://localhost:2199/
```

#### Step 4: Monitoring Dashboard

Access Grafana at `http://localhost:3000`:
- **Username**: admin
- **Password**: admin


### End Result
Upon successful deployment, you will have:
- ✓ Autonomous camera-trap detecting animals in real-time
- ✓ MQTT-based event communication system
- ✓ Drone coordination ready for autonomous missions
- ✓ Real-time monitoring dashboard
- ✓ Centralized logging infrastructure

---

# How-To Guides

## How to Configure Camera-Trap Detection Thresholds

### Problem Description
Adjusting detection sensitivity to balance false positives against missed detections in varying field conditions.

### Steps

1. Access the camera-trap configuration in [ct-config/cameratrap-config.py](ct-config/cameratrap-config.py)

2. Modify the `detection_thresholds` parameter:
   ```python
   "detection_thresholds": "{\"animal\": \"0.4\", \"image_store_save_threshold\": \"0\", \"image_store_reduce_save_threshold\": \"0\"}"
   ```

3. Threshold values range from 0.0 to 1.0:
   - **0.3-0.4**: High sensitivity (more detections, more false positives)
   - **0.5-0.6**: Balanced (recommended for most scenarios)
   - **0.7-0.8**: High precision (fewer false positives, may miss detections)

4. Apply changes:
   ```bash
   python3 cameratrap-config.py
   ```

### Advanced Tips
- Test different thresholds during daytime before field deployment
- Monitor detection logs in `./logs/` to tune sensitivity
- Use higher thresholds in high-traffic areas to reduce false positives

### Troubleshooting
- **Too many false positives**: Increase threshold to 0.6+
- **Missing obvious animals**: Decrease threshold to 0.3-0.4
- **Camera not responding**: Check network connectivity with `ping icicle-ct1.local`

## How to View Real-Time System Logs

### Problem Description
Monitoring system operations and debugging issues during field deployment.

### Steps

1. **View all service logs**:
   ```bash
   docker-compose logs -f
   ```

2. **View specific service logs**:
   ```bash
   docker-compose logs -f wildwings
   docker-compose logs -f smartfield
   docker-compose logs -f openpasslite
   ```

3. **Filter logs by time**:
   ```bash
   docker-compose logs --since 30m smartfield
   ```

4. **Export logs for analysis**:
   ```bash
   docker-compose logs > system-logs-$(date +%Y%m%d).txt
   ```

### Code Examples

**Python log reader**:
```python
import subprocess

def tail_logs(service_name, lines=50):
    cmd = f"docker-compose logs --tail {lines} {service_name}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout
```

### Troubleshooting
- **Logs not appearing**: Check if service is running with `docker-compose ps`
- **Permission denied**: Run with `sudo` or add user to docker group
- **Disk space issues**: Use the provided [log-cleaner.sh](log-cleaner.sh) script

## How to Manually Trigger a Drone Mission

### Problem Description
Testing drone deployment without waiting for camera-trap detections.

### Steps

1. Ensure drone is connected and WildWings service is running:
   ```bash
   docker-compose ps wildwings
   ```

2. Access the SmartField API to publish a test detection:
   ```bash
   curl -X POST http://localhost:2188/test-detection \
     -H "Content-Type: application/json" \
     -d '{"location": {"lat": 40.0, "lon": -83.0}, "confidence": 0.95}'
   ```

3. Monitor mission execution in logs:
   ```bash
   docker-compose logs -f openpasslite wildwings
   ```

4. Check mission status via OpenPassLite:
   ```bash
   curl http://localhost:2177/mission/status
   ```

### Relevant Configuration

Edit [config.toml](config.toml) to adjust mission parameters:
```toml
[drone]
mission_duration = 45  # seconds
altitude = 10  # meters
video_quality = "high"
```

### Troubleshooting
- **Drone not connecting**: Check USB connection with `lsusb | grep Parrot`
- **Mission fails to start**: Verify GPS lock and battery level
- **Video not recording**: Check storage space in `./AnafiMedia`

## How to Add Custom MQTT Event Handlers

### Problem Description
Extending the system to respond to custom detection events or external triggers.

### Steps

1. Create a new subscriber in [services/mqtt_subscriber/](services/mqtt_subscriber/)

2. Add your handler function:
   ```python
   def on_custom_event(client, userdata, message):
       payload = json.loads(message.payload)
       # Your custom logic here
       print(f"Custom event: {payload}")
   ```

3. Subscribe to your topic:
   ```python
   client.subscribe("smartfield/custom/events")
   client.message_callback_add("smartfield/custom/events", on_custom_event)
   ```

4. Rebuild and restart:
   ```bash
   docker-compose up -d --build mqtt_subscriber
   ```

### Potential Variations
- Filter events by confidence threshold
- Forward events to external systems
- Aggregate multiple detections before triggering actions

### Troubleshooting
- **Messages not received**: Verify topic name matches publisher
- **Connection refused**: Check MQTT broker is running on port 1883
- **Callback not firing**: Ensure proper topic subscription syntax

---

# Explanation

## System Architecture Overview

### Problem Context
Traditional animal ecology fieldwork faces fundamental operational constraints that limit research effectiveness:

- **Manual Data Collection**: Human-operated protocols introduce systematic quality degradation and require continuous field personnel deployment
- **Network Limitations**: Remote study sites operate beyond conventional network infrastructure, precluding real-time monitoring capabilities
- **Single-Modal Systems**: Existing sensing platforms remain predominantly single-modal, requiring multiple independent hardware deployments and increasing complexity
- **Post-Processing Paradigm**: Traditional methodologies sacrifice temporal resolution through delayed data processing workflows
- **Operational Discontinuity**: Repeated battery replacement, manual sensor maintenance, and physical data retrieval create vulnerability to data corruption and storage limitations

### Solution Design

The Smart Backpack System addresses these challenges through an integrated autonomous monitoring framework that combines:

1. **Edge Computing Infrastructure**: Local processing eliminates dependency on network connectivity
2. **Multimodal Sensing**: Unified platform integrating ground and aerial observation capabilities
3. **Autonomous Coordination**: Software-driven orchestration eliminates human intervention requirements
4. **Real-Time Processing**: Immediate inference and decision-making at the point of data capture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Smart Backpack System                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐      ┌──────────────┐      ┌────────────┐ │
│  │ Camera-Trap │─────▶│  SmartField  │─────▶│ WildWings  │ │
│  │  (Detect)   │      │ (Coordinate) │      │  (Observe) │ │
│  └─────────────┘      └──────────────┘      └────────────┘ │
│         │                     │                     │        │
│         └─────────────────────┴─────────────────────┘        │
│                           │                                   │
│                      ┌────▼────┐                             │
│                      │  MQTT   │                             │
│                      │ Broker  │                             │
│                      └─────────┘                             │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Monitoring Stack (Grafana/Loki)              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Module Architecture

#### 1. Camera-Trap Module
**Purpose**: Real-time animal detection at the edge

**Key Design Decisions**:
- **Motion-Triggered Capture**: Reduces power consumption and storage requirements
- **Edge ML Inference**: YOLOv5 model runs locally, eliminating network dependency
- **Threshold-Based Classification**: Configurable confidence scoring balances sensitivity and precision
- **MQTT Publishing**: Lightweight event notification enables loose coupling

**Why This Approach**:
Traditional camera-traps store all images for post-processing. Our edge inference approach provides immediate classification, reducing data volume by 95% and enabling real-time system response.

#### 2. SmartField Module
**Purpose**: Central event coordination and mission orchestration

**Key Design Decisions**:
- **Event-Driven Architecture**: Reacts to detection events rather than polling
- **Stateless Processing**: Enables horizontal scaling and fault tolerance
- **API-First Design**: RESTful interfaces allow easy integration with external systems

**Why This Approach**:
A centralized coordinator ensures system-wide state consistency while maintaining loose coupling between detection and response modules.

#### 3. OpenPassLite Module
**Purpose**: Autonomous drone mission planning

**Key Design Decisions**:
- **Geospatial Planning**: Converts detection coordinates to flight paths
- **Temporal Optimization**: Schedules missions to minimize flight time and battery usage
- **Safety-First Logic**: Pre-flight checks, no-fly zones, and emergency protocols

**Why This Approach**:
Separating mission planning from execution allows sophisticated path optimization while keeping the drone control layer simple and responsive.

#### 4. WildWings Module
**Purpose**: Drone control and video capture

**Key Design Decisions**:
- **Olympe SDK Integration**: Leverages Parrot's official Python SDK for reliable control
- **Video Pipeline**: Hardware-accelerated encoding reduces processing overhead
- **Privileged Container**: Direct hardware access for USB and networking

**Why This Approach**:
Using an open-source autonomous UAS platform ensures reproducibility and allows researchers to modify flight behaviors for specific study requirements.

### Detection-to-Documentation Pipeline

The system orchestrates a comprehensive autonomous workflow:

```
1. Camera-Trap Detects Animal (Confidence > 0.4)
                  ↓
2. MQTT Event Published (Location, Timestamp, Species)
                  ↓
3. SmartField Receives Event & Validates
                  ↓
4. OpenPassLite Plans Mission (Path, Altitude, Duration)
                  ↓
5. WildWings Executes Flight (40-50 seconds)
                  ↓
6. Video Captured & Stored (AnafiMedia/)
                  ↓
7. OpenPassLite Plans Return-To-Home Mission (Path, Altitude, Duration)
                  ↓
8. System Returns to Standby
```

**Result**: Synchronized multimodal dataset with ground-level detection paired with aerial behavioral observation—without human intervention.

### Network Architecture

**Host Networking Mode**: All services use `network_mode: host` for:
- Direct hardware access (USB devices, cameras)
- Low-latency inter-service communication
- Simplified port management in field deployments

**Message-Oriented Middleware**: MQTT broker provides:
- Publish-subscribe pattern for loose coupling
- Quality of Service (QoS) guarantees for critical messages
- Persistent sessions for network interruption resilience

### Monitoring and Observability

**Loki + Promtail + Grafana Stack**:
- **Loki**: Efficient log aggregation without indexing overhead
- **Promtail**: Scrapes logs from all services automatically
- **Grafana**: Real-time visualization with custom dashboards

**Design Rationale**: Field deployments require operational visibility without external dependencies. The embedded monitoring stack provides insights even when disconnected from internet.

### Field Validation

**Testing Profile**:
- **Duration**: 20 hours continuous operation
- **Detections**: 45+ animal detection events processed
- **Missions**: 38 autonomous drone deployments completed
- **Success Rate**: 92% mission completion (failures due to low battery)

**Validation Scope**:
- Complete detection-deployment-recovery cycles
- Network resilience testing (WiFi disconnections)
- Power management under field conditions
- Weather resistance (light rain, wind gusts)

### Design Patterns Used

1. **Event-Driven Architecture**: Asynchronous communication enables independent module evolution
2. **Microservices**: Containerized services allow independent scaling and deployment
3. **Publisher-Subscriber**: MQTT decouples event producers from consumers
4. **Infrastructure as Code**: Docker Compose enables reproducible deployments
5. **Centralized Logging**: Observability without code instrumentation

### Future Extensibility

The architecture supports:
- **Multi-Camera Networks**: MQTT topics can namespace multiple camera-traps
- **Advanced ML Models**: Swap detection models without changing pipeline
- **Cloud Integration**: Optional data sync when network available
- **Additional Sensors**: Acoustic, thermal, or environmental monitoring
- **Multi-Drone Coordination**: Scale to fleet operations

### Suggested Readings

- [Edge Computing in Wildlife Monitoring](https://example.com) - Survey of ML at the edge
- [Autonomous UAS for Ecology](https://example.com) - Drone applications in field research
- [MQTT Protocol Specification](https://mqtt.org/mqtt-specification/) - Understanding message patterns
- [Docker Compose Best Practices](https://docs.docker.com/compose/compose-file/) - Production deployments
- [YOLOv5 Documentation](https://github.com/ultralytics/yolov5) - Understanding object detection

---

## System Requirements

### Minimum Specifications
- **Processor**: Dual-core ARM/x86 (Raspberry Pi 4B compatible)
- **RAM**: 4GB
- **Storage**: 64GB (32GB for OS/software, 32GB for data)
- **Network**: WiFi 802.11n or Ethernet
- **OS**: Linux kernel 5.x+ (Ubuntu 20.04+ recommended)

### Recommended Specifications
- **Processor**: Quad-core ARM64/x86_64
- **RAM**: 8GB
- **Storage**: 128GB+ (SSD preferred)
- **GPU**: Optional for accelerated ML inference
- **Network**: Dual-band WiFi for drone control separation

### Power Requirements
- **Idle**: ~15W (all services running, no drone)
- **Active Detection**: ~20W (camera + inference)
- **Drone Mission**: ~25W (includes video processing)
- **Recommended Battery**: 200Wh+ power station for 8+ hours

---

**Note**: This system is designed for ecological research purposes. Ensure compliance with local regulations regarding drone operation and wildlife monitoring in your deployment area.
