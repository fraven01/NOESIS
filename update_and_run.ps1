# NOESIS - Skript zum Aktualisieren und Starten der Anwendung

# --- Schritt 0: Gezieltes Beenden alter Prozesse ---
Write-Host "0. Beende alte Anwendungs-Prozesse (Web & Worker)..."

# Finde und beende den Web-Prozess über den Port (hier: 8000)
try {
    $webProcess = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction Stop
    if ($webProcess) {
        Write-Host "  -> Finde Web-Prozess auf Port 8000 mit PID $($webProcess.OwningProcess). Beende ihn..."
        Stop-Process -Id $webProcess.OwningProcess -Force
    }
} catch {
    Write-Host "  -> Kein Web-Prozess auf Port 8000 gefunden."
}

# Finde und beende die Worker-Prozesse über die Kommandozeile
# (Der Befehl muss ggf. an den Inhalt der 'Procfile' angepasst werden)
$workerProcesses = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' AND CommandLine LIKE '%manage.py%'"
if ($workerProcesses) {
    foreach ($worker in $workerProcesses) {
        # Filtere den Prozess, der dieses Skript ausführt, aus
        if ($worker.ProcessId -ne $PID) {
            Write-Host "  -> Finde Worker-Prozess mit PID $($worker.ProcessId). Beende ihn..."
            Stop-Process -Id $worker.ProcessId -Force
        }
    }
} else {
    Write-Host "  -> Keine laufenden Worker-Prozesse gefunden."
}

# Schritt 1: Aktuelle Änderungen aus dem Git-Repository ziehen
Write-Host "1. Führe 'git pull' aus, um das Repository zu aktualisieren..."
git pull

# Prüfen, ob der letzte Befehl erfolgreich war
if ($LASTEXITCODE -ne 0) {
    Write-Host "Fehler bei 'git pull'. Skript wird abgebrochen."
    exit 1
}

# Schritt 2: Frontend-Abhängigkeiten bauen
Write-Host "2. Baue Frontend-Assets mit npm..."
npm --prefix theme/static_src run build

# Prüfen, ob der letzte Befehl erfolgreich war
if ($LASTEXITCODE -ne 0) {
    Write-Host "Fehler bei 'npm run build'. Skript wird abgebrochen."
    exit 1
}

# Schritt 3: Anwendung mit Honcho starten
Write-Host "3. Starte die Anwendung mit 'honcho start'..."
honcho start

Write-Host "Skript beendet."