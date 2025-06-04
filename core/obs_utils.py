from pathlib import Path
from obsws_python import obsws, requests

HOST = 'localhost'
PORT = 4455
PASSWORD = ''


def _connect():
    ws = obsws(HOST, PORT, PASSWORD)
    ws.connect()
    return ws


def start_recording(bereich: str, base_dir: Path):
    directory = base_dir / 'recordings' / bereich
    directory.mkdir(parents=True, exist_ok=True)
    ws = _connect()
    try:
        ws.call(requests.SetRecordDirectory(str(directory)))
        ws.call(requests.SetFilenameFormatting(f"{bereich}_%CCYY-%MM-%DD_%hh-%mm.wav"))
        ws.call(requests.StartRecord())
    finally:
        ws.disconnect()


def stop_recording():
    ws = _connect()
    try:
        ws.call(requests.StopRecord())
    finally:
        ws.disconnect()


def is_recording() -> bool:
    ws = _connect()
    try:
        status = ws.call(requests.GetRecordStatus())
        return status.get("outputActive", False)
    finally:
        ws.disconnect()
