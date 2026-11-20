"""Buffer API Integration for CREOVIS.

Connects to the Buffer GraphQL API (https://api.buffer.com) using a Bearer token
to list connected social channels, create posts, and schedule video clip publishing
across TikTok, Instagram, YouTube, Facebook, LinkedIn, Twitter/X, Threads, Pinterest, and Bluesky.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("buffer_publisher")

BUFFER_API_ENDPOINT = "https://api.buffer.com"
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = Path(os.getenv("OPENSHORT_ENV_PATH", str(BASE_DIR / ".env")))


def get_buffer_token(env_path: Optional[str] = None) -> Optional[str]:
    """Retrieve Buffer access token from environment or .env file."""
    token = os.environ.get("BUFFER_ACCESS_TOKEN")
    if token and token.strip():
        return token.strip()

    target_env = env_path or ENV_PATH
    if os.path.exists(target_env):
        try:
            with open(target_env, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("BUFFER_ACCESS_TOKEN="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            os.environ["BUFFER_ACCESS_TOKEN"] = val
                            return val
        except Exception as e:
            logger.warning(f"Failed to read Buffer token from {target_env}: {e}")

    return None


def is_buffer_configured(env_path: Optional[str] = None) -> bool:
    """Return True if a Buffer API access token is available."""
    return bool(get_buffer_token(env_path))


def save_buffer_token_to_env(token: str, env_path: Optional[str] = None) -> None:
    """Persist Buffer access token into the .env file."""
    target_env = env_path or ENV_PATH
    token = token.strip()
    os.environ["BUFFER_ACCESS_TOKEN"] = token

    if os.path.exists(target_env):
        with open(target_env, "r") as f:
            content = f.read()

        if re.search(r"^BUFFER_ACCESS_TOKEN=.*$", content, flags=re.MULTILINE):
            content = re.sub(r"^BUFFER_ACCESS_TOKEN=.*$", f"BUFFER_ACCESS_TOKEN={token}", content, flags=re.MULTILINE)
        else:
            content = content.rstrip() + f"\nBUFFER_ACCESS_TOKEN={token}\n"

        with open(target_env, "w") as f:
            f.write(content)
    else:
        with open(target_env, "w") as f:
            f.write(f"BUFFER_ACCESS_TOKEN={token}\n")


def execute_graphql(query: str, variables: Optional[Dict[str, Any]] = None, token: Optional[str] = None) -> Dict[str, Any]:
    """Execute a GraphQL query or mutation against the Buffer API."""
    auth_token = token or get_buffer_token()
    if not auth_token:
        raise ValueError("Buffer Access Token is not configured. Set BUFFER_ACCESS_TOKEN in .env.")

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "User-Agent": "CREOVIS-SocialPublisher/1.0"
    }

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    response = requests.post(BUFFER_API_ENDPOINT, headers=headers, json=payload, timeout=25)
    
    if response.status_code != 200:
        raise RuntimeError(f"Buffer API HTTP {response.status_code}: {response.text}")

    result = response.json()
    if "errors" in result and result["errors"]:
        error_msgs = [e.get("message", str(e)) for e in result["errors"]]
        raise RuntimeError(f"Buffer GraphQL Error: {'; '.join(error_msgs)}")

    return result.get("data", {})


def get_account_info(token: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve Buffer account and organization details."""
    query = """
    query GetAccountInfo {
      account {
        id
        email
        name
        organizations {
          id
          name
          channelCount
        }
      }
    }
    """
    data = execute_graphql(query, token=token)
    return data.get("account") or {}


def list_channels(token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all connected channels across the user's organizations."""
    account = get_account_info(token=token)
    orgs = account.get("organizations") or []
    all_channels = []

    channel_query = """
    query GetOrgChannels($orgId: OrganizationId!) {
      channels(input: { organizationId: $orgId }) {
        id
        name
        displayName
        service
        serviceId
        type
        avatar
        isDisconnected
        isLocked
      }
    }
    """

    for org in orgs:
        org_id = org.get("id")
        if not org_id:
            continue
        try:
            data = execute_graphql(channel_query, variables={"orgId": org_id}, token=token)
            channels = data.get("channels") or []
            for ch in channels:
                ch["organizationId"] = org_id
                ch["organizationName"] = org.get("name")
            all_channels.extend(channels)
        except Exception as e:
            logger.warning(f"Failed to fetch channels for org {org_id}: {e}")

    return all_channels


def create_post(
    channel_id: str,
    text: str,
    video_url: Optional[str] = None,
    mode: str = "shareNow",
    due_at: Optional[str] = None,
    service: Optional[str] = None,
    title: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create or schedule a post on a specific Buffer channel.
    
    Args:
        channel_id: Target Buffer ChannelId
        text: Post text or caption
        video_url: Publicly accessible URL of the video clip
        mode: ShareMode ('shareNow', 'addToQueue', 'customScheduled', 'shareNext')
        due_at: ISO-8601 string when mode is 'customScheduled'
        service: Social service name (e.g. 'youtube', 'instagram', 'tiktok', etc.)
        title: Title for platforms supporting titles (YouTube, TikTok, Reels)
        token: Optional override token
    """
    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess {
          post {
            id
            status
            dueAt
            sentAt
            channelId
            channelService
          }
        }
        ... on MutationError {
          message
        }
      }
    }
    """

    # If due_at is provided, switch mode to customScheduled
    post_mode = "customScheduled" if due_at else mode

    assets = []
    if video_url:
        assets.append({
            "video": {
                "url": video_url,
                "metadata": {
                    "title": title or (text[:60] if text else "Short Clip")
                }
            }
        })

    # Prepare service-specific metadata
    metadata = {}
    svc = (service or "").lower()
    if svc == "youtube":
        metadata["youtube"] = {
            "title": title or (text[:60] if text else "Viral Short"),
            "privacy": "public"
        }
    elif svc == "instagram":
        metadata["instagram"] = {
            "type": "reel",
            "shouldShareToFeed": True
        }
    elif svc == "tiktok":
        metadata["tiktok"] = {
            "title": title or (text[:60] if text else "Viral Clip")
        }
    elif svc == "facebook":
        metadata["facebook"] = {
            "type": "reel"
        }

    post_input: Dict[str, Any] = {
        "channelId": channel_id,
        "text": text or "",
        "mode": post_mode,
        "schedulingType": "automatic",
        "needsApproval": False,
        "assets": assets
    }

    if due_at:
        post_input["dueAt"] = due_at

    if metadata:
        post_input["metadata"] = metadata

    data = execute_graphql(mutation, variables={"input": post_input}, token=token)
    payload = data.get("createPost") or {}

    typename = payload.get("__typename")
    if typename == "PostActionSuccess":
        return {
            "success": True,
            "post": payload.get("post"),
            "channel_id": channel_id
        }
    else:
        err_msg = payload.get("message") or f"Buffer post creation failed: {payload}"
        raise RuntimeError(err_msg)


def filter_channels_for_services(channels: List[Dict[str, Any]], services: List[str]) -> List[Dict[str, Any]]:
    """Return active connected channels matching requested services (e.g. ['instagram', 'youtube'])."""
    service_set = set(s.lower().strip() for s in services if s)
    matched = []
    for ch in channels:
        if ch.get("isDisconnected") or ch.get("isLocked"):
            continue
        svc = (ch.get("service") or "").lower().strip()
        if svc in service_set:
            matched.append(ch)
    return matched


def publish_to_buffer_channels(
    channels: List[Dict[str, Any]],
    text: str,
    video_url: Optional[str] = None,
    due_at: Optional[str] = None,
    mode: str = "customScheduled",
    title: Optional[str] = None,
    token: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Publish or schedule content across multiple Buffer channels."""
    results = []
    for ch in channels:
        ch_id = ch.get("id")
        ch_service = ch.get("service")
        ch_name = ch.get("name") or ch.get("displayName") or ch_id
        try:
            res = create_post(
                channel_id=ch_id,
                text=text,
                video_url=video_url,
                mode=mode,
                due_at=due_at,
                service=ch_service,
                title=title,
                token=token
            )
            results.append({
                "channel_id": ch_id,
                "service": ch_service,
                "name": ch_name,
                "success": True,
                "post_id": res.get("post", {}).get("id"),
                "status": res.get("post", {}).get("status")
            })
        except Exception as e:
            logger.error(f"Failed to post to Buffer channel {ch_id} ({ch_name}): {e}")
            results.append({
                "channel_id": ch_id,
                "service": ch_service,
                "name": ch_name,
                "success": False,
                "error": str(e)
            })

    return results
