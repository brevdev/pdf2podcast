from celery import Celery
import os
from docling.document_converter import DocumentConverter
import logging

logger = logging.getLogger(__name__)

celery_app = Celery(
    "pdf_converter",
    broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0"),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max runtime
    task_soft_time_limit=3300,  # 55 minutes soft limit
)


@celery_app.task(bind=True, max_retries=3)
def convert_pdf_task(self, file_path: str) -> str:  # Change return type hint
    try:
        converter = DocumentConverter()
        result = converter.convert(file_path)
        markdown = result.document.export_to_markdown()
        try:
            os.unlink(file_path)
            logger.info(f"Cleaned up file: {file_path}")
        except Exception as e:
            logger.error(f"Error cleaning up file: {e}")
        return markdown
    except Exception as exc:
        logger.error(f"Error converting PDF: {exc}")
        retry_in = 5 * (2**self.request.retries)
        raise self.retry(exc=exc, countdown=retry_in)
