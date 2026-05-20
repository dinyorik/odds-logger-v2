"""Shared helper: check user_token expiry from curl.txt.
user_token (cookie) is what the browser sends in x-auth header for MakeBetWeb.
access_token is a separate, shorter-lived token used for other endpoints."""
import base64
import json
import os
import re
import time

from paths import CURL_FILE


def get_token_seconds_left(curl_path: str = CURL_FILE):
    """
    Returns (seconds_left, error).
    seconds_left is int, negative if already expired.
    """
    if not os.path.exists(curl_path):
        return None, f"{curl_path} not found"
    try:
        with open(curl_path, encoding="utf-8") as f:
            curl = f.read()
    except OSError as e:
        return None, f"cannot read {curl_path}: {e}"

    m = re.search(r'user_token=([^;\s\'"]+)', curl)
    if not m:
        return None, "user_token not found in curl.txt"
    token = m.group(1)
    parts = token.split(".")
    if len(parts) < 2:
        return None, "user_token is not a JWT"

    try:
        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
    except (ValueError, base64.binascii.Error) as e:
        return None, f"cannot decode JWT payload: {e}"

    exp = payload.get("exp", 0)
    if not exp:
        return None, "JWT has no exp field"

    return int(exp) - int(time.time()), None


def format_state(seconds_left, error) -> str:
    """Human-readable summary."""
    if error:
        return f"token check failed: {error}"
    if seconds_left < 0:
        m = (-seconds_left) // 60
        return f"TOKEN EXPIRED {m} min ago"
    if seconds_left < 1800:
        return f"token expires in {seconds_left // 60} min - refresh curl.txt soon"
    return f"token valid for {seconds_left // 60} min"
