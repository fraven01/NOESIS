from pathlib import Path
import obsws_python as obs

HOST = 'localhost'
PORT = 4455
PASSWORD = 'BpJznpdkIZC2pevm'


def _connect() -> obs.ReqClient:
    """Create a connection to the OBS websocket."""
    return obs.ReqClient(host=HOST, port=PORT, password=PASSWORD, timeout=3)


def start_recording(bereich: str, base_dir: Path) -> None:
    """Start OBS recording. OBS must already be configured with the correct
    record directory for the given ``bereich``. The directory is created if it
    does not exist so that the path exists on the filesystem."""
    directory = base_dir / 'recordings' / bereich
    directory.mkdir(parents=True, exist_ok=True)
    ws = _connect()
    try:
        ws.start_record()
    finally:
        pass  # no disconnect needed for ReqClient


def stop_recording() -> None:
    """Stop OBS recording."""
    ws = _connect()
    try:
        ws.stop_record()
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
