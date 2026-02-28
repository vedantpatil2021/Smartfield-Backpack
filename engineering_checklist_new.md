# Engineering Checklist — Smartfield Backpack
## Use this before pushing code or deploying. Not a ceremony, just a sanity check.

---

## Code

- [ ] **No `assert` for logic** — `assert x` gets stripped by Python's `-O` flag. Use `if not x: raise RuntimeError("...")` instead. Asserts are only for tests.
- [ ] **No `print()` in services** — Use `logger.info(...)`. Print statements mean the code was never cleaned up.
- [ ] **No bare `except:`** — Catch the specific exception. If you catch broadly, at least log what you caught. Never silently swallow errors.
- [ ] **No hardcoded values in logic** — Timeouts, IPs, ports, durations belong in `config.toml`. If someone needs to change a number, they should not have to touch the code.
- [ ] **No copy-pasted code across services** — If two services have the same logging setup or HTTP retry logic, it lives in `services/common/`. Copy-paste is how bugs stay hidden.
- [ ] **`asyncio.Lock()` in async code, not `threading.Lock()`** — Holding a `threading.Lock` across an `await` point can deadlock. If you're in an `async def`, use `asyncio.Lock()`.
- [ ] **asyncio objects created inside `lifespan()`** — `asyncio.Event()`, `asyncio.Lock()`, `asyncio.Queue()` cannot be created at module level. They must be created inside a running event loop.
- [ ] **Every external call has a timeout** — HTTP calls, subprocess waits, drone SDK calls. If there's no timeout, a hung call hangs the entire service.

---

## Logging

- [ ] **Logs are JSON** — Use `services/common/logging_setup.py`. One JSON object per line makes logs parseable by Promtail/Loki.
- [ ] **At startup, log your config** — Every service should log its port, log level, and the URLs it will call when it starts. Makes debugging in the field much faster.
- [ ] **Mission start and end are always logged** — With what coordinates, which service, and whether it succeeded or failed.

---

## APIs (FastAPI)

- [ ] **Every service has `GET /healthz`** — Returns `{"status": "ok"}` with HTTP 200. K3s uses this for liveness probes. Without it, K3s cannot restart hung pods.
- [ ] **Status endpoints return structured data** — `GET /mission_status` returns JSON with at least `{"status": "running"|"idle", "success": true|false}`. Smartfields polls this. Log files are not a status API.
- [ ] **`lifespan()` is used for startup/shutdown** — Resource setup (loading models, creating HTTP sessions, connecting clients) goes inside `lifespan()`. Not at module level, not in `@app.on_event`.

---

## Kubernetes Manifests

- [ ] **`livenessProbe` on every Deployment** — No liveness probe = hung pod runs forever. K3s cannot help you.
- [ ] **`resources.requests` and `resources.limits` on every container** — Without requests, the scheduler is guessing. Without limits, one runaway process can take down the node.
- [ ] **`strategy: Recreate` for hardware-bound services** — `openpasslite`, `wildwings`, and `mosquitto` can only have one instance. `Recreate` kills the old pod before starting the new one. `RollingUpdate` would start a second one first, which breaks drone/broker exclusivity.
- [ ] **`dnsPolicy: ClusterFirstWithHostNet` on hostNetwork pods** — `openpasslite` and `wildwings` use `hostNetwork: true`. Without this DNS policy, K3s's own service DNS stops working in those pods (so `mosquitto` hostname won't resolve).
- [ ] **Image tags are not `:latest` in manifests** — Use `1.1.0` or similar. `:latest` makes it impossible to roll back or know what's actually running.
- [ ] **ConfigMap, not baked-in config** — `config.toml` is mounted from the `smartfield-config` ConfigMap. Changing config does not require rebuilding an image.

---

## Before Every Deploy

```bash
# All pods should be Running
kubectl -n smartfield get pods

# Health checks pass
curl http://localhost:2177/healthz
curl http://localhost:2188/healthz
curl http://localhost:2199/healthz

# Check logs aren't spamming errors
kubectl -n smartfield logs deployment/smartfields --tail=30
```

---

## Things That Are Fixed and Should Stay Fixed

These were bugs. They're documented here so they don't come back:

| Was broken | Fix applied | Do not revert |
|---|---|---|
| `threading.Lock()` in async code in smartfields | Replaced with `asyncio.Lock()` | |
| `wait_for_completion()` reading log files | Polls `/mission_status` HTTP endpoint instead | |
| `assert drone.connect()` in openpasslite | `if not result: raise RuntimeError(...)` | |
| `launch.sh` → `controller.py` subprocess chain | Direct `subprocess.Popen([sys.executable, 'controller.py'])` | |
| YOLO model reloaded every mission | Loaded once in `lifespan()`, held in memory | |
| `opencv-python` + `opencv-python-headless` both installed | Only `opencv-python-headless` | |
| `broker = "localhost"` in config | `broker = "mosquitto"` (K3s DNS name) | |
| Relative log paths in config | Absolute: `/var/log/smartfield/` | |

---

## What NOT to Change

- **`hostNetwork: true`** on openpasslite and wildwings — the drone WiFi is at 192.168.42.x, K3s overlay network can't reach it.
- **Mission scripts** (`TAKEOFF/`, `LTT/`, `RTB/`, `LAND/`, `ORTHOMOSAIC/`) — the `run(drone, lat, long)` interface works.
- **`navigation.py` tracking logic** — works, just move the magic numbers to config.
- **Grafana dashboard JSON** — already configured, reprovision via ConfigMap.
