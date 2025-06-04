from pathlib import Path
import obsws_python as obs # This is likely the correct way to import

HOST = 'localhost'
PORT = 4455
PASSWORD = 'BpJznpdkIZC2pevm'

def _connect():
    ws = obs.ReqClient(host=HOST, port=PORT, password=PASSWORD, timeout=3)
    return ws

def start_recording(bereich: str, base_dir: Path):
    directory = base_dir / 'recordings' / bereich
    directory.mkdir(parents=True, exist_ok=True)
    ws = _connect()
    try:
        ws.set_record_directory(str(directory))
        ws.set_filename_formatting(f"{bereich}_%CCYY-%MM-%DD_%hh-%mm.wav")
        ws.start_record()
    finally:
        pass # ws.disconnect() might not be needed for ReqClient

def stop_recording():
    ws = _connect()
    try:
        ws.stop_record()
    finally:
        pass # ws.disconnect() might not be needed

def is_recording() -> bool:
    ws = _connect()
    try:
        status = ws.get_record_status()
        return status.output_active
    finally:
        pass # ws.disconnect() might not be needed