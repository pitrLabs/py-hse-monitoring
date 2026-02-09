# HSE Monitoring System

Sistem monitoring keselamatan kerja (HSE) dengan integrasi AI detection, multi-source video streaming, dan centralized storage.

---

## System Architecture

### High-Level Overview

```mermaid
flowchart TB
    subgraph FIELD["📍 Field - Site"]
        CAM1[🎥 IP Camera 1]
        CAM2[🎥 IP Camera 2]
        CAM3[🎥 IP Camera 3]
        CAM4[🎥 IP Camera N...]
    end

    subgraph AIBOXES["🤖 AI Processing Layer"]
        subgraph BOX1["AI Box #1 - Site A"]
            BMAPP1[BM-APP]
            MQTT1[MQTT Broker]
            BMAPP1 <--> MQTT1
        end

        subgraph BOX2["AI Box #2 - Site B"]
            BMAPP2[BM-APP]
            MQTT2[MQTT Broker]
            BMAPP2 <--> MQTT2
        end

        subgraph BOX3["AI Box #3 - Site C"]
            BMAPP3[BM-APP]
            MQTT3[MQTT Broker]
            BMAPP3 <--> MQTT3
        end
    end

    subgraph STORAGE["💾 Distributed Storage - Docker Host"]
        subgraph MINIO_CLUSTER["MinIO Cluster (Docker Containers)"]
            NGINX_LB[Nginx Load Balancer]
            MINIO1[MinIO Node 1]
            MINIO2[MinIO Node 2]
            MINIO3[MinIO Node 3]
            MINIO4[MinIO Node 4]
        end

        subgraph NAS_STORAGE["NAS Devices (Pure Storage via NFS)"]
            NAS1[(NAS #1)]
            NAS2[(NAS #2)]
            NAS3[(NAS #3)]
            NAS4[(NAS #4)]
        end
    end

    subgraph BACKEND["⚙️ HSE Backend"]
        API[FastAPI Server]
        WS_MGR[WebSocket Manager]
        SYNC[Media Sync Service]
        DB[(PostgreSQL)]
    end

    subgraph NOTIFY["📢 Notifications"]
        TELEGRAM[Telegram Bot]
    end

    subgraph FRONTEND["🖥️ Frontend"]
        ANGULAR[Angular Web App]
    end

    %% Camera to AI Box connections
    CAM1 --> BMAPP1
    CAM2 --> BMAPP1
    CAM3 --> BMAPP2
    CAM4 --> BMAPP3

    %% AI Box to Backend connections
    BMAPP1 -->|HTTP API + WebSocket| API
    BMAPP2 -->|HTTP API + WebSocket| API
    BMAPP3 -->|HTTP API + WebSocket| API

    WS_MGR -->|Alarm Events| BMAPP1
    WS_MGR -->|Alarm Events| BMAPP2
    WS_MGR -->|Alarm Events| BMAPP3

    %% MinIO cluster connections
    NGINX_LB --> MINIO1
    NGINX_LB --> MINIO2
    NGINX_LB --> MINIO3
    NGINX_LB --> MINIO4

    MINIO1 -.->|NFS mount| NAS1
    MINIO2 -.->|NFS mount| NAS2
    MINIO3 -.->|NFS mount| NAS3
    MINIO4 -.->|NFS mount| NAS4

    %% Backend connections
    API --> DB
    API --> NGINX_LB
    SYNC --> NGINX_LB
    SYNC --> BMAPP1
    SYNC --> BMAPP2
    SYNC --> BMAPP3

    API --> TELEGRAM
    ANGULAR --> API
```

---

### AI Box (BM-APP) Internal Architecture

```mermaid
flowchart LR
    subgraph AIBOX["AI Box - BM-APP"]
        subgraph INPUT["Input"]
            RTSP[RTSP Stream]
            HTTP_CAM[HTTP Camera]
        end

        subgraph CORE["Core Services"]
            DECODER[Video Decoder]
            AI_ENGINE[AI Engine]
            ALGORITHMS[Detection Algorithms]
        end

        subgraph MESSAGING["Messaging"]
            MQTT_BROKER[MQTT Broker<br/>Port 1883]
            ALARM_PUB[Alarm Publisher]
            CONTROL_SUB[Control Subscriber]
        end

        subgraph API_LAYER["API Layer"]
            REST_API[REST API<br/>Port 2323]
            WS_SERVER["WebSocket Server<br/>Alarm + Video Stream"]
        end

        subgraph STORAGE_LOCAL["Local Storage"]
            RECORDINGS[Video Recordings]
            SNAPSHOTS[Alarm Snapshots]
        end
    end

    RTSP --> DECODER
    HTTP_CAM --> DECODER
    DECODER --> AI_ENGINE
    AI_ENGINE --> ALGORITHMS

    ALGORITHMS -->|Detection Event| ALARM_PUB
    ALARM_PUB --> MQTT_BROKER
    MQTT_BROKER -->|Alarm| WS_SERVER

    CONTROL_SUB --> MQTT_BROKER
    CONTROL_SUB -->|Start/Stop Task| AI_ENGINE

    AI_ENGINE -->|Live Stream| WS_SERVER
    AI_ENGINE --> RECORDINGS
    ALGORITHMS --> SNAPSHOTS

    REST_API -->|Query Data| RECORDINGS
    REST_API -->|Query Data| SNAPSHOTS
```

#### MQTT Topics dalam BM-APP

| Topic | Direction | Description |
|-------|-----------|-------------|
| `alarm/{task_session}` | Publish | Real-time alarm events |
| `control/{task_session}` | Subscribe | Start/stop AI tasks |
| `status/{device_id}` | Publish | Device health status |
| `recording/{task_session}` | Publish | Recording status updates |

---

### Multi AI Box Connection Flow

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant BE as HSE Backend
    participant BOX1 as AI Box #1
    participant BOX2 as AI Box #2
    participant BOX3 as AI Box #3
    participant TG as Telegram
    participant MINIO as MinIO

    Note over BE: Startup - Connect to all AI Boxes

    BE->>BOX1: Connect WebSocket ws://box1:2323/alarm/
    BE->>BOX2: Connect WebSocket ws://box2:2323/alarm/
    BE->>BOX3: Connect WebSocket ws://box3:2323/alarm/

    BOX1-->>BE: Connected ✓
    BOX2-->>BE: Connected ✓
    BOX3-->>BE: Connected ✓

    Note over BOX1: AI Detection Event
    BOX1->>BE: Alarm: NoHelmet detected
    BE->>BE: Save to PostgreSQL
    BE->>BE: Identify source: AI Box #1

    BE->>MINIO: Upload alarm image
    MINIO-->>BE: minio_path: alarm-images/2024/...

    BE->>TG: Send notification with photo
    BE->>FE: WebSocket broadcast to clients

    Note over BOX2: Different AI Box Event
    BOX2->>BE: Alarm: Fire detected
    BE->>BE: Save with aibox_id = Box #2
    BE->>TG: Send critical alert
```

---

### Storage Architecture: Multiple NAS with MinIO

```mermaid
flowchart TB
    subgraph SOURCES["Data Sources"]
        ALARM_IMG[Alarm Images<br/>from AI Boxes]
        RECORDINGS[Video Recordings<br/>from AI Boxes]
        LOCAL_VID[Local Video<br/>Manual Upload]
    end

    subgraph HSE_BACKEND["HSE Backend"]
        MEDIA_SYNC[Media Sync Service]
        STORAGE_SVC[MinIO Storage Service]
        API[FastAPI]
    end

    subgraph SERVER["Docker Host Server"]
        subgraph DOCKER["Docker Containers"]
            LB["Nginx Load Balancer<br/>:9000 API, :9001 Console"]

            subgraph NODES["MinIO Nodes - Erasure Coded"]
                M1[minio1:9000]
                M2[minio2:9000]
                M3[minio3:9000]
                M4[minio4:9000]
            end
        end

        subgraph MOUNTS["NFS or iSCSI Mount Points"]
            MNT1["mnt/nas1"]
            MNT2["mnt/nas2"]
            MNT3["mnt/nas3"]
            MNT4["mnt/nas4"]
        end
    end

    subgraph NAS_DEVICES["NAS Devices - Pure Storage Only"]
        NAS1[(NAS #1<br/>8TB)]
        NAS2[(NAS #2<br/>8TB)]
        NAS3[(NAS #3<br/>8TB)]
        NAS4[(NAS #4<br/>8TB)]
    end

    ALARM_IMG --> MEDIA_SYNC
    RECORDINGS --> MEDIA_SYNC
    LOCAL_VID --> API

    MEDIA_SYNC --> STORAGE_SVC
    API --> STORAGE_SVC
    STORAGE_SVC --> LB

    LB --> M1 & M2 & M3 & M4

    M1 -.->|volume mount| MNT1
    M2 -.->|volume mount| MNT2
    M3 -.->|volume mount| MNT3
    M4 -.->|volume mount| MNT4

    MNT1 ===|NFS/iSCSI| NAS1
    MNT2 ===|NFS/iSCSI| NAS2
    MNT3 ===|NFS/iSCSI| NAS3
    MNT4 ===|NFS/iSCSI| NAS4

    style LB fill:#f9f,stroke:#333
    style NODES fill:#bbf,stroke:#333
    style NAS_DEVICES fill:#ffd,stroke:#333
```

> **Note:** NAS devices hanya menyediakan storage (NFS/iSCSI share). MinIO berjalan sebagai Docker container di server, bukan di NAS.

#### Erasure Coding Benefit

```
┌───────────────────────────────────────────────────────┐
│  File: alarm_2024_001.jpg (100KB)                     │
├───────────────────────────────────────────────────────┤
│                                                       │
│  Erasure Coded (EC:2) - Can survive 2 node failures   │
│                                                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
│  │ NAS #1  │  │ NAS #2  │  │ NAS #3  │  │ NAS #4  │   │
│  │ Data 1  │  │ Data 2  │  │ Parity 1│  │ Parity 2│   │
│  │  25KB   │  │  25KB   │  │  25KB   │  │  25KB   │   │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │
│       ✓            ✓            ✗            ✗        │
│                          (2 nodes down = still OK!)   │
│                                                       │
└───────────────────────────────────────────────────────┘
```

---

### Complete Data Flow

```mermaid
flowchart LR
    subgraph CAMERA["Camera"]
        C[🎥 IP Camera]
    end

    subgraph AIBOX["AI Box"]
        direction TB
        A1[RTSP Input]
        A2[AI Detection]
        A3[MQTT Publish]
        A4[WebSocket Push]
        A1 --> A2 --> A3 --> A4
    end

    subgraph BACKEND["HSE Backend"]
        direction TB
        B1[WS Manager]
        B2[Alarm Router]
        B3[Media Sync]
        B4[PostgreSQL]
        B1 --> B2
        B2 --> B3
        B2 --> B4
    end

    subgraph STORAGE["MinIO + NAS"]
        direction TB
        S1[MinIO Cluster]
        S2[(4x NAS)]
        S1 --> S2
    end

    subgraph OUTPUT["Output"]
        direction TB
        O1[📱 Telegram]
        O2[🖥️ Web Dashboard]
        O3[📊 Excel Reports]
    end

    C -->|RTSP| AIBOX
    AIBOX -->|WS: Alarm| BACKEND
    BACKEND -->|Store Media| STORAGE
    BACKEND --> OUTPUT
```

---

### Database Schema for Multi AI Box

```mermaid
erDiagram
    AI_BOXES ||--o{ VIDEO_SOURCES : contains
    AI_BOXES ||--o{ ALARMS : generates
    AI_BOXES ||--o{ RECORDINGS : stores
    VIDEO_SOURCES ||--o{ AI_TASKS : has
    VIDEO_SOURCES ||--o{ ALARMS : triggers
    ALARMS ||--o{ RECORDINGS : linked
    USERS ||--o{ ALARMS : acknowledges

    AI_BOXES {
        uuid id PK
        string name "Site A, Site B"
        string code "SITE_A, SITE_B"
        string api_url "http://box1:2323/api"
        string alarm_ws_url "ws://box1:2323/alarm/"
        string webrtc_url "http://box1:2323/webrtc"
        boolean is_active
        boolean is_online
        datetime last_seen_at
    }

    VIDEO_SOURCES {
        uuid id PK
        uuid aibox_id FK
        string name
        string stream_name
        string url
        boolean is_active
    }

    ALARMS {
        uuid id PK
        uuid aibox_id FK
        string aibox_name
        string alarm_type
        string camera_name
        string image_url
        string minio_image_path
        datetime alarm_time
    }

    RECORDINGS {
        uuid id PK
        uuid aibox_id FK
        string file_name
        string minio_file_path
        datetime start_time
    }
```

---

### Deployment Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PRODUCTION SETUP                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │   SITE A        │     │   SITE B        │     │   SITE C        │       │
│  │   Semarang      │     │   Pekalongan    │     │   Cilacap       │       │
│  │                 │     │                 │     │                 │       │
│  │  ┌───────────┐  │     │  ┌───────────┐  │     │  ┌───────────┐  │       │
│  │  │ AI Box #1 │  │     │  │ AI Box #2 │  │     │  │ AI Box #3 │  │       │
│  │  │ 10.0.1.10 │  │     │  │ 10.0.2.10 │  │     │  │ 10.0.3.10 │  │       │
│  │  └─────┬─────┘  │     │  └─────┬─────┘  │     │  └─────┬─────┘  │       │
│  │        │        │     │        │        │     │        │        │       │
│  │  ┌─────┴─────┐  │     │  ┌─────┴─────┐  │     │  ┌─────┴─────┐  │       │
│  │  │ 4 Cameras │  │     │  │ 8 Cameras │  │     │  │ 6 Cameras │  │       │
│  │  └───────────┘  │     │  └───────────┘  │     │  └───────────┘  │       │
│  └────────┬────────┘     └────────┬────────┘     └────────┬────────┘       │
│           │                       │                       │                 │
│           └───────────────────────┼───────────────────────┘                 │
│                                   │                                         │
│                          ┌────────▼────────┐                                │
│                          │   VPN / WAN     │                                │
│                          └────────┬────────┘                                │
│                                   │                                         │
│  ┌────────────────────────────────▼─────────────────────────────────────┐  │
│  │                         DATA CENTER                                   │  │
│  │                                                                       │  │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐  │  │
│  │   │ HSE Backend │    │ PostgreSQL  │    │ MinIO Cluster           │  │  │
│  │   │ FastAPI     │◄──►│ Database    │    │ ┌─────┐┌─────┐          │  │  │
│  │   │ Port 8001   │    │ Port 5432   │    │ │NAS 1││NAS 2│          │  │  │
│  │   └──────┬──────┘    └─────────────┘    │ └─────┘└─────┘          │  │  │
│  │          │                              │ ┌─────┐┌─────┐          │  │  │
│  │          │                              │ │NAS 3││NAS 4│          │  │  │
│  │          ▼                              │ └─────┘└─────┘          │  │  │
│  │   ┌─────────────┐                       │ Port 9000/9001          │  │  │
│  │   │  Telegram   │                       └─────────────────────────┘  │  │
│  │   │  Bot API    │                                                    │  │
│  │   └─────────────┘                                                    │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│                          ┌─────────────────┐                                │
│                          │  Angular Web    │                                │
│                          │  Dashboard      │                                │
│                          │  Port 80/443    │                                │
│                          └─────────────────┘                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Features

- ✅ **JWT Authentication** - Login with JWT tokens
- ✅ **User Management** - CRUD operations for users
- ✅ **Role-Based Access Control** - Flexible role and permission system
- ✅ **User Levels** - User levels from 1-10
- ✅ **Password Hashing** - Passwords hashed using bcrypt
- ✅ **Superuser Support** - Admin with full access

## Database Structure

### User Model
- `id` - Primary key
- `username` - Unique username
- `email` - Unique email
- `hashed_password` - Hashed password
- `full_name` - Full name
- `is_active` - User active status
- `is_superuser` - Superuser status
- `user_level` - User level (1-10)
- `roles` - Many-to-many relationship with Role

### Role Model
- `id` - Primary key
- `name` - Unique role name
- `description` - Role description
- `permissions` - Many-to-many relationship with Permission

### Permission Model
- `id` - Primary key
- `name` - Unique permission name
- `resource` - Protected resource (e.g., "users", "roles")
- `action` - Allowed action (e.g., "read", "create", "update", "delete")
- `description` - Permission description

## Installation

1. Install dependencies:
```bash
uv sync
```

2. Configure environment variables (create `.env` file):
```bash
DATABASE_URL=postgresql://user:password@localhost:5432/hse_monitoring
SECRET_KEY=your-secret-key-change-this-in-production
```

3. Initialize database:
```bash
python init_db.py
```

4. Run the server:
```bash
python main.py
```

Server will run at `http://localhost:8000`

## Default Credentials

After running `init_db.py`, a default user will be created:

- **Username**: admin
- **Password**: admin123
- **Role**: admin (full access)

⚠️ **IMPORTANT**: Change this default password immediately!

## Default Roles

The system creates 3 default roles:

1. **admin** - Full access to all resources
2. **manager** - Read, create, update access
3. **viewer** - Read-only access

## API Endpoints

### Authentication

- `POST /auth/register` - Register new user
- `POST /auth/login` - Login and get access token
- `GET /auth/me` - Get current user info
- `PUT /auth/me` - Update current user info

### User Management

- `GET /users` - List all users (requires permission)
- `GET /users/{user_id}` - Get user by ID (requires permission)
- `POST /users` - Create new user (requires permission)
- `PUT /users/{user_id}` - Update user (requires permission)
- `DELETE /users/{user_id}` - Delete user (requires permission)

### Role & Permission Management

- `GET /roles/permissions` - List all permissions
- `POST /roles/permissions` - Create permission (superuser only)
- `DELETE /roles/permissions/{permission_id}` - Delete permission (superuser only)
- `GET /roles` - List all roles
- `GET /roles/{role_id}` - Get role by ID
- `POST /roles` - Create new role
- `PUT /roles/{role_id}` - Update role
- `DELETE /roles/{role_id}` - Delete role

## API Documentation

After the server is running, access interactive documentation at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Usage Examples

### 1. Register New User

```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "johndoe",
    "email": "john@example.com",
    "password": "password123",
    "full_name": "John Doe",
    "user_level": 5,
    "role_ids": [2]
  }'
```

### 2. Login

```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 3. Get Current User (with token)

```bash
curl -X GET "http://localhost:8000/auth/me" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 4. Create Role with Permissions

```bash
curl -X POST "http://localhost:8000/roles" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "operator",
    "description": "Operator with limited access",
    "permission_ids": [1, 5, 9]
  }'
```

## Security Configuration

⚠️ **IMPORTANT for Production**:

1. Change `SECRET_KEY` in `.env` file
2. Use PostgreSQL database (already configured)
3. Change default admin password
4. Use HTTPS for production
5. Set environment variables for sensitive data
6. Enable database connection pooling
7. Add rate limiting for API endpoints

## Permission System

The permission system uses `resource.action` format:

- **resource**: Protected resource (users, roles, monitoring, etc.)
- **action**: Allowed action (read, create, update, delete)

Examples: `users.read`, `roles.create`, `monitoring.delete`

### Checking Permissions in Code

```python
from app.auth import require_permission

@router.get("/")
def list_items(
    _: User = Depends(require_permission("items", "read"))
):
    # Your code here
    pass
```

### Checking User Level

```python
from app.auth import require_user_level

@router.get("/")
def admin_only(
    _: User = Depends(require_user_level(8))
):
    # Requires user level >= 8
    pass
```

## User Levels

User levels range from 1-10 and determine access hierarchy in the system:

| Level | Nama | Deskripsi | Akses Kamera |
|-------|------|-----------|--------------|
| 1 | Operator Junior | Operator level dasar | Hanya kamera yang di-assign |
| 2 | Operator | Operator standar | Hanya kamera yang di-assign |
| 3 | Operator Senior | Operator berpengalaman | Hanya kamera yang di-assign |
| 4 | Supervisor Junior | Supervisor pemula | Hanya kamera yang di-assign |
| 5 | Supervisor | Supervisor standar | Hanya kamera yang di-assign |
| 6 | Supervisor Senior | Supervisor berpengalaman | Hanya kamera yang di-assign |
| 7 | Manager Junior | Manager pemula | Semua kamera |
| 8 | Manager | Manager standar | Semua kamera |
| 9 | Manager Senior | Manager berpengalaman | Semua kamera |
| 10 | Administrator | Full system access | Semua kamera |

### Akses Kamera Berdasarkan Level & Role

Sistem menggunakan kombinasi **User Level** dan **Role** untuk menentukan akses:

1. **Superuser / Admin** → Akses semua kamera
2. **Role: Manager, Admin, Superadmin** → Akses semua kamera
3. **Role: Operator / Viewer** → Hanya kamera yang di-assign

### Cara Assign Kamera ke Operator

1. Buka **Admin → Users**
2. Cari user dengan role Operator
3. Klik icon **kamera** di kolom Actions
4. Pilih kamera yang ingin di-assign
5. Klik **Save**

### Fitur Berdasarkan Level

| Fitur | Level 1-3 | Level 4-6 | Level 7-9 | Level 10 |
|-------|-----------|-----------|-----------|----------|
| View Monitor | ✅ (assigned) | ✅ (assigned) | ✅ (all) | ✅ (all) |
| View Monitoring AI | ✅ (assigned) | ✅ (assigned) | ✅ (all) | ✅ (all) |
| View Events/Alarms | ✅ | ✅ | ✅ | ✅ |
| Acknowledge Alarms | ❌ | ✅ | ✅ | ✅ |
| Resolve Alarms | ❌ | ❌ | ✅ | ✅ |
| Manage Video Sources | ❌ | ❌ | ❌ | ✅ |
| Manage AI Tasks | ❌ | ❌ | ❌ | ✅ |
| Manage Users | ❌ | ❌ | ❌ | ✅ |
| Manage Roles | ❌ | ❌ | ❌ | ✅ |

### Contoh Penggunaan di Code

```python
from app.auth import require_user_level

# Minimal level 5 untuk akses endpoint ini
@router.get("/supervisor-only")
def supervisor_endpoint(
    _: User = Depends(require_user_level(5))
):
    pass

# Minimal level 8 untuk manager
@router.post("/manager-action")
def manager_action(
    _: User = Depends(require_user_level(8))
):
    pass
```

### Single Session Authentication

Setiap user hanya bisa login di 1 device/browser. Jika login di tempat lain:
- Session sebelumnya otomatis ter-logout
- User akan melihat pesan "Sesi Anda telah berakhir karena login dari perangkat lain"

Superusers (`is_superuser=True`) bypass semua permission checks.

```sh
docs/
├── 00-overview.md
├── 01-architecture-flow.md
├── 02-http-reporting.md
├── 03-mqtt-control.md
├── 04-algorithm-capability.md
├── 05-media-channel.md
├── 06-algorithm-task.md
├── 07-end-to-end-flow.md
└── 08-version-notes.md
```

---

## MinIO Object Storage

MinIO digunakan untuk menyimpan media files secara terpusat:
- **Bukti Foto Alarm** - Screenshot dari deteksi AI
- **Rekaman Video** - Recording dari kamera
- **Local Video** - Video yang di-upload manual

### Quick Start

```bash
# Start MinIO
docker-compose up -d minio

# Akses MinIO Console
# URL: http://localhost:9001
# Login: minioadmin / minioadmin123
```

### Buckets

| Bucket | Deskripsi |
|--------|-----------|
| `alarm-images` | Gambar dan video dari alarm deteksi |
| `recordings` | Rekaman video dari BM-APP |
| `local-videos` | Video upload manual untuk analisis |

### Konfigurasi Environment

```ini
# MinIO Object Storage
MINIO_ENABLED=true
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_SECURE=false
MINIO_BUCKET_ALARM_IMAGES=alarm-images
MINIO_BUCKET_RECORDINGS=recordings
MINIO_BUCKET_LOCAL_VIDEOS=local-videos
MINIO_PRESIGNED_URL_EXPIRY=3600
```

### API Endpoints - Local Videos

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/local-videos` | List semua video |
| GET | `/local-videos/{id}` | Get detail video |
| POST | `/local-videos/upload` | Direct upload (< 100MB) |
| POST | `/local-videos/upload/init` | Init presigned upload (large files) |
| POST | `/local-videos/upload/complete` | Complete presigned upload |
| PUT | `/local-videos/{id}` | Update metadata |
| DELETE | `/local-videos/{id}` | Hapus video |
| GET | `/local-videos/{id}/stream-url` | Get presigned stream URL |
| GET | `/local-videos/stats/summary` | Statistik storage |

### API Endpoints - Storage

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/storage/health` | Cek koneksi MinIO |
| GET | `/storage/buckets` | List bucket dengan statistik |

### Database Migration untuk MinIO

```sql
-- Add MinIO columns to alarms
ALTER TABLE alarms
ADD COLUMN IF NOT EXISTS minio_image_path VARCHAR(500),
ADD COLUMN IF NOT EXISTS minio_video_path VARCHAR(500),
ADD COLUMN IF NOT EXISTS minio_synced_at TIMESTAMP;

-- Add MinIO columns to recordings
ALTER TABLE recordings
ADD COLUMN IF NOT EXISTS minio_file_path VARCHAR(500),
ADD COLUMN IF NOT EXISTS minio_thumbnail_path VARCHAR(500),
ADD COLUMN IF NOT EXISTS minio_synced_at TIMESTAMP;

-- Create local_videos table
CREATE TABLE IF NOT EXISTS local_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    description VARCHAR(1000),
    original_filename VARCHAR(300) NOT NULL,
    minio_path VARCHAR(500) NOT NULL,
    thumbnail_path VARCHAR(500),
    file_size INTEGER NOT NULL DEFAULT 0,
    duration INTEGER,
    resolution VARCHAR(20),
    format VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'processing',
    error_message VARCHAR(500),
    uploaded_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_local_videos_status ON local_videos(status);
CREATE INDEX IF NOT EXISTS idx_local_videos_created_at ON local_videos(created_at);
```

---

## Scaling MinIO: Dari Testing ke Production dengan 4 NAS

### Current Setup (Development/Testing)

Single node dengan Docker volume - data disimpan di local storage server.

```yaml
minio:
  image: minio/minio:latest
  command: server /data --console-address ":9001"
  volumes:
    - minio_data:/data  # Local Docker volume
```

**Tidak perlu NAS untuk testing** - data tersimpan di `/var/lib/docker/volumes/`.

### Production Setup: Distributed Mode dengan 4 NAS

#### Arsitektur

```
                    ┌─────────────┐
                    │   Nginx     │
                    │ Load Balancer│
                    └──────┬──────┘
                           │
        ┌──────────┬───────┴───────┬──────────┐
        │          │               │          │
   ┌────▼───┐ ┌────▼───┐     ┌────▼───┐ ┌────▼───┐
   │ MinIO  │ │ MinIO  │     │ MinIO  │ │ MinIO  │
   │ Node 1 │ │ Node 2 │     │ Node 3 │ │ Node 4 │
   └────┬───┘ └────┬───┘     └────┬───┘ └────┬───┘
        │          │               │          │
   ┌────▼───┐ ┌────▼───┐     ┌────▼───┐ ┌────▼───┐
   │  NAS 1 │ │  NAS 2 │     │  NAS 3 │ │  NAS 4 │
   └────────┘ └────────┘     └────────┘ └────────┘
```

#### Docker Compose untuk 4 NAS

Buat file `docker-compose.distributed.yml`:

```yaml
version: "3.9"

x-minio-common: &minio-common
  image: minio/minio:latest
  command: server --console-address ":9001" http://minio{1...4}:9000/data
  environment:
    MINIO_ROOT_USER: ${MINIO_ROOT_USER:-minioadmin}
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-your-secure-password-here}
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
    interval: 30s
    timeout: 20s
    retries: 3
  networks:
    - minio-distributed

services:
  minio1:
    <<: *minio-common
    hostname: minio1
    container_name: minio1
    volumes:
      - /mnt/nas1/minio:/data  # Mount point NAS 1

  minio2:
    <<: *minio-common
    hostname: minio2
    container_name: minio2
    volumes:
      - /mnt/nas2/minio:/data  # Mount point NAS 2

  minio3:
    <<: *minio-common
    hostname: minio3
    container_name: minio3
    volumes:
      - /mnt/nas3/minio:/data  # Mount point NAS 3

  minio4:
    <<: *minio-common
    hostname: minio4
    container_name: minio4
    volumes:
      - /mnt/nas4/minio:/data  # Mount point NAS 4

  nginx:
    image: nginx:alpine
    container_name: minio-lb
    volumes:
      - ./nginx-minio.conf:/etc/nginx/nginx.conf:ro
    ports:
      - "9000:9000"  # MinIO API
      - "9001:9001"  # MinIO Console
    depends_on:
      - minio1
      - minio2
      - minio3
      - minio4
    networks:
      - minio-distributed

networks:
  minio-distributed:
    driver: bridge
```

#### Nginx Load Balancer Config

Buat file `nginx-minio.conf`:

```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 4096;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    keepalive_timeout 65;

    # MinIO upstream servers
    upstream minio_api {
        least_conn;
        server minio1:9000;
        server minio2:9000;
        server minio3:9000;
        server minio4:9000;
    }

    upstream minio_console {
        least_conn;
        server minio1:9001;
        server minio2:9001;
        server minio3:9001;
        server minio4:9001;
    }

    # MinIO API (S3)
    server {
        listen 9000;
        server_name _;
        client_max_body_size 0;
        proxy_buffering off;
        proxy_request_buffering off;

        location / {
            proxy_pass http://minio_api;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 300;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            chunked_transfer_encoding off;
        }
    }

    # MinIO Console
    server {
        listen 9001;
        server_name _;
        client_max_body_size 0;
        proxy_buffering off;

        location / {
            proxy_pass http://minio_console;
            proxy_set_header Host $http_host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 300;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

#### Migration dari Single Node ke Distributed

1. **Backup data** dari single node:
   ```bash
   # Install MinIO Client
   mc alias set local http://localhost:9000 minioadmin minioadmin123

   # Backup semua bucket
   mc mirror local/alarm-images ./backup/alarm-images
   mc mirror local/recordings ./backup/recordings
   mc mirror local/local-videos ./backup/local-videos
   ```

2. **Mount 4 NAS** ke server:
   ```bash
   # Contoh mount NFS
   mount -t nfs nas1.local:/share /mnt/nas1
   mount -t nfs nas2.local:/share /mnt/nas2
   mount -t nfs nas3.local:/share /mnt/nas3
   mount -t nfs nas4.local:/share /mnt/nas4
   ```

3. **Start distributed MinIO**:
   ```bash
   docker-compose -f docker-compose.distributed.yml up -d
   ```

4. **Restore data**:
   ```bash
   mc alias set distributed http://localhost:9000 minioadmin your-secure-password
   mc mirror ./backup/alarm-images distributed/alarm-images
   mc mirror ./backup/recordings distributed/recordings
   mc mirror ./backup/local-videos distributed/local-videos
   ```

5. **Update `.env`** jika endpoint berubah

#### Keuntungan Distributed Mode

| Fitur | Deskripsi |
|-------|-----------|
| **Erasure Coding** | Data di-split dengan parity, survive hingga 2 node failure |
| **High Availability** | Tetap berjalan meski 2 dari 4 NAS offline |
| **Auto Healing** | Otomatis repair data corrupt atau missing |
| **Horizontal Scaling** | Tambah kapasitas dengan menambah node |
| **Load Balancing** | Request di-distribute ke semua node |

#### Minimum Requirements

- Minimum 4 node (untuk erasure coding)
- Setiap node minimal 1 drive/mount point
- Network: Gigabit ethernet minimum, 10GbE recommended
- NAS protocol: NFS v4 atau iSCSI recommended

---

## Troubleshooting

### MinIO tidak bisa start

```bash
# Cek logs
docker-compose logs minio

# Cek port
lsof -i :9000
lsof -i :9001
```

### Upload gagal

1. Cek storage health: `GET /storage/health`
2. Cek bucket exists di MinIO Console
3. Cek file size limit (100MB untuk direct upload)

### Media sync tidak jalan

```bash
# Cek logs
docker-compose logs app | grep MediaSync

# Pastikan MINIO_ENABLED=true
```

---

## Multiple AI Box (BM-APP) Configuration

Sistem mendukung multiple AI Box yang tersebar di berbagai lokasi. Setiap AI Box memiliki kamera, AI detection, dan WebSocket sendiri.

### Database Model: AIBox

```sql
CREATE TABLE ai_boxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,              -- "Site Semarang", "Site Pekalongan"
    code VARCHAR(20) UNIQUE NOT NULL,        -- "SMG", "PKL", "CLP"
    api_url VARCHAR(500) NOT NULL,           -- http://10.0.1.10:2323/api
    alarm_ws_url VARCHAR(500) NOT NULL,      -- ws://10.0.1.10:2323/alarm/
    webrtc_url VARCHAR(500) NOT NULL,        -- http://10.0.1.10:2323/webrtc
    mqtt_host VARCHAR(200),                  -- 10.0.1.10
    mqtt_port INTEGER DEFAULT 1883,
    is_active BOOLEAN DEFAULT true,
    is_online BOOLEAN DEFAULT false,
    last_seen_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Link video sources to AI Box
ALTER TABLE video_sources ADD COLUMN aibox_id UUID REFERENCES ai_boxes(id);

-- Link alarms to AI Box (denormalized for performance)
ALTER TABLE alarms ADD COLUMN aibox_id UUID REFERENCES ai_boxes(id);
ALTER TABLE alarms ADD COLUMN aibox_name VARCHAR(100);

-- Link recordings to AI Box
ALTER TABLE recordings ADD COLUMN aibox_id UUID REFERENCES ai_boxes(id);
```

### Environment Variables

```ini
# Legacy single AI Box (masih didukung untuk backward compatibility)
BMAPP_ENABLED=true
BMAPP_API_URL=http://103.75.84.183:2323/api
BMAPP_ALARM_WS_URL=ws://103.75.84.183:2323/alarm/
BMAPP_WEBRTC_URL=http://103.75.84.183:2323/webrtc

# Multiple AI Box mode (override legacy jika enabled)
MULTI_AIBOX_ENABLED=true
```

### API Endpoints - AI Box Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ai-boxes` | List semua AI Box |
| GET | `/ai-boxes/{id}` | Get detail AI Box |
| POST | `/ai-boxes` | Tambah AI Box baru |
| PUT | `/ai-boxes/{id}` | Update AI Box |
| DELETE | `/ai-boxes/{id}` | Hapus AI Box |
| GET | `/ai-boxes/{id}/status` | Cek status koneksi |
| POST | `/ai-boxes/{id}/sync-cameras` | Sync kamera dari AI Box |
| GET | `/ai-boxes/{id}/cameras` | List kamera di AI Box |

### WebSocket Manager untuk Multiple AI Box

```python
class MultiAIBoxWebSocketManager:
    """Manages WebSocket connections to multiple AI Boxes"""

    def __init__(self):
        self.connections: Dict[UUID, WebSocketConnection] = {}
        self.reconnect_tasks: Dict[UUID, asyncio.Task] = {}

    async def connect_all(self, db: Session):
        """Connect to all active AI Boxes on startup"""
        ai_boxes = db.query(AIBox).filter(AIBox.is_active == True).all()
        for box in ai_boxes:
            await self.connect(box)

    async def connect(self, ai_box: AIBox):
        """Connect to single AI Box WebSocket"""
        try:
            ws = await websockets.connect(ai_box.alarm_ws_url)
            self.connections[ai_box.id] = ws
            ai_box.is_online = True
            ai_box.last_seen_at = datetime.utcnow()
            asyncio.create_task(self._listen(ai_box, ws))
        except Exception as e:
            ai_box.is_online = False
            self._schedule_reconnect(ai_box)

    async def _listen(self, ai_box: AIBox, ws):
        """Listen for alarms from AI Box"""
        async for message in ws:
            alarm_data = json.loads(message)
            alarm_data['aibox_id'] = str(ai_box.id)
            alarm_data['aibox_name'] = ai_box.name
            await self._process_alarm(alarm_data)
```

### Contoh Konfigurasi Multi-Site

```
┌─────────────────────────────────────────────────────────────────┐
│  AI Box Registry                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ID: 550e8400-e29b-41d4-a716-446655440001                │   │
│  │ Name: Site Semarang                                      │   │
│  │ Code: SMG                                                │   │
│  │ API: http://103.75.84.183:2323/api                      │   │
│  │ WS: ws://103.75.84.183:2323/alarm/                      │   │
│  │ WebRTC: http://103.75.84.183:2323/webrtc                │   │
│  │ MQTT: 103.75.84.183:1883                                │   │
│  │ Status: 🟢 Online | Cameras: 4 | Last Seen: 2 min ago   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ID: 550e8400-e29b-41d4-a716-446655440002                │   │
│  │ Name: Site Pekalongan                                    │   │
│  │ Code: PKL                                                │   │
│  │ API: http://192.168.1.100:2323/api                      │   │
│  │ WS: ws://192.168.1.100:2323/alarm/                      │   │
│  │ WebRTC: http://192.168.1.100:2323/webrtc                │   │
│  │ MQTT: 192.168.1.100:1883                                │   │
│  │ Status: 🟢 Online | Cameras: 8 | Last Seen: 1 min ago   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ID: 550e8400-e29b-41d4-a716-446655440003                │   │
│  │ Name: Site Cilacap                                       │   │
│  │ Code: CLP                                                │   │
│  │ API: http://10.0.50.10:2323/api                         │   │
│  │ WS: ws://10.0.50.10:2323/alarm/                         │   │
│  │ WebRTC: http://10.0.50.10:2323/webrtc                   │   │
│  │ MQTT: 10.0.50.10:1883                                   │   │
│  │ Status: 🔴 Offline | Cameras: 6 | Last Seen: 15 min ago │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Frontend: AI Box Selector

Di halaman Monitoring AI, user bisa memilih AI Box mana yang ingin dilihat:

```typescript
// Component
selectedAiBox = signal<AIBox | null>(null);
aiBoxes = signal<AIBox[]>([]);

async loadAiBoxes() {
  const boxes = await this.aiBoxService.getAll();
  this.aiBoxes.set(boxes);
  // Auto-select first online box
  const onlineBox = boxes.find(b => b.is_online);
  if (onlineBox) this.selectedAiBox.set(onlineBox);
}

onAiBoxChange(box: AIBox) {
  this.selectedAiBox.set(box);
  // Reload cameras from selected AI Box
  this.loadCameras(box.id);
  // Reconnect WebSocket to selected box
  this.reconnectAlarmWs(box.alarm_ws_url);
}
```

### Alarm dengan Source AI Box

Setiap alarm menyimpan informasi dari AI Box mana asalnya:

```json
{
  "id": "uuid-alarm-123",
  "alarm_type": "NoHelmet",
  "camera_name": "Entrance Gate",
  "aibox_id": "uuid-aibox-smg",
  "aibox_name": "Site Semarang",
  "alarm_time": "2024-01-28T10:30:00Z",
  "image_url": "http://103.75.84.183:2323/...",
  "minio_image_path": "alarm-images/2024/01/28/..."
}
```

### Filter Alarm by AI Box

```http
GET /alarms?aibox_id=uuid-aibox-smg&limit=100

# Response includes aibox info
{
  "items": [
    {
      "id": "...",
      "alarm_type": "NoHelmet",
      "aibox_name": "Site Semarang",
      ...
    }
  ]
}
```

### Health Monitoring

```http
GET /ai-boxes/health

{
  "total": 3,
  "online": 2,
  "offline": 1,
  "boxes": [
    {"id": "...", "name": "Site Semarang", "status": "online", "latency_ms": 45},
    {"id": "...", "name": "Site Pekalongan", "status": "online", "latency_ms": 120},
    {"id": "...", "name": "Site Cilacap", "status": "offline", "last_error": "Connection refused"}
  ]
}
```