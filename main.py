from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db, SessionLocal
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, users, roles, video_sources, ai_tasks
from app.routers import alarms, locations, recordings, camera_status, analytics
from app.services.bmapp import start_alarm_listener, stop_alarm_listener
from app.services.camera_status import start_camera_status_poller, stop_camera_status_poller
from app.services.analytics_sync import start_analytics_sync, stop_analytics_sync
from app.services.mediamtx import add_stream_path
from app.routers.alarms import save_alarm_from_bmapp
from app.models import VideoSource
import asyncio


async def on_alarm_received(alarm_data: dict):
    """Callback when alarm is received from BM-APP"""
    db = SessionLocal()
    try:
        await save_alarm_from_bmapp(alarm_data, db)
    finally:
        db.close()


async def sync_mediamtx_on_startup():
    """Sync all active video sources to MediaMTX on startup"""
    db = SessionLocal()
    try:
        sources = db.query(VideoSource).filter(VideoSource.is_active == True).all()
        if sources:
            print(f"[Startup] Syncing {len(sources)} video sources to MediaMTX...")
            for source in sources:
                success = await add_stream_path(source.stream_name, source.url)
                if success:
                    print(f"[Startup] Added stream: {source.stream_name}")
                else:
                    print(f"[Startup] Failed to add stream: {source.stream_name}")
            print(f"[Startup] MediaMTX sync complete")
    except Exception as e:
        print(f"[Startup] MediaMTX sync error: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    await start_alarm_listener(on_alarm_received)
    # Sync MediaMTX after a short delay to ensure MediaMTX is ready
    asyncio.create_task(delayed_mediamtx_sync())
    # Start camera status polling (real-time online/offline detection)
    await start_camera_status_poller()
    # Start auto-sync for BM-APP analytics data (people count, zone occupancy, etc.)
    await start_analytics_sync()
    yield
    # Shutdown
    stop_alarm_listener()
    stop_camera_status_poller()
    stop_analytics_sync()


async def delayed_mediamtx_sync():
    """Delay MediaMTX sync to ensure the server is ready"""
    await asyncio.sleep(3)
    await sync_mediamtx_on_startup()


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
app.include_router(locations.router)
app.include_router(recordings.router)
app.include_router(camera_status.router)
app.include_router(analytics.router)

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
