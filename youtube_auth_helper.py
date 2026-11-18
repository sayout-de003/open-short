#!/usr/bin/env python3
"""YouTube OAuth2 Helper Script for OpenShorts.

This script helps you generate the OAuth2 refresh token needed for YouTube Data API v3
and automatically saves the credentials to your /root/openshort/.env file.

Usage:
    python youtube_auth_helper.py
    python youtube_auth_helper.py --client-secrets path/to/client_secret.json
    python youtube_auth_helper.py --client-id YOUR_ID --client-secret YOUR_SECRET
"""

import argparse
import json
import os
import re
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]

ENV_PATH = "/root/openshort/.env"


def update_env_file(client_id: str, client_secret: str, refresh_token: str, env_path: str = ENV_PATH):
    """Write or update YouTube credentials in .env file."""
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updates = {
        "YOUTUBE_CLIENT_ID": client_id,
        "YOUTUBE_CLIENT_SECRET": client_secret,
        "YOUTUBE_REFRESH_TOKEN": refresh_token,
    }

    seen = set()
    new_lines = []
    for line in lines:
        matched = False
        for key, val in updates.items():
            if line.startswith(f"{key}=") or line.startswith(f"#{key}="):
                new_lines.append(f"{key}={val}\n")
                seen.add(key)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for key, val in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={val}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"\n✅ Successfully updated YouTube credentials in: {env_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate YouTube OAuth2 Refresh Token")
    parser.add_argument("--client-secrets", help="Path to Google client_secret.json file")
    parser.add_argument("--client-id", help="Google OAuth2 Client ID")
    parser.add_argument("--client-secret", help="Google OAuth2 Client Secret")
    parser.add_argument("--env-path", default=ENV_PATH, help="Path to .env file to update")
    parser.add_argument("--port", type=int, default=8080, help="Local port for OAuth callback")
    args = parser.parse_args()

    client_id = args.client_id or os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = args.client_secret or os.environ.get("YOUTUBE_CLIENT_SECRET")
    client_secrets_file = args.client_secrets or os.environ.get("YOUTUBE_CLIENT_SECRETS_FILE")

    flow = None
    if client_secrets_file and os.path.exists(client_secrets_file):
        print(f"Loading credentials from: {client_secrets_file}")
        with open(client_secrets_file, "r") as f:
            secret_data = json.load(f)
            web_or_installed = secret_data.get("installed") or secret_data.get("web") or {}
            client_id = client_id or web_or_installed.get("client_id")
            client_secret = client_secret or web_or_installed.get("client_secret")

        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    else:
        if not client_id:
            client_id = input("Enter Google Client ID: ").strip()
        if not client_secret:
            client_secret = input("Enter Google Client Secret: ").strip()

        if not client_id or not client_secret:
            print("Error: Client ID and Client Secret are required.")
            sys.exit(1)

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [f"http://localhost:{args.port}/", "urn:ietf:wg:oauth:2.0:oob"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    print("\nStarting OAuth authorization flow...")
    print("If running on a remote server without GUI, a URL will be shown for you to visit.")

    try:
        # Try local server first (if browser is available or port can be forwarded)
        creds = flow.run_local_server(
            port=args.port,
            prompt="consent",
            access_type="offline",
            open_browser=False,
        )
    except Exception as e:
        print(f"Local server authorization could not start ({e}).")
        print("Falling back to console authorization URL:")
        flow.redirect_uri = f"http://localhost:{args.port}/"
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        print(f"\n1. Open this URL in your browser:\n\n{auth_url}\n")
        auth_code = input("2. Enter the authorization code / full redirected URL: ").strip()
        if "code=" in auth_code:
            match = re.search(r"code=([^&]+)", auth_code)
            if match:
                auth_code = match.group(1)
        flow.fetch_token(code=auth_code)
        creds = flow.credentials

    refresh_token = creds.refresh_token
    if not refresh_token:
        print("⚠️ Warning: Google did not return a refresh_token.")
        print("This happens if consent was already granted without prompt=consent.")
        print("To fix, go to your Google Account permissions, revoke access for this app, and run again.")
    else:
        print(f"\n✅ Refresh Token obtained successfully!")
        print(f"YOUTUBE_CLIENT_ID={client_id}")
        print(f"YOUTUBE_CLIENT_SECRET={client_secret}")
        print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")

        update_env_file(client_id, client_secret, refresh_token, args.env_path)
        print("\nTo apply the changes, restart the backend service:")
        print("  systemctl restart openshort-backend\n")


if __name__ == "__main__":
    main()
