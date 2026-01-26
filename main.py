from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db, SessionLocal
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, users, roles, video_sources, ai_tasks
from app.routers import alarms
from app.services.bmapp import start_alarm_listener, stop_alarm_listener
from app.routers.alarms import save_alarm_from_bmapp


async def on_alarm_received(alarm_data: dict):
    """Callback when alarm is received from BM-APP"""
    db = SessionLocal()
    try:
        await save_alarm_from_bmapp(alarm_data, db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    await start_alarm_listener(on_alarm_received)
    yield
    # Shutdown
    stop_alarm_listener()


app = FastAPI(
    title="HSE Object Detection Monitoring",
    description="User Management with Authentication, Roles, and Permissions",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(CORSMiddleware,
                   allow_credentials=True,
                   allow_origins=["*"],
                   allow_methods=["*"],
                   allow_headers=["*"])

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(video_sources.router)
app.include_router(alarms.router)
app.include_router(ai_tasks.router)

@app.get("/")
def root():
    return {
        "message": "HSE Monitoring API",
        "version": "1.0.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
