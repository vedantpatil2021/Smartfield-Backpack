# SmartField Backpack — Systems Architecture

> Single-node K3s cluster running on a Raspberry Pi field backpack.
> Five diagrams, each zooming into a different layer of the system.

---

## 1. Full System Overview

Who talks to whom, and over what protocol.

```mermaid
flowchart TB
    subgraph EXTERNAL["External World"]
        CT["📷 Camera Trap\nRaspberry Pi\nMQTT Publisher"]
        DRONE["🚁 Parrot ANAFI Drone\n192.168.42.1  ·  WiFi 5 GHz\nRTSP + ANAFI SDK"]
        BROWSER["💻 Field Scientist\nLaptop Browser"]
    end

    subgraph NODE["K3s Node — SmartField Backpack Pi"]

        subgraph NS["namespace: smartfield"]

            subgraph FLANNEL["Flannel Overlay Network  (pod-to-pod)"]
                MOSQ["🟢 mosquitto\neclipse-mosquitto:2.0.18\nTCP 1883"]
                SUB["🟢 mqtt-subscriber\nsmartfield-mqtt-subscriber\nhealthz :8080"]
                SF_SVC{{"ClusterIP\nsmartfields\n:2188"}}
                MOSQ_SVC{{"ClusterIP\nmosquitto\n:1883"}}
            end

            subgraph HOSTNET["Host Network  (bypass flannel — direct node IP)"]
                SF["🔵 smartfields\n:2188\nOrchestrator + Web UI\nMission Logger"]
                OPL["🔵 openpasslite\n:2177\nANAFI Drone Controller"]
                WW["🔵 wildwings\n:2199\nYOLOv5 Detection\n(privileged)"]
                GO2["🔵 go2rtc\n:1984 HTTP  ·  :8555/UDP\nRTSP → WebRTC Proxy"]
            end

            subgraph STORAGE["Persistent Storage"]
                CFGMAP[["ConfigMap\nsmartfield-config\nconfig.toml"]]
                LOGS[("PVC  smartfield-logs\n5 Gi  ·  local-path")]
                MISSIONS[("PVC  smartfield-missions\n20 Gi  ·  local-path")]
                MEDIA[("PVC  smartfield-media\n50 Gi  ·  local-path")]
                MODEL["hostPath\n/opt/smartfield/models\nyolov5su.pt  1.3 GB"]
            end

        end

        subgraph CP["K3s Control Plane"]
            API["API Server\n:6443"]
            DNS["CoreDNS\nsvc DNS resolution"]
            PROXY["kube-proxy\niptables  ClusterIP routing"]
            PROV["local-path Provisioner\ndynamic PV binding"]
            FLANNEL_CNI["Flannel CNI\noverlay  10.42.0.0/16"]
        end

    end

    %% External → cluster
    CT        -->|"MQTT publish\ncameratrap/events"| MOSQ_SVC
    BROWSER   -->|"HTTP  :2188/ui"| SF
    BROWSER   -->|"WebRTC UDP  :8555"| GO2

    %% Cluster internal
    MOSQ_SVC  -->  MOSQ
    MOSQ      -->|"subscribe"| SUB
    SUB       -->|"HTTP POST\n/initiate_pipeline"| SF_SVC
    SF_SVC    -->  SF

    %% hostNetwork services call each other via localhost
    SF        -->|"HTTP  localhost:2177"| OPL
    SF        -->|"HTTP  localhost:2199"| WW

    %% Drone comms
    OPL       -->|"ANAFI SDK\nWiFi"| DRONE
    GO2       -->|"RTSP pull\nrtsp://192.168.42.1/live"| DRONE

    %% Storage mounts
    CFGMAP    -.->|"/app/config.toml"| SF
    CFGMAP    -.->|"/app/config.toml"| OPL
    CFGMAP    -.->|"/app/config.toml"| WW
    CFGMAP    -.->|"/app/config.toml"| SUB
    LOGS      -.->|"/var/log/smartfield"| SF
    LOGS      -.->|"/var/log/smartfield"| OPL
    LOGS      -.->|"/var/log/smartfield"| WW
    LOGS      -.->|"/var/log/smartfield"| SUB
    MISSIONS  -.->|"/app/mission"| OPL
    MEDIA     -.->|"/app/media"| WW
    MODEL     -.->|"/app/models"| WW
```

---

## 2. Network Topology — hostNetwork vs Flannel

The most important networking concept in this deployment.

```mermaid
flowchart LR
    subgraph HOST_NS["Host Network Namespace  (shared with Linux kernel)"]
        direction TB
        ETH["eth0 / wlan0\nNode IP  192.168.x.x"]
        WLAN_DRONE["wlan1  drone WiFi\n192.168.42.x subnet"]

        subgraph HOSTPODS["Pods with hostNetwork: true"]
            SF2["smartfields :2188"]
            OPL2["openpasslite :2177"]
            WW2["wildwings :2199"]
            GO2B["go2rtc :1984 :8555"]
        end

        IPTR["kube-proxy iptables\nClusterIP → hostIP DNAT\nChain: KUBE-SERVICES"]
    end

    subgraph FLANNEL_NS["Pod Network Namespace  (flannel  10.42.0.0/16)"]
        direction TB
        subgraph OVERLAY["Overlay Pods  — own IP e.g. 10.42.0.x"]
            MOSQ2["mosquitto\n10.42.0.5"]
            SUB2["mqtt-subscriber\n10.42.0.6"]
        end
        CLUSTERIPS["ClusterIPs  (virtual)\nmosquitto   10.43.0.10\nsmartfields 10.43.0.11"]
    end

    subgraph COREDNS_BOX["CoreDNS  10.43.0.10"]
        DNS2["mosquitto.smartfield.svc → 10.43.0.10\nsmartfields.smartfield.svc → 10.43.0.11"]
    end

    %% How sub reaches SF via ClusterIP even though SF is hostNetwork
    SUB2      -->|"HTTP to smartfields ClusterIP\n10.43.0.11:2188"| CLUSTERIPS
    CLUSTERIPS-->|"iptables DNAT\n→ Node IP:2188"| IPTR
    IPTR      -->  SF2

    %% Mosquitto internal
    SUB2      -->|"MQTT subscribe\nmosquitto:1883  DNS→ClusterIP"| CLUSTERIPS
    CLUSTERIPS-->  MOSQ2

    %% Drone WiFi only reachable from host namespace
    OPL2      -->|"ANAFI SDK"| WLAN_DRONE
    GO2B      -->|"RTSP"| WLAN_DRONE

    %% hostNetwork pods call each other over loopback
    SF2       -->|"localhost:2177"| OPL2
    SF2       -->|"localhost:2199"| WW2

    %% Browser hits host IP directly
    BROWSER2["Browser"] -->|"192.168.x.x:2188"| ETH
    ETH -->  SF2
```

**Key insight:** `hostNetwork: true` gives a pod the node's real network interfaces.
kube-proxy's iptables rules (`KUBE-SERVICES` chain) live in the host network namespace,
so ClusterIP routing still works — mqtt-subscriber can reach the smartfields ClusterIP,
which DNAT-rewrites to the node IP, landing in the smartfields pod. No overlay needed.

---

## 3. Mission Pipeline — Sequence

Full lifecycle from camera-trap MQTT event to RTB completion.

```mermaid
sequenceDiagram
    autonumber
    actor CT  as Camera Trap
    participant MQ  as mosquitto<br/>(ClusterIP)
    participant SUB as mqtt-subscriber
    participant SF  as smartfields<br/>MissionLogger
    participant OPL as openpasslite
    participant WW  as wildwings
    participant DRN as Parrot ANAFI<br/>Drone

    CT  ->>  MQ  : MQTT publish<br/>topic: cameratrap/events<br/>payload: {lat, lon, camid}
    MQ  ->>  SUB : deliver message (QoS 1)
    SUB ->>  SF  : POST /initiate_pipeline<br/>?lat=…&lon=…&camid=…

    SF  ->>  SF  : create missions/YYYY-MM-DD_HH-MM-SS_pi-001/<br/>write meta.json {status:running}<br/>open pipeline.log

    note over SF  : Step 1 — LTT (Long Time Tracking)
    SF  ->>  OPL : POST /start_mission?name=LTT&lat=…&long=…
    OPL ->>  DRN : takeoff + begin tracking (ANAFI SDK)
    loop poll every 2s
        SF  ->>  OPL : GET /mission_status
        OPL -->> SF  : {status: "running"}
    end
    OPL -->> DRN : land
    OPL -->> SF  : {status: "idle"}
    SF  ->>  SF  : step_end("ok")  ·  5s pause

    note over SF  : Step 2 — WildWings Detection
    SF  ->>  WW  : POST /start_mission?lat=…&lon=…&model=yolov5su
    WW  ->>  WW  : subprocess controller.py<br/>YOLOv5 inference on video
    loop poll every 2s
        SF  ->>  WW  : GET /mission_status
        WW  -->> SF  : {status: "running"}
    end
    WW  -->> SF  : {status: "idle"}
    SF  ->>  SF  : step_end("ok")  ·  5s pause<br/>note: WildWings failure → skip, not abort

    note over SF  : Step 3 — RTB (Return to Base)
    SF  ->>  OPL : POST /start_mission?name=RTB&lat=…&long=…
    OPL ->>  DRN : fly home + land (ANAFI SDK)
    loop poll every 2s
        SF  ->>  OPL : GET /mission_status
        OPL -->> SF  : {status: "running"}
    end
    OPL -->> SF  : {status: "idle"}
    SF  ->>  SF  : mission.close("success")<br/>overwrite meta.json {status:success, steps:[…]}<br/>close pipeline.log

    SF  -->> SUB : 200 OK  {status:"pipeline_started"}
```

---

## 4. Storage & Configuration Architecture

How config and data flow through persistent volumes.

```mermaid
flowchart LR
    subgraph HELM["Helm Chart  charts/smartfield/"]
        VALUES["values.yaml\nsingle source of truth\nfor all config + image tags"]
        CFGT["templates/configmap.yaml\nrenders config.toml\nfrom values"]
        VALUES -->|"helm template"| CFGT
    end

    subgraph K8S_STORAGE["K3s Storage Layer"]
        CM2[["ConfigMap\nsmartfield-config\nconfig.toml"]]
        CFGT -->|"kubectl apply"| CM2

        LPROV["local-path Provisioner\nbinds PVCs → hostPath dirs\non node filesystem"]
        PV_LOGS[("PV  smartfield-logs\n/var/lib/rancher/k3s/…\n5 Gi")]
        PV_MISS[("PV  smartfield-missions\n20 Gi")]
        PV_MEDIA[("PV  smartfield-media\n50 Gi")]
        LPROV --> PV_LOGS & PV_MISS & PV_MEDIA
    end

    subgraph MOUNTS["Pod Volume Mounts"]
        direction TB
        SF_M["smartfields\n/app/config.toml  ← ConfigMap\n/var/log/smartfield  ← logs PVC\n/var/log/smartfield/missions  ← mission dirs"]
        OPL_M["openpasslite\n/app/config.toml  ← ConfigMap\n/var/log/smartfield  ← logs PVC\n/app/mission  ← missions PVC\n/app/media  ← media PVC"]
        WW_M["wildwings\n/app/config.toml  ← ConfigMap\n/var/log/smartfield  ← logs PVC\n/app/models  ← hostPath  yolov5su.pt"]
        SUB_M["mqtt-subscriber\n/app/config.toml  ← ConfigMap\n/var/log/smartfield  ← logs PVC"]
    end

    subgraph LOG_LAYOUT["Log Layout on PVC"]
        direction TB
        LL["/var/log/smartfield/\n├── smartfields.log      ← service errors\n├── openpasslite.log\n├── wildwings.log\n└── missions/\n    ├── 2026-03-01_14-32-05_pi-001/\n    │   ├── meta.json   ← structured summary\n    │   └── pipeline.log ← human narrative\n    └── 2026-03-01_09-15-42_pi-001/\n        ├── meta.json\n        └── pipeline.log"]
    end

    CM2      -.->|"subPath mount\nreadOnly"| SF_M & OPL_M & WW_M & SUB_M
    PV_LOGS  -.->  SF_M & OPL_M & WW_M & SUB_M
    PV_MISS  -.->  OPL_M
    PV_MEDIA -.->  WW_M
    SF_M     -->   LOG_LAYOUT
```

---

## 5. Kubernetes Resource Map

Every K3s object and how they relate.

```mermaid
flowchart TB
    subgraph HELM2["Helm Release: smartfield"]
        direction LR
        CHART["charts/smartfield/\nChart.yaml v1.1.0\nvalues.yaml"]
    end

    subgraph NS2["namespace: smartfield"]

        subgraph DEPLOYMENTS["Deployments  (strategy: Recreate)"]
            D1["Deployment\nmosquitto"]
            D2["Deployment\nmqtt-subscriber"]
            D3["Deployment\nsmartfields\nhostNetwork"]
            D4["Deployment\nopenpasslite\nhostNetwork + privileged"]
            D5["Deployment\nwildwings\nhostNetwork + privileged"]
            D6["Deployment\ngo2rtc\nhostNetwork"]
        end

        subgraph PODS["Pods  (1 replica each — single node)"]
            P1["Pod  mosquitto-xxxx"]
            P2["Pod  mqtt-subscriber-xxxx"]
            P3["Pod  smartfields-xxxx"]
            P4["Pod  openpasslite-xxxx"]
            P5["Pod  wildwings-xxxx"]
            P6["Pod  go2rtc-xxxx"]
        end

        subgraph SERVICES["Services  (ClusterIP)"]
            S1{{"mosquitto\n:1883"}}
            S2{{"smartfields\n:2188"}}
        end

        subgraph PVCS["PersistentVolumeClaims"]
            C1[("smartfield-logs\n5 Gi  RWO")]
            C2[("smartfield-missions\n20 Gi  RWO")]
            C3[("smartfield-media\n50 Gi  RWO")]
        end

        subgraph CMS["ConfigMaps"]
            CM3[["smartfield-config\nconfig.toml"]]
            GO2_CM[["go2rtc-config\ngo2rtc.yaml"]]
        end

        subgraph PROBES["Liveness Probes"]
            PR1["HTTP GET /healthz :2177\nopenpasslite"]
            PR2["HTTP GET /healthz :2188\nsmartfields"]
            PR3["HTTP GET /healthz :2199\nwildwings"]
            PR4["TCP  :8080\nmqtt-subscriber"]
            PR5["TCP  :1883\nmosquitto"]
            PR6["TCP  :1984\ngo2rtc"]
        end

    end

    CHART -->|"renders + applies"| DEPLOYMENTS
    CHART -->|"renders + applies"| PVCS & CMS & SERVICES

    D1 -->|"owns"| P1
    D2 -->|"owns"| P2
    D3 -->|"owns"| P3
    D4 -->|"owns"| P4
    D5 -->|"owns"| P5
    D6 -->|"owns"| P6

    S1 -->|"selector: app=mosquitto"| P1
    S2 -->|"selector: app=smartfields"| P3

    CM3  -.->|"volume"| P2 & P3 & P4 & P5
    GO2_CM -.->|"volume"| P6
    C1   -.->|"volume"| P2 & P3 & P4 & P5
    C2   -.->|"volume"| P4
    C3   -.->|"volume"| P5

    PR1 -.->|"monitored by kubelet"| P4
    PR2 -.->|"monitored by kubelet"| P3
    PR3 -.->|"monitored by kubelet"| P5
    PR4 -.->|"monitored by kubelet"| P2
    PR5 -.->|"monitored by kubelet"| P1
    PR6 -.->|"monitored by kubelet"| P6
```

---

## Component Reference

| Pod | Image | Network | Ports | Role |
|---|---|---|---|---|
| mosquitto | eclipse-mosquitto:2.0.18 | Flannel overlay | 1883/TCP | MQTT broker — event bus |
| mqtt-subscriber | smartfield-mqtt-subscriber | Flannel overlay | 8080/TCP (health) | Bridges MQTT events → smartfields HTTP |
| smartfields | smartfield-smartfields | **hostNetwork** | 2188/TCP | Pipeline orchestrator + web dashboard |
| openpasslite | smartfield-openpasslite | **hostNetwork + privileged** | 2177/TCP | ANAFI drone controller (LTT, RTB) |
| wildwings | smartfield-wildwings | **hostNetwork + privileged** | 2199/TCP | YOLOv5 bird detection |
| go2rtc | ghcr.io/alexxit/go2rtc | **hostNetwork** | 1984/TCP + 8555/UDP | RTSP → WebRTC proxy for live feed |

## Why hostNetwork on 4 of 6 Pods?

The Parrot ANAFI drone creates a WiFi access point on `192.168.42.x`. Kubernetes's overlay
network (Flannel) cannot route to this subnet — it only manages the `10.42.0.0/16` pod CIDR.
Pods with `hostNetwork: true` bypass Flannel entirely and share the node's network interfaces,
giving them direct access to the drone WiFi and the ability to open real host ports
(2177, 2188, 2199, 1984, 8555) that the field scientist's browser and camera traps can reach
without an Ingress controller or NodePort service.

The ClusterIP Services for mosquitto and smartfields still work for the overlay pods
(mqtt-subscriber) because kube-proxy's iptables rules live in the host network namespace
and apply to all connections regardless of which network namespace originates them.
