"""
Service for fetching camera locations from RTU UP2DJTY external API
"""
import httpx
from datetime import datetime
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CameraLocation


class RTUAPIClient:
    """Client for RTU UP2DJTY API"""

    def __init__(self):
        self.api_key = settings.rtu_api_key
        self.keypoint_url = settings.rtu_keypoint_url
        self.gps_tim_har_url = settings.rtu_gps_tim_har_url
        self.headers = {
            "X-API-KEY": self.api_key,
            "Accept": "application/json"
        }

    async def fetch_keypoints(self) -> List[Dict[str, Any]]:
        """Fetch keypoints from RTU API"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.keypoint_url,
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()

                # Handle different response formats
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    # Check common response patterns
                    if "data" in data:
                        return data["data"] if isinstance(data["data"], list) else []
                    elif "keypoints" in data:
                        return data["keypoints"]
                    elif "results" in data:
                        return data["results"]
                return []
        except httpx.HTTPError as e:
            print(f"[RTU API] Error fetching keypoints: {e}")
            raise
        except Exception as e:
            print(f"[RTU API] Unexpected error: {e}")
            raise

    async def fetch_gps_tim_har(self) -> List[Dict[str, Any]]:
        """Fetch GPS TIM HAR data from RTU API"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.gps_tim_har_url,
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()

                # Handle different response formats
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    if "data" in data:
                        return data["data"] if isinstance(data["data"], list) else []
                    elif "gps" in data:
                        return data["gps"]
                    elif "results" in data:
                        return data["results"]
                return []
        except httpx.HTTPError as e:
            print(f"[RTU API] Error fetching GPS TIM HAR: {e}")
            raise
        except Exception as e:
            print(f"[RTU API] Unexpected error: {e}")
            raise


def parse_keypoint(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse keypoint data from API response"""
    # Try different field names for coordinates
    lat = (
        data.get("latitude") or
        data.get("lat") or
        data.get("Latitude") or
        data.get("y") or
        0.0
    )
    lng = (
        data.get("longitude") or
        data.get("lng") or
        data.get("lon") or
        data.get("Longitude") or
        data.get("x") or
        0.0
    )

    # Try to convert to float
    try:
        lat = float(lat) if lat else 0.0
        lng = float(lng) if lng else 0.0
    except (ValueError, TypeError):
        lat, lng = 0.0, 0.0

    # Get name from various fields
    name = (
        data.get("name") or
        data.get("Name") or
        data.get("keypoint_name") or
        data.get("location_name") or
        data.get("description") or
        f"Keypoint {data.get('id', 'Unknown')}"
    )

    # Get ID
    external_id = str(
        data.get("id") or
        data.get("ID") or
        data.get("keypoint_id") or
        ""
    )

    return {
        "external_id": external_id,
        "source": "keypoint",
        "name": str(name),
        "latitude": lat,
        "longitude": lng,
        "location_type": data.get("type") or data.get("category") or data.get("jenis"),
        "description": data.get("description") or data.get("keterangan"),
        "address": data.get("address") or data.get("alamat") or data.get("lokasi"),
        "extra_data": {k: v for k, v in data.items() if k not in ["id", "name", "latitude", "longitude", "lat", "lng"]}
    }


def parse_gps_tim_har(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse GPS TIM HAR data from API response"""
    lat = (
        data.get("latitude") or
        data.get("lat") or
        data.get("Latitude") or
        0.0
    )
    lng = (
        data.get("longitude") or
        data.get("lng") or
        data.get("lon") or
        data.get("Longitude") or
        0.0
    )

    try:
        lat = float(lat) if lat else 0.0
        lng = float(lng) if lng else 0.0
    except (ValueError, TypeError):
        lat, lng = 0.0, 0.0

    name = (
        data.get("name") or
        data.get("Name") or
        data.get("unit_name") or
        data.get("kendaraan") or
        f"GPS {data.get('id', 'Unknown')}"
    )

    external_id = str(
        data.get("id") or
        data.get("ID") or
        data.get("gps_id") or
        data.get("unit_id") or
        ""
    )

    return {
        "external_id": external_id,
        "source": "gps_tim_har",
        "name": str(name),
        "latitude": lat,
        "longitude": lng,
        "location_type": data.get("type") or data.get("jenis") or "GPS",
        "description": data.get("description") or data.get("keterangan"),
        "address": data.get("address") or data.get("lokasi"),
        "extra_data": {k: v for k, v in data.items() if k not in ["id", "name", "latitude", "longitude", "lat", "lng"]}
    }


async def sync_locations_from_api(db: Session, source: str = "all") -> Tuple[int, int, int, List[str]]:
    """
    Sync camera locations from external API to database

    Args:
        db: Database session
        source: Which API to sync from ('keypoint', 'gps_tim_har', or 'all')

    Returns:
        Tuple of (total_synced, created, updated, errors)
    """
    client = RTUAPIClient()
    created = 0
    updated = 0
    errors: List[str] = []
    locations_data: List[Dict[str, Any]] = []

    # Fetch from APIs based on source
    if source in ["keypoint", "all"]:
        try:
            keypoints = await client.fetch_keypoints()
            for kp in keypoints:
                parsed = parse_keypoint(kp)
                if parsed["latitude"] != 0.0 and parsed["longitude"] != 0.0:
                    locations_data.append(parsed)
                else:
                    errors.append(f"Keypoint '{parsed['name']}' has invalid coordinates")
        except Exception as e:
            errors.append(f"Failed to fetch keypoints: {str(e)}")

    if source in ["gps_tim_har", "all"]:
        try:
            gps_data = await client.fetch_gps_tim_har()
            for gps in gps_data:
                parsed = parse_gps_tim_har(gps)
                if parsed["latitude"] != 0.0 and parsed["longitude"] != 0.0:
                    locations_data.append(parsed)
                else:
                    errors.append(f"GPS '{parsed['name']}' has invalid coordinates")
        except Exception as e:
            errors.append(f"Failed to fetch GPS TIM HAR: {str(e)}")

    # Sync to database
    now = datetime.utcnow()
    for loc_data in locations_data:
        try:
            # Check if exists by external_id and source
            existing = None
            if loc_data["external_id"]:
                existing = db.query(CameraLocation).filter(
                    CameraLocation.external_id == loc_data["external_id"],
                    CameraLocation.source == loc_data["source"]
                ).first()

            if existing:
                # Update existing
                for key, value in loc_data.items():
                    if value is not None and key != "external_id":
                        setattr(existing, key, value)
                existing.last_synced_at = now
                updated += 1
            else:
                # Create new
                new_location = CameraLocation(
                    **loc_data,
                    last_synced_at=now
                )
                db.add(new_location)
                created += 1

        except Exception as e:
            errors.append(f"Error syncing '{loc_data.get('name', 'Unknown')}': {str(e)}")

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"Database commit failed: {str(e)}")

    total = created + updated
    return total, created, updated, errors


# Singleton client
rtu_client = RTUAPIClient()
