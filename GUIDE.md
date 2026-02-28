# Smartfield — Deployment Guide

This guide explains everything you need to get Smartfield running, whether your node has internet access or not.

---

## What is Smartfield?

Smartfield is a system that automates wildlife monitoring in the field. When a camera-trap detects an animal, it automatically triggers a drone to fly out and record aerial footage of the area.

The system has five services that run as containers on a lightweight Kubernetes cluster (k3s):

```
Camera-trap (Raspberry Pi)
        │
        │  MQTT event ("animal detected at GPS coords")
        ▼
┌─────────────────┐
│  mosquitto      │  ← Message broker (routes events between services)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ mqtt-subscriber │  ← Listens for camera-trap events, calls smartfields
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  smartfields    │  ← Pipeline controller: orchestrates everything
└──────┬──────────┘
       │                    │
       ▼                    ▼
┌─────────────┐    ┌──────────────┐
│ openpasslite│    │  wildwings   │
│ (drone ctrl)│    │ (bird detect)│
└─────────────┘    └──────────────┘
```

| Service | What it does |
|---|---|
| **mosquitto** | MQTT message broker — the "post office" between all services |
| **mqtt-subscriber** | Listens for camera-trap events and kicks off the pipeline |
| **smartfields** | The brain — receives triggers, coordinates the drone + AI |
| **openpasslite** | Controls the Parrot ANAFI drone (takeoff, flight, landing) |
| **wildwings** | Runs YOLOv5 bird detection on drone camera footage |

---

## Which path applies to you?

| Situation | Path |
|---|---|
| Your field node has internet access | [Online install](#path-a--online-install) |
| Your field node has no internet | [Offline install](#path-b--offline-install) |

---

## Path A — Online Install

### What you need
- A Linux machine (Ubuntu 22.04+ recommended)
- Internet access
- `sudo` rights
- The YOLOv5 model file: `yolov5su.pt`

### Step 1 — Clone the repo

```bash
git clone https://github.com/icicle-ai/smartfield.git
cd smartfield
```

### Step 2 — Install k3s and Helm

```bash
make install
```

This installs k3s (lightweight Kubernetes) and Helm, and creates `/opt/smartfield/models/`.

After it finishes, either **log out and back in** or run:

```bash
export KUBECONFIG=$HOME/.kube/config
```

### Step 3 — Place the AI model

```bash
cp /path/to/yolov5su.pt /opt/smartfield/models/
```

The wildwings service won't start without this file.

### Step 4 — Create the image pull secret

The container images are stored in a private registry. You need a GitHub Personal Access Token (PAT) with `read:packages` scope.

```bash
kubectl create namespace smartfield

kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=<your-github-username> \
  --docker-password=<your-github-pat> \
  --namespace smartfield
```

### Step 5 — Deploy

```bash
make deploy
```

### Step 6 — Verify everything is running

```bash
make status
```

You should see all 5 pods with `Running` status:

```
NAME                          READY   STATUS    RESTARTS
mosquitto-xxx                 1/1     Running   0
mqtt-subscriber-xxx           1/1     Running   0
openpasslite-xxx              1/1     Running   0
smartfields-xxx               1/1     Running   0
wildwings-xxx                 1/1     Running   0
```

---

## Path B — Offline Install

This is for air-gapped edge nodes (no internet). Everything is bundled into a single archive you transfer via USB or SD card.

### Step 1 — Build the offline bundle (on a machine with internet)

**Option A — via GitHub Actions (recommended):**

```bash
# Tag a release — the workflow builds and attaches the bundle automatically
git tag v1.1.0
git push origin v1.1.0
```

Then go to: `GitHub repo → Releases → smartfield v1.1.0` and download:
- `smartfield-offline-1.1.0.tar.gz`
- `smartfield-offline-1.1.0.tar.gz.sha256`

**Option B — build locally:**

```bash
# On a machine that has internet, Docker, and Helm
TAG=1.1.0

# Log in to the image registry
echo "$GITHUB_PAT" | docker login ghcr.io -u <your-github-username> --password-stdin

# Download k3s binaries
mkdir -p offline-bundle/bin offline-bundle/images
curl -fsSL https://github.com/k3s-io/k3s/releases/download/v1.29.3+k3s1/k3s \
  -o offline-bundle/bin/k3s && chmod +x offline-bundle/bin/k3s
curl -fsSL https://github.com/k3s-io/k3s/releases/download/v1.29.3+k3s1/k3s-airgap-images-amd64.tar.gz \
  -o offline-bundle/images/k3s-airgap-images.tar.gz
curl -fsSL https://get.k3s.io -o offline-bundle/bin/k3s-install.sh && chmod +x offline-bundle/bin/k3s-install.sh
curl -fsSL https://get.helm.sh/helm-v3.14.3-linux-amd64.tar.gz | \
  tar xz -C offline-bundle/bin --strip-components=1 linux-amd64/helm

# Save all images
docker pull eclipse-mosquitto:2.0.18
docker save eclipse-mosquitto:2.0.18 | gzip > offline-bundle/images/mosquitto.tar.gz
for svc in mqtt-subscriber openpasslite smartfields wildwings; do
  docker pull ghcr.io/icicle-ai/smartfield-${svc}:${TAG}
  docker save ghcr.io/icicle-ai/smartfield-${svc}:${TAG} \
    | gzip > offline-bundle/images/smartfield-${svc}.tar.gz
done

# Package Helm chart
helm package charts/smartfield --version ${TAG} --app-version ${TAG} --destination offline-bundle/

# Create archive
tar -czf smartfield-offline-${TAG}.tar.gz offline-bundle/
```

### Step 2 — Transfer to the field node

```bash
# Via SCP (if you have local network access)
scp smartfield-offline-1.1.0.tar.gz user@field-node:~

# Or copy to USB and plug it in on the field node
```

### Step 3 — Place the AI model in the bundle

Before archiving (or alongside the bundle), include `yolov5su.pt`. On the field node, it needs to go to `/opt/smartfield/models/` — `load.sh` creates this directory automatically.

```bash
# On the field node, after extracting:
cp /media/usb/yolov5su.pt /opt/smartfield/models/
```

### Step 4 — Install on the field node

```bash
# Verify the file wasn't corrupted in transit
sha256sum -c smartfield-offline-1.1.0.tar.gz.sha256

# Extract
tar xzf smartfield-offline-1.1.0.tar.gz

# Run the installer (handles k3s + Helm + images + Helm chart, all offline)
sudo ./offline-bundle/load.sh
```

If k3s is already installed on the node:

```bash
sudo ./offline-bundle/load.sh --skip-k3s
```

---

## Day-to-day commands

### Check pod status

```bash
make status
# or
kubectl get pods -n smartfield
```

### Stream logs

```bash
make logs-sf     # smartfields (pipeline controller)
make logs-opl    # openpasslite (drone)
make logs-ww     # wildwings (bird detection)
make logs-sub    # mqtt-subscriber
```

### Restart everything

```bash
kubectl rollout restart deployment -n smartfield
```

### Tear down

```bash
make uninstall
```

### Update to a new version

```bash
# Edit charts/smartfield/values.yaml to bump image tags, then:
make upgrade
```

---

## How a mission runs end-to-end

```
1. Camera-trap (Raspberry Pi) detects an animal via motion sensor
2. Publishes an MQTT event to topic:  cameratrap/events
   Payload includes: GPS coordinates, camera ID, timestamp

3. mqtt-subscriber receives the event
4. Calls smartfields HTTP endpoint:  POST /initiate_pipeline

5. smartfields tells openpasslite to launch the drone
6. Drone takes off, flies to the GPS coordinates (openpasslite)

7. While airborne, wildwings runs YOLOv5 on the live camera feed
   → detects and logs any birds/animals in frame

8. Mission ends after the configured duration (default: 25 seconds)
9. Drone returns home and lands automatically

10. Media (video/images) saved to the smartfield-media volume
    Mission logs saved to the smartfield-missions volume
```

---

## Configuration

All settings live in `charts/smartfield/values.yaml`. The key ones:

| Setting | Default | What it controls |
|---|---|---|
| `config.wildwings.missionDurationSeconds` | `25` | How long the drone flies per trigger |
| `config.openpasslite.missionTimeoutSeconds` | `180` | Max time before a mission is force-ended |
| `config.subscriber.broker` | `mosquitto` | MQTT broker hostname |
| `config.topic.name` | `cameratrap/events` | MQTT topic to listen on |
| `config.topic.lat` / `config.topic.lon` | OSU coords | Default GPS coordinates |
| `storage.logs.size` | `5Gi` | Log storage volume size |
| `storage.missions.size` | `20Gi` | Mission data volume size |
| `storage.media.size` | `50Gi` | Video/image storage volume size |

After changing values, apply with:

```bash
make upgrade
```

---

## Troubleshooting

### Pods stuck in `Pending`

```bash
kubectl describe pod <pod-name> -n smartfield | tail -20
```

Common causes:
- PVC not bound → check `kubectl get pvc -n smartfield`
- Not enough memory/CPU on the node → check `kubectl describe node`

### `ErrImagePull` / `ImagePullBackOff`

The node can't pull the container images. Either:
- You're on an **online** node but haven't created the pull secret → re-run Step 4 of the online install
- You're on an **offline** node but forgot to load the images → re-run `load.sh`

### wildwings crashes on startup

The YOLOv5 model is missing. Check:

```bash
ls /opt/smartfield/models/
# Should contain: yolov5su.pt
```

### MQTT events not triggering the pipeline

```bash
# Check if the subscriber is connected to mosquitto
make logs-sub

# Manually publish a test event
kubectl exec -n smartfield deployment/mosquitto -- \
  mosquitto_pub -t cameratrap/events -m '{"lat":40.0,"lon":-83.0,"camid":"test"}'
```
