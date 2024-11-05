from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException
from shared.shared_types import ServiceType, JobStatus, StatusResponse
from shared.job import JobStatusManager
from fastapi.responses import PlainTextResponse
import httpx
import tempfile
import os
import logging
import time
import asyncio
from typing import Optional
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(debug=True)
job_manager = JobStatusManager(ServiceType.PDF)

# Configuration
MODEL_API_URL = os.getenv("MODEL_API_URL", "https://pdf-gyrdps568.brevlab.com")
DEFAULT_TIMEOUT = 600  # seconds


class PDFRequest(BaseModel):
    job_id: str


async def convert_pdf_to_markdown(pdf_path: str) -> str:
    """Convert PDF to Markdown using the external API service"""
    logger.info(f"Sending PDF to external conversion service: {pdf_path}")

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            # Initial conversion request
            with open(pdf_path, "rb") as pdf_file:
                files = {"file": ("document.pdf", pdf_file, "application/pdf")}
                logger.info(f"Sending PDF to model API: {MODEL_API_URL}")
                response = await client.post(f"{MODEL_API_URL}/convert", files=files)

                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Model API error: {response.text}",
                    )

                task_data = response.json()
                task_id = task_data["task_id"]

                # Poll the status endpoint until the task is complete
                while True:
                    status_response = await client.get(
                        f"{MODEL_API_URL}/status/{task_id}"
                    )
                    status_data = status_response.json()
                    logger.info(
                        f"Status check response: Code={status_response.status_code}, Data={status_data}"
                    )

                    if status_response.status_code == 200:
                        # Task completed successfully
                        result = status_data.get("result")
                        if result:
                            logger.info("Successfully received markdown result")
                            return result
                        logger.error(f"No result found in response data: {status_data}")
                        raise HTTPException(
                            status_code=500,
                            detail="Server returned success but no result was found",
                        )
                    elif status_response.status_code == 425:
                        # Task still processing
                        logger.info("Task still processing, waiting 2 seconds...")
                        await asyncio.sleep(2)
                    else:
                        error_msg = status_data.get("error", "Unknown error")
                        logger.error(f"Error response received: {error_msg}")
                        raise HTTPException(
                            status_code=status_response.status_code,
                            detail=f"PDF conversion failed: {error_msg}",
                        )

        except httpx.TimeoutException:
            logger.error("Request timed out")
            raise HTTPException(status_code=504, detail="Model API request timed out")
        except httpx.RequestError as e:
            logger.error(f"Request error: {str(e)}")
            raise HTTPException(
                status_code=502, detail=f"Error connecting to Model API: {str(e)}"
            )


async def process_pdf(job_id: str, file_content: bytes):
    """Background task to process PDF conversion"""
    try:
        job_manager.update_status(
            job_id, JobStatus.PROCESSING, "Creating temporary file"
        )

        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name

        try:
            job_manager.update_status(
                job_id,
                JobStatus.PROCESSING,
                "Converting PDF to Markdown via external service",
            )

            # Convert the PDF to markdown using external service
            markdown_content = await convert_pdf_to_markdown(temp_file_path)

            if not isinstance(markdown_content, str):
                markdown_content = str(markdown_content)

            # Store result
            job_manager.set_result(job_id, markdown_content.encode())
            job_manager.update_status(
                job_id, JobStatus.COMPLETED, "PDF conversion completed successfully"
            )

        finally:
            # Clean up the temporary file
            os.unlink(temp_file_path)
            logger.info(f"Cleaned up temporary file: {temp_file_path}")

    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        job_manager.update_status(
            job_id, JobStatus.FAILED, f"PDF conversion failed: {str(e)}"
        )
        raise


@app.post("/convert", status_code=202)
async def convert_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    job_id: Optional[str] = None,
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Read file content
    content = await file.read()

    # Create job
    if not job_id:
        job_id = str(int(time.time()))

    job_manager.create_job(job_id)

    # Start processing in background
    background_tasks.add_task(process_pdf, job_id, content)

    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_status(job_id: str) -> StatusResponse:  # Add return type annotation
    """Get status of PDF conversion job"""
    status_data = job_manager.get_status(job_id)
    return StatusResponse(**status_data)


@app.get("/output/{job_id}", response_class=PlainTextResponse)
async def get_output(job_id: str):
    """Get the converted markdown content"""
    result = job_manager.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result.decode()  # Decode bytes to string for markdown content


@app.get("/health")
async def health():
    """Check health of the service and its connection to the model API"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{MODEL_API_URL}/health")
            if response.status_code != 200:
                return {
                    "status": "unhealthy",
                    "error": f"Model API returned status code {response.status_code}",
                }

            return {
                "status": "healthy",
                "service": "pdf-converter",
                "model_api": response.json(),
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": f"Error connecting to Model API: {str(e)}",
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)
