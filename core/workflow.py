from django_q.tasks import async_task
import logging

from .models import BVProject, BVProjectStatusHistory, ProjectStatus, Gutachten


def set_project_status(projekt: BVProject, status: str) -> None:
    """Setzt den Status eines BVProject.

    :param projekt: Das zu aktualisierende Projekt
    :param status: Schlüssel des neuen Status
    :raises ValueError: Wenn der Status ungültig ist
    """
    try:
        status_obj = ProjectStatus.objects.get(key=status)
    except ProjectStatus.DoesNotExist as exc:
        raise ValueError("Ungültiger Status") from exc
    projekt.status = status_obj
    projekt.save(update_fields=["status"])
    BVProjectStatusHistory.objects.create(projekt=projekt, status=status_obj)


logger = logging.getLogger(__name__)


def task_completion_hook(task) -> None:
    """Einfacher Hook, der den Abschluss eines Tasks protokolliert."""
    logger.info("Task %s abgeschlossen", task)


def run_generate_gutachten(gutachten: Gutachten) -> None:
    """Startet die asynchrone Erstellung eines Gutachtens."""

    logger.info("Starting Gutachten generation for Gutachten %s", gutachten.id)
    async_task(
        "core.llm_tasks.worker_generate_gutachten",
        gutachten.id,
        task_name=f"Generate Gutachten #{gutachten.id}",
        hook="core.workflow.task_completion_hook",
    )
