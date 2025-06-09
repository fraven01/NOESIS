import os
from pathlib import Path

import time

import obsws_python as obs

HOST = "localhost"
PORT = 4455
PASSWORD = os.getenv("OBS_PASSWORD", "")


def _connect() -> obs.ReqClient:
    """Create a connection to the OBS websocket."""
    return obs.ReqClient(host=HOST, port=PORT, password=PASSWORD, timeout=3)


def start_recording(bereich: str, base_dir: Path) -> None:
    """Start OBS recording. OBS must already be configured with the correct
    record directory for the given ``bereich``. The directory is created if it
    does not exist so that the path exists on the filesystem."""
    directory = base_dir / "recordings" / bereich
    directory.mkdir(parents=True, exist_ok=True)
    ws = _connect()
    try:
        ws.start_record()
    finally:
        pass  # no disconnect needed for ReqClient


def stop_recording(wait: bool = True, timeout: float = 10.0) -> None:
    """Stop OBS recording.

    If ``wait`` is ``True`` (default), this call blocks until OBS reports that
    recording has actually stopped or until ``timeout`` seconds have elapsed.
    """

    ws = _connect()
    try:
        ws.stop_record()
        if wait:
            end = time.time() + timeout
            while time.time() < end:
                status = ws.get_record_status()
                if not status.output_active:
                    break
                time.sleep(0.5)
    finally:
        pass


def is_recording() -> bool:
    """Return True if OBS is currently recording."""
    ws = _connect()
    try:
        status = ws.get_record_status()
        return status.output_active
    finally:
        pass
