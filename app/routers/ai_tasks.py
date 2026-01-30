"""
AI Tasks Router
Manages AI detection tasks in the database and syncs with BM-APP
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from app import schemas
from app.auth import get_current_user, get_current_superuser
from app.database import get_db
from app.models import AITask, VideoSource, User
from app.config import settings
from app.services.bmapp_client import get_bmapp_client

router = APIRouter(prefix="/ai-tasks", tags=["AI Tasks"])


# Background task to sync AI task to BM-APP
async def sync_task_to_bmapp(
    db: Session,
    task_id: UUID,
    task_name: str,
    media_name: str,
    algorithms: List[int],
    description: str = "",
    action: str = "create"
):
    """Sync an AI task to BM-APP and update database sync status"""
    if not settings.bmapp_enabled:
        return

    try:
        client = get_bmapp_client()

        if action == "create":
            await client.create_task(
                task_session=task_name,
                media_name=media_name,
                alg_info=[1],  # Person detection category
                method_config=algorithms,
                task_desc=description
            )
        elif action == "delete":
            await client.delete_task(task_name)
        elif action == "start":
            await client.control_task(task_name, "start")
        elif action == "stop":
            await client.control_task(task_name, "stop")

        # Update sync status in database
        task = db.query(AITask).filter(AITask.id == task_id).first()
        if task:
            task.is_synced_bmapp = True
            task.bmapp_sync_error = None
            if action == "start":
                task.status = "running"
                task.started_at = datetime.utcnow()
            elif action == "stop":
                task.status = "stopped"
                task.stopped_at = datetime.utcnow()
            db.commit()

    except Exception as e:
        # Update sync error in database
        task = db.query(AITask).filter(AITask.id == task_id).first()
        if task:
            task.is_synced_bmapp = False
            task.bmapp_sync_error = str(e)[:500]
            if action in ["start", "create"]:
                task.status = "failed"
            db.commit()
        print(f"Failed to sync task to BM-APP: {e}")


@router.get("/", response_model=List[schemas.AITaskResponse])
def list_ai_tasks(
    skip: int = 0,
    limit: int = 100,
    video_source_id: Optional[UUID] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all AI tasks from database. Available for all authenticated users."""
    query = db.query(AITask)

    if video_source_id:
        query = query.filter(AITask.video_source_id == video_source_id)

    if status:
        query = query.filter(AITask.status == status)

    tasks = query.order_by(AITask.created_at.desc()).offset(skip).limit(limit).all()
    return tasks


@router.get("/bmapp", status_code=status.HTTP_200_OK)
async def list_bmapp_tasks(
    current_user: User = Depends(get_current_user)
):
    """Get all AI tasks directly from BM-APP (for comparison/debugging)."""
    if not settings.bmapp_enabled:
        return {"tasks": [], "bmapp_disabled": True}

    try:
        client = get_bmapp_client()
        tasks = await client.get_task_list()
        return {"tasks": tasks}
    except Exception as e:
        print(f"Failed to get AI tasks from BM-APP: {e}")
        return {"tasks": [], "error": str(e)}


@router.get("/{task_id}", response_model=schemas.AITaskResponse)
def get_ai_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific AI task by ID."""
    task = db.query(AITask).filter(AITask.id == task_id).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI task not found"
        )

    return task


@router.post("/", response_model=schemas.AITaskResponse, status_code=status.HTTP_201_CREATED)
async def create_ai_task(
    task_data: schemas.AITaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Create a new AI task. Only for superusers (admins).

    This will:
    1. Validate that the video source exists
    2. Create the task in the database
    3. Sync the task to BM-APP in the background
    4. Optionally start the task automatically
    """
    # Validate video source exists
    video_source = db.query(VideoSource).filter(VideoSource.id == task_data.video_source_id).first()
    if not video_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video source not found"
        )

    # Generate task name if not provided
    task_name = task_data.task_name
    if not task_name:
        task_name = f"task_{video_source.stream_name}"

    # Check if task name already exists
    existing = db.query(AITask).filter(AITask.task_name == task_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task name already exists"
        )

    # Create the task in database
    db_task = AITask(
        task_name=task_name,
        video_source_id=task_data.video_source_id,
        algorithms=task_data.algorithms,
        description=task_data.description,
        status="pending",
        created_by_id=current_user.id
    )

    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    # Sync to BM-APP in background
    if settings.bmapp_enabled:
        # Create a new session for background task
        from app.database import SessionLocal
        bg_session = SessionLocal()

        async def sync_and_start():
            try:
                await sync_task_to_bmapp(
                    db=bg_session,
                    task_id=db_task.id,
                    task_name=task_name,
                    media_name=video_source.stream_name,
                    algorithms=task_data.algorithms,
                    description=task_data.description or "",
                    action="create"
                )

                # Auto-start if requested
                if task_data.auto_start:
                    await sync_task_to_bmapp(
                        db=bg_session,
                        task_id=db_task.id,
                        task_name=task_name,
                        media_name=video_source.stream_name,
                        algorithms=task_data.algorithms,
                        description=task_data.description or "",
                        action="start"
                    )
            finally:
                bg_session.close()

        background_tasks.add_task(sync_and_start)

    return db_task


@router.put("/{task_id}", response_model=schemas.AITaskResponse)
async def update_ai_task(
    task_id: UUID,
    task_update: schemas.AITaskUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Update an AI task. Only for superusers (admins)."""
    task = db.query(AITask).filter(AITask.id == task_id).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI task not found"
        )

    # Update fields
    if task_update.algorithms is not None:
        task.algorithms = task_update.algorithms

    if task_update.description is not None:
        task.description = task_update.description

    if task_update.status is not None:
        task.status = task_update.status

    db.commit()
    db.refresh(task)

    # Re-sync to BM-APP if algorithms changed
    if task_update.algorithms is not None and settings.bmapp_enabled:
        video_source = db.query(VideoSource).filter(VideoSource.id == task.video_source_id).first()
        if video_source:
            from app.database import SessionLocal
            bg_session = SessionLocal()

            async def resync():
                try:
                    await sync_task_to_bmapp(
                        db=bg_session,
                        task_id=task.id,
                        task_name=task.task_name,
                        media_name=video_source.stream_name,
                        algorithms=task_update.algorithms,
                        description=task.description or "",
                        action="create"  # Create with Restart=True updates the task
                    )
                finally:
                    bg_session.close()

            background_tasks.add_task(resync)

    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_task(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Delete an AI task. Only for superusers (admins)."""
    task = db.query(AITask).filter(AITask.id == task_id).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI task not found"
        )

    task_name = task.task_name

    db.delete(task)
    db.commit()

    # Delete from BM-APP in background
    if settings.bmapp_enabled:
        async def delete_from_bmapp():
            try:
                client = get_bmapp_client()
                await client.delete_task(task_name)
            except Exception as e:
                print(f"Failed to delete task from BM-APP: {e}")

        background_tasks.add_task(delete_from_bmapp)

    return None


@router.post("/{task_id}/control", response_model=schemas.AITaskResponse)
async def control_ai_task(
    task_id: UUID,
    control: schemas.AITaskControl,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Start, stop, or restart an AI task. Only for superusers (admins)."""
    task = db.query(AITask).filter(AITask.id == task_id).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AI task not found"
        )

    video_source = db.query(VideoSource).filter(VideoSource.id == task.video_source_id).first()
    if not video_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated video source not found"
        )

    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    action = control.action

    # Handle restart as stop + start
    if action == "restart":
        from app.database import SessionLocal
        bg_session = SessionLocal()

        async def restart_task():
            try:
                await sync_task_to_bmapp(
                    db=bg_session,
                    task_id=task.id,
                    task_name=task.task_name,
                    media_name=video_source.stream_name,
                    algorithms=task.algorithms or [195, 5],
                    description=task.description or "",
                    action="stop"
                )
                await sync_task_to_bmapp(
                    db=bg_session,
                    task_id=task.id,
                    task_name=task.task_name,
                    media_name=video_source.stream_name,
                    algorithms=task.algorithms or [195, 5],
                    description=task.description or "",
                    action="start"
                )
            finally:
                bg_session.close()

        background_tasks.add_task(restart_task)
    else:
        from app.database import SessionLocal
        bg_session = SessionLocal()

        async def control_task():
            try:
                await sync_task_to_bmapp(
                    db=bg_session,
                    task_id=task.id,
                    task_name=task.task_name,
                    media_name=video_source.stream_name,
                    algorithms=task.algorithms or [195, 5],
                    description=task.description or "",
                    action=action
                )
            finally:
                bg_session.close()

        background_tasks.add_task(control_task)

    # Update status immediately (will be confirmed by background task)
    if action == "start" or action == "restart":
        task.status = "pending"  # Will be updated to "running" after sync
    elif action == "stop":
        task.status = "stopped"
        task.stopped_at = datetime.utcnow()

    db.commit()
    db.refresh(task)

    return task


@router.post("/sync-bmapp", status_code=status.HTTP_200_OK)
async def sync_all_to_bmapp(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Sync all AI tasks to BM-APP. Only for superusers (admins)."""
    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    tasks = db.query(AITask).all()
    synced_count = 0

    for task in tasks:
        video_source = db.query(VideoSource).filter(VideoSource.id == task.video_source_id).first()
        if video_source:
            from app.database import SessionLocal
            bg_session = SessionLocal()

            async def sync_task(t=task, vs=video_source, sess=bg_session):
                try:
                    await sync_task_to_bmapp(
                        db=sess,
                        task_id=t.id,
                        task_name=t.task_name,
                        media_name=vs.stream_name,
                        algorithms=t.algorithms or [195, 5],
                        description=t.description or "",
                        action="create"
                    )
                finally:
                    sess.close()

            background_tasks.add_task(sync_task)
            synced_count += 1

    return {"message": f"Syncing {synced_count} AI tasks to BM-APP"}


@router.get("/abilities/list")
async def get_ai_abilities(
    current_user: User = Depends(get_current_user)
):
    """Get all available AI detection algorithms from BM-APP."""
    if not settings.bmapp_enabled:
        return {"abilities": []}

    try:
        client = get_bmapp_client()
        abilities = await client.get_abilities()

        # Simplify the response for frontend
        simplified = []
        for ability in abilities:
            simplified.append({
                "id": ability.get("item"),
                "code": ability.get("code"),
                "name": ability.get("name"),
                "description": ability.get("desc", ability.get("detail", "")),
                "parameters": ability.get("parameters", [])
            })

        return {"abilities": simplified}
    except Exception as e:
        print(f"Failed to get abilities: {e}")
        return {"abilities": []}


@router.get("/media/list")
async def get_bmapp_media(
    current_user: User = Depends(get_current_user)
):
    """Get all media/cameras from BM-APP with their status."""
    if not settings.bmapp_enabled:
        return {"media": []}

    try:
        client = get_bmapp_client()
        media_list = await client.get_media_list()

        # Simplify the response
        simplified = []
        for media in media_list:
            status_info = media.get("MediaStatus", {})
            simplified.append({
                "name": media.get("MediaName"),
                "url": media.get("MediaUrl"),
                "description": media.get("MediaDesc", ""),
                "status": status_info.get("label", "Unknown"),
                "status_type": status_info.get("type", 0),
                "status_style": status_info.get("style", ""),
                "resolution": status_info.get("size", {})
            })

        return {"media": simplified}
    except Exception as e:
        print(f"Failed to get media: {e}")
        return {"media": []}


@router.get("/streams/list")
async def get_available_streams(
    current_user: User = Depends(get_current_user)
):
    """Get all available WebRTC streams from ZLMediaKit."""
    if not settings.bmapp_enabled:
        return {"streams": []}

    try:
        client = get_bmapp_client()
        streams = await client.get_zlmediakit_streams()

        simplified = []
        for stream in streams:
            simplified.append({
                "app": stream.get("app"),
                "stream": stream.get("stream"),
                "schema": stream.get("schema"),
                "vhost": stream.get("vhost", "__defaultVhost__"),
                "tracks": stream.get("tracks", []),
                "readers": stream.get("readerCount", 0)
            })

        return {"streams": simplified}
    except Exception as e:
        print(f"Failed to get streams: {e}")
        return {"streams": []}


@router.get("/preview/channels")
async def get_preview_channels(
    current_user: User = Depends(get_current_user)
):
    """Get preview channels from BM-APP for video streaming."""
    if not settings.bmapp_enabled:
        return {"channels": {}}

    try:
        client = get_bmapp_client()
        channels = await client.get_preview_channels()
        return {"channels": channels}
    except Exception as e:
        print(f"Failed to get preview channels: {e}")
        return {"channels": {}, "error": str(e)}


@router.post("/import-from-bmapp", status_code=status.HTTP_200_OK)
async def import_tasks_from_bmapp(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
):
    """Import all AI tasks from BM-APP into our database.

    This will:
    1. Fetch all tasks from BM-APP
    2. Match tasks with existing video sources by MediaName
    3. Create AITask entries in database (skip if task_name exists)

    Prerequisites: Video sources should be imported first via /video-sources/import-from-bmapp

    Only for superusers (admins).
    """
    if not settings.bmapp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="BM-APP integration is disabled"
        )

    try:
        client = get_bmapp_client()
        task_list = await client.get_task_list()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch tasks from BM-APP: {str(e)}"
        )

    imported = 0
    skipped = 0
    errors = []

    for task in task_list:
        task_name = task.get("AlgTaskSession", "")
        media_name = task.get("MediaName", "")
        task_desc = task.get("TaskDesc", "")
        user_data = task.get("UserData", {})
        method_config = user_data.get("MethodConfig", [])
        task_status_info = task.get("AlgTaskStatus", {})

        if not task_name:
            errors.append(f"Invalid task entry (no name): {task}")
            continue

        # Check if task already exists
        existing_task = db.query(AITask).filter(AITask.task_name == task_name).first()
        if existing_task:
            skipped += 1
            continue

        # Find matching video source by stream_name (MediaName)
        video_source = db.query(VideoSource).filter(VideoSource.stream_name == media_name).first()
        if not video_source:
            errors.append(f"Task '{task_name}' - no matching video source for media '{media_name}'")
            continue

        # Determine status from BM-APP status
        status_type = task_status_info.get("type", 0)
        if status_type == 2:
            db_status = "running"
        elif status_type == 1:
            db_status = "pending"
        else:
            db_status = "stopped"

        # Create new AI task
        try:
            db_task = AITask(
                task_name=task_name,
                video_source_id=video_source.id,
                algorithms=method_config if method_config else None,
                description=task_desc,
                status=db_status,
                is_synced_bmapp=True,
                created_by_id=current_user.id
            )
            db.add(db_task)
            db.commit()
            db.refresh(db_task)

            imported += 1
        except Exception as e:
            db.rollback()
            errors.append(f"Failed to import task '{task_name}': {str(e)}")

    return {
        "message": f"Import completed",
        "imported": imported,
        "skipped": skipped,
        "total_from_bmapp": len(task_list),
        "errors": errors if errors else None
    }
