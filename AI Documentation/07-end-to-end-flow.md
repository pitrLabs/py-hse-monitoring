# 07. End-to-End Flow

Dokumen ini menjelaskan **alur end-to-end sistem secara teknikal**
mulai dari **device boot**, **MQTT connect**, **konfigurasi**, **task execution**,
hingga **alarm reporting via HTTP**.

Dokumen ini menggabungkan seluruh bagian sebelumnya (02–06)
ke dalam **flow operasional nyata**.

---
## 7.1 High-Level System Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#4f46e5', 'primaryTextColor': '#fff', 'primaryBorderColor': '#3730a3', 'lineColor': '#6366f1', 'secondaryColor': '#818cf8', 'tertiaryColor': '#c7d2fe'}}}%%
flowchart
    A[Box Boot] --> B[Load Config]
    B --> C[Connect MQTT Broker]
    C --> D[Send Heartbeat]
    D --> E[Wait Control Command]
    E --> F[Receive Config]
    F --> G[Create Media]
    G --> H[Create Task]
    H --> I[Task Running]
    I --> J[Algorithm Triggered]
    J --> K[Upload Video HTTP]
    K --> L[Send Alarm HTTP]

    style A fill:#4f46e5,stroke:#3730a3,color:#fff
    style B fill:#6366f1,stroke:#4f46e5,color:#fff
    style C fill:#818cf8,stroke:#6366f1,color:#fff
    style D fill:#a5b4fc,stroke:#818cf8,color:#1e1b4b
    style E fill:#c7d2fe,stroke:#a5b4fc,color:#1e1b4b
    style F fill:#10b981,stroke:#059669,color:#fff
    style G fill:#34d399,stroke:#10b981,color:#064e3b
    style H fill:#6ee7b7,stroke:#34d399,color:#064e3b
    style I fill:#f59e0b,stroke:#d97706,color:#fff
    style J fill:#fbbf24,stroke:#f59e0b,color:#78350f
    style K fill:#ef4444,stroke:#dc2626,color:#fff
    style L fill:#f87171,stroke:#ef4444,color:#fff
```
---

## 7.2 Device Boot & Initialization

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#4f46e5', 'actorTextColor': '#fff', 'actorBorder': '#3730a3', 'signalColor': '#6366f1', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#e0e7ff', 'labelTextColor': '#3730a3', 'loopTextColor': '#4f46e5', 'noteBkgColor': '#fef3c7', 'noteTextColor': '#78350f', 'noteBorderColor': '#f59e0b'}}}%%
sequenceDiagram
    participant Device as Edge Box
    participant OS
    participant App

    OS->>App: Start edge application
    App->>App: Load local config
    App->>App: Init algorithm engine
    App->>App: Init media pipeline
```
---

## 7.3 MQTT Connection & Heartbeat
### 7.3.1 MQTT Connect Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#10b981', 'actorTextColor': '#fff', 'actorBorder': '#059669', 'signalColor': '#34d399', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#d1fae5', 'labelTextColor': '#059669', 'loopTextColor': '#10b981', 'noteBkgColor': '#fef3c7', 'noteTextColor': '#78350f', 'noteBorderColor': '#f59e0b'}}}%%
sequenceDiagram
    participant Device as Edge Box
    participant Broker as MQTT
    participant Platform

    Device->>Broker: CONNECT
    Broker->>Device: CONNACK
    Device->>Broker: SUBSCRIBE /edge_app_controller
    Device->>Broker: PUBLISH /board_ping (heartbeat)
    Platform->>Broker: SUBSCRIBE /board_ping
```
---

### 7.3.2 Heartbeat Runtime Flow
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#f59e0b', 'actorTextColor': '#fff', 'actorBorder': '#d97706', 'signalColor': '#fbbf24', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#fef3c7', 'labelTextColor': '#d97706', 'loopTextColor': '#f59e0b', 'noteBkgColor': '#e0e7ff', 'noteTextColor': '#3730a3', 'noteBorderColor': '#6366f1'}}}%%
sequenceDiagram
    participant Device as Edge Box
    participant MQTT
    participant Platform

    loop every 5s
        Device->>MQTT: Publish /board_ping
        Platform->>Platform: Update device status
    end
```
---

## 7.4 Capability Discovery Flow
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#8b5cf6', 'actorTextColor': '#fff', 'actorBorder': '#7c3aed', 'signalColor': '#a78bfa', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#ede9fe', 'labelTextColor': '#7c3aed', 'loopTextColor': '#8b5cf6', 'noteBkgColor': '#fef3c7', 'noteTextColor': '#78350f', 'noteBorderColor': '#f59e0b'}}}%%
sequenceDiagram
    participant Platform
    participant MQTT
    participant Device as Edge Box

    Platform->>MQTT: Publish /alg_ability_fetch
    MQTT->>Device: Deliver command
    Device->>Device: Collect algorithm capability
    Device->>MQTT: Reply capability list
    MQTT->>Platform: Capability response
```
---

## 7.5 Media Channel Configuration Flow
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#06b6d4', 'actorTextColor': '#fff', 'actorBorder': '#0891b2', 'signalColor': '#22d3ee', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#cffafe', 'labelTextColor': '#0891b2', 'loopTextColor': '#06b6d4', 'noteBkgColor': '#fef3c7', 'noteTextColor': '#78350f', 'noteBorderColor': '#f59e0b'}}}%%
sequenceDiagram
    participant Platform
    participant MQTT
    participant Device as Edge Box

    Platform->>MQTT: /alg_media_config
    MQTT->>Device: Create media
    Device->>Device: Validate RTSP
    Device->>MQTT: Reply result
    MQTT->>Platform: Media config response
```

Failure path (RTSP error):
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#ef4444', 'actorTextColor': '#fff', 'actorBorder': '#dc2626', 'signalColor': '#f87171', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#fee2e2', 'labelTextColor': '#dc2626', 'loopTextColor': '#ef4444', 'noteBkgColor': '#fef3c7', 'noteTextColor': '#78350f', 'noteBorderColor': '#f59e0b'}}}%%
sequenceDiagram
    participant Device as Edge Box
    participant MQTT
    participant Platform

    Device->>Device: RTSP connect failed
    Device->>MQTT: Result.Code != 0
    MQTT->>Platform: Media error
```
---

## 7.6 Algorithm Task Creation Flow
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#14b8a6', 'actorTextColor': '#fff', 'actorBorder': '#0d9488', 'signalColor': '#2dd4bf', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#ccfbf1', 'labelTextColor': '#0d9488', 'loopTextColor': '#14b8a6', 'noteBkgColor': '#fef3c7', 'noteTextColor': '#78350f', 'noteBorderColor': '#f59e0b'}}}%%
sequenceDiagram
    participant Platform
    participant MQTT
    participant Device as Edge Box

    Platform->>MQTT: /alg_task_config
    MQTT->>Device: Create task
    Device->>Device: Bind media + algorithm
    Device->>Device: Validate parameters
    Device->>Device: Auto start task
    Device->>MQTT: Reply success
    MQTT->>Platform: Task created
```
---

## 7.7 Task Runtime Execution
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#f59e0b', 'primaryTextColor': '#fff', 'primaryBorderColor': '#d97706', 'lineColor': '#fbbf24', 'secondaryColor': '#fcd34d', 'tertiaryColor': '#fef3c7'}}}%%
flowchart LR
    A[Video Frame] --> B[Primary Algorithm]
    B --> C[Sub Algorithm]
    C --> D{Rule Match?}
    D -- No --> A
    D -- Yes --> E[Generate Event]

    style A fill:#3b82f6,stroke:#2563eb,color:#fff
    style B fill:#8b5cf6,stroke:#7c3aed,color:#fff
    style C fill:#a855f7,stroke:#9333ea,color:#fff
    style D fill:#f59e0b,stroke:#d97706,color:#fff
    style E fill:#10b981,stroke:#059669,color:#fff
```
---

## 7.8 Alarm Reporting End-to-End Flow
### 7.8.1 Normal Alarm Flow (With Video)
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#ec4899', 'actorTextColor': '#fff', 'actorBorder': '#db2777', 'signalColor': '#f472b6', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#fce7f3', 'labelTextColor': '#db2777', 'loopTextColor': '#ec4899', 'noteBkgColor': '#fef3c7', 'noteTextColor': '#78350f', 'noteBorderColor': '#f59e0b'}}}%%
sequenceDiagram
    participant Algo as Algorithm
    participant Device as Edge Box
    participant HTTP as HTTP Server

    Algo->>Device: Alarm triggered
    Device->>Device: Record video
    Device->>HTTP: POST /video/upload
    HTTP-->>Device: VideoId
    Device->>HTTP: POST /alarm/report
    HTTP-->>Device: 200 OK
```
---

### 7.8.2 Alarm Flow (Without Video)
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#f97316', 'actorTextColor': '#fff', 'actorBorder': '#ea580c', 'signalColor': '#fb923c', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#ffedd5', 'labelTextColor': '#ea580c', 'loopTextColor': '#f97316', 'noteBkgColor': '#e0e7ff', 'noteTextColor': '#3730a3', 'noteBorderColor': '#6366f1'}}}%%
sequenceDiagram
    participant Algo as Algorithm
    participant Device as Edge Box
    participant HTTP as HTTP Server

    Algo->>Device: Alarm triggered
    Device->>HTTP: POST /alarm/report
    HTTP-->>Device: 200 OK
```
---

## 7.9 Alarm Failure & Retry Flow
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#ef4444', 'actorTextColor': '#fff', 'actorBorder': '#dc2626', 'signalColor': '#f87171', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#fee2e2', 'labelTextColor': '#dc2626', 'loopTextColor': '#ef4444', 'noteBkgColor': '#fef3c7', 'noteTextColor': '#78350f', 'noteBorderColor': '#f59e0b'}}}%%
sequenceDiagram
    participant Device as Edge Box
    participant HTTP as HTTP Server

    Device->>HTTP: POST alarm
    HTTP-->>Device: timeout / error
    Device->>Device: Mark as failed
    Device->>Device: Retry later
```

Retry policy:
- Retry internal queue
- Backoff strategy
- Max retry configurable

---

## 7.10 Task Control Flow (Start / Stop)
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#6366f1', 'actorTextColor': '#fff', 'actorBorder': '#4f46e5', 'signalColor': '#818cf8', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#e0e7ff', 'labelTextColor': '#4f46e5', 'loopTextColor': '#6366f1', 'noteBkgColor': '#fef3c7', 'noteTextColor': '#78350f', 'noteBorderColor': '#f59e0b'}}}%%
sequenceDiagram
    participant Platform
    participant MQTT
    participant Device as Edge Box

    Platform->>MQTT: /alg_task_control (stop)
    MQTT->>Device: Stop task
    Device->>Device: Release resources
    Device->>MQTT: Reply stopped
    MQTT->>Platform: Status update
```
---

## 7.11 Task Delete Flow
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#dc2626', 'actorTextColor': '#fff', 'actorBorder': '#b91c1c', 'signalColor': '#ef4444', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#fee2e2', 'labelTextColor': '#b91c1c', 'loopTextColor': '#dc2626', 'noteBkgColor': '#e0e7ff', 'noteTextColor': '#3730a3', 'noteBorderColor': '#6366f1'}}}%%
sequenceDiagram
    participant Platform
    participant MQTT
    participant Device as Edge Box

    Platform->>MQTT: /alg_task_delete
    MQTT->>Device: Delete task
    Device->>Device: Clear state
    Device->>MQTT: Reply deleted
    MQTT->>Platform: Task removed
```
---

## 7.12 Schedule Impact Flow
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'actorBkg': '#84cc16', 'actorTextColor': '#fff', 'actorBorder': '#65a30d', 'signalColor': '#a3e635', 'signalTextColor': '#fff', 'labelBoxBkgColor': '#ecfccb', 'labelTextColor': '#65a30d', 'loopTextColor': '#84cc16', 'noteBkgColor': '#fef3c7', 'noteTextColor': '#78350f', 'noteBorderColor': '#f59e0b'}}}%%
sequenceDiagram
    participant Scheduler
    participant Device as Edge Box

    Scheduler->>Device: Schedule inactive
    Device->>Device: Pause task
    Scheduler->>Device: Schedule active
    Device->>Device: Resume task
```
---

## 7.13 Failure Domains Overview
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#ef4444', 'primaryTextColor': '#fff', 'primaryBorderColor': '#dc2626', 'lineColor': '#f87171', 'secondaryColor': '#fca5a5', 'tertiaryColor': '#fee2e2'}}}%%
flowchart TD
    A[MQTT Down] --> B[No Control]
    C[RTSP Error] --> D[No Detection]
    E[HTTP Down] --> F[Alarm Pending]
    G[Algo Crash] --> H[Task Restart]

    style A fill:#ef4444,stroke:#dc2626,color:#fff
    style B fill:#fca5a5,stroke:#ef4444,color:#7f1d1d
    style C fill:#f97316,stroke:#ea580c,color:#fff
    style D fill:#fdba74,stroke:#f97316,color:#7c2d12
    style E fill:#eab308,stroke:#ca8a04,color:#fff
    style F fill:#fde047,stroke:#eab308,color:#713f12
    style G fill:#8b5cf6,stroke:#7c3aed,color:#fff
    style H fill:#c4b5fd,stroke:#8b5cf6,color:#4c1d95
```
---

## 7.14 End-to-End Responsibility Matrix
|Component|Responsibility|
|-|-|
|Edge Box|Detection, execution, reporting|
|MQTT|Control plane|
|HTTP|Data plane|
|Platform|Orchestration|
|Algorithm|Intelligence|

---

## 7.15 End-to-End Summary
```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#4f46e5', 'primaryTextColor': '#fff', 'primaryBorderColor': '#3730a3', 'lineColor': '#6366f1', 'secondaryColor': '#818cf8', 'tertiaryColor': '#c7d2fe'}}}%%
flowchart LR
    Boot --> MQTT
    MQTT --> Config
    Config --> Media
    Media --> Task
    Task --> Detect
    Detect --> Report

    style Boot fill:#4f46e5,stroke:#3730a3,color:#fff
    style MQTT fill:#10b981,stroke:#059669,color:#fff
    style Config fill:#06b6d4,stroke:#0891b2,color:#fff
    style Media fill:#8b5cf6,stroke:#7c3aed,color:#fff
    style Task fill:#f59e0b,stroke:#d97706,color:#fff
    style Detect fill:#ec4899,stroke:#db2777,color:#fff
    style Report fill:#ef4444,stroke:#dc2626,color:#fff
```
