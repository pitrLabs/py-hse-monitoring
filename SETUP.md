# Setup Guide

## Prerequisites

- Python 3.13 or higher
- PostgreSQL 12 or higher
- uv package manager (or pip)

## PostgreSQL Setup

### 1. Install PostgreSQL

Download and install PostgreSQL from https://www.postgresql.org/download/

### 2. Create Database

Open PostgreSQL command line (psql) or pgAdmin and create a database:

```sql
CREATE DATABASE hse_monitoring;
```

### 3. Create User (Optional)

If you want to create a dedicated user:

```sql
CREATE USER hse_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE hse_monitoring TO hse_user;
```

## Application Setup

### 1. Clone/Download Project

```bash
cd py-hse-monitoring
```

### 2. Install Dependencies

Using uv:
```bash
uv sync
```

Or using pip:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy the example environment file:
```bash
cp .env.example .env
```

Edit `.env` and configure your database connection:
```env
DATABASE_URL=postgresql://username:password@localhost:5432/hse_monitoring
SECRET_KEY=generate-a-secure-random-key-here
```

To generate a secure SECRET_KEY, you can use:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Initialize Database

Run the initialization script to create tables and seed default data:

```bash
python init_db.py
```

This will:
- Create all database tables
- Create default permissions (users, roles, monitoring)
- Create default roles (admin, manager, viewer)
- Create admin user (username: admin, password: admin123)

**Important**: Change the admin password immediately after first login!

### 5. Run the Application

```bash
python main.py
```

The API will be available at:
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## First Steps

### 1. Login as Admin

Use the Swagger UI at http://localhost:8000/docs

1. Go to `/auth/login` endpoint
2. Click "Try it out"
3. Enter credentials:
   - username: `admin`
   - password: `admin123`
4. Copy the `access_token` from the response

### 2. Authorize Requests

1. Click the "Authorize" button at the top of Swagger UI
2. Enter: `Bearer YOUR_ACCESS_TOKEN`
3. Click "Authorize"

Now you can test all authenticated endpoints!

### 3. Change Admin Password

1. Go to `/auth/me` endpoint (PUT method)
2. Update with new password:
```json
{
  "password": "your_new_secure_password"
}
```

## Database Migration (Production)

For production, it's recommended to use a migration tool like Alembic:

```bash
# Install alembic
uv add alembic

# Initialize alembic
alembic init alembic

# Create migration
alembic revision --autogenerate -m "Initial migration"

# Apply migration
alembic upgrade head
```

## Docker Setup (Optional)

If you prefer using Docker:

```bash
# Start PostgreSQL with Docker
docker run -d \
  --name hse-postgres \
  -e POSTGRES_DB=hse_monitoring \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  postgres:15
```

Then update your `.env`:
```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/hse_monitoring
```

## Troubleshooting

### Cannot connect to PostgreSQL

1. Check if PostgreSQL is running:
   ```bash
   # Windows
   Get-Service postgresql*
   
   # Linux/Mac
   sudo systemctl status postgresql
   ```

2. Verify database exists:
   ```bash
   psql -U postgres -l
   ```

3. Check connection string in `.env` file

### Import errors

Make sure you're in the correct directory and virtual environment is activated:
```bash
# Activate venv if using standard venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Or use uv run
uv run python main.py
```

### Permission denied errors

Make sure the database user has proper permissions:
```sql
GRANT ALL PRIVILEGES ON DATABASE hse_monitoring TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
```

## Testing

To test the API:

```bash
# Register a new user
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "testpass123",
    "user_level": 3,
    "role_ids": [3]
  }'

# Login
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=testuser&password=testpass123"
```

## Production Deployment

For production deployment:

1. Use a strong SECRET_KEY
2. Set DEBUG=False
3. Use HTTPS
4. Configure proper CORS settings
5. Set up database backups
6. Use environment variables for all sensitive data
7. Consider using a reverse proxy (nginx)
8. Enable rate limiting
9. Set up monitoring and logging
10. Use a production WSGI server (gunicorn)

Example production start:
```bash
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```
