"""
WebRTC Proxy Router

Proxies WebRTC signaling requests to BM-APP and rewrites SDP to use public IPs.
This is needed because ZLMediaKit returns private IPs in SDP which are not
reachable from external networks.
"""
import re
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
import httpx

from app.database import get_db
from app.models import AIBox

router = APIRouter(prefix="/webrtc-proxy", tags=["WebRTC Proxy"])

# Known private IP to public IP mappings
# Format: {"private_ip": "public_ip"}
# These can be extended or loaded from config
PRIVATE_TO_PUBLIC_IP = {
    "172.16.200.190": "103.75.84.183",
    # Add more mappings as needed
}

# SSH tunnel endpoint for WebRTC media
# When set, all WebRTC media IPs will be replaced with this IP
# This allows routing through SSH tunnel: Dashboard(58002) -> AI Box(58002)
WEBRTC_TUNNEL_IP = "103.105.55.136"  # Dashboard server IP with SSH tunnel


def extract_host_from_url(url: str) -> str:
    """Extract host (IP or domain) from URL."""
    parsed = urlparse(url)
    return parsed.hostname or ""


def rewrite_sdp_ips(sdp: str, public_ip: str) -> str:
    """
    Rewrite private IPs in SDP to use public IP.

    This handles:
    - c= lines (connection info): c=IN IP4 172.16.200.190
    - a=candidate lines: a=candidate:... 172.16.200.190 58002 ...
    - a=rtcp lines: a=rtcp:58002 IN IP4 172.16.200.190
    - o= lines (origin): o=- 123 456 IN IP4 172.16.200.190
    - Removes IPv6 link-local candidates (fe80::) that won't work externally
    - Increases priority of IPv4 candidates
    """
    result = sdp

    for private_ip, mapped_public_ip in PRIVATE_TO_PUBLIC_IP.items():
        # Use the provided public_ip if it matches, otherwise use mapping
        target_ip = public_ip if public_ip else mapped_public_ip

        # Replace in connection line: c=IN IP4 172.16.200.190
        result = re.sub(
            rf'(c=IN IP4 ){private_ip}',
            rf'\g<1>{target_ip}',
            result
        )

        # Replace in origin line: o=- 123 456 IN IP4 172.16.200.190
        result = re.sub(
            rf'(o=.* IN IP4 ){private_ip}',
            rf'\g<1>{target_ip}',
            result
        )

        # Replace in RTCP line: a=rtcp:58002 IN IP4 172.16.200.190
        result = re.sub(
            rf'(a=rtcp:\d+ IN IP4 ){private_ip}',
            rf'\g<1>{target_ip}',
            result
        )

        # Replace in candidate lines: a=candidate:... udp 120 172.16.200.190 58002 ...
        # Pattern: ... <priority> <ip> <port> typ ...
        result = re.sub(
            rf'(a=candidate:\S+ \d+ (?:udp|tcp) \d+ ){private_ip}( \d+)',
            rf'\g<1>{target_ip}\g<2>',
            result,
            flags=re.IGNORECASE
        )

    # Remove IPv6 link-local candidates (fe80::) - they won't work externally
    result = re.sub(
        r'a=candidate:[^\r\n]*fe80::[^\r\n]*\r\n',
        '',
        result
    )

    # Rewrite candidates to Chrome-compatible format with generation field
    # Give TCP higher priority than UDP since UDP seems blocked
    # Priority formula: type_preference * 2^24 + local_preference * 2^8 + 256 - component_id
    # Host TCP: 2130706431 (highest), Host UDP: 2113929471 (lower)

    # Route all traffic through dashboard server (103.105.55.136)
    # UDP: via socat UDP-to-TCP tunnel over SSH
    # TCP: via SSH tunnel directly
    tunnel_ip = WEBRTC_TUNNEL_IP if WEBRTC_TUNNEL_IP else None

    # Rewrite UDP candidates to use dashboard IP (UDP tunneled via socat+SSH)
    result = re.sub(
        r'a=candidate:udpcandidate 1 udp \d+ \d+\.\d+\.\d+\.\d+ (\d+) typ host\r\n',
        rf'a=candidate:udpcandidate 1 udp 2130706431 {tunnel_ip} \1 typ host generation 0\r\n',
        result
    )

    # Fix TCP candidates - use tunnel IP for media routing via SSH tunnel
    if tunnel_ip:
        result = re.sub(
            r'a=candidate:tcpcandidate 1 tcp \d+ \d+\.\d+\.\d+\.\d+ (\d+) typ host tcptype passive\r\n',
            rf'a=candidate:tcpcandidate 1 tcp 2113929471 {tunnel_ip} \1 typ host tcptype passive generation 0\r\n',
            result
        )
        # Update c= and a=rtcp lines to use tunnel IP
        result = re.sub(
            r'(c=IN IP4 )\d+\.\d+\.\d+\.\d+',
            rf'\g<1>{tunnel_ip}',
            result
        )
        result = re.sub(
            r'(a=rtcp:\d+ IN IP4 )\d+\.\d+\.\d+\.\d+',
            rf'\g<1>{tunnel_ip}',
            result
        )
    else:
        result = re.sub(
            r'a=candidate:tcpcandidate 1 tcp \d+ (\d+\.\d+\.\d+\.\d+) (\d+) typ host tcptype passive\r\n',
            r'a=candidate:tcpcandidate 1 tcp 2113929471 \1 \2 typ host tcptype passive generation 0\r\n',
            result
        )

    return result


@router.post("/{aibox_id}")
async def proxy_webrtc(
    aibox_id: str,
    request: Request,
    app: str = Query(..., description="ZLMediaKit app name"),
    stream: str = Query(..., description="Stream name"),
    type: str = Query("play", description="play or push"),
    db: Session = Depends(get_db)
):
    """
    Proxy WebRTC signaling request to BM-APP and rewrite SDP.

    Flow:
    1. Get AI Box config from database
    2. Forward WebRTC request to BM-APP
    3. Rewrite private IPs in SDP response to public IPs
    4. Return modified SDP to client
    """
    # Get AI Box
    ai_box = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not ai_box:
        raise HTTPException(status_code=404, detail="AI Box not found")

    # Build WebRTC URL from AI Box api_url
    # api_url: http://103.75.84.183:2323/api -> http://103.75.84.183:2323/webrtc
    base_url = ai_box.api_url.replace("/api", "")
    webrtc_url = f"{base_url}/webrtc"

    # Extract public IP from AI Box URL for SDP rewriting
    public_ip = extract_host_from_url(ai_box.api_url)

    # Get request body (SDP offer from browser)
    body = await request.body()

    # Forward request to BM-APP
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                webrtc_url,
                params={"app": app, "stream": stream, "type": type},
                content=body,
                headers={
                    "Content-Type": request.headers.get("Content-Type", "application/sdp"),
                }
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="BM-APP WebRTC timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"BM-APP WebRTC error: {str(e)}")

    # Check response
    if response.status_code != 200:
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers)
        )

    # BM-APP returns JSON: {"sdp": "...", "type": "answer", "code": 0}
    # We need to parse JSON, rewrite SDP inside, and return JSON
    import json

    try:
        response_data = response.json()
        if "sdp" in response_data:
            original_sdp = response_data["sdp"]
            modified_sdp = rewrite_sdp_ips(original_sdp, public_ip)
            response_data["sdp"] = modified_sdp

            # Log the rewrite for debugging
            if original_sdp != modified_sdp:
                print(f"[WebRTC Proxy] Rewrote SDP for AI Box {ai_box.name}")
                print(f"[WebRTC Proxy] Public IP: {public_ip}")
                # Show candidate lines
                for line in modified_sdp.split('\r\n'):
                    if 'candidate' in line:
                        print(f"[WebRTC Proxy] {line}")

            return Response(
                content=json.dumps(response_data),
                status_code=200,
                media_type="application/json",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                }
            )
    except json.JSONDecodeError:
        pass

    # Fallback: treat as raw SDP
    sdp_content = response.text
    modified_sdp = rewrite_sdp_ips(sdp_content, public_ip)

    return Response(
        content=modified_sdp,
        status_code=200,
        media_type="application/sdp",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )


@router.options("/{aibox_id}")
async def webrtc_options(aibox_id: str):
    """Handle CORS preflight for WebRTC proxy."""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }
    )


@router.get("/test/{aibox_id}")
async def test_webrtc_connection(
    aibox_id: str,
    db: Session = Depends(get_db)
):
    """Test WebRTC endpoint connectivity for an AI Box."""
    ai_box = db.query(AIBox).filter(AIBox.id == aibox_id).first()
    if not ai_box:
        raise HTTPException(status_code=404, detail="AI Box not found")

    base_url = ai_box.api_url.replace("/api", "")
    webrtc_url = f"{base_url}/webrtc"
    public_ip = extract_host_from_url(ai_box.api_url)

    # Test connectivity
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(webrtc_url)
            reachable = True
            error = None
    except Exception as e:
        reachable = False
        error = str(e)

    return {
        "aibox_id": str(ai_box.id),
        "aibox_name": ai_box.name,
        "webrtc_url": webrtc_url,
        "public_ip": public_ip,
        "private_ip_mappings": PRIVATE_TO_PUBLIC_IP,
        "reachable": reachable,
        "error": error
    }
