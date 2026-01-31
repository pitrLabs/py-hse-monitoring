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

User levels range from 1-10:

- **1-3**: Basic users
- **4-6**: Advanced users
- **7-9**: Managers/Supervisors
- **10**: Administrators

Superusers bypass all permission checks.

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