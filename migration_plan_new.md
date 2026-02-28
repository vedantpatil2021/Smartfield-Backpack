# Smartfield Backpack — Migration Plan
## Docker Compose → K3s

> **The goal**: Get this running on K3s with clean enough code that someone else can read and maintain it.
> Not perfect. Not enterprise. Just solid and working.

---

## What's Actually Broken (and worth fixing)

### smartfields/main.py
- `threading.Lock()` used with `await` inside it — this can deadlock. Swap to `asyncio.Lock()`.
- `asyncio.Event()` created at module level — needs to be inside the FastAPI `lifespan()` function.
- `wait_for_completion()` reads the sibling service's log file to know if a mission finished — this is fragile. A file buffer delay or log rotation will silently break the pipeline. Replace with polling the status endpoint (`GET /mission_status`) on a loop.
- `aiohttp.ClientSession` created fresh every HTTP call — move it to a module-level singleton.

### openpasslite / AnafiPiloting.py
- `assert drone.connect()` everywhere — asserts are not error handling, they get stripped in optimized mode. Replace with `if not result: raise RuntimeError("...")`.

### wildwings/main.py + launch.sh
- Python → bash → Python process chain. SIGTERM sent to the outer Python never reaches the inner controller process. Remove `launch.sh` entirely. Call `controller.py` as a subprocess directly from Python.
- YOLOv5 model loaded fresh on every 25-second mission. Load it once at startup and keep it in memory.

### requirements.txt files
- `wildwings` has both `opencv-python` and `opencv-python-headless` — these conflict. Keep only `opencv-python-headless`.
- Timeouts (180s, 15s, etc.) are hardcoded in the code. Move them into `config.toml`.

### config.toml
- `broker = "localhost"` — when broker is its own pod, use `broker = "mosquitto"` (K3s DNS name).
- Log paths are relative (`logs/openpasslite.log`). Use an absolute path that matches the mounted volume: `/var/log/smartfield/`.

---

## Host Network — Leave It Alone

`openpasslite` and `wildwings` stay on `hostNetwork: true`. The Anafi drone creates a WiFi network at 192.168.42.x. K3s's internal pod network (flannel) cannot reach it. There is no fix for this — it's a hardware constraint. This is fine and normal for edge hardware deployments.

One thing to add: `dnsPolicy: ClusterFirstWithHostNet` on those two pods so K3s service DNS still works while using host network.

`smartfields` needs to reach `openpasslite` and `wildwings`. Since they're on host network, they're reachable at the node's IP. Inject that with the Kubernetes Downward API as `NODE_IP` env var.

---

## New Project Layout

```
smartfield-backpack/
├── deploy/                  # All K3s manifests go here
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── pvc.yaml
│   ├── mosquitto.yaml       # Deployment + Service
│   ├── mqtt-subscriber.yaml
│   ├── openpasslite.yaml
│   ├── smartfields.yaml
│   ├── wildwings.yaml
│   ├── observability.yaml   # Loki + Grafana + Promtail
│   └── kustomization.yaml
├── services/
│   ├── common/              # Shared code (logging, config loading, http retry)
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── logging_setup.py
│   │   └── http_client.py
│   ├── mqtt-subscriber/
│   ├── openpasslite/
│   ├── smartfields/
│   └── wildwings/
├── scripts/
│   ├── install-k3s.sh
│   └── deploy.sh
├── config.toml
├── Makefile
└── .gitignore
```

The `services/common/` folder is new. Three files. Every service imports from it instead of copy-pasting the same logging setup and config loader four times.

---

## K3s Manifests

### `deploy/namespace.yaml`
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: smartfield
```

### `deploy/configmap.yaml`
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: smartfield-config
  namespace: smartfield
data:
  config.toml: |
    [meta]
    version = "1.1.0"

    [openpasslite]
    host = "0.0.0.0"
    port = 2177
    log_level = "INFO"
    mission_timeout_seconds = 180
    drone_disconnect_wait_seconds = 15

    [smartfields]
    host = "0.0.0.0"
    port = 2188
    log_level = "INFO"
    openpasslite_url = "${OPENPASSLITE_URL}"
    wildwings_url = "${WILDWINGS_URL}"

    [wildwings]
    host = "0.0.0.0"
    port = 2199
    log_level = "INFO"
    mission_duration_seconds = 25
    model_path = "/app/models/yolov5su.pt"

    [subscriber]
    client_id = "smartfield-subscriber"
    qos = 1
    broker = "mosquitto"
    port = 1883
    log_level = "INFO"
    smartfields_url = "http://smartfields:2188/initiate_pipeline"
    reconnect_max_delay_seconds = 60

    [subscriber.topics."cameratrap/events"]
    lat = 40.008278960212
    lon = -83.0175149068236
    camid = "pi-001"
```

### `deploy/pvc.yaml`
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: smartfield-logs
  namespace: smartfield
spec:
  accessModes: [ReadWriteMany]
  storageClassName: local-path
  resources:
    requests:
      storage: 5Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: smartfield-missions
  namespace: smartfield
spec:
  accessModes: [ReadWriteMany]
  storageClassName: local-path
  resources:
    requests:
      storage: 20Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: smartfield-media
  namespace: smartfield
spec:
  accessModes: [ReadWriteMany]
  storageClassName: local-path
  resources:
    requests:
      storage: 50Gi
```

### `deploy/mosquitto.yaml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mosquitto
  namespace: smartfield
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: mosquitto
  template:
    metadata:
      labels:
        app: mosquitto
    spec:
      containers:
        - name: mosquitto
          image: eclipse-mosquitto:2.0.18
          ports:
            - containerPort: 1883
          volumeMounts:
            - name: data
              mountPath: /mosquitto/data
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
          livenessProbe:
            tcpSocket:
              port: 1883
            initialDelaySeconds: 5
            periodSeconds: 10
      volumes:
        - name: data
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: mosquitto
  namespace: smartfield
spec:
  selector:
    app: mosquitto
  ports:
    - port: 1883
      targetPort: 1883
```

### `deploy/mqtt-subscriber.yaml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mqtt-subscriber
  namespace: smartfield
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: mqtt-subscriber
  template:
    metadata:
      labels:
        app: mqtt-subscriber
    spec:
      containers:
        - name: mqtt-subscriber
          image: ghcr.io/icicle-ai/smartfield-mqtt-subscriber:1.1.0
          imagePullPolicy: IfNotPresent
          volumeMounts:
            - name: config
              mountPath: /app/config.toml
              subPath: config.toml
              readOnly: true
            - name: logs
              mountPath: /var/log/smartfield
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
          livenessProbe:
            tcpSocket:
              port: 8080
            initialDelaySeconds: 10
            periodSeconds: 15
      volumes:
        - name: config
          configMap:
            name: smartfield-config
        - name: logs
          persistentVolumeClaim:
            claimName: smartfield-logs
```

### `deploy/openpasslite.yaml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: openpasslite
  namespace: smartfield
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: openpasslite
  template:
    metadata:
      labels:
        app: openpasslite
    spec:
      hostNetwork: true                   # needed for drone WiFi (192.168.42.x)
      dnsPolicy: ClusterFirstWithHostNet  # keep K3s DNS working
      containers:
        - name: openpasslite
          image: ghcr.io/icicle-ai/smartfield-openpasslite:1.1.0
          imagePullPolicy: IfNotPresent
          env:
            - name: PYTHONUNBUFFERED
              value: "1"
            - name: OLYMPE_LOG_LEVEL
              value: "WARNING"
          volumeMounts:
            - name: config
              mountPath: /app/config.toml
              subPath: config.toml
              readOnly: true
            - name: logs
              mountPath: /var/log/smartfield
            - name: missions
              mountPath: /app/mission
            - name: media
              mountPath: /app/media
          resources:
            requests:
              cpu: "200m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
          livenessProbe:
            httpGet:
              path: /healthz
              port: 2177
            initialDelaySeconds: 15
            periodSeconds: 20
      volumes:
        - name: config
          configMap:
            name: smartfield-config
        - name: logs
          persistentVolumeClaim:
            claimName: smartfield-logs
        - name: missions
          persistentVolumeClaim:
            claimName: smartfield-missions
        - name: media
          persistentVolumeClaim:
            claimName: smartfield-media
---
apiVersion: v1
kind: Service
metadata:
  name: openpasslite
  namespace: smartfield
spec:
  selector:
    app: openpasslite
  ports:
    - port: 2177
      targetPort: 2177
```

### `deploy/smartfields.yaml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: smartfields
  namespace: smartfield
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: smartfields
  template:
    metadata:
      labels:
        app: smartfields
    spec:
      containers:
        - name: smartfields
          image: ghcr.io/icicle-ai/smartfield-smartfields:1.1.0
          imagePullPolicy: IfNotPresent
          env:
            - name: PYTHONUNBUFFERED
              value: "1"
            # NODE_IP lets smartfields reach hostNetwork services
            - name: NODE_IP
              valueFrom:
                fieldRef:
                  fieldPath: status.hostIP
            - name: OPENPASSLITE_URL
              value: "http://$(NODE_IP):2177"
            - name: WILDWINGS_URL
              value: "http://$(NODE_IP):2199"
          volumeMounts:
            - name: config
              mountPath: /app/config.toml
              subPath: config.toml
              readOnly: true
            - name: logs
              mountPath: /var/log/smartfield
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
          livenessProbe:
            httpGet:
              path: /healthz
              port: 2188
            initialDelaySeconds: 10
            periodSeconds: 15
      volumes:
        - name: config
          configMap:
            name: smartfield-config
        - name: logs
          persistentVolumeClaim:
            claimName: smartfield-logs
---
apiVersion: v1
kind: Service
metadata:
  name: smartfields
  namespace: smartfield
spec:
  selector:
    app: smartfields
  ports:
    - port: 2188
      targetPort: 2188
```

### `deploy/wildwings.yaml`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: wildwings
  namespace: smartfield
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: wildwings
  template:
    metadata:
      labels:
        app: wildwings
    spec:
      hostNetwork: true                   # needed for drone WiFi
      dnsPolicy: ClusterFirstWithHostNet
      containers:
        - name: wildwings
          image: ghcr.io/icicle-ai/smartfield-wildwings:1.1.0
          imagePullPolicy: IfNotPresent
          env:
            - name: PYTHONUNBUFFERED
              value: "1"
            - name: DISPLAY
              value: ":99"
            - name: OLYMPE_LOG_LEVEL
              value: "WARNING"
          volumeMounts:
            - name: config
              mountPath: /app/config.toml
              subPath: config.toml
              readOnly: true
            - name: logs
              mountPath: /var/log/smartfield
            - name: missions
              mountPath: /app/mission
            - name: media
              mountPath: /app/media
            - name: models
              mountPath: /app/models
              readOnly: true
          resources:
            requests:
              cpu: "500m"
              memory: "2Gi"
            limits:
              cpu: "4"
              memory: "8Gi"
          livenessProbe:
            httpGet:
              path: /healthz
              port: 2199
            initialDelaySeconds: 30
            periodSeconds: 20
          securityContext:
            privileged: true   # needs /dev/net/tun, /dev/video*
      volumes:
        - name: config
          configMap:
            name: smartfield-config
        - name: logs
          persistentVolumeClaim:
            claimName: smartfield-logs
        - name: missions
          persistentVolumeClaim:
            claimName: smartfield-missions
        - name: media
          persistentVolumeClaim:
            claimName: smartfield-media
        - name: models
          hostPath:
            path: /opt/smartfield/models
            type: Directory
---
apiVersion: v1
kind: Service
metadata:
  name: wildwings
  namespace: smartfield
spec:
  selector:
    app: wildwings
  ports:
    - port: 2199
      targetPort: 2199
```

### `deploy/kustomization.yaml`
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: smartfield
resources:
  - namespace.yaml
  - configmap.yaml
  - pvc.yaml
  - mosquitto.yaml
  - mqtt-subscriber.yaml
  - openpasslite.yaml
  - smartfields.yaml
  - wildwings.yaml
  - observability.yaml
```

---

## Shared `services/common/` — Three Files

### `services/common/logging_setup.py`
```python
import logging
import sys
import json
from datetime import datetime, timezone
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out)


def setup_logging(service: str, level: str = "INFO", log_dir: str | None = None) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root.addHandler(h)

    if log_dir:
        p = Path(log_dir) / f"{service}.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(p)
        fh.setFormatter(JsonFormatter())
        root.addHandler(fh)
```

### `services/common/http_client.py`
```python
import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)
_session: aiohttp.ClientSession | None = None


def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
    return _session


async def close_session() -> None:
    global _session
    if _session and not _session.closed:
        await _session.close()


async def post(url: str, params: dict | None = None, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            async with get_session().post(url, params=params) as r:
                r.raise_for_status()
                return await r.json()
        except Exception as e:
            wait = 2 ** attempt
            logger.warning("POST %s failed (attempt %d): %s — retry in %ds", url, attempt + 1, e, wait)
            if attempt < retries - 1:
                await asyncio.sleep(wait)
    raise RuntimeError(f"POST {url} failed after {retries} attempts")


async def get(url: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            async with get_session().get(url) as r:
                r.raise_for_status()
                return await r.json()
        except Exception as e:
            wait = 2 ** attempt
            logger.warning("GET %s failed (attempt %d): %s — retry in %ds", url, attempt + 1, e, wait)
            if attempt < retries - 1:
                await asyncio.sleep(wait)
    raise RuntimeError(f"GET {url} failed after {retries} attempts")
```

### `services/common/config.py`
```python
import tomllib
from pathlib import Path


def load_config(path: str = "/app/config.toml") -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)
```

---

## Code Fixes — What to Change and Where

### Fix 1: smartfields — asyncio lock + lifespan

```python
# BEFORE (broken)
pipeline_lock = threading.Lock()
pipeline_stop_event = asyncio.Event()  # created at module level

# AFTER
from contextlib import asynccontextmanager
pipeline_lock: asyncio.Lock
pipeline_stop_event: asyncio.Event

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pipeline_lock, pipeline_stop_event
    pipeline_lock = asyncio.Lock()
    pipeline_stop_event = asyncio.Event()
    yield
    await close_session()

app = FastAPI(lifespan=lifespan)
```

### Fix 2: smartfields — stop polling log files

```python
# BEFORE (fragile)
with open(f"logs/{service}.log") as f:
    if f"Mission {mission} thread finished" in f.read():
        return True

# AFTER — poll the service's own status endpoint
async def wait_for_completion(status_url: str, timeout: int = 180) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if pipeline_stop_event.is_set():
            return False
        try:
            data = await get(status_url)
            if data.get("status") == "idle":
                return True
        except Exception:
            pass
        await asyncio.sleep(2)
    return False
```

### Fix 3: openpasslite — remove asserts

```python
# BEFORE
assert drone.connect(), "Could not connect"

# AFTER
if not drone.connect():
    raise RuntimeError("Failed to connect to drone at 192.168.42.1")
```

### Fix 4: wildwings — remove shell wrapper

```python
# BEFORE — bash → python chain (signal propagation breaks)
process = subprocess.Popen(['bash', '/app/launch.sh'])

# AFTER — call controller.py directly
process = subprocess.Popen(
    [sys.executable, '/app/controller.py',
     '--output-dir', output_dir, '--lat', str(lat), '--lon', str(lon)],
    stdout=log_file, stderr=subprocess.STDOUT
)
```

### Fix 5: wildwings — load YOLO model once

```python
# BEFORE — loaded every 25-second mission
def run_mission():
    model = YOLO('yolov5su.pt')  # every time

# AFTER — load in lifespan, pass to mission
_model: YOLO | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    _model = YOLO(config['wildwings']['model_path'])
    yield
```

### Fix 6: wildwings — fix conflicting opencv packages

```
# Remove from requirements / pyproject.toml:
opencv-python

# Keep only:
opencv-python-headless
```

### Fix 7: Add `/healthz` to each FastAPI service

Every service needs this — it's what K3s uses for `livenessProbe`:

```python
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
```

---

## Install and Deploy Scripts

### `scripts/install-k3s.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail

curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE="644" sh -s - \
    --disable traefik --disable servicelb

echo "Waiting for node..."
until kubectl get nodes | grep -q " Ready"; do sleep 2; done

mkdir -p /opt/smartfield/models
echo "Done. Copy yolov5su.pt to /opt/smartfield/models/"
```

### `scripts/deploy.sh`
```bash
#!/usr/bin/env bash
set -euo pipefail

kubectl apply -k deploy/
echo "Waiting for pods..."
kubectl -n smartfield wait deployment --all --for=condition=Available --timeout=300s
kubectl -n smartfield get pods
```

### `Makefile`
```makefile
.PHONY: install deploy status logs-sf logs-opl logs-ww

install:
	sudo bash scripts/install-k3s.sh

deploy:
	bash scripts/deploy.sh

status:
	kubectl -n smartfield get pods -o wide

logs-sf:
	kubectl -n smartfield logs -f deployment/smartfields

logs-opl:
	kubectl -n smartfield logs -f deployment/openpasslite

logs-ww:
	kubectl -n smartfield logs -f deployment/wildwings

logs-sub:
	kubectl -n smartfield logs -f deployment/mqtt-subscriber
```

---

## Phases

### Phase 1 — Setup (half a day)
1. `sudo bash scripts/install-k3s.sh`
2. Copy `yolov5su.pt` to `/opt/smartfield/models/`
3. `kubectl apply -f deploy/namespace.yaml`
4. Apply PVCs and ConfigMap, verify they come up

### Phase 2 — Fix the code (2-3 days)
1. Create `services/common/` with the three files above
2. Fix smartfields (asyncio lock + status polling)
3. Fix openpasslite (remove asserts, add `/healthz`)
4. Fix wildwings (direct subprocess, preload YOLO, remove launch.sh, add `/healthz`)
5. Fix mqtt-subscriber (reconnect loop, add `/healthz` on port 8080)
6. Fix `config.toml` (broker hostname, absolute log paths)

### Phase 3 — Deploy and verify (1 day)
1. Build images, push to registry (or load locally with `k3s ctr images import`)
2. `make deploy`
3. `make status` — all pods Running
4. Test: `curl http://localhost:2177/healthz`, `curl http://localhost:2188/healthz`, `curl http://localhost:2199/healthz`
5. Simulate a MQTT event, watch logs flow through the pipeline
