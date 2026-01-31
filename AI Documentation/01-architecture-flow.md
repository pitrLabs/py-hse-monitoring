# Architecture & Data Flow
## Multi-Path Recognition Algorithm Protocol

---

## 1. System Topology

### 1.1 Logical Topology

Core components:
- Edge AI Boxes (N units)
- MQTT Broker
- Customer / Service Platform
- HTTP Alarm & Video Receiver

Communication paths:
- Box ⇄ MQTT Broker ⇄ Platform
- Box ⇄ HTTP Server (direct)

The MQTT broker acts as a **message bus**, not a processing unit.

---

## 2. Integration Topology

### 2.1 Network-Level View

- Each box connects outward to:
  - MQTT Broker (TCP / WebSocket)
  - HTTP endpoints (alarm & video)

- Platform:
  - Subscribes to MQTT topics
  - Exposes HTTP endpoints

No inbound connection to box is required.

---

## 3. Data Flow Overview

### 3.1 Core Message Bus

All real-time coordination occurs through:
- **MQTT Message Bus**

Responsibilities:
- Control message delivery
- Status reporting
- Heartbeat
- Log aggregation

HTTP is **only** used for:
- Large payload transfer
- Alarm/video upload

---

## 4. Alarm & Video Reporting Flow (HTTP)

### 4.1 Trigger Condition

1. Algorithm task detects violation
2. Alarm event is generated
3. Optional video recording starts

---

### 4.2 Video Upload Flow (If Enabled)

1. Box records short video clip
2. Box uploads video via HTTP `multipart/form-data`
3. HTTP server returns:
   - `VideoId`
4. `VideoId` is cached in memory
5. Alarm JSON references `VideoId`

---

### 4.3 Alarm Upload Flow

1. Alarm JSON constructed
2. Payload includes:
   - Device metadata
   - Media info
   - Algorithm result
   - Optional base64 images
3. Box POSTs JSON to alarm endpoint
4. HTTP response handling:
   - Valid JSON + `Code != 0` → failure
   - Any other HTTP 200 → success

Retry behavior depends on firmware config.

---

## 5. MQTT Control Flow

### 5.1 Downstream Control (Platform → Box)

Used for:
- Media channel config
- Algorithm task lifecycle
- Scheduling
- Software upgrade
- Parameter modification

Flow:
1. Platform publishes command to `/edge_app_controller`
2. Payload includes:
   - `BoardId`
   - `Event`
   - Command-specific fields
3. Box validates `BoardId`
4. Box executes command
5. Box publishes response to `/edge_app_controller_reply`

---

### 5.2 Upstream Status (Box → Platform)

Used for:
- Heartbeat
- Logs
- Execution status

Topics:
- `/board_ping` → heartbeat
- `/edge_app_notify` → logs & errors

---

## 6. Heartbeat Flow

### 6.1 MQTT Heartbeat (Default)

Interval:
- Default: 5 seconds

Payload includes:
- Device status
- Resource usage
- Media channel state
- Task state

Used by platform to:
- Detect offline devices
- Monitor performance
- Inspect task health

---

### 6.2 HTTP Heartbeat (>= 0.0.43)

Optional alternative:
- HTTP POST JSON
- Same payload structure as MQTT heartbeat
- Configured via system parameters

---

## 7. End-to-End Operational Flow

### 7.1 Initial Provisioning

1. Box boots
2. Connects to MQTT broker
3. Starts heartbeat reporting
4. Waits for platform commands

---

### 7.2 Normal Operation

1. Platform configures media channels
2. Platform queries algorithm capabilities
3. Platform creates schedules
4. Platform creates algorithm tasks
5. Tasks auto-start
6. Alarms generated and reported
7. Heartbeats continuously sent

---

### 7.3 Remote Management

- Start / stop tasks → MQTT
- Modify parameters → MQTT
- Upgrade software → MQTT
- Observe state → MQTT heartbeat

---

## 8. Failure Domains

| Area | Impact | Notes |
|----|------|------|
| MQTT down | No control / heartbeat | Tasks may continue running |
| HTTP down | Alarm loss | Retry behavior firmware-dependent |
| Video upload fail | Alarm still sent | `VideoFile` empty |
| Partial MQTT loss | Command timeout | Platform must retry |

---

## 9. Design Constraints

- Box is **stateful**
- Platform must be **idempotent**
- MQTT messages are **stateless**
- No guaranteed ordering across topics
- All commands must be safe to retry

---

## 10. Next Documents

- `02-http-reporting.md` → HTTP endpoints (video & alarm)
- `03-mqtt-control.md` → MQTT command catalog
