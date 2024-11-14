from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException
from shared.shared_types import ServiceType, JobStatus, StatusResponse
from shared.job import JobStatusManager
from shared.otel import OpenTelemetryInstrumentation, OpenTelemetryConfig
from opentelemetry.trace.status import StatusCode
import httpx
import tempfile
import os
import logging
import time
import asyncio
import ujson as json
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

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


class ConversionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class PDFConversionResult(BaseModel):
    filename: str
    content: str = ""
    status: ConversionStatus
    error: str | None = None


class PDFMetadata(BaseModel):
    filename: str
    markdown: str = ""
    summary: str = ""
    status: ConversionStatus
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


async def convert_pdfs_to_markdown(pdf_paths: List[str]) -> List[PDFConversionResult]:
    """Convert multiple PDFs to Markdown using the external API service"""
    logger.info(f"Sending {len(pdf_paths)} PDFs to external conversion service")
    with telemetry.tracer.start_as_current_span("pdf.convert_pdfs_to_markdown") as span:
        span.set_attribute("num_pdfs", len(pdf_paths))
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            try:
                # Send all files in a single request
                files = []
                for i, path in enumerate(pdf_paths):
                    with open(path, "rb") as pdf_file:
                        files.append(
                            ("files", (f"doc_{i}.pdf", pdf_file, "application/pdf"))
                        )
                    span.set_attribute(f"pdf_path_{i}", path)

                logger.info(f"Sending PDFs to model API: {MODEL_API_URL}")
                span.set_attribute("model_api_url", MODEL_API_URL)
                response = await client.post(f"{MODEL_API_URL}/convert", files=files)

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
                    logger.debug(
                        f"Status check response: Code={status_response.status_code}, Data={status_data}"
                    )

                    if status_response.status_code == 200:
                        # Task completed successfully
                        results = status_data.get("result", [])
                        if results:
                            # Convert raw results to PDFConversionResult models
                            conversion_results = []
                            for result in results:
                                if result["status"] == "success":
                                    conversion_results.append(
                                        PDFConversionResult(
                                            filename=result.get("filename", "unknown"),
                                            content=result["content"],
                                            status=ConversionStatus.SUCCESS,
                                        )
                                    )
                                else:
                                    conversion_results.append(
                                        PDFConversionResult(
                                            filename=result.get("filename", "unknown"),
                                            error=result.get(
                                                "error", "Unknown conversion error"
                                            ),
                                            status=ConversionStatus.FAILED,
                                        )
                                    )

                            logger.info(
                                f"Successfully received {len(conversion_results)} markdown results"
                            )
                            return conversion_results

                        logger.error(
                            f"No results found in response data: {status_data}"
                        )
                        raise HTTPException(
                            status_code=500,
                            detail="Server returned success but no results were found",
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


async def process_pdfs(job_id: str, contents: List[bytes], filenames: List[str]):
    """Process multiple PDFs and return metadata for each"""
    with telemetry.tracer.start_as_current_span("pdf.process_pdfs") as span:
        try:
            job_manager.update_status(
                job_id, JobStatus.PROCESSING, f"Processing {len(contents)} PDFs"
            )

            # Create temporary files for all PDFs
            temp_files = []
            for content in contents:
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pdf"
                ) as temp_file:
                    temp_file.write(content)
                    temp_files.append(temp_file.name)

            try:
                # Convert all PDFs in a single batch
                results = await convert_pdfs_to_markdown(temp_files)

                # Create metadata list
                pdf_metadata_list = []
                for filename, result in zip(filenames, results):
                    metadata = PDFMetadata(
                        filename=filename,
                        markdown=result.content
                        if result.status == ConversionStatus.SUCCESS
                        else "",
                        status=result.status,
                        error=result.error,
                    )
                    pdf_metadata_list.append(metadata)

                # Store result
                job_manager.set_result(
                    job_id,
                    json.dumps([m.model_dump() for m in pdf_metadata_list]).encode(),
                )
                job_manager.update_status(
                    job_id, JobStatus.COMPLETED, "All PDFs processed successfully"
                )

            finally:
                # Clean up all temporary files
                for temp_file in temp_files:
                    try:
                        os.unlink(temp_file)
                        logger.info(f"Cleaned up temporary file: {temp_file}")
                    except Exception as e:
                        logger.error(f"Error cleaning up file {temp_file}: {e}")

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
        background_tasks.add_task(process_pdfs, job_id, contents, filenames)

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


@app.get("/output/{job_id}")
async def get_output(job_id: str):
    """Get the converted markdown content"""
    with telemetry.tracer.start_as_current_span("pdf.get_output") as span:
        span.set_attribute("job_id", job_id)
        result = job_manager.get_result(job_id)
        if result is None:
            span.set_status(StatusCode.ERROR, "result not found")
            raise HTTPException(status_code=404, detail="Result not found")

        # Parse the stored JSON back into PDFMetadata objects
        metadata_list = [PDFMetadata(**item) for item in json.loads(result.decode())]
        return metadata_list


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
