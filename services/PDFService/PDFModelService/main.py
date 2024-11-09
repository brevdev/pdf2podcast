from fastapi import FastAPI, File, UploadFile, HTTPException
from celery.result import AsyncResult
from shared.otel import OpenTelemetryInstrumentation, OpenTelemetryConfig
from opentelemetry.trace.status import StatusCode
import os
import logging
from typing import Dict
import uuid
from fastapi.responses import JSONResponse


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(debug=True)

telemetry = OpenTelemetryInstrumentation()
config = OpenTelemetryConfig(
    service_name="agent-service",
    otlp_endpoint=os.getenv("OTLP_ENDPOINT", "http://jaeger:4317"),
    enable_redis=True,
    enable_requests=True,
)
telemetry.initialize(config, app)


def get_celery_task():
    """Lazy import of Celery task to avoid immediate docling import"""
    from tasks import convert_pdf_task

    return convert_pdf_task


@app.post("/convert")
async def convert_pdf(file: UploadFile = File(...)) -> Dict[str, str]:
    """
    Start an asynchronous PDF conversion task
    """
    with telemetry.tracer.start_as_current_span("pdf.convert_pdf") as span:
        span.set_attribute("file_content_type", file.content_type)
        span.set_attribute("file_size", file.size)
        if file.content_type != "application/pdf":
            raise HTTPException(status_code=400, detail="File must be a PDF")

        try:
            # Save file with unique name
            file_id = str(uuid.uuid4())
            span.set_attribute("file_id", file_id)
            temp_dir = os.getenv("TEMP_FILE_DIR", "/tmp/pdf_conversions")
            os.makedirs(temp_dir, exist_ok=True)
            temp_file_path = os.path.join(temp_dir, f"{file_id}.pdf")

            content = await file.read()
            with open(temp_file_path, "wb") as temp_file:
                temp_file.write(content)

            # Get celery task and start conversion
            convert_pdf_task = get_celery_task()
            task = convert_pdf_task.delay(temp_file_path)

            return {
                "task_id": task.id,
                "status": "processing",
                "status_url": f"/status/{task.id}",
            }

        except Exception as e:
            span.set_status(StatusCode.ERROR)
            logger.error(f"Error starting conversion: {str(e)}")
            # Clean up file if task creation fails
            if "temp_file_path" in locals() and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{task_id}")
async def get_conversion_status(task_id: str):
    """
    Check the status of a PDF conversion task
    Returns:
    - 200: Task completed successfully
    - 425: Task is still processing
    - 500: Task failed
    """
    with telemetry.tracer.start_as_current_span("pdf.get_status") as span:
        span.set_attribute("task_id", task_id)
        try:
            task_result = AsyncResult(task_id)

            if task_result.ready():
                if task_result.successful():
                    result = task_result.get()
                    if result:
                        return JSONResponse(
                            content={"status": "completed", "result": result},
                            status_code=200,
                        )
                    else:
                        return JSONResponse(
                            content={
                                "status": "failed",
                                "error": "Task completed but no result was returned",
                            },
                            status_code=500,
                        )
                else:
                    error = str(task_result.result)
                    span.set_status(StatusCode.ERROR)
                    span.set_attribute("error", error)
                    return JSONResponse(
                        content={"status": "failed", "error": error}, status_code=500
                    )
            else:
                span.set_attribute("status", "processing")
                return JSONResponse(
                    content={
                        "status": "processing",
                        "message": "Your PDF is still being converted",
                    },
                    status_code=425,
                )

        except Exception as e:
            logger.error(f"Error checking status: {str(e)}")
            span.set_status(StatusCode.ERROR)
            return JSONResponse(
                content={"status": "failed", "error": str(e)}, status_code=500
            )


@app.get("/health")
async def health():
    """
    Health check endpoint
    """
    try:
        return {"status": "healthy", "service": "pdf-model-api"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
