"""Direct YouTube publishing using YouTube Data API v3 (videos.insert).

Allows publishing clips directly from OpenShorts to YouTube Shorts without
requiring third-party aggregator services (like Upload-Post).

Configuration (.env):
    YOUTUBE_CLIENT_ID=...
    YOUTUBE_CLIENT_SECRET=...
    YOUTUBE_REFRESH_TOKEN=...
    YOUTUBE_DEFAULT_PRIVACY=public  # public, unlisted, or private
    YOUTUBE_CATEGORY_ID=22          # 22 = People & Blogs, 20 = Gaming
    # Or direct access token (for temporary testing):
    # YOUTUBE_ACCESS_TOKEN=...
"""

import os
import sys
import time
from typing import Dict, Any, List, Optional

try:
    import google.oauth2.credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    google = None
    Request = None
    build = None
    MediaFileUpload = None
    HttpError = Exception  # type: ignore
    GOOGLE_AUTH_AVAILABLE = False

import social_platforms

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]

DEFAULT_CATEGORY_ID = os.environ.get("YOUTUBE_CATEGORY_ID", "22")
DEFAULT_PRIVACY = os.environ.get("YOUTUBE_DEFAULT_PRIVACY", "public").lower()


def is_direct_youtube_configured() -> bool:
    """Check if direct YouTube Data API credentials are configured in environment."""
    if os.environ.get("YOUTUBE_ACCESS_TOKEN"):
        return True
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    return bool(client_id and client_secret and refresh_token)


def test_api_key(api_key: Optional[str] = None) -> Dict[str, Any]:
    """Test YouTube Data API v3 access using API key."""
    key = api_key or os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return {"success": False, "error": "No API key configured"}
    import requests
    url = f"https://www.googleapis.com/youtube/v3/videoCategories?part=snippet&regionCode=US&key={key}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            categories = [item.get("snippet", {}).get("title") for item in data.get("items", [])[:5]]
            return {
                "success": True,
                "message": "YouTube Data API v3 is active and operational with provided API key",
                "sample_categories": categories,
            }
        return {
            "success": False,
            "status_code": resp.status_code,
            "error": resp.text,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def exchange_code_for_tokens(code: str, redirect_uri: str) -> Dict[str, Any]:
    """Exchange an OAuth2 authorization code for refresh and access tokens."""
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise ValueError("YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set")
    import requests
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    resp = requests.post(token_url, data=data, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    return resp.json()


def get_youtube_credentials() -> Any:
    """Build and refresh Google OAuth2 Credentials object from environment variables."""
    if not GOOGLE_AUTH_AVAILABLE:
        raise RuntimeError("google-auth-oauthlib is not installed.")
    access_token = os.environ.get("YOUTUBE_ACCESS_TOKEN")
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not is_direct_youtube_configured():
        raise ValueError(
            "YouTube credentials not configured. Please set YOUTUBE_CLIENT_ID, "
            "YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN in your .env file."
        )

    creds = google.oauth2.credentials.Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=YOUTUBE_SCOPES,
    )

    # Refresh token if needed
    if not creds.valid or not creds.token:
        request = Request()
        creds.refresh(request)

    return creds


def get_youtube_service():
    """Build an authenticated YouTube Data API v3 service."""
    creds = get_youtube_credentials()
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def prepare_shorts_title(title: str) -> str:
    """Prepare title suitable for YouTube Short (max 100 chars, with #Shorts if room)."""
    raw_title = (title or "Viral Short").strip()
    # Ensure #Shorts tag is present for automatic Shorts detection
    if "#Shorts" not in raw_title and "#shorts" not in raw_title:
        candidate = f"{raw_title} #Shorts"
        if len(candidate) <= social_platforms.YOUTUBE_TITLE_MAX:
            raw_title = candidate

    return social_platforms.youtube_title(raw_title)


def prepare_shorts_description(description: str) -> str:
    """Format description ensuring #Shorts hashtag is present."""
    desc = (description or "").strip()
    if "#Shorts" not in desc and "#shorts" not in desc:
        desc = f"{desc}\n\n#Shorts #Viral" if desc else "#Shorts #Viral"
    return desc


def upload_video_to_youtube(
    file_path: str,
    title: str,
    description: str = "",
    privacy_status: Optional[str] = None,
    tags: Optional[List[str]] = None,
    category_id: Optional[str] = None,
    progress_callback=None,
) -> Dict[str, Any]:
    """Upload a video file directly to YouTube using YouTube Data API v3 (videos.insert).

    Args:
        file_path: Absolute path to video file on disk.
        title: Title of the video (max 100 characters).
        description: Description of the video.
        privacy_status: 'public', 'unlisted', or 'private'. Defaults to YOUTUBE_DEFAULT_PRIVACY.
        tags: List of keywords/tags.
        category_id: YouTube numeric category id (default 22).
        progress_callback: Optional callable(percent_int).

    Returns:
        dict with video_id, url, shorts_url, title, description, privacy_status
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")

    status_val = (privacy_status or DEFAULT_PRIVACY).strip().lower()
    if status_val not in ("public", "unlisted", "private"):
        status_val = "public"

    final_title = prepare_shorts_title(title)
    final_desc = prepare_shorts_description(description)

    final_tags = list(tags or [])
    if "shorts" not in [t.lower() for t in final_tags]:
        final_tags.append("shorts")

    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title": final_title,
            "description": final_desc,
            "tags": final_tags,
            "categoryId": str(category_id or DEFAULT_CATEGORY_ID),
        },
        "status": {
            "privacyStatus": status_val,
            "selfDeclaredMadeForKids": False,
        },
    }

    # Resumable upload chunk size (4MB chunks)
    media = MediaFileUpload(
        file_path,
        mimetype="video/mp4",
        chunksize=1024 * 1024 * 4,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    last_reported = -1
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            if pct != last_reported:
                last_reported = pct
                print(f"[YouTube Upload] Progress: {pct}%")
                if progress_callback:
                    try:
                        progress_callback(pct)
                    except Exception:
                        pass

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError(f"YouTube upload failed: No video ID in response ({response})")

    url = f"https://youtu.be/{video_id}"
    shorts_url = f"https://www.youtube.com/shorts/{video_id}"
    print(f"✅ [YouTube Upload] Successfully published video: {video_id} -> {shorts_url}")

    return {
        "success": True,
        "video_id": video_id,
        "url": url,
        "shorts_url": shorts_url,
        "title": final_title,
        "description": final_desc,
        "privacy_status": status_val,
        "response": response,
    }
