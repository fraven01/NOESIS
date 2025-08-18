#!/usr/bin/env python3
"""Diagnoseskript zum Testen der Datenbankverbindung in Cloud Run."""

import os
import sys

import psycopg2


print("Starting database connection test...")

try:
    # Lese die Credentials aus den Umgebungsvariablen
    db_name = os.environ.get("DB_NAME")
    db_user = os.environ.get("DB_USER")
    db_pass = os.environ.get("DB_PASSWORD")
    db_host_socket = f"/cloudsql/{os.environ.get('DB_HOST')}"

    print(
        f"Attempting to connect to db='{db_name}' user='{db_user}' host='{db_host_socket}'"
    )

    # Baue die Verbindungszeichenfolge
    conn_string = f"dbname='{db_name}' user='{db_user}' password='{db_pass}' host='{db_host_socket}'"

    # Stelle die Verbindung her
    conn = psycopg2.connect(conn_string)
    print("SUCCESS: Database connection established successfully!")
    conn.close()
    sys.exit(0)  # Erfolgreich beenden

except Exception as e:  # noqa: BLE001
    print("ERROR: Database connection failed.")
    print("-----------------------------------")
    print(f"Error Type: {type(e).__name__}")
    print(f"Error Details: {e}")
    print("-----------------------------------")
    sys.exit(1)  # Mit Fehler beenden
