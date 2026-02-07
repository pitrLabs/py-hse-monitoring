# HSE Monitoring System - User Management

Complete user management system with authentication, user levels, and role-based access control (RBAC).

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