import os
import threading
import time
from datetime import datetime

import requests
from django.conf import settings

ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"
REQUEST_TIMEOUT = 10
# Refresh the cached token this many seconds before Zoom says it expires.
TOKEN_EXPIRY_MARGIN = 60


class ZoomError(Exception):
    """Base error for Zoom API failures. Callers must never let these fail an event write."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class ZoomNotConfigured(ZoomError):
    """Raised when the ZOOM_* environment variables are not set."""


_token_cache = {"access_token": None, "expires_at": 0.0}
_token_lock = threading.Lock()


def _get_credentials():
    account_id = os.getenv("ZOOM_ACCOUNT_ID")
    client_id = os.getenv("ZOOM_CLIENT_ID")
    client_secret = os.getenv("ZOOM_CLIENT_SECRET")
    if not (account_id and client_id and client_secret):
        raise ZoomNotConfigured("Set ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, and ZOOM_CLIENT_SECRET to enable Zoom.")
    return account_id, client_id, client_secret


def _get_access_token():
    account_id, client_id, client_secret = _get_credentials()
    with _token_lock:
        if _token_cache["access_token"] and time.monotonic() < _token_cache["expires_at"]:
            return _token_cache["access_token"]

        response = requests.post(
            ZOOM_TOKEN_URL,
            data={"grant_type": "account_credentials", "account_id": account_id},
            auth=(client_id, client_secret),
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code != 200:
            raise ZoomError(f"Zoom token request failed: {response.text}", status_code=response.status_code)

        payload = response.json()
        _token_cache["access_token"] = payload["access_token"]
        _token_cache["expires_at"] = time.monotonic() + payload.get("expires_in", 3600) - TOKEN_EXPIRY_MARGIN
        return _token_cache["access_token"]


def _request(method, path, json=None):
    token = _get_access_token()
    response = requests.request(
        method,
        f"{ZOOM_API_BASE}{path}",
        json=json,
        headers={"Authorization": f"Bearer {token}"},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code >= 400:
        raise ZoomError(
            f"Zoom API {method} {path} failed ({response.status_code}): {response.text}",
            status_code=response.status_code,
        )
    return response


def _meeting_payload(event):
    start = datetime.combine(event.event_date, event.start_time)
    end = datetime.combine(event.event_date, event.end_time)
    return {
        "topic": event.title,
        "type": 2,  # scheduled meeting
        "start_time": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "duration": max(1, int((end - start).total_seconds() // 60)),
        "timezone": settings.TIME_ZONE,
        "settings": {
            "waiting_room": False,
            "join_before_host": True,
            "mute_upon_entry": False,
            "auto_recording": "cloud",
        },
    }


def create_meeting(host_email, event):
    response = _request("POST", f"/users/{host_email}/meetings", json=_meeting_payload(event))
    payload = response.json()
    return {"id": payload["id"], "join_url": payload["join_url"]}


def update_meeting(meeting_id, event):
    _request("PATCH", f"/meetings/{meeting_id}", json=_meeting_payload(event))


def delete_meeting(meeting_id):
    _request("DELETE", f"/meetings/{meeting_id}")
