# Multi-Path Recognition Algorithm Protocol
## Technical Overview

Document Version: 0.0.17  
Compiled: April 19, 2022  
Scope: Edge AI Box ↔ Platform Integration  
Protocols: MQTT, HTTP

---

## 1. System Purpose

This system defines a **communication and control protocol** between:
- Edge computing devices (AI boxes)
- Service / customer platform

Primary capabilities:
- Video stream ingestion
- Algorithm-based recognition
- Alarm reporting
- Remote configuration & lifecycle control
- Task scheduling & execution
- Device health monitoring

---

## 2. Core Communication Model

### 2.1 Protocol Split

| Function | Protocol |
|--------|---------|
| Alarm & video reporting | HTTP |
| Device control & configuration | MQTT |
| Heartbeat | MQTT / HTTP |
| Software upgrade | MQTT |
| Algorithm & media management | MQTT |

---

## 3. High-Level Component Roles

### 3.1 Edge AI Box
Responsibilities:
- Connect to MQTT broker
- Execute recognition algorithms
- Manage RTSP media channels
- Upload alarms & video clips
- Periodically report heartbeat

Identified by:
- `BoardId` (unique device ID)
- `BoardIp` (current network address)

---

### 3.2 MQTT Broker
Responsibilities:
- Message bus between platform and edge devices
- Supports:
  - TCP
  - WebSocket (for frontend usage)

Connection formats:
- `tcp://ip:port`
- `ws://ip:port`
- Auth supported:
  `tcp://username:password@ip:port`

---

### 3.3 Platform / Client System
Responsibilities:
- Subscribe to device events
- Issue control commands
- Receive alarms & videos
- Monitor device health
- Manage algorithms, schedules, and tasks

---

## 4. Topic & Message Direction

### 4.1 Downstream (Platform → Box)
Used for:
- Configuration
- Control
- Task management

General rule:
- All control messages **must include `BoardId`**
- Sent to:
  `/edge_app_controller`

---

### 4.2 Upstream (Box → Platform)
Used for:
- Heartbeat
- Logs
- Alarm notifications

Common topics:
- `/board_ping` → heartbeat
- `/edge_app_notify` → logs
- HTTP endpoints → alarms & video

---

## 5. Response Convention

- Every MQTT command response:
  - Sent to `{topic}_reply`
- Response payload always includes:
  - `BoardId`
  - `BoardIp`
  - `Event`
  - `Result { Code, Desc }`

Success rule:
- `Result.Code == 0` → success
- Non-zero → failure

---

## 6. Time & Data Units

| Field | Unit |
|-----|-----|
| `TimeStamp` | microseconds |
| Heartbeat time | milliseconds |
| GPS speed | km/h & knots |
| Image coordinates | normalized (0.0–1.0) |

---

## 7. Version Sensitivity

⚠️ Behavior depends on firmware version.

Examples:
- Alarm upload success response supported **>= 0.0.37**
- HTTP heartbeat supported **>= 0.0.43**
- Extended heartbeat fields **>= 0.0.46**

All implementations **must not assume backward compatibility**.

---

## 8. Next Documents

- `01-architecture-flow.md` → topology & data flow
- `02-http-reporting.md` → video & alarm endpoints
- `03-mqtt-control.md` → full MQTT command spec
