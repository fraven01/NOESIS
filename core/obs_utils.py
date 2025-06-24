import os
from pathlib import Path

import time

import obsws_python as obs

HOST = "localhost"
PORT = 4455
PASSWORD = os.getenv("OBS_PASSWORD", "")


def _connect() -> obs.ReqClient:
    """Stellt eine Verbindung zum OBS-Websocket her."""
    return obs.ReqClient(host=HOST, port=PORT, password=PASSWORD, timeout=3)


def start_recording(bereich: str, base_dir: Path) -> None:
    """Startet die OBS-Aufnahme. OBS muss bereits mit dem richtigen
    Aufnahmeverzeichnis für den angegebenen ``bereich`` konfiguriert sein.
    Das Verzeichnis wird angelegt, falls es nicht existiert, sodass der Pfad im
    Dateisystem vorhanden ist."""
    directory = base_dir / "recordings" / bereich
    directory.mkdir(parents=True, exist_ok=True)
    ws = _connect()
    try:
        ws.start_record()
    finally:
        pass  # no disconnect needed for ReqClient


def stop_recording(wait: bool = True, timeout: float = 10.0) -> None:
    """Beendet die OBS-Aufnahme.

    Wenn ``wait`` ``True`` ist (Standard), blockiert der Aufruf, bis OBS das
    Ende der Aufnahme bestätigt oder ``timeout`` Sekunden verstrichen sind.
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
    """Gibt ``True`` zurück, falls OBS aktuell aufnimmt."""
    ws = _connect()
    try:
        status = ws.get_record_status()
        return status.output_active
    finally:
        pass
