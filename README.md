# SmartField


## System Requirements

- **OS**: Ubuntu 22.04 LTS
- **RAM**: Minimum 4GB
- **Hardware**: Anafi Parrot drone
- **Software**: Docker and Docker Compose

## Services

### openpasslite (:2177) - Anafi drone control with LTT/RTB missions

**Description**: Controls Anafi Parrot drone for various mission types including Land, Takeoff, Lauch to Target (LTT), Return to Base (RTB), and Orthomosaic missions.

#### API Endpoints

- **`GET /`** - Health check
  - **Response**: `{"message": "OpenPassLite Service", "status": "running"}`

- **`POST /start_mission`** - Start drone mission
  - **Required Parameters**:
    - `name` (string): Mission name. Available options: `LAND`, `TAKEOFF`, `LTT`, `RTB`, `ORTHOMOSAIC`
  - **Optional Parameters**:
    - `lat` (string): Latitude coordinate 
    - `long` (string): Longitude coordinate (note: parameter is 'long', not 'lon')
  - **Response**: 
    ```json
    {
      "status": "success",
      "message": "Mission 'RTB' started",
      "mission_name": "RTB",
      "coordinates": {"lat": "40.00811", "long": "-83.01809"}
    }
    ```
  - **Error Responses**: 
    - `400`: Mission name required or mission already running
    - `500`: Failed to start mission

- **`POST /stop_mission`** - Stop currently running mission
  - **Parameters**: None
  - **Response**: `{"status": "success", "message": "Mission stop requested"}`
  - **Error Responses**:
    - `400`: No mission currently running
    - `500`: Failed to stop mission

- **`GET /mission_status`** - Get current mission status
  - **Response**:
    ```json
    {
      "status": "running|stopping|idle",
      "thread_alive": true,
      "stop_requested": false
    }
    ```

- **`GET /logs`** - View service logs
  - **Optional Parameters**:
    - `lines` (int): Number of recent log lines to retrieve (default: 100)
  - **Response**: 
    ```json
    {
      "logs": ["log line 1", "log line 2", ...],
      "total_lines": 1000
    }
    ```

#### Available Mission Types
- **LAND**: Landing 
- **TAKEOFF**: Takeoff  
- **LTT**: Launch to Target
- **RTB**: Return to Base mission
- **ORTHOMOSAIC**: Orthomosaic data collection mission

### smartfields (:2188) - Field monitoring and analysis

**Description**: Orchestrates the complete field analysis pipeline by coordinating drone missions and data processing. Manages the execution flow of openpasslite and wildwings services.

#### API Endpoints

- **`GET /`** - Health check
  - **Response**: `{"message": "SmartFields Service", "status": "running"}`

- **`GET /initiate_process`** - Start complete field analysis pipeline
  - **Required Parameters**:
    - `lat` (float): Latitude coordinate (must be valid float)
    - `lon` (float): Longitude coordinate (must be valid float)
  - **Optional Parameters**:
    - `camid` (string): Camera trap ID for identification
  - **Response**:
    ```json
    {
      "message": "Process initiated with coordinates: 40.00811,-83.01809. Pipeline started.",
      "status": "pipeline_started",
      "coordinates": {"lat": 40.00811, "lon": -83.01809},
      "camera_id": "cam001"
    }
    ```
  - **Error Responses**:
    - `400`: Invalid coordinates (must be valid numbers)
    - `409`: Pipeline already running

- **`GET /logs`** - View service logs (HTML format)
  - **Response**: HTML formatted log content
  - **Content-Type**: `text/html`

- **`GET /pipeline_status`** - Get current pipeline execution status
  - **Response**:
    ```json
    {
      "pipeline_running": true,
      "coordinates": {"lat": 40.00811, "lon": -83.01809},
      "status": "running|idle"
    }
    ```

- **`GET /health`** - Service health check with dependencies
  - **Response**:
    ```json
    {
      "status": "healthy",
      "pipeline_running": false,
      "services_configured": ["openpasslite", "wildwings"],
      "service": "smartfields"
    }
    ```
  - **Error Response**: `503`: Service unhealthy

- **`POST /start_mission`** - Legacy endpoint (deprecated)
  - **Response**: `400`: Use /initiate_process endpoint instead

- **`POST /stop_mission`** - Stop all missions across services
  - **Parameters**: None
  - **Response**:
    ```json
    {
      "message": "Stopped missions: openpasslite, wildwings",
      "stopped_services": ["openpasslite", "wildwings"],
      "failed_services": [],
      "status": "success"
    }
    ```
  - **Error Responses**:
    - `500`: Service configuration not found or no missions stopped

#### Pipeline Flow
The smartfields service orchestrates the following sequence:
1. **LTT Mission**: Executes Launch to Target mission via openpasslite
2. **30-second delay**: Waits between missions
3. **RTB Mission**: Executes Return to Base mission via openpasslite

### wildwings (:2199) - Route visualization and navigation

**Description**: Handles wildlife monitoring missions with route visualization and navigation capabilities. Provides real-time mission streaming and log management.

#### API Endpoints

- **`GET /`** - Health check
  - **Response**: `{"message": "WildWings Service", "status": "running"}`

- **`POST /start_mission`** - Start navigation/monitoring mission
  - **Parameters**: None
  - **Response**: Server-Sent Events (SSE) stream
    - **Content-Type**: `text/event-stream`
    - **Stream Data**:
      ```json
      data: {"message": "Mission started", "status": "running"}
      data: {"log": "Starting mission at 20240813_143022", "status": "running"}
      data: {"message": "Mission completed", "status": "completed"}
      ```
  - **Error Response**: Stream with error if mission already running
    ```json
    data: {"error": "Mission already running"}
    ```

- **`POST /stop_mission`** - Stop currently running mission
  - **Parameters**: None
  - **Response**: `{"message": "Mission stopped", "status": "stopped"}`
  - **Error Responses**:
    - `400`: No mission running or no process to terminate
    - `500`: Failed to stop mission

- **`GET /mission_status`** - Get current mission status with recent logs
  - **Response**:
    ```json
    {
      "status": "running|idle",
      "is_running": true,
      "total_logs": 25,
      "recent_logs": ["log1", "log2", ...]
    }
    ```

- **`GET /logs`** - Get all mission logs
  - **Response**:
    ```json
    {
      "logs": ["Complete log history"],
      "total_count": 100,
      "is_running": false
    }
    ```

#### Mission Output
- Creates timestamped mission directories: `missions/mission_record_{YYYYMMDD_HHMMSS}`
- Executes `controller.py` for mission logic
- Provides real-time log streaming via Server-Sent Events

## Monitoring Stack

- **Grafana** (:3000) - Dashboard (admin/admin)
- **Loki** (:3100) - Log aggregation
- **Promtail** - Log collection

## Quick Start

```bash
# Build and run all services
docker-compose up --build

# Or with Podman
podman-compose up --build
```

## API Usage Examples

### SmartFields Pipeline
```bash
# Start complete field analysis pipeline
curl "http://127.0.0.1:2188/initiate_process?lat=40.00811&lon=-83.01809&camid=cam001"

# Check pipeline status
curl "http://127.0.0.1:2188/pipeline_status"

# Stop all missions
curl -X POST "http://127.0.0.1:2188/stop_mission"
```

### OpenPassLite Drone Control
```bash
# Start specific drone mission
curl -X POST "http://127.0.0.1:2177/start_mission?name=RTB&lat=40.00811&long=-83.01809"

# Check mission status
curl "http://127.0.0.1:2177/mission_status"

# Stop current mission
curl -X POST "http://127.0.0.1:2177/stop_mission"

# Get recent logs
curl "http://127.0.0.1:2177/logs?lines=50"
```

### WildWings Navigation
```bash
# Start streaming mission (returns Server-Sent Events)
curl -X POST "http://127.0.0.1:2199/start_mission"

# Get mission status in another terminal
curl "http://127.0.0.1:2199/mission_status"

# Stop mission
curl -X POST "http://127.0.0.1:2199/stop_mission"
```

### Service Health Checks
```bash
# Check individual service health
curl "http://127.0.0.1:2177/"  # OpenPassLite
curl "http://127.0.0.1:2188/"  # SmartFields  
curl "http://127.0.0.1:2199/"  # WildWings

# SmartFields comprehensive health
curl "http://127.0.0.1:2188/health"
```

## Configuration

### Service Configuration (`config.toml`)
```toml
[openpasslite]
host = "0.0.0.0"
port = 2177
cors_origin = "*"
debug = false
logfile_path = "logs/openpasslite.txt"

[smartfields]
host = "0.0.0.0"
port = 2188
cors_origin = "*"
debug = false
logfile_path = "logs/smartfields.txt"

[wildwings]
host = "0.0.0.0"
port = 2199
cors_origin = "*"
debug = false
logfile_path = "logs/wildwings.txt"
```

### Directory Structure
- **Logs**: `./logs/` - Service logs for debugging and monitoring
- **Missions**: `./mission/` - OpenPassLite mission configurations and data
- **WildWings Output**: `./missions/mission_record_{timestamp}/` - WildWings mission outputs

### Environment Variables
- `OPENPASSLITE_URL`: OpenPassLite service URL (default: `openpasslite:2177`)
- `WILDWINGS_URL`: WildWings service URL (default: `wildwings:2199`)

### Important Notes
- All services use CORS origin "*" for development - restrict in production
- Services bind to 0.0.0.0 for Docker compatibility
- Log files are persistent and stored in the `./logs/` directory
- Mission data persists between container restarts