"""
Audit Logs Router
View-only access to audit logs with advanced filtering and export capabilities
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_, func
import csv
import json
import io

from app.database import get_db
from app.models import User, AuditLog
from app.auth import get_current_user, require_permission
from app.schemas import AuditLogResponse, AuditLogStats

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("/", response_model=List[AuditLogResponse])
def list_audit_logs(
    # Pagination
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),

    # Filters
    user_id: Optional[UUID] = None,
    username: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[UUID] = None,
    status: Optional[str] = None,  # "success" | "failed" | "partial"
    ip_address: Optional[str] = None,

    # Date range
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,

    # Search
    search: Optional[str] = None,  # Search in resource_name, changes_summary, error_message

    # Dependencies
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit-logs", "read"))
):
    """
    List audit logs with flexible filtering and pagination.

    Query Parameters:
    - skip, limit: Pagination (default: 0, 50)
    - user_id: Filter by specific user
    - username: Filter by username (partial match)
    - action: Filter by action type (e.g., "user.created")
    - resource_type: Filter by resource type (e.g., "user", "alarm")
    - resource_id: Filter by specific resource
    - status: Filter by status ("success", "failed", "partial")
    - ip_address: Filter by IP address
    - start_date, end_date: Date range filter
    - search: Full-text search across resource_name, changes_summary, error_message

    Returns:
        List of audit log entries, ordered by timestamp (newest first)
    """
    query = db.query(AuditLog)

    # Apply filters
    filters = []

    if user_id:
        filters.append(AuditLog.user_id == user_id)

    if username:
        filters.append(AuditLog.username.ilike(f"%{username}%"))

    if action:
        filters.append(AuditLog.action == action)

    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)

    if resource_id:
        filters.append(AuditLog.resource_id == resource_id)

    if status:
        filters.append(AuditLog.status == status)

    if ip_address:
        filters.append(AuditLog.ip_address == ip_address)

    if start_date:
        filters.append(AuditLog.timestamp >= start_date)

    if end_date:
        filters.append(AuditLog.timestamp <= end_date)

    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            AuditLog.resource_name.ilike(search_pattern),
            AuditLog.changes_summary.ilike(search_pattern),
            AuditLog.error_message.ilike(search_pattern)
        ))

    if filters:
        query = query.filter(and_(*filters))

    # Order by timestamp descending (newest first)
    query = query.order_by(desc(AuditLog.timestamp))

    # Pagination
    total = query.count()
    logs = query.offset(skip).limit(limit).all()

    return logs


@router.get("/stats", response_model=AuditLogStats)
def get_audit_log_stats(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit-logs", "read"))
):
    """
    Get audit log statistics for dashboard.

    Query Parameters:
    - start_date, end_date: Date range (defaults to last 7 days)

    Returns:
        Statistics including total events, failed logins, by action type, by resource type, etc.
    """
    # Default to last 7 days
    if not start_date:
        start_date = datetime.utcnow() - timedelta(days=7)
    if not end_date:
        end_date = datetime.utcnow()

    query = db.query(AuditLog).filter(
        AuditLog.timestamp >= start_date,
        AuditLog.timestamp <= end_date
    )

    # Total events
    total_events = query.count()

    # Success vs Failed
    success_count = query.filter(AuditLog.status == "success").count()
    failed_count = query.filter(AuditLog.status == "failed").count()

    # Failed login attempts
    failed_logins = query.filter(AuditLog.action == "user.login_failed").count()

    # By action type
    by_action = db.query(
        AuditLog.action,
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.timestamp >= start_date,
        AuditLog.timestamp <= end_date
    ).group_by(AuditLog.action).order_by(desc('count')).limit(10).all()

    # By resource type
    by_resource = db.query(
        AuditLog.resource_type,
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.timestamp >= start_date,
        AuditLog.timestamp <= end_date
    ).group_by(AuditLog.resource_type).order_by(desc('count')).limit(10).all()

    # Top users by activity
    top_users = db.query(
        AuditLog.username,
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.timestamp >= start_date,
        AuditLog.timestamp <= end_date
    ).group_by(AuditLog.username).order_by(desc('count')).limit(10).all()

    # Events per day (for timeline chart)
    events_per_day = db.query(
        func.date(AuditLog.timestamp).label('date'),
        func.count(AuditLog.id).label('count')
    ).filter(
        AuditLog.timestamp >= start_date,
        AuditLog.timestamp <= end_date
    ).group_by(func.date(AuditLog.timestamp)).order_by('date').all()

    return {
        "total_events": total_events,
        "success_count": success_count,
        "failed_count": failed_count,
        "failed_logins": failed_logins,
        "by_action": [{"action": a, "count": c} for a, c in by_action],
        "by_resource": [{"resource_type": r, "count": c} for r, c in by_resource],
        "top_users": [{"username": u, "count": c} for u, c in top_users],
        "events_per_day": [{"date": str(d), "count": c} for d, c in events_per_day],
        "date_range": {"start": start_date, "end": end_date}
    }


@router.get("/{log_id}", response_model=AuditLogResponse)
def get_audit_log(
    log_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit-logs", "read"))
):
    """
    Get detailed information for a single audit log entry.
    """
    log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Audit log not found")

    return log


@router.get("/export/csv")
def export_audit_logs_csv(
    # Same filters as list endpoint
    user_id: Optional[UUID] = None,
    username: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    search: Optional[str] = None,

    # Export specific
    limit: int = Query(default=10000, le=50000),  # Max 50k records

    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit-logs", "export"))
):
    """
    Export audit logs to CSV format.

    Max 50,000 records per export.
    """
    # Build query with same filters as list endpoint
    query = db.query(AuditLog)

    filters = []
    if user_id:
        filters.append(AuditLog.user_id == user_id)
    if username:
        filters.append(AuditLog.username.ilike(f"%{username}%"))
    if action:
        filters.append(AuditLog.action == action)
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)
    if status:
        filters.append(AuditLog.status == status)
    if start_date:
        filters.append(AuditLog.timestamp >= start_date)
    if end_date:
        filters.append(AuditLog.timestamp <= end_date)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            AuditLog.resource_name.ilike(search_pattern),
            AuditLog.changes_summary.ilike(search_pattern),
            AuditLog.error_message.ilike(search_pattern)
        ))

    if filters:
        query = query.filter(and_(*filters))

    query = query.order_by(desc(AuditLog.timestamp)).limit(limit)

    logs = query.all()

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'Timestamp', 'Username', 'Email', 'Action', 'Resource Type', 'Resource Name',
        'IP Address', 'Status', 'Changes Summary', 'Error Message', 'Endpoint', 'Method'
    ])

    # Data rows
    for log in logs:
        writer.writerow([
            log.timestamp.isoformat(),
            log.username,
            log.user_email,
            log.action,
            log.resource_type,
            log.resource_name or '',
            log.ip_address or '',
            log.status,
            log.changes_summary or '',
            log.error_message or '',
            log.endpoint or '',
            log.method or ''
        ])

    output.seek(0)

    filename = f"audit_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/json")
def export_audit_logs_json(
    # Same filters as list endpoint
    user_id: Optional[UUID] = None,
    username: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    search: Optional[str] = None,

    limit: int = Query(default=10000, le=50000),

    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit-logs", "export"))
):
    """
    Export audit logs to JSON format.

    Max 50,000 records per export.
    """
    # Build query (same as CSV)
    query = db.query(AuditLog)

    filters = []
    if user_id:
        filters.append(AuditLog.user_id == user_id)
    if username:
        filters.append(AuditLog.username.ilike(f"%{username}%"))
    if action:
        filters.append(AuditLog.action == action)
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)
    if status:
        filters.append(AuditLog.status == status)
    if start_date:
        filters.append(AuditLog.timestamp >= start_date)
    if end_date:
        filters.append(AuditLog.timestamp <= end_date)
    if search:
        search_pattern = f"%{search}%"
        filters.append(or_(
            AuditLog.resource_name.ilike(search_pattern),
            AuditLog.changes_summary.ilike(search_pattern),
            AuditLog.error_message.ilike(search_pattern)
        ))

    if filters:
        query = query.filter(and_(*filters))

    query = query.order_by(desc(AuditLog.timestamp)).limit(limit)

    logs = query.all()

    # Generate JSON
    export_data = []
    for log in logs:
        export_data.append({
            "timestamp": log.timestamp.isoformat(),
            "user_id": str(log.user_id) if log.user_id else None,
            "username": log.username,
            "user_email": log.user_email,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id) if log.resource_id else None,
            "resource_name": log.resource_name,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "endpoint": log.endpoint,
            "method": log.method,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "changes_summary": log.changes_summary,
            "status": log.status,
            "error_message": log.error_message,
            "extra_metadata": log.extra_metadata
        })

    filename = f"audit_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

    return StreamingResponse(
        iter([json.dumps(export_data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
