from fastapi import FastAPI, BackgroundTasks, HTTPException
from shared.shared_types import (
    ServiceType,
    JobStatus,
    Conversation,
    TranscriptionRequest,
    PodcastOutline,
)
from podcast_flow import (
    podcast_summarize_pdfs,
    podcast_generate_raw_outline,
    podcast_generate_structured_outline,
    podcast_process_segments,
    podcast_generate_dialogue,
    podcast_combine_dialogues,
    podcast_create_final_conversation,
)
from monologue_flow import (
    monologue_summarize_pdfs,
    monologue_generate_raw_outline,
    monologue_generate_monologue,
    monologue_create_final_conversation,
)
from shared.storage import StorageManager
from shared.llmmanager import LLMManager
from shared.job import JobStatusManager
from shared.otel import OpenTelemetryInstrumentation, OpenTelemetryConfig
from opentelemetry.trace.status import StatusCode
import ujson as json
import os
import logging
from shared.prompt_tracker import PromptTracker


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

job_manager = JobStatusManager(ServiceType.AGENT, telemetry=telemetry)
storage_manager = StorageManager(telemetry=telemetry)


async def process_transcription(job_id: str, request: TranscriptionRequest):
    """Main processing function for transcription requests"""
    with telemetry.tracer.start_as_current_span("agent.process_transcription") as span:
        try:
            llm_manager = LLMManager(
                api_key=os.getenv("NIM_KEY"),
                telemetry=telemetry,
                config_path=os.getenv("MODEL_CONFIG_PATH"),
            )
            span.set_attribute("model_config_path", os.getenv("MODEL_CONFIG_PATH"))
            prompt_tracker = PromptTracker(job_id, storage_manager)

            # Initialize processing
            job_manager.update_status(
                job_id, JobStatus.PROCESSING, "Initializing processing"
            )

            if request.monologue:
                # Summarize PDFs
                summarized_pdfs = await monologue_summarize_pdfs(
                    request.pdf_metadata,
                    job_id,
                    llm_manager,
                    prompt_tracker,
                    job_manager,
                    logger,
                )

                # Generate raw outline
                raw_outline = monologue_generate_raw_outline(
                    summarized_pdfs,
                    request,
                    llm_manager,
                    prompt_tracker,
                    job_id,
                    job_manager,
                )

                # Generate monologue
                monologue = monologue_generate_monologue(
                    raw_outline,
                    request,
                    llm_manager,
                    prompt_tracker,
                    job_id,
                    job_manager,
                )

                # Create final conversation
                final_conversation = monologue_create_final_conversation(
                    monologue, request, llm_manager, prompt_tracker, job_id, job_manager
                )

                # Store result
                job_manager.set_result_with_expiration(
                    job_id, final_conversation.model_dump_json().encode(), ex=120
                )
                job_manager.update_status(
                    job_id, JobStatus.COMPLETED, "Transcription completed successfully"
                )

            else:
                # Summarize PDFs
                summarized_pdfs = await podcast_summarize_pdfs(
                    request.pdf_metadata,
                    job_id,
                    llm_manager,
                    prompt_tracker,
                    job_manager,
                    logger,
                )

                # Generate initial outline
                raw_outline = podcast_generate_raw_outline(
                    summarized_pdfs,
                    request,
                    llm_manager,
                    prompt_tracker,
                    job_id,
                    job_manager,
                    logger,
                )

                # Convert outline to structured format
                outline: PodcastOutline = podcast_generate_structured_outline(
                    raw_outline,
                    request,
                    llm_manager,
                    prompt_tracker,
                    job_id,
                    job_manager,
                    logger,
                )

                # Process segments in parallel
                segments = await podcast_process_segments(
                    outline,
                    request,
                    llm_manager,
                    prompt_tracker,
                    job_id,
                    job_manager,
                    logger,
                )

                # Generate dialogues from segments in parallel
                segment_dialogues = await podcast_generate_dialogue(
                    segments,
                    outline,
                    request,
                    llm_manager,
                    prompt_tracker,
                    job_id,
                    job_manager,
                    logger,
                )

                # Combine transcripts iteratively
                combined_dialogues = podcast_combine_dialogues(
                    segment_dialogues,
                    outline,
                    llm_manager,
                    prompt_tracker,
                    job_id,
                    job_manager,
                    logger,
                )

                # Create final conversation by formatting as JSON
                final_conversation: Conversation = podcast_create_final_conversation(
                    combined_dialogues,
                    request,
                    llm_manager,
                    prompt_tracker,
                    job_id,
                    job_manager,
                    logger,
                )
                # Store result
                job_manager.set_result_with_expiration(
                    job_id, final_conversation.model_dump_json().encode(), ex=120
                )
                job_manager.update_status(
                    job_id, JobStatus.COMPLETED, "Transcription completed successfully"
                )

        except Exception as e:
            span.set_status(StatusCode.ERROR, "transcription failed")
            span.record_exception(e)
            logger.error(f"Error processing job {job_id}: {str(e)}")
            job_manager.update_status(job_id, JobStatus.FAILED, str(e))
            raise


# API Endpoints
@app.post("/transcribe", status_code=202)
def transcribe(request: TranscriptionRequest, background_tasks: BackgroundTasks):
    with telemetry.tracer.start_as_current_span("agent.transcribe") as span:
        span.set_attribute("request", request.model_dump(exclude={"markdown"}))
        job_manager.create_job(request.job_id)
        background_tasks.add_task(process_transcription, request.job_id, request)
        return {"job_id": request.job_id}


@app.get("/status/{job_id}")
def get_status(job_id: str):
    with telemetry.tracer.start_as_current_span("agent.get_status") as span:
        span.set_attribute("job_id", job_id)
        status = job_manager.get_status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Job not found")
        span.set_attribute("status", status.get("status"))
        return status


@app.get("/output/{job_id}")
def get_output(job_id: str):
    with telemetry.tracer.start_as_current_span("agent.get_output") as span:
        span.set_attribute("job_id", job_id)
        result = job_manager.get_result(job_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Result not found")
        return json.loads(result.decode())


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8964)
