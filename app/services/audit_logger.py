"""
Audit Logger Service
Utility functions for logging all significant system actions to audit_logs table
"""
from typing import Optional, Dict, Any
from uuid import UUID
from fastapi import Request
from sqlalchemy.orm import Session
from app.models import User, AuditLog


def log_audit(
    db: Session,
    user: Optional[User],
    action: str,
    resource_type: str,
    resource_id: Optional[UUID] = None,
    resource_name: Optional[str] = None,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    changes_summary: Optional[str] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None
) -> AuditLog:
    """
    Create an audit log entry.

    Args:
        db: Database session
        user: User who performed the action (None for system actions)
        action: Action identifier (e.g., "user.created", "alarm.deleted")
        resource_type: Type of resource affected
        resource_id: ID of affected resource
        resource_name: Human-readable name of resource
        old_values: State before change (for updates)
        new_values: State after change (for creates/updates)
        changes_summary: Human-readable summary of changes
        status: "success" | "failed" | "partial"
        error_message: Error details if failed
        extra_metadata: Additional context data
        request: FastAPI Request object (for IP, user-agent, endpoint)

    Returns:
        Created AuditLog instance

    Example:
        log_audit(
            db=db,
            user=current_user,
            action="user.updated",
            resource_type="user",
            resource_id=user.id,
            resource_name=user.username,
            old_values={"email": "old@example.com"},
            new_values={"email": "new@example.com"},
            request=request
        )
    """
    # Extract request metadata
    ip_address = None
    user_agent = None
    endpoint = None
    method = None

    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        endpoint = str(request.url.path)
        method = request.method

    # Auto-generate changes_summary if not provided
    if changes_summary is None and old_values and new_values:
        changed_fields = []
        for key in new_values.keys():
            if key in old_values and old_values[key] != new_values[key]:
                changed_fields.append(key)
        if changed_fields:
            changes_summary = f"Updated: {', '.join(changed_fields)}"

    # Sanitize sensitive data
    if old_values:
        old_values = sanitize_values(old_values)
    if new_values:
        new_values = sanitize_values(new_values)

    # Create audit log
    audit = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else "system",
        user_email=user.email if user else "system",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        ip_address=ip_address,
        user_agent=user_agent,
        endpoint=endpoint,
        method=method,
        old_values=old_values,
        new_values=new_values,
        changes_summary=changes_summary,
        status=status,
        error_message=error_message,
        extra_metadata=extra_metadata
    )

    db.add(audit)
    db.commit()
    db.refresh(audit)

    return audit


def compute_diff(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Compute differences between old and new values.

    Args:
        old: Old state dictionary
        new: New state dictionary

    Returns:
        Dictionary with format: {"field_name": {"old": old_value, "new": new_value}}

    Example:
        >>> old = {"name": "John", "age": 25, "city": "NYC"}
        >>> new = {"name": "John", "age": 26, "city": "LA"}
        >>> compute_diff(old, new)
        {"age": {"old": 25, "new": 26}, "city": {"old": "NYC", "new": "LA"}}
    """
    diff = {}
    all_keys = set(old.keys()) | set(new.keys())

    for key in all_keys:
        old_val = old.get(key)
        new_val = new.get(key)

        if old_val != new_val:
            diff[key] = {"old": old_val, "new": new_val}

    return diff


def sanitize_values(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove sensitive fields before logging to audit log.

    Args:
        data: Dictionary to sanitize

    Returns:
        Sanitized dictionary with sensitive fields redacted
    """
    sensitive_keys = [
        'password',
        'hashed_password',
        'token',
        'access_token',
        'refresh_token',
        'secret_key',
        'api_key',
        'private_key',
        'session_id',
        'active_session_id'
    ]

    return {
        k: '***REDACTED***' if k in sensitive_keys else v
        for k, v in data.items()
    }


def format_changes_summary(diff: Dict[str, Dict[str, Any]], max_fields: int = 5) -> str:
    """
    Format diff dictionary into human-readable summary.

    Args:
        diff: Difference dictionary from compute_diff()
        max_fields: Maximum number of fields to include in summary

    Returns:
        Human-readable summary string

    Example:
        >>> diff = {"age": {"old": 25, "new": 26}, "city": {"old": "NYC", "new": "LA"}}
        >>> format_changes_summary(diff)
        "Changed age (25 → 26), city (NYC → LA)"
    """
    if not diff:
        return "No changes"

    fields = list(diff.keys())

    if len(fields) <= max_fields:
        changes = []
        for field, values in diff.items():
            old_val = str(values.get('old', 'None'))
            new_val = str(values.get('new', 'None'))
            # Truncate long values
            if len(old_val) > 50:
                old_val = old_val[:47] + '...'
            if len(new_val) > 50:
                new_val = new_val[:47] + '...'
            changes.append(f"{field} ({old_val} → {new_val})")
        return f"Changed {', '.join(changes)}"
    else:
        shown_fields = fields[:max_fields]
        remaining = len(fields) - max_fields
        changes = [f"{field}" for field in shown_fields]
        return f"Changed {', '.join(changes)} and {remaining} more field(s)"
