from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import init_db, SessionLocal
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, users, roles, video_sources, ai_tasks
from app.routers import alarms, locations, recordings, camera_status, analytics
from app.routers import local_videos, storage, ai_boxes, webrtc_proxy, alarm_types
from app.services.bmapp import start_alarm_listener, stop_alarm_listener
from app.services.camera_status import start_camera_status_poller, stop_camera_status_poller
from app.services.analytics_sync import start_analytics_sync, stop_analytics_sync
from app.services.minio_storage import initialize_minio
from app.services.media_sync import start_media_sync, stop_media_sync
from app.services.auto_recorder import start_auto_recorder, stop_auto_recorder
from app.services.mediamtx import add_stream_path
from app.services.gps_history import start_gps_history_recorder, stop_gps_history_recorder
from app.routers.alarms import save_alarm_from_bmapp
from app.models import VideoSource
from app.config import settings
import asyncio


async def on_alarm_received(alarm_data: dict):
    """Callback when alarm is received from BM-APP"""
    db = SessionLocal()
    try:
        await save_alarm_from_bmapp(alarm_data, db)
    except Exception as e:
        print(f"[Main] Failed to save alarm to database: {e}")
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

    # Start alarm listener (WebSocket to BM-APP)
    if settings.alarm_listener_enabled:
        await start_alarm_listener(on_alarm_received)
        print("[Startup] Alarm listener started")
    else:
        print("[Startup] Alarm listener DISABLED")

    # Sync MediaMTX after a short delay to ensure MediaMTX is ready
    asyncio.create_task(delayed_mediamtx_sync())

    # Start camera status polling (real-time online/offline detection)
    if settings.camera_status_enabled:
        await start_camera_status_poller()
        print("[Startup] Camera status poller started")
    else:
        print("[Startup] Camera status poller DISABLED")

    # Start auto-sync for BM-APP analytics data
    if settings.analytics_sync_enabled:
        await start_analytics_sync()
        print("[Startup] Analytics sync started")
    else:
        print("[Startup] Analytics sync DISABLED")

    # Initialize MinIO storage and start media sync
    if settings.minio_enabled:
        initialize_minio()
        await start_media_sync()
        print("[Startup] MinIO and media sync started")

        # Start auto-recorder for AI camera streams
        if settings.auto_recorder_enabled:
            await start_auto_recorder()
            print("[Startup] Auto-recorder started")
        else:
            print("[Startup] Auto-recorder DISABLED")
    else:
        print("[Startup] MinIO DISABLED (media sync and auto-recorder skipped)")

    # Start GPS history recorder (for tracking device positions over time)
    if settings.gps_history_enabled:
        await start_gps_history_recorder()
        print(f"[Startup] GPS history recorder started (interval={settings.gps_history_interval}s)")
    else:
        print("[Startup] GPS history recorder DISABLED")

    yield

    # Shutdown
    if settings.alarm_listener_enabled:
        stop_alarm_listener()
    if settings.camera_status_enabled:
        stop_camera_status_poller()
    if settings.analytics_sync_enabled:
        stop_analytics_sync()
    if settings.minio_enabled:
        stop_media_sync()
        if settings.auto_recorder_enabled:
            stop_auto_recorder()
    if settings.gps_history_enabled:
        stop_gps_history_recorder()


async def delayed_mediamtx_sync():
    """Delay MediaMTX sync to ensure the server is ready"""
    await asyncio.sleep(3)
    await sync_mediamtx_on_startup()


app = FastAPI(
    title="HSSE Object Detection Monitoring",
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
app.include_router(local_videos.router)
app.include_router(storage.router)
app.include_router(ai_boxes.router)
app.include_router(webrtc_proxy.router)
app.include_router(alarm_types.router)

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
