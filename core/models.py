from django.conf import settings
from django.db import models
from pathlib import Path


def recording_upload_path(instance, filename):
    slug = (
        instance.bereich.slug if hasattr(instance.bereich, "slug") else instance.bereich
    )
    return f"recordings/{slug}/{filename}"


def transcript_upload_path(instance, filename):
    stem = Path(filename).stem
    slug = (
        instance.bereich.slug if hasattr(instance.bereich, "slug") else instance.bereich
    )
    return f"transcripts/{slug}/{stem}.md"


class Recording(models.Model):
    PERSONAL = "personal"
    WORK = "work"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    bereich = models.ForeignKey("core.Area", on_delete=models.CASCADE)
    audio_file = models.FileField(upload_to=recording_upload_path)
    transcript_file = models.FileField(upload_to=transcript_upload_path, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    duration = models.FloatField(null=True, blank=True)
    excerpt = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        slug = self.bereich.slug if hasattr(self.bereich, "slug") else self.bereich
        return f"{self.audio_file.name} ({slug})"

    @property
    def recording_path(self):
        return self.audio_file.name

    @property
    def transcript_path(self):
        return self.transcript_file.name if self.transcript_file else ""


class ProjectStatus(models.Model):
    """Möglicher Status eines BVProject."""

    name = models.CharField(max_length=100)
    key = models.CharField(max_length=50, unique=True)
    ordering = models.PositiveIntegerField(default=0)
    is_default = models.BooleanField(default=False)
    is_done_status = models.BooleanField(default=False)

    class Meta:
        ordering = ["ordering", "name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class BVProject(models.Model):
    """Projekt zur Bewertung von Betriebsvereinbarungen."""

    title = models.CharField("Titel", max_length=50, blank=True)
    beschreibung = models.TextField("Beschreibung", blank=True)
    software_typen = models.CharField("Software-Typen", max_length=200, blank=True)
    status = models.ForeignKey(
        ProjectStatus,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="projects",
    )
    created_at = models.DateTimeField("Erstellt am", auto_now_add=True)
    classification_json = models.JSONField("Klassifizierung", null=True, blank=True)
    gutachten_file = models.FileField("Gutachten", upload_to="gutachten", blank=True)
    gutachten_function_note = models.TextField("LLM-Hinweis Gutachten", blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        """Speichert das Projekt und setzt den Titel aus den Software-Namen."""
        if self.software_typen:
            cleaned = ", ".join(
                [s.strip() for s in self.software_typen.split(",") if s.strip()]
            )
            self.software_typen = cleaned
            if not self.title:
                self.title = cleaned
        is_new = self._state.adding
        if not self.status:
            self.status = ProjectStatus.objects.filter(is_default=True).first()
        super().save(*args, **kwargs)
        if is_new:
            BVProjectStatusHistory.objects.create(projekt=self, status=self.status)

    def __str__(self) -> str:
        return self.title


def get_default_project_status():
    """
    Gibt die ID des als Standard markierten Projektstatus zurück.
    """
    # Annahme: ProjectStatus ist bereits importiert oder in derselben Datei definiert
    default_status = ProjectStatus.objects.filter(is_default=True).first()
    if default_status:
        return default_status.pk
    # Fallback, falls kein Standard definiert ist (sollte nicht passieren)
    first_status = ProjectStatus.objects.order_by("ordering").first()
    if first_status:
        return first_status.pk
    return None


class BVProjectStatusHistory(models.Model):
    """Historie der Projektstatus."""

    projekt = models.ForeignKey(
        BVProject,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    status = models.ForeignKey(
        ProjectStatus, on_delete=models.PROTECT, default=get_default_project_status
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["changed_at"]

    def __str__(self) -> str:
        return f"{self.projekt} -> {self.status.name}"


class BVProjectFile(models.Model):
    """Datei-Anlagen zu einem BVProject."""

    projekt = models.ForeignKey(
        BVProject,
        on_delete=models.CASCADE,
        related_name="anlagen",
    )
    anlage_nr = models.PositiveSmallIntegerField(
        "Anlage Nr",
        choices=[(i, str(i)) for i in range(1, 7)],
    )
    upload = models.FileField("Upload", upload_to="bv_files")
    text_content = models.TextField("Textinhalt", blank=True)
    analysis_json = models.JSONField("Analyse", null=True, blank=True)
    manual_analysis_json = models.JSONField(blank=True, null=True)
    manual_comment = models.TextField("Kommentar", blank=True)
    question_review = models.JSONField(blank=True, null=True)
    verification_json = models.JSONField(
        blank=True,
        null=True,
        help_text="Ergebnis der KI-gestützten Verifizierung der Funktionen.",
    )

    class Meta:
        ordering = ["anlage_nr"]

    def __str__(self) -> str:
        return f"Anlage {self.anlage_nr} zu {self.projekt}"


class SoftwareKnowledge(models.Model):
    """Kenntnisstand des LLM zu einer Software in einem Projekt."""

    projekt = models.ForeignKey(
        BVProject,
        on_delete=models.CASCADE,
        related_name="softwareknowledge",
    )
    software_name = models.CharField(max_length=100)
    is_known_by_llm = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    last_checked = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("projekt", "software_name")
        ordering = ["software_name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.software_name


class Prompt(models.Model):
    """Speichert Texte für LLM-Prompts."""

    name = models.CharField(max_length=50, unique=True)
    text = models.TextField()

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Area(models.Model):
    """Bereich wie 'work' oder 'personal'."""

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    image = models.ImageField(upload_to="area_images/", blank=True, null=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.name


class LLMConfig(models.Model):
    """Konfiguration der LLM-Modelle."""

    default_model = models.CharField(max_length=100, blank=True)
    gutachten_model = models.CharField(max_length=100, blank=True)
    anlagen_model = models.CharField(max_length=100, blank=True)
    available_models = models.JSONField(null=True, blank=True)
    models_changed = models.BooleanField(default=False)

    class Meta:
        verbose_name = "LLM Konfiguration"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "LLMConfig"

    @classmethod
    def get_default(cls, kind: str = "default") -> str:
        """Gibt das Standardmodell für einen Typ zurück."""
        from django.conf import settings

        cfg = cls.objects.first()
        if not cfg:
            return settings.GOOGLE_LLM_MODEL
        if kind == "gutachten":
            return cfg.gutachten_model or cfg.default_model or settings.GOOGLE_LLM_MODEL
        if kind == "anlagen":
            return cfg.anlagen_model or cfg.default_model or settings.GOOGLE_LLM_MODEL
        return cfg.default_model or settings.GOOGLE_LLM_MODEL

    @classmethod
    def get_available(cls) -> list[str]:
        from django.conf import settings

        cfg = cls.objects.first()
        if cfg and cfg.available_models:
            return list(cfg.available_models)
        return settings.GOOGLE_AVAILABLE_MODELS

    @classmethod
    def get_categories(cls) -> dict[str, dict[str, str]]:
        """Mapping von Modellkategorien auf Modellnamen und Labels."""
        return {
            "default": {
                "model": cls.get_default("default"),
                "label": "Standard",
            },
            "gutachten": {
                "model": cls.get_default("gutachten"),
                "label": "Gutachten",
            },
            "anlagen": {
                "model": cls.get_default("anlagen"),
                "label": "Anlagen",
            },
        }


class Anlage1Config(models.Model):
    """Steuert die Aktivierung einzelner Fragen in Anlage 1."""

    enable_q1 = models.BooleanField(default=True)
    enable_q2 = models.BooleanField(default=True)
    enable_q3 = models.BooleanField(default=True)
    enable_q4 = models.BooleanField(default=True)
    enable_q5 = models.BooleanField(default=True)
    enable_q6 = models.BooleanField(default=True)
    enable_q7 = models.BooleanField(default=True)
    enable_q8 = models.BooleanField(default=True)
    enable_q9 = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Anlage1 Konfiguration"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "Anlage1Config"


class Anlage1Question(models.Model):
    """Frage aus Anlage 1.

    Eine Frage wird nur ber\xfccksichtigt, wenn sowohl dieses ``enabled``-Flag
    als auch das entsprechende Feld in :class:`Anlage1Config` gesetzt sind.
    """

    num = models.PositiveSmallIntegerField(unique=True)
    text = models.TextField()
    enabled = models.BooleanField(default=True)
    parser_enabled = models.BooleanField(default=True)
    llm_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["num"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Frage {self.num}"

    def save(self, *args, **kwargs) -> None:
        """Speichert die Frage und legt ggf. eine erste Variante an."""
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new and not self.variants.exists():
            Anlage1QuestionVariant.objects.create(question=self, text=self.text)


class Anlage1QuestionVariant(models.Model):
    """Alternative Formulierungen für eine Frage aus Anlage 1."""

    question = models.ForeignKey(
        Anlage1Question,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    text = models.TextField()

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Variante zu Frage {self.question_id}"


class Anlage2Config(models.Model):
    """Konfiguration der Spaltenüberschriften für Anlage 2."""

    #: Hilfsfeld, um nur eine Instanz zuzulassen
    singleton_enforcer = models.BooleanField(default=True, unique=True, editable=False)

    enforce_subquestion_override = models.BooleanField(
        default=False,
        help_text=(
            "Wenn aktiviert, wird eine Hauptfunktion automatisch als 'technisch "
            "vorhanden' markiert, wenn mindestens eine ihrer Unterfragen als "
            "'technisch vorhanden' bewertet wird."
        ),
    )

    class Meta:
        verbose_name = "Anlage2 Konfiguration"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "Anlage2Config"

    @classmethod
    def get_instance(cls) -> "Anlage2Config":
        """Liefert die einzige vorhandene Konfiguration oder legt sie an."""
        return cls.objects.first() or cls.objects.create()


class Anlage2ColumnHeading(models.Model):
    """Mögliche Überschrift für ein Anlage-2-Feld."""

    FIELD_CHOICES = [
        ("technisch_vorhanden", "Technisch vorhanden"),
        ("einsatz_bei_telefonica", "Einsatz bei Telefónica"),
        ("zur_lv_kontrolle", "Zur LV-Kontrolle"),
        ("ki_beteiligung", "KI-Beteiligung"),
    ]

    config = models.ForeignKey(
        Anlage2Config, on_delete=models.CASCADE, related_name="headers"
    )
    field_name = models.CharField(max_length=50, choices=FIELD_CHOICES)
    text = models.CharField(max_length=200)

    class Meta:
        ordering = ["field_name", "id"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.field_name}: {self.text}"


class Anlage2GlobalPhrase(models.Model):
    """Globale Erkennungsphrase für Anlage 2."""

    PHRASE_TYPE_CHOICES = [
        ("technisch_verfuegbar_true", "Technisch vorhanden: Ja"),
        ("technisch_verfuegbar_false", "Technisch vorhanden: Nein"),
        ("einsatz_telefonica_true", "Einsatz bei Telefónica: Ja"),
        ("einsatz_telefonica_false", "Einsatz bei Telefónica: Nein"),
        ("zur_lv_kontrolle_true", "Zur LV-Kontrolle: Ja"),
        ("zur_lv_kontrolle_false", "Zur LV-Kontrolle: Nein"),
        ("ki_beteiligung_true", "KI-Beteiligung: Ja"),
        ("ki_beteiligung_false", "KI-Beteiligung: Nein"),
    ]

    config = models.ForeignKey(
        Anlage2Config, on_delete=models.CASCADE, related_name="global_phrases"
    )
    phrase_type = models.CharField(max_length=50, choices=PHRASE_TYPE_CHOICES)
    phrase_text = models.CharField(
        max_length=200, help_text="Die exakte Phrase, nach der im Text gesucht wird."
    )

    class Meta:
        ordering = ["phrase_type", "phrase_text"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.get_phrase_type_display()}: {self.phrase_text}"


class Tile(models.Model):
    """Kachel für das Dashboard."""

    PERSONAL = "personal"
    WORK = "work"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    bereich = models.ForeignKey("core.Area", on_delete=models.CASCADE)
    url_name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, blank=True)
    description = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to="tile_images/", blank=True, null=True)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="UserTileAccess",
        related_name="tiles",
    )

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.name


class UserTileAccess(models.Model):
    """Verknüpfung zwischen Benutzer und Tile."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tile = models.ForeignKey(Tile, on_delete=models.CASCADE)

    class Meta:
        unique_together = [("user", "tile")]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.user} -> {self.tile}"


class Anlage2Function(models.Model):
    """Funktion aus Anlage 2."""

    name = models.CharField(max_length=200, unique=True)
    detection_phrases = models.JSONField(
        blank=True,
        default=dict,
        help_text="JSON-Objekt zur Speicherung von Erkennungsphrasen für den Text-Parser.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class Anlage2FunctionResult(models.Model):
    """Speichert das Prüfergebnis einer Anlage-2-Funktion."""

    projekt = models.ForeignKey(BVProject, on_delete=models.CASCADE)
    funktion = models.ForeignKey(Anlage2Function, on_delete=models.CASCADE)
    technisch_verfuegbar = models.BooleanField(null=True)
    ki_beteiligung = models.BooleanField(null=True)
    raw_json = models.JSONField(null=True, blank=True)
    source = models.CharField(max_length=10, default="llm")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("projekt", "funktion")]
        ordering = ["funktion__name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.projekt} - {self.funktion}"


class Anlage2SubQuestion(models.Model):
    """Teilfrage zu einer Anlage-2-Funktion."""

    funktion = models.ForeignKey(Anlage2Function, on_delete=models.CASCADE)
    frage_text = models.TextField()
    detection_phrases = models.JSONField(
        blank=True,
        default=dict,
        help_text="JSON-Objekt zur Speicherung von Erkennungsphrasen für den Text-Parser.",
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.frage_text
