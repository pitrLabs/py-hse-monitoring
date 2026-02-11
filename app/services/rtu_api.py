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
    """Client for RTU UP2DJTY API (v2)"""

    def __init__(self):
        self.api_key = settings.rtu_api_key
        self.keypoint_url = settings.rtu_keypoint_url
        self.tim_koper_url = settings.rtu_tim_koper_url
        self.gps_tim_har_url = settings.rtu_gps_tim_har_url
        self.headers = {
            "x-api-key": self.api_key,
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

    async def fetch_tim_koper(self) -> List[Dict[str, Any]]:
        """Fetch all koper CCTV data from RTU API v2 (includes status_perangkat)"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.tim_koper_url,
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
                    elif "results" in data:
                        return data["results"]
                return []
        except httpx.HTTPError as e:
            print(f"[RTU API] Error fetching tim_koper: {e}")
            raise
        except Exception as e:
            print(f"[RTU API] Unexpected error fetching tim_koper: {e}")
            raise

    async def fetch_gps_tim_har(self) -> List[Dict[str, Any]]:
        """Fetch GPS TIM HAR data from RTU API v2 (koper with GPS coordinates)"""
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


def parse_coordinate_string(coord_str: str) -> tuple:
    """
    Parse coordinate string in various formats:
    - "-7.538173,110.589176" (standard)
    - "-7,2831381, 109,0254788" (comma as decimal separator)
    - " -6,8697800, 108,8380210" (with spaces)
    - "-7. 0173493,110.3571547" (space after decimal point)
    """
    if not coord_str or not isinstance(coord_str, str):
        return 0.0, 0.0

    # Clean up the string - remove spaces around/within numbers
    coord_str = coord_str.strip()

    # Remove spaces that appear after decimal points or within numbers
    # e.g., "-7. 0173493" -> "-7.0173493"
    import re
    coord_str = re.sub(r'(\d)\s+(\d)', r'\1\2', coord_str)  # "7. 01" -> "7.01"
    coord_str = re.sub(r'\.\s+', '.', coord_str)  # ". " -> "."
    coord_str = re.sub(r'\s+\.', '.', coord_str)  # " ." -> "."

    lat, lng = 0.0, 0.0

    # Try to detect format and parse
    try:
        # Check if it uses comma as decimal separator (European format)
        # Pattern: has more than one comma but coordinates are separated by comma+space
        if ", " in coord_str or " ," in coord_str:
            # Split by comma followed by space (or space followed by comma)
            parts = [p.strip() for p in coord_str.replace(" ,", ",").split(", ")]
            if len(parts) == 2:
                # Replace comma with dot for decimal (European format)
                lat_str = parts[0].replace(",", ".")
                lng_str = parts[1].replace(",", ".")
                lat, lng = float(lat_str), float(lng_str)

        # Standard format: comma separates lat and lng
        elif "," in coord_str:
            parts = coord_str.split(",")
            if len(parts) == 2:
                lat, lng = float(parts[0].strip()), float(parts[1].strip())
            elif len(parts) == 4:
                # Format like "-7,2831381, 109,0254788" parsed as 4 parts
                # Reconstruct: parts[0]+"."+parts[1] and parts[2]+"."+parts[3]
                lat = float(f"{parts[0].strip()}.{parts[1].strip()}")
                lng = float(f"{parts[2].strip()}.{parts[3].strip()}")

    except (ValueError, TypeError, IndexError) as e:
        print(f"[RTU API] Failed to parse coordinate: {coord_str}, error: {e}")
        return 0.0, 0.0

    # Validate coordinate ranges
    # Latitude: -90 to 90, Longitude: -180 to 180
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        print(f"[RTU API] Invalid coordinate range: {coord_str} -> lat={lat}, lng={lng}")
        return 0.0, 0.0

    return lat, lng


def parse_keypoint(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse keypoint data from API response"""
    lat = 0.0
    lng = 0.0

    # First try KOORDINAT_GPS field (RTU API format)
    koordinat_gps = data.get("KOORDINAT_GPS") or data.get("koordinat_gps")
    if koordinat_gps:
        lat, lng = parse_coordinate_string(koordinat_gps)

    # Fallback to separate lat/lng fields
    if lat == 0.0 and lng == 0.0:
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

        # Validate coordinate ranges for fallback values
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            print(f"[RTU API] Invalid fallback coordinate range: lat={lat}, lng={lng}")
            lat, lng = 0.0, 0.0

    # Get name from various fields (RTU API uses KEYPOINT_NAME or KEYPOINT_SCADA)
    name = (
        data.get("KEYPOINT_NAME") or
        data.get("KEYPOINT_SCADA") or
        data.get("name") or
        data.get("Name") or
        data.get("keypoint_name") or
        data.get("location_name") or
        data.get("description") or
        f"Keypoint {data.get('id', 'Unknown')}"
    )

    # Clean up empty names
    if not name or name.strip() == "":
        name = data.get("KEYPOINT_SCADA") or f"Keypoint-{data.get('FEEDER_01', 'Unknown')}"

    # Get ID (RTU API doesn't have explicit ID, use KEYPOINT_SCADA as unique identifier)
    external_id = str(
        data.get("id") or
        data.get("ID") or
        data.get("keypoint_id") or
        data.get("KEYPOINT_SCADA") or
        ""
    )

    return {
        "external_id": external_id,
        "source": "keypoint",
        "name": str(name).strip(),
        "latitude": lat,
        "longitude": lng,
        "location_type": data.get("TYPE_KP") or data.get("type") or data.get("category") or data.get("jenis"),
        "description": data.get("STATUS") or data.get("description") or data.get("keterangan"),
        "address": data.get("ALAMAT") or data.get("address") or data.get("alamat") or data.get("lokasi"),
        "extra_data": {k: v for k, v in data.items() if k not in ["id", "name", "latitude", "longitude", "lat", "lng", "KOORDINAT_GPS"]}
    }


def parse_google_maps_url(url: str) -> tuple:
    """
    Parse coordinates from Google Maps URL
    Formats:
    - https://www.google.com/maps?q=-7.123,110.456
    - https://maps.google.com/?q=-7.123,110.456
    - https://www.google.com/maps/place/-7.123,110.456
    """
    import re
    if not url or not isinstance(url, str):
        return 0.0, 0.0

    # Try q= parameter format
    match = re.search(r'[?&]q=(-?\d+\.?\d*),\s*(-?\d+\.?\d*)', url)
    if match:
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
        except (ValueError, TypeError):
            pass

    # Try /place/ format
    match = re.search(r'/place/(-?\d+\.?\d*),\s*(-?\d+\.?\d*)', url)
    if match:
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
        except (ValueError, TypeError):
            pass

    # Try @lat,lng format
    match = re.search(r'@(-?\d+\.?\d*),\s*(-?\d+\.?\d*)', url)
    if match:
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
        except (ValueError, TypeError):
            pass

    return 0.0, 0.0


def parse_tim_koper(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse TIM KOPER data from API v2 response

    API Response format:
    {
        "id_alat": "KOPER_01",
        "nama_tim": "DCC1-HAR KP 1",
        "status_perangkat": "ON" or "OFF",
        ...
    }
    """
    lat = 0.0
    lng = 0.0

    # Try 'gps' field first
    gps_field = data.get("gps")
    if gps_field and isinstance(gps_field, str):
        lat, lng = parse_coordinate_string(gps_field)

    # Fallback: try lokasi_tim_har (Google Maps URL)
    if lat == 0.0 and lng == 0.0:
        lokasi_url = data.get("lokasi_tim_har")
        if lokasi_url and isinstance(lokasi_url, str) and "google" in lokasi_url.lower():
            lat, lng = parse_google_maps_url(lokasi_url)

    # Get name
    name = (
        data.get("nama_tim") or
        data.get("name") or
        f"Koper {data.get('id_alat', data.get('id', 'Unknown'))}"
    )

    # Get external_id
    external_id = str(
        data.get("id_alat") or
        data.get("id") or
        ""
    )

    # Get status (ON/OFF)
    status_str = str(data.get("status_perangkat", "")).upper()
    is_online = status_str == "ON"

    return {
        "external_id": external_id,
        "source": "tim_koper",
        "name": str(name).strip(),
        "latitude": lat,
        "longitude": lng,
        "location_type": data.get("jenis_har") or "Koper CCTV",
        "description": data.get("kondisi_jaringan"),
        "address": data.get("keypoint_name"),
        "is_active": is_online,
        "extra_data": {k: v for k, v in data.items() if v is not None and k not in ["id", "name", "latitude", "longitude", "gps"]}
    }


def parse_gps_tim_har(data: Dict[str, Any]) -> Dict[str, Any]:
    """Parse GPS TIM HAR data from API response

    API Response format:
    {
        "id_alat": "KOPER_01",
        "nama_tim": "DCC1-HAR KP 1",
        "gps": "-7.123,110.456" or null,
        "status_perangkat": "ON",
        "lokasi_tim_har": "https://www.google.com/maps?q=..." or null,
        ...
    }
    """
    lat = 0.0
    lng = 0.0

    # Try 'gps' field first (format: "-7.123,110.456")
    gps_field = data.get("gps")
    if gps_field and isinstance(gps_field, str):
        lat, lng = parse_coordinate_string(gps_field)

    # Fallback: try parsing lokasi_tim_har (Google Maps URL)
    if lat == 0.0 and lng == 0.0:
        lokasi_url = data.get("lokasi_tim_har")
        if lokasi_url and isinstance(lokasi_url, str) and "google" in lokasi_url.lower():
            lat, lng = parse_google_maps_url(lokasi_url)

    # Fallback: try KOORDINAT_GPS field
    if lat == 0.0 and lng == 0.0:
        koordinat_gps = data.get("KOORDINAT_GPS") or data.get("koordinat_gps")
        if koordinat_gps:
            lat, lng = parse_coordinate_string(koordinat_gps)

    # Fallback to separate lat/lng fields
    if lat == 0.0 and lng == 0.0:
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

        # Validate coordinate ranges for fallback values
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            print(f"[RTU API] Invalid fallback coordinate range: lat={lat}, lng={lng}")
            lat, lng = 0.0, 0.0

    # Get name - prioritize nama_tim for gps_tim_har API
    name = (
        data.get("nama_tim") or
        data.get("name") or
        data.get("Name") or
        data.get("unit_name") or
        data.get("kendaraan") or
        f"GPS {data.get('id_alat', data.get('id', 'Unknown'))}"
    )

    # Get external_id - prioritize id_alat for gps_tim_har API
    external_id = str(
        data.get("id_alat") or
        data.get("id") or
        data.get("ID") or
        data.get("gps_id") or
        data.get("unit_id") or
        ""
    )

    # Get status
    status = data.get("status_perangkat", "").upper() == "ON"

    return {
        "external_id": external_id,
        "source": "gps_tim_har",
        "name": str(name).strip(),
        "latitude": lat,
        "longitude": lng,
        "location_type": data.get("jenis_har") or data.get("type") or "GPS Tim HAR",
        "description": data.get("kondisi_jaringan") or data.get("description"),
        "address": data.get("keypoint_name") or data.get("address"),
        "is_active": status,
        "extra_data": {k: v for k, v in data.items() if v is not None and k not in ["id", "name", "latitude", "longitude", "lat", "lng", "gps", "life_saving_rules"]}
    }


async def sync_locations_from_api(db: Session, source: str = "all") -> Tuple[int, int, int, List[str]]:
    """
    Sync camera locations from external API to database

    Args:
        db: Database session
        source: Which API to sync from ('keypoint', 'tim_koper', 'gps_tim_har', or 'all')

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

    if source in ["tim_koper", "all"]:
        try:
            koper_data = await client.fetch_tim_koper()
            for koper in koper_data:
                parsed = parse_tim_koper(koper)
                # Tim koper might not have GPS, we still save it for status tracking
                locations_data.append(parsed)
        except Exception as e:
            errors.append(f"Failed to fetch tim_koper: {str(e)}")

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
