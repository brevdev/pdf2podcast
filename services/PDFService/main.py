from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException
from shared.shared_types import ServiceType, JobStatus, StatusResponse
from shared.job import JobStatusManager
from fastapi.responses import PlainTextResponse
from shared.otel import OpenTelemetryInstrumentation, OpenTelemetryConfig
from opentelemetry.trace.status import StatusCode
import httpx
import tempfile
import os
import logging
import time
import asyncio
import ujson as json
from typing import Optional, List, Tuple
from pydantic import BaseModel
from collections.abc import Coroutine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(debug=True)

telemetry = OpenTelemetryInstrumentation()
config = OpenTelemetryConfig(
    service_name="pdf-service",
    otlp_endpoint=os.getenv("OTLP_ENDPOINT", "http://jaeger:4317"),
    enable_redis=True,
    enable_requests=True,
)
telemetry.initialize(config, app)

job_manager = JobStatusManager(ServiceType.PDF, telemetry=telemetry)

# Configuration
MODEL_API_URL = os.getenv("MODEL_API_URL", "https://pdf-gyrdps568.brevlab.com")
DEFAULT_TIMEOUT = 600  # seconds


class PDFRequest(BaseModel):
    job_id: str


async def convert_pdf_to_markdown(pdf_path: str) -> str:
    """Convert PDF to Markdown using the external API service"""
    logger.info(f"Sending PDF to external conversion service: {pdf_path}")
    with telemetry.tracer.start_as_current_span("pdf.convert_pdf_to_markdown") as span:
        span.set_attribute("pdf_path", pdf_path)
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            try:
                # Initial conversion request
                with open(pdf_path, "rb") as pdf_file:
                    files = {"file": ("document.pdf", pdf_file, "application/pdf")}
                    logger.info(f"Sending PDF to model API: {MODEL_API_URL}")
                    span.set_attribute("model_api_url", MODEL_API_URL)
                    response = await client.post(
                        f"{MODEL_API_URL}/convert", files=files
                    )

                    if response.status_code != 200:
                        raise HTTPException(
                            status_code=response.status_code,
                            detail=f"Model API error: {response.text}",
                        )

                    task_data = response.json()
                    task_id = task_data["task_id"]
                    span.set_attribute("task_id", task_id)

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
                            logger.error(
                                f"No result found in response data: {status_data}"
                            )
                            raise HTTPException(
                                status_code=500,
                                detail="Server returned success but no result was found",
                            )
                        elif status_response.status_code == 202:
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
                span.set_status(StatusCode.ERROR)
                logger.error("Request timed out")
                raise HTTPException(
                    status_code=504, detail="Model API request timed out"
                )
            except httpx.RequestError as e:
                span.set_status(StatusCode.ERROR)
                logger.error(f"Request error: {str(e)}")
                raise HTTPException(
                    status_code=502, detail=f"Error connecting to Model API: {str(e)}"
                )


async def process_pdf(job_id: str, file_content: bytes):
    """Background task to process PDF conversion"""
    with telemetry.tracer.start_as_current_span("pdf.process_pdf") as span:
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
            span.set_status(StatusCode.ERROR)
            span.record_exception(e)
            job_manager.update_status(
                job_id, JobStatus.FAILED, f"PDF conversion failed: {str(e)}"
            )
            raise


async def process_multiple_pdfs(
    job_id: str, contents: List[bytes], filenames: List[str]
):
    """Process multiple PDFs and return metadata for each"""
    with telemetry.tracer.start_as_current_span("pdf.process_multiple_pdfs") as span:
        try:
            job_manager.update_status(
                job_id, JobStatus.PROCESSING, f"Processing {len(contents)} PDFs"
            )

            # Process all PDFs in parallel
            tasks: List[Tuple[str, str, Coroutine]] = []
            for idx, (content, filename) in enumerate(zip(contents, filenames)):
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pdf"
                ) as temp_file:
                    temp_file.write(content)
                    tasks.append(
                        (
                            temp_file.name,
                            filename,
                            convert_pdf_to_markdown(temp_file.name),
                        )
                    )

            # Wait for all conversions to complete
            pdf_metadata_list = []
            for temp_file_path, filename, task in tasks:
                try:
                    markdown = await task
                    pdf_metadata_list.append(
                        {
                            "filename": filename,
                            "markdown": markdown,
                            "summary": "",  # Empty summary placeholder
                        }
                    )
                finally:
                    os.unlink(temp_file_path)

            # Store result
            job_manager.set_result(job_id, json.dumps(pdf_metadata_list).encode())
            job_manager.update_status(
                job_id, JobStatus.COMPLETED, "All PDFs processed successfully"
            )

        except Exception as e:
            logger.error(f"Error processing PDFs: {str(e)}")
            span.set_status(StatusCode.ERROR)
            span.record_exception(e)
            job_manager.update_status(
                job_id, JobStatus.FAILED, f"PDF conversion failed: {str(e)}"
            )
            raise


@app.post("/convert", status_code=202)
async def convert_pdf(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    job_id: Optional[str] = None,
):
    """Convert multiple PDFs to Markdown"""
    with telemetry.tracer.start_as_current_span("pdf.convert_pdf") as span:
        # Validate all files are PDFs
        for file in files:
            if file.content_type != "application/pdf":
                raise HTTPException(status_code=400, detail="All files must be PDFs")
            span.set_attribute(f"file_{file.filename}_size", file.size)

        # Read all file contents and filenames
        contents = []
        filenames = []
        for file in files:
            content = await file.read()
            contents.append(content)
            filenames.append(file.filename)

        # Create job
        if not job_id:
            job_id = str(int(time.time()))

        span.set_attribute("job_id", job_id)
        span.set_attribute("num_files", len(files))
        job_manager.create_job(job_id)

        # Start processing in background
        background_tasks.add_task(process_multiple_pdfs, job_id, contents, filenames)

        return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_status(job_id: str) -> StatusResponse:  # Add return type annotation
    """Get status of PDF conversion job"""
    with telemetry.tracer.start_as_current_span("pdf.get_status") as span:
        span.set_attribute("job_id", job_id)
        status_data = job_manager.get_status(job_id)
        if status_data is None:
            span.set_status(StatusCode.ERROR)
            raise HTTPException(status_code=404, detail="Job not found")
        span.set_attribute("status", status_data.get("status"))
        return StatusResponse(**status_data)


@app.get("/output/{job_id}", response_class=PlainTextResponse)
async def get_output(job_id: str):
    """Get the converted markdown content"""
    with telemetry.tracer.start_as_current_span("pdf.get_output") as span:
        span.set_attribute("job_id", job_id)
        result = job_manager.get_result(job_id)
        if result is None:
            span.set_status(StatusCode.ERROR, "result not found")
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
