from fastapi import FastAPI, File, UploadFile, HTTPException
from celery.result import AsyncResult
import os
import logging
from typing import Dict
import uuid
from fastapi.responses import JSONResponse


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(debug=True)


def get_celery_task():
    """Lazy import of Celery task to avoid immediate docling import"""
    from tasks import convert_pdf_task

    return convert_pdf_task


@app.post("/convert")
async def convert_pdf(file: UploadFile = File(...)) -> Dict[str, str]:
    """
    Start an asynchronous PDF conversion task
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    try:
        # Save file with unique name
        file_id = str(uuid.uuid4())
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
    - 202: Task is still processing
    - 500: Task failed
    """
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
                return JSONResponse(
                    content={"status": "failed", "error": error}, status_code=500
                )
        else:
            return JSONResponse(
                content={
                    "status": "processing",
                    "message": "Your PDF is still being converted",
                },
                status_code=202,
            )

    except Exception as e:
        logger.error(f"Error checking status: {str(e)}")
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
