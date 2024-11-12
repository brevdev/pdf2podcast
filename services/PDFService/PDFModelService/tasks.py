from celery import Celery
import os
from docling.document_converter import DocumentConverter
from docling_core.types.doc import ImageRefMode
import logging
from typing import List, Dict
from pathlib import Path

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
def convert_pdf_task(self, file_paths: List[str]) -> List[Dict[str, str]]:
    try:
        converter = DocumentConverter()

        # Convert paths to Path objects for docling
        input_paths = [Path(path) for path in file_paths]

        # Use batch conversion
        results = []
        conversion_results = converter.convert_all(
            input_paths,
            raises_on_error=False,  # Continue processing even if some files fail
        )

        # Process results
        for result in conversion_results:
            file_path = str(result.input.file)
            try:
                if result.status == "SUCCESS":
                    markdown = result.document.export_to_markdown(
                        image_mode=ImageRefMode.EMBEDDED
                    )
                    results.append(
                        {
                            "filename": os.path.basename(file_path),
                            "status": "success",
                            "content": markdown,
                        }
                    )
                else:
                    results.append(
                        {
                            "filename": os.path.basename(file_path),
                            "status": "failed",
                            "error": str(result.errors)
                            if hasattr(result, "errors")
                            else "Conversion failed",
                        }
                    )
            finally:
                # Clean up the temporary file
                try:
                    os.unlink(file_path)
                    logger.info(f"Cleaned up file: {file_path}")
                except Exception as e:
                    logger.error(f"Error cleaning up file: {e}")

        return results

    except Exception as exc:
        logger.error(f"Error in batch conversion: {exc}")
        retry_in = 5 * (2**self.request.retries)
        raise self.retry(exc=exc, countdown=retry_in)
