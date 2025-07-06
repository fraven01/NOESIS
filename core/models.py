from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import models
from pathlib import Path


class BVProjectManager(models.Manager):
    """Manager mit Unterstützung für das alte ``software_typen``-Feld."""

    def create(self, *args, **kwargs):
        software = kwargs.pop("software_typen", None)
        projekt = super().create(*args, **kwargs)
        if software:
            if isinstance(software, str):
                names = [s.strip() for s in software.split(",") if s.strip()]
            else:
                names = [s.strip() for s in software if s.strip()]
            for name in names:
                BVSoftware.objects.create(projekt=projekt, name=name)
            if not projekt.title and names:
                projekt.title = ", ".join(names)
                projekt.save(update_fields=["title"])
        return projekt


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

    objects = BVProjectManager()

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        """Speichert das Projekt und legt bei Bedarf einen Status an."""
        is_new = self._state.adding
        if not self.status:
            self.status = ProjectStatus.objects.filter(is_default=True).first()
        super().save(*args, **kwargs)
        if is_new:
            BVProjectStatusHistory.objects.create(projekt=self, status=self.status)

    def __str__(self) -> str:
        return self.title

    @property
    def software_list(self) -> list[str]:
        return list(self.bvsoftware_set.values_list("name", flat=True))

    @property
    def software_string(self) -> str:
        return ", ".join(self.software_list)

    # Alias f\u00fcr alte Feldbezeichnung
    @property
    def software_typen(self) -> str:  # pragma: no cover - kompatibel
        return self.software_string


class BVSoftware(models.Model):
    """Software-Eintrag innerhalb eines Projekts."""

    projekt = models.ForeignKey(BVProject, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


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
    anlage4_config = models.ForeignKey(
        "Anlage4Config", on_delete=models.SET_NULL, null=True, blank=True
    )
    anlage4_parser_config = models.ForeignKey(
        "Anlage4ParserConfig", on_delete=models.SET_NULL, null=True, blank=True
    )
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
    manual_reviewed = models.BooleanField("Manuell geprüft", default=False)
    verhandlungsfaehig = models.BooleanField("Verhandlungsfähig", default=False)

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


class SoftwareType(models.Model):
    """Typ einer Software-Komponente."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class Gutachten(models.Model):
    """Gutachten zu einer Software-Komponente."""

    software_knowledge = models.OneToOneField(
        SoftwareKnowledge,
        on_delete=models.CASCADE,
        related_name="gutachten",
    )
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        proj = self.software_knowledge.projekt
        name = self.software_knowledge.software_name
        return f"{proj} - {name}"


class LLMRole(models.Model):
    """Definiert eine wiederverwendbare LLM-Rolle."""

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Ein kurzer, wiedererkennbarer Name für die Rolle.",
    )
    role_prompt = models.TextField(
        help_text=(
            "Der eigentliche System-Prompt, der die Persona und Anweisungen "
            "für die KI definiert."
        )
    )
    is_default = models.BooleanField(
        default=False,
        help_text=(
            "Soll diese Rolle als globaler Standard verwendet werden, "
            "wenn einem Prompt keine spezifische Rolle zugewiesen ist?"
        ),
    )

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name

    def clean(self) -> None:
        """Stellt sicher, dass nur eine Rolle als Standard markiert ist."""
        if self.is_default and LLMRole.objects.filter(is_default=True).exclude(pk=self.pk).exists():
            raise ValidationError(
                "Es kann nur eine Rolle als globaler Standard definiert werden."
            )

class Prompt(models.Model):
    """Speichert Texte für LLM-Prompts."""

    name = models.CharField(max_length=50, unique=True)
    text = models.TextField()
    role = models.ForeignKey(
        LLMRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=(
            "Optionale, spezifische Rolle für diesen Prompt. Überschreibt die "
            "globale Standard-Rolle."
        ),
    )
    use_system_role = models.BooleanField(
        default=True,
        help_text=(
            "Wenn aktiviert, wird diesem Prompt der globale oder zugewiesene "
            "Rollen-Prompt vorangestellt. Deaktivieren für einfache Abfragen, "
            "die eine strikte, kurze Antwort erfordern."
        ),
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Area(models.Model):
    """Bereich wie 'work' oder 'personal'."""

    slug = models.SlugField(unique=True)
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Einzigartiger Name des Bereichs, z.B. 'work' oder 'personal'",
    )
    image = models.ImageField(upload_to="area_images/", blank=True, null=True)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="UserAreaAccess",
        related_name="areas",
        blank=True,
        help_text="Benutzer mit Zugriff auf diesen Bereich.",
    )

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.name


class LLMConfig(models.Model):
    """Konfiguration der LLM-Modelle."""

    default_model = models.CharField(max_length=100, blank=True)
    gutachten_model = models.CharField(max_length=100, blank=True)
    anlagen_model = models.CharField(max_length=100, blank=True)
    vision_model = models.CharField(max_length=100, blank=True)
    available_models = models.JSONField(null=True, blank=True)
    models_changed = models.BooleanField(default=False)

    class Meta:
        verbose_name = "LLM Konfiguration"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "LLMConfig"

    @classmethod
    def get_instance(cls) -> "LLMConfig":
        """Liefert die einzige vorhandene Konfiguration oder legt sie an."""
        return cls.objects.first() or cls.objects.create()

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
        if kind == "vision":
            return cfg.vision_model or cfg.default_model or settings.GOOGLE_VISION_MODEL
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
            "vision": {
                "model": cls.get_default("vision"),
                "label": "Vision",
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


    PARSER_CHOICES = [
        ("auto", "Automatisch"),
        ("table_only", "Nur Tabellen"),
        ("text_only", "Nur Text"),
    ]

    parser_mode = models.CharField(
        max_length=20,
        choices=PARSER_CHOICES,
        default="auto",
    )

    parser_order = models.JSONField(
        default=list,
        help_text="Reihenfolge der zu verwendenden Parser.",
    )

    text_technisch_verfuegbar_true = models.JSONField(

        default=list,
        help_text="Reihenfolge der zu verwendenden Parser.",
    )


    class Meta:
        verbose_name = "Anlage2 Konfiguration"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "Anlage2Config"

    @classmethod
    def get_instance(cls) -> "Anlage2Config":
        """Liefert die einzige vorhandene Konfiguration oder legt sie an."""
        return cls.objects.first() or cls.objects.create(parser_order=["table"])


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


class FormatBParserRule(models.Model):
    """Regel für den vereinfachten Textparser (Format B)."""

    FIELD_CHOICES = [
        ("technisch_verfuegbar", "Technisch verfügbar"),
        ("einsatz_telefonica", "Einsatz Telefónica"),
        ("zur_lv_kontrolle", "Zur LV-Kontrolle"),
        ("ki_beteiligung", "KI-Beteiligung"),
    ]

    key = models.CharField(max_length=20, unique=True)
    target_field = models.CharField(max_length=50, choices=FIELD_CHOICES)
    ordering = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordering", "key"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.key


class AntwortErkennungsRegel(models.Model):
    """Regel zum Erkennen von Antworten in unstrukturiertem Text."""

    regel_name = models.CharField(max_length=100)
    erkennungs_phrase = models.CharField(max_length=200)
    ziel_feld = models.CharField(
        max_length=50,
        choices=FormatBParserRule.FIELD_CHOICES,
    )
    wert = models.BooleanField()
    prioritaet = models.IntegerField(default=0)

    class Meta:
        ordering = ["prioritaet"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.regel_name


class Anlage4Config(models.Model):
    """Konfiguration f\u00fcr Anlage 4."""

    table_columns = models.JSONField(default=list, blank=True)
    regex_patterns = models.JSONField(default=list, blank=True)
    negative_patterns = models.JSONField(default=list, blank=True)
    prompt_template = models.TextField(blank=True)

    class Meta:
        verbose_name = "Anlage4 Konfiguration"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "Anlage4Config"


class Anlage4ParserConfig(models.Model):
    """Konfiguration für den Anlage-4-Parser."""

    table_columns = models.JSONField(default=list, blank=True)
    delimiter_phrase = models.CharField(
        max_length=255,
        default=r"Name der (\d+|\w+)\. Auswertung",
        help_text="Regulärer Ausdruck, der den Beginn einer neuen Auswertung markiert.",
    )
    gesellschaften_phrase = models.CharField(
        max_length=255,
        default="Gesellschaften, in denen die Auswertung verwendet wird:",
        help_text="Die exakte Phrase, die dem Wert für 'Gesellschaften' vorangeht.",
    )
    fachbereiche_phrase = models.CharField(
        max_length=255,
        default="Fachbereiche, in denen die Auswertung eingesetzt wird:",
        help_text="Die exakte Phrase, die dem Wert für 'Fachbereiche' vorangeht.",
    )
    prompt_extraction = models.TextField(blank=True)
    prompt_plausibility = models.TextField(blank=True)

    class Meta:
        verbose_name = "Anlage4 Parser Konfiguration"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return "Anlage4ParserConfig"


class Tile(models.Model):
    """Kachel für das Dashboard."""

    PERSONAL = "personal"
    WORK = "work"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    url_name = models.CharField(max_length=100)
    areas = models.ManyToManyField(
        Area,
        related_name="tiles",
        help_text="Die Bereiche, in denen diese Kachel angezeigt wird.",
    )
    icon = models.CharField(max_length=50, blank=True)
    description = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to="tile_images/", blank=True, null=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Übergeordnete Kachel",
    )
    permission = models.OneToOneField(
        Permission,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Benötigte Berechtigung",
    )
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


class UserAreaAccess(models.Model):
    """Verknüpfung zwischen Benutzer und Bereich."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    area = models.ForeignKey(Area, on_delete=models.CASCADE)

    class Meta:
        unique_together = [("user", "area")]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.user} -> {self.area}"


class Anlage2Function(models.Model):
    """Funktion aus Anlage 2."""

    name = models.CharField(max_length=200, unique=True)
    detection_phrases = models.JSONField(default=dict, blank=True)

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

    def get_lookup_key(self) -> str:
        """Liefert den eindeutigen Lookup-Schlüssel für dieses Ergebnis."""
        sub_id = None
        if isinstance(self.raw_json, dict):
            sub_id = self.raw_json.get("subquestion_id")
        if sub_id:
            try:
                sub = Anlage2SubQuestion.objects.get(pk=sub_id)
                return f"{self.funktion.name}: {sub.frage_text}"
            except Anlage2SubQuestion.DoesNotExist:
                pass
        return self.funktion.name


class Anlage2SubQuestion(models.Model):
    """Teilfrage zu einer Anlage-2-Funktion."""

    funktion = models.ForeignKey(Anlage2Function, on_delete=models.CASCADE)
    frage_text = models.TextField()
    detection_phrases = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.frage_text
