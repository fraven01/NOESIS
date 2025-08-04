# Deployment-Notizen

## Erforderliche Umgebungsvariablen

- `DJANGO_SECRET_KEY`: Geheimschlüssel der Django-Installation.
- `OPENAI_API_KEY`: API-Schlüssel für OpenAI-basierte Funktionen (optional).
- `GOOGLE_API_KEY`: API-Schlüssel für Gemini-Modelle (optional).
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`: Zugangsdaten für PostgreSQL. Sind sie nicht gesetzt, verwendet NOESIS automatisch SQLite.

## Medienverzeichnis

Hochgeladene Dateien werden im Verzeichnis gespeichert, das durch `MEDIA_ROOT` festgelegt ist. Standardmäßig entspricht dies `BASE_DIR / "media"`. Der Benutzer, der den `qcluster`-Worker-Prozess ausführt, benötigt Lese- und Schreibrechte auf dieses Verzeichnis und auf alle enthaltenen Dateien.
