"""
Alarm Types API Router

Provides endpoint to fetch alarm types dynamically from actual data.
Alarm types come from BM-APP data stored in the alarms table.
"""

import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import distinct, func
from app.database import get_db
from app.models import Alarm
from app.alarm_types import get_alarm_color, get_alarm_severity

router = APIRouter(prefix="/alarm-types", tags=["alarm-types"])


@router.get("/")
def list_alarm_types(db: Session = Depends(get_db)):
    """
    Get all alarm types that exist in the system.

    Returns unique alarm_type values from the alarms table,
    with description extracted from raw_data.Result.Description.

    This is dynamic - only returns types that have actually been
    received from BM-APP, not a hardcoded list.
    """
    # Query unique alarm types with their count and a sample raw_data
    results = db.query(
        Alarm.alarm_type,
        func.count(Alarm.id).label('count'),
        func.max(Alarm.raw_data).label('sample_raw_data')
    ).group_by(Alarm.alarm_type).all()

    alarm_types = {}
    for row in results:
        alarm_type = row.alarm_type
        if not alarm_type:
            continue

        # Try to extract description from raw_data
        description = None
        if row.sample_raw_data:
            try:
                raw = json.loads(row.sample_raw_data) if isinstance(row.sample_raw_data, str) else row.sample_raw_data
                description = raw.get('Result', {}).get('Description')
            except (json.JSONDecodeError, TypeError):
                pass

        alarm_types[alarm_type] = {
            "type": alarm_type,
            "description": description or alarm_type,
            "count": row.count,
            "color": get_alarm_color(alarm_type),
            "severity": get_alarm_severity(alarm_type)
        }

    return alarm_types


@router.get("/summary")
def alarm_types_summary(db: Session = Depends(get_db)):
    """
    Get a simple list of alarm types with counts.
    """
    results = db.query(
        Alarm.alarm_type,
        func.count(Alarm.id).label('count')
    ).group_by(Alarm.alarm_type).order_by(func.count(Alarm.id).desc()).all()

    return [
        {"type": row.alarm_type, "count": row.count}
        for row in results if row.alarm_type
    ]
