from fastapi import (
    HTTPException,
    FastAPI,
    File,
    UploadFile,
    Form,
    BackgroundTasks,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from shared.shared_types import (
    ServiceType,
    JobStatus,
    StatusUpdate,
    TranscriptionParams,
    SavedPodcast,
    SavedPodcastWithAudio,
    Conversation,
    PromptTracker,
)
from shared.connection import ConnectionManager
from shared.storage import StorageManager
from shared.otel import OpenTelemetryInstrumentation, OpenTelemetryConfig
from opentelemetry.trace.status import StatusCode
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
import redis
import requests
import ujson as json
import os
import logging
import time
import asyncio
from typing import Dict, List, Union

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(debug=True)

# Initialize OpenTelemetry
telemetry = OpenTelemetryInstrumentation()
config = OpenTelemetryConfig(
    service_name="api-service",
    otlp_endpoint=os.getenv("OTLP_ENDPOINT", "http://jaeger:4317"),
    enable_redis=True,
    enable_requests=True,
)
telemetry.initialize(config, app)

# Initialize other services
redis_client = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://redis:6379"), decode_responses=False
)

# Initialize the connection manager
manager = ConnectionManager(redis_client=redis_client)
storage_manager = StorageManager(telemetry=telemetry)

# Service URLs
PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "http://localhost:8003")
AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "http://localhost:8964")
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://localhost:8889")

# MP3 Cache TTL
MP3_CACHE_TTL = 60 * 60 * 4  # 4 hours

# CORS setup
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000")
allowed_origins = [origin.strip() for origin in CORS_ORIGINS.split(",")]
logger.info(f"Configuring CORS with allowed origins: {allowed_origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
    max_age=3600,
)


@app.websocket("/ws/status/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    try:
        # Accept the WebSocket connection
        await manager.connect(websocket, job_id)

        # Send initial status for all services
        for service in ServiceType:
            status_data = redis_client.hgetall(f"status:{job_id}:{service}")
            if status_data:
                status_msg = {
                    "service": service.value,
                    "status": status_data.get(b"status", b"").decode(),
                    "message": status_data.get(b"message", b"").decode(),
                }
                await websocket.send_json(status_msg)
                logger.info(f"Sent initial status for {job_id} {service}: {status_msg}")

        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages (ping/pong handled automatically by FastAPI)
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break

            await asyncio.sleep(0.1)

    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {e}")
    finally:
        manager.disconnect(websocket, job_id)


def process_pdf_task(
    job_id: str, files_content: List[bytes], transcription_params: TranscriptionParams
):
    with telemetry.tracer.start_as_current_span("api.process_pdf_task") as span:
        span.set_attribute("job_id", job_id)
        try:
            pubsub = redis_client.pubsub()
            pubsub.subscribe("status_updates:all")

            # Store all original PDFs
            for idx, content in enumerate(files_content):
                storage_manager.store_file(
                    job_id,
                    content,
                    f"{job_id}_{idx}.pdf",
                    "application/pdf",
                    transcription_params,
                )
            logger.info(
                f"Stored {len(files_content)} original PDFs for {job_id} in storage"
            )

            # Send all PDFs to PDF Service
            files = [
                ("files", (f"file_{i}.pdf", content, "application/pdf"))
                for i, content in enumerate(files_content)
            ]

            requests.post(
                f"{PDF_SERVICE_URL}/convert", files=files, data={"job_id": job_id}
            )

            # Monitor services
            current_service = ServiceType.PDF
            while True:
                message = pubsub.get_message()
                if message and message["type"] == "message":
                    update = StatusUpdate.model_validate_json(message["data"].decode())

                    if update.job_id == job_id:
                        logger.info(f"Received update for job {job_id}: {update}")

                        if update.status == JobStatus.FAILED:
                            raise Exception(f"{update.service}: {update.message}")

                        if update.status == JobStatus.COMPLETED:
                            if current_service == ServiceType.PDF:
                                # Get PDF metadata list
                                pdf_metadata_list = requests.get(
                                    f"{PDF_SERVICE_URL}/output/{job_id}"
                                ).json()

                                # Start Agent Service with PDF metadata
                                requests.post(
                                    f"{AGENT_SERVICE_URL}/transcribe",
                                    json={
                                        "pdf_metadata": pdf_metadata_list,
                                        "job_id": job_id,
                                        **transcription_params.model_dump(),
                                    },
                                )
                                current_service = ServiceType.AGENT

                            elif current_service == ServiceType.AGENT:
                                # Start TTS Service
                                agent_result = requests.get(
                                    f"{AGENT_SERVICE_URL}/output/{job_id}"
                                ).json()

                                # Store script result in minio
                                storage_manager.store_file(
                                    job_id,
                                    json.dumps(agent_result).encode(),
                                    f"{job_id}_agent_result.json",
                                    "application/json",
                                    transcription_params,
                                )
                                logger.info(
                                    f"Stored agent result for {job_id} in minio, size: {len(json.dumps(agent_result).encode())} bytes"
                                )

                                requests.post(
                                    f"{TTS_SERVICE_URL}/generate_tts",
                                    json={
                                        "dialogue": agent_result["dialogue"],
                                        "job_id": job_id,
                                        "voice_mapping": transcription_params.voice_mapping,  # Forward the voice mapping
                                    },
                                )
                                current_service = ServiceType.TTS

                            elif current_service == ServiceType.TTS:
                                # Get final output and store it
                                logger.info(
                                    f"TTS completed for {job_id}, fetching and storing result"
                                )
                                audio_content = requests.get(
                                    f"{TTS_SERVICE_URL}/output/{job_id}"
                                ).content

                                # Store both the content and the ready flag
                                redis_client.set(
                                    f"result:{job_id}:{ServiceType.TTS}",
                                    audio_content,
                                    ex=MP3_CACHE_TTL,
                                )
                                redis_client.set(
                                    f"final_status:{job_id}", "ready", ex=MP3_CACHE_TTL
                                )

                                # Store in DB
                                storage_manager.store_audio(
                                    job_id,
                                    audio_content,
                                    f"{job_id}.mp3",
                                    transcription_params,
                                )

                                logger.info(
                                    f"Stored TTS result for {job_id}, size: {len(audio_content)} bytes, with TTL: {MP3_CACHE_TTL} seconds"
                                )
                                return audio_content

                time.sleep(0.01)

        except Exception as e:
            span.set_status(StatusCode.ERROR, "process_pdf_task failed")
            span.record_exception(e)
            logger.error(f"Job {job_id} failed: {str(e)}")
            raise


@app.post("/process_pdf", status_code=202)
async def process_pdf(
    background_tasks: BackgroundTasks,
    files: Union[UploadFile, List[UploadFile]] = File(...),
    transcription_params: str = Form(...),
):
    with telemetry.tracer.start_as_current_span("api.process_pdf") as span:
        # Convert single file to list for consistent handling
        files_list = [files] if isinstance(files, UploadFile) else files

        span.set_attribute("request", transcription_params)
        span.set_attribute("num_files", len(files_list))

        # Validate all files are PDFs
        for file in files_list:
            if file.content_type != "application/pdf":
                span.set_status(
                    status=StatusCode.ERROR, description="invalid file type"
                )
                raise HTTPException(
                    status_code=400, detail="Only PDF files are allowed"
                )

        try:
            params_dict = json.loads(transcription_params)
            params = TranscriptionParams.model_validate(params_dict)
            span.set_attribute("transcription_params", params.model_dump())
        except (json.JSONDecodeError, ValidationError) as e:
            span.set_status(status=StatusCode.ERROR, description="invalid params")
            raise HTTPException(status_code=400, detail=str(e))

        # Create job
        job_id = str(int(time.time()))
        span.set_attribute("job_id", job_id)

        # Read all files
        files_content = []
        for file in files_list:
            content = await file.read()
            files_content.append(content)

        # Start processing
        background_tasks.add_task(process_pdf_task, job_id, files_content, params)
        span.set_status(status=StatusCode.OK)

        return {"job_id": job_id}


@app.get("/status/{job_id}")
async def get_status(job_id: str):
    """Get aggregated status from all services"""
    with telemetry.tracer.start_as_current_span("api.job.status") as span:
        span.set_attribute("job_id", job_id)
        statuses = {}
        for service in ServiceType:
            status = redis_client.hgetall(f"status:{job_id}:{service}")
            if status:
                span.set_attribute(
                    f"{service.value}.status", status.get(b"status", b"").decode()
                )
                # Decode the bytes to strings
                statuses[service] = {k.decode(): v.decode() for k, v in status.items()}

        if not statuses:
            raise HTTPException(status_code=404, detail="Job not found")

        return statuses


# This needs to also interact with our db as well. Check cache first if job running. If nothing there, check db
@app.get("/output/{job_id}")
async def get_output(job_id: str):
    """Get the final TTS output"""
    with telemetry.tracer.start_as_current_span("api.job.output") as span:
        # First check if the final result is ready
        span.set_attribute("job_id", job_id)
        is_ready = redis_client.get(f"final_status:{job_id}")
        span.set_attribute("is_ready", is_ready if is_ready else False)
        if not is_ready:
            # Check if TTS service reports completion
            tts_status = redis_client.hgetall(f"status:{job_id}:{ServiceType.TTS}")
            if not tts_status:
                raise HTTPException(status_code=404, detail="Result not found")
            if tts_status.get(b"status", b"").decode() != "completed":
                span.set_attribute(
                    "tts_status", tts_status.get(b"status", b"").decode()
                )
                raise HTTPException(status_code=404, detail="TTS not completed")

            # If TTS reports complete but result not ready, it's still being fetched
            raise HTTPException(
                status_code=202,  # Too Early
                detail="Result is being prepared",
            )

        result = redis_client.get(f"result:{job_id}:{ServiceType.TTS}")
        if not result:
            logger.info(f"Final result not found in cache for {job_id}. Checking DB...")
            result = storage_manager.get_podcast_audio(job_id)
            if not result:
                span.set_status(StatusCode.ERROR, "result not found")
                raise HTTPException(status_code=404, detail="Result not found")

        return Response(
            content=result,
            media_type="audio/mpeg",
            headers={"Content-Disposition": f"attachment; filename={job_id}.mp3"},
        )


@app.post("/cleanup")
async def cleanup_jobs():
    """Clean up old jobs across all services"""
    removed = 0
    for service in ServiceType:
        pattern = f"status:*:{service}"
        for key in redis_client.scan_iter(match=pattern):
            job_id = key.split(b":")[1].decode()  # Handle bytes key
            redis_client.delete(key)
            redis_client.delete(f"result:{job_id}:{service}")
            removed += 1
    return {"message": f"Removed {removed} old jobs"}


@app.get("/saved_podcasts", response_model=Dict[str, List[SavedPodcast]])
async def get_saved_podcasts():
    """Get a list of all saved podcasts from storage with their audio data"""
    try:
        with telemetry.tracer.start_as_current_span("api.saved_podcasts") as span:
            saved_files = storage_manager.list_files_metadata()
            span.set_attribute("num_files", len(saved_files))
            return {
                "podcasts": [
                    SavedPodcast(
                        job_id=file["job_id"],
                        filename=file["filename"],
                        created_at=file["created_at"],
                        size=file["size"],
                        transcription_params=file.get("transcription_params", {}),
                    )
                    for file in saved_files
                ]
            }
    except Exception as e:
        logger.error(f"Failed to list saved podcasts: {str(e)}")
        span.set_status(StatusCode.ERROR, "failed to list saved podcasts")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve saved podcasts: {str(e)}"
        )


@app.get("/saved_podcast/{job_id}/metadata", response_model=SavedPodcast)
async def get_saved_podcast_metadata(job_id: str):
    """Get a specific saved podcast metadata without audio data"""
    try:
        with telemetry.tracer.start_as_current_span(
            "api.saved_podcast.metadata"
        ) as span:
            span.set_attribute("job_id", job_id)
            saved_files = storage_manager.list_files_metadata()
            podcast_metadata = next(
                (file for file in saved_files if file["job_id"] == job_id), None
            )
            if not podcast_metadata:
                raise HTTPException(
                    status_code=404, detail=f"Podcast with job_id {job_id} not found"
                )
            return SavedPodcast(
                job_id=podcast_metadata["job_id"],
                filename=podcast_metadata["filename"],
                created_at=podcast_metadata["created_at"],
                size=podcast_metadata["size"],
                transcription_params=podcast_metadata.get("transcription_params", {}),
            )
    except Exception as e:
        logger.error(f"Failed to get podcast metadata {job_id}: {str(e)}")
        span.set_status(StatusCode.ERROR, "failed to get podcast metadata")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve podcast metadata: {str(e)}"
        )


@app.get("/saved_podcast/{job_id}/audio", response_model=SavedPodcastWithAudio)
async def get_saved_podcast(job_id: str):
    """Get a specific saved podcast with its audio data"""
    try:
        with telemetry.tracer.start_as_current_span("api.saved_podcast.audio") as span:
            span.set_attribute("job_id", job_id)
            # Get metadata first
            saved_files = storage_manager.list_files_metadata()
            podcast_metadata = next(
                (file for file in saved_files if file["job_id"] == job_id), None
            )

            if not podcast_metadata:
                raise HTTPException(
                    status_code=404, detail=f"Podcast with job_id {job_id} not found"
                )

            # Get audio data
            audio_data = storage_manager.get_podcast_audio(job_id)
            if not audio_data:
                raise HTTPException(
                    status_code=404, detail=f"Audio data for podcast {job_id} not found"
                )

            return SavedPodcastWithAudio(
                job_id=podcast_metadata["job_id"],
                filename=podcast_metadata["filename"],
                created_at=podcast_metadata["created_at"],
                size=podcast_metadata["size"],
                transcription_params=podcast_metadata.get("transcription_params", {}),
                audio_data=audio_data,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get podcast {job_id}: {str(e)}")
        span.set_status(StatusCode.ERROR, "failed to get podcast")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve podcast: {str(e)}"
        )


@app.get("/saved_podcast/{job_id}/transcript", response_model=Conversation)
async def get_saved_podcast_transcript(job_id: str):
    """Get a specific saved podcast transcript"""
    with telemetry.tracer.start_as_current_span("api.saved_podcast.transcript") as span:
        try:
            span.set_attribute("job_id", job_id)
            filename = f"{job_id}_agent_result.json"
            span.set_attribute("filename", filename)
            raw_data = storage_manager.get_file(job_id, filename)

            if not raw_data:
                raise HTTPException(
                    status_code=404, detail=f"Transcript for {job_id} not found"
                )

            agent_result = json.loads(raw_data)
            return Conversation.model_validate(agent_result)

        except ValidationError as e:
            span.set_status(StatusCode.ERROR, "validation error")
            logger.error(f"Validation error for transcript {job_id}: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Invalid transcript format: {str(e)}"
            )
        except Exception as e:
            span.set_status(StatusCode.ERROR, "failed to get transcript")
            logger.error(f"Failed to get transcript for {job_id}: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"Failed to retrieve transcript: {str(e)}"
            )


@app.get("/saved_podcast/{job_id}/history")
async def get_saved_podcast_agent_workflow(job_id: str):
    """Get a specific saved podcast agent workflow"""
    with telemetry.tracer.start_as_current_span("api.saved_podcast.history") as span:
        try:
            span.set_attribute("job_id", job_id)
            filename = f"{job_id}_prompt_tracker.json"
            span.set_attribute("filename", filename)
            raw_data = storage_manager.get_file(job_id, filename)

            if not raw_data:
                span.set_status(StatusCode.ERROR, "not found")
                raise HTTPException(
                    status_code=404, detail=f"History for {job_id} not found"
                )

            return PromptTracker.model_validate_json(raw_data)

        except Exception as e:
            logger.error(f"Failed to get history for {job_id}: {str(e)}")
            span.set_status(StatusCode.ERROR, "failed to get history")
            raise HTTPException(
                status_code=500, detail=f"Failed to retrieve history: {str(e)}"
            )


@app.get("/saved_podcast/{job_id}/pdf")
async def get_saved_podcast_pdf(job_id: str):
    """Get the original PDF file for a specific podcast"""
    with telemetry.tracer.start_as_current_span("api.saved_podcast.pdf") as span:
        try:
            span.set_attribute("job_id", job_id)
            filename = f"{job_id}.pdf"
            span.set_attribute("filename", filename)
            pdf_data = storage_manager.get_file(job_id, filename)

            if not pdf_data:
                span.set_status(StatusCode.ERROR, "not found")
                raise HTTPException(
                    status_code=404, detail=f"PDF for podcast {job_id} not found"
                )

            return Response(
                content=pdf_data,
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename={job_id}.pdf"},
            )

        except Exception as e:
            logger.error(f"Failed to get PDF for {job_id}: {str(e)}")
            span.set_status(StatusCode.ERROR, "failed to get PDF")
            raise HTTPException(
                status_code=500, detail=f"Failed to retrieve PDF: {str(e)}"
            )


@app.delete("/saved_podcast/{job_id}")
async def delete_saved_podcast(job_id: str):
    """Delete a specific saved podcast and all its associated files"""
    with telemetry.tracer.start_as_current_span("api.saved_podcast.delete") as span:
        try:
            span.set_attribute("job_id", job_id)
            saved_files = storage_manager.list_files_metadata()
            span.set_attribute("num_files", len(saved_files))
            podcast_metadata = next(
                (file for file in saved_files if file["job_id"] == job_id), None
            )

            if not podcast_metadata:
                span.set_status(StatusCode.ERROR, "not found")
                raise HTTPException(
                    status_code=404, detail=f"Podcast with job_id {job_id} not found"
                )

            success = storage_manager.delete_job_files(job_id)

            if not success:
                raise HTTPException(
                    status_code=500, detail=f"Failed to delete podcast {job_id}"
                )

            # Also clean up any Redis entries
            for service in ServiceType:
                redis_client.delete(f"status:{job_id}:{service}")
                redis_client.delete(f"result:{job_id}:{service}")
            redis_client.delete(f"final_status:{job_id}")

            return {"message": f"Successfully deleted podcast {job_id}"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to delete podcast {job_id}: {str(e)}")
            span.set_status(StatusCode.ERROR, "failed to delete podcast")
            raise HTTPException(
                status_code=500, detail=f"Failed to delete podcast: {str(e)}"
            )


@app.get("/health")
async def health():
    """Health check endpoint with OpenTelemetry instrumentation"""
    with telemetry.tracer.start_as_current_span("api.health_check") as span:
        try:
            # Check Redis connection
            with telemetry.tracer.start_as_current_span(
                "api.redis_check"
            ) as redis_span:
                redis_alive = redis_client.ping()
                redis_span.set_attribute(
                    "redis.status", "up" if redis_alive else "down"
                )
                logger.info(f"Redis status: {'up' if redis_alive else 'down'}")

            # Check dependent services
            services = {
                "pdf": PDF_SERVICE_URL,
                "agent": AGENT_SERVICE_URL,
                "tts": TTS_SERVICE_URL,
            }

            service_status = {}
            for service_name, url in services.items():
                with telemetry.tracer.start_as_current_span(
                    f"api.{service_name}_check"
                ) as service_span:
                    try:
                        response = requests.get(f"{url}/health", timeout=5)
                        status = "up" if response.status_code == 200 else "down"
                        service_span.set_attribute(f"{service_name}.status", status)
                        service_span.set_attribute(
                            f"{service_name}.response_code", response.status_code
                        )
                        service_status[service_name] = status
                    except Exception as e:
                        logger.error(f"Error checking {service_name}: {str(e)}")
                        service_span.set_attribute(f"{service_name}.status", "down")
                        service_span.set_attribute(f"{service_name}.error", str(e))
                        service_span.record_exception(e)
                        service_status[service_name] = "down"

            # Set overall health status
            all_healthy = redis_alive and all(
                status == "up" for status in service_status.values()
            )
            span.set_attribute(
                "health.status", "healthy" if all_healthy else "unhealthy"
            )
            logger.info(
                f"Overall health status: {'healthy' if all_healthy else 'unhealthy'}"
            )

            return {
                "status": "healthy" if all_healthy else "unhealthy",
                "redis": "up" if redis_alive else "down",
                "services": service_status,
                "timestamp": time.time(),
            }

        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            span.set_attribute("health.status", "unhealthy")
            span.record_exception(e)
            return {"status": "unhealthy", "error": str(e), "timestamp": time.time()}
