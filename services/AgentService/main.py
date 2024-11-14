from fastapi import FastAPI, BackgroundTasks, HTTPException
from shared.shared_types import (
    ServiceType,
    JobStatus,
    Conversation,
    PDFMetadata,
    TranscriptionRequest,
    PodcastOutline,
)
from shared.storage import StorageManager
from shared.llmmanager import LLMManager
from shared.job import JobStatusManager
from shared.otel import OpenTelemetryInstrumentation, OpenTelemetryConfig
from opentelemetry.trace.status import StatusCode
from typing import List, Dict, Any, Coroutine
import json
import os
import logging
import time
from prompts import PodcastPrompts
from langchain_core.messages import AIMessage
import asyncio


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


# TODO: Move this to shared
class PromptTracker:
    """Track prompts and responses and save them to storage"""

    def __init__(self, job_id: str, storage_manager: StorageManager):
        self.job_id = job_id
        self.steps: Dict[str, Dict[str, str]] = {}
        self.storage_manager = storage_manager

    def track(self, step_name: str, prompt: str, model: str, response: str = None):
        self.steps[step_name] = {
            "step_name": step_name,
            "prompt": prompt,
            "response": response if response else "",
            "model": model,
            "timestamp": time.time(),
        }
        if response:
            self._save()
        logger.info(f"Tracked step {step_name} for {self.job_id}")

    def update_result(self, step_name: str, response: str):
        if step_name in self.steps:
            self.steps[step_name]["response"] = response
            self._save()
            logger.info(f"Updated response for step {step_name}")
        else:
            logger.warning(f"Step {step_name} not found in prompt tracker")

    def _save(self):
        self.storage_manager.store_file(
            self.job_id,
            json.dumps({"steps": list(self.steps.values())}).encode(),
            f"{self.job_id}_prompt_tracker.json",
            "application/json",
        )
        logger.info(
            f"Stored prompt tracker for {self.job_id} in minio. Length: {len(self.steps)}"
        )


async def summarize_pdf(
    pdf_metadata: PDFMetadata, llm_manager: LLMManager, prompt_tracker: PromptTracker
) -> AIMessage:
    """Summarize a single PDF document"""
    template = PodcastPrompts.get_template("summary_prompt")
    prompt = template.render(text=pdf_metadata.markdown)

    summary_response: AIMessage = await llm_manager.query_async(
        "reasoning",
        [{"role": "user", "content": prompt}],
        f"summarize_{pdf_metadata.filename}",
    )
    prompt_tracker.track(
        f"summarize_{pdf_metadata.filename}",
        prompt,
        llm_manager.model_configs["reasoning"].name,
    )
    return summary_response


async def summarize_pdfs(
    pdfs: List[PDFMetadata],
    job_id: str,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
) -> List[PDFMetadata]:
    """Summarize all PDFs in the request"""
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, f"Summarizing {len(pdfs)} PDFs"
    )

    summaries: List[AIMessage] = await asyncio.gather(
        *[summarize_pdf(pdf, llm_manager, prompt_tracker) for pdf in pdfs]
    )

    for pdf, summary in zip(pdfs, summaries):
        pdf.summary = summary.content
        prompt_tracker.update_result(f"summarize_{pdf.filename}", pdf.summary)
        logger.info(f"Successfully summarized {pdf.filename}")

    return pdfs


def generate_raw_outline(
    summarized_pdfs: List[PDFMetadata],
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
) -> str:
    """Generate initial raw outline from summarized PDFs"""
    # Prepare document summaries in XML format
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, "Generating initial outline"
    )
    documents = []
    for pdf in summarized_pdfs:
        doc_str = f"""
        <document>
        <is_important>true</is_important>
        <path>{pdf.filename}</path>
        <summary>
        {pdf.summary}
        </summary>
        </document>"""
        documents.append(doc_str)

    template = PodcastPrompts.get_template("multi_pdf_outline_prompt")
    prompt = template.render(
        total_duration=request.duration,
        focus_instructions=request.guide if request.guide else None,
        documents="\n\n".join(documents),
    )
    raw_outline: AIMessage = llm_manager.query_sync(
        "reasoning",
        [{"role": "user", "content": prompt}],
        "raw_outline",
    )

    prompt_tracker.track(
        "raw_outline",
        prompt,
        llm_manager.model_configs["reasoning"].name,
        raw_outline.content,
    )

    return raw_outline


# TODO: i dont like how this is returning a dict and not an AIMessage
def generate_structured_outline(
    raw_outline: str,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
) -> Dict:
    """Convert raw outline to structured format"""
    job_manager.update_status(
        job_id,
        JobStatus.PROCESSING,
        "Converting raw outline to structured format",
    )

    # Force the model to only reference valid filenames
    valid_filenames = [pdf.filename for pdf in request.pdf_metadata]
    schema = PodcastOutline.model_json_schema()
    schema["$defs"]["PodcastSegment"]["properties"]["references"]["items"] = {
        "type": "string",
        "enum": valid_filenames,
    }

    schema = PodcastOutline.model_json_schema()
    template = PodcastPrompts.get_template("multi_pdf_structured_outline_prompt")
    prompt = template.render(
        outline=raw_outline,
        schema=json.dumps(schema, indent=2),
        valid_filenames=[pdf.filename for pdf in request.pdf_metadata],
    )
    outline: Dict = llm_manager.query_sync(
        "json",
        [{"role": "user", "content": prompt}],
        "outline",
        json_schema=schema,
    )
    prompt_tracker.track(
        "outline", prompt, llm_manager.model_configs["json"].name, outline
    )
    return outline


async def process_segment(
    segment: Any,
    idx: int,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
) -> tuple[str, str]:
    """Process a single segment"""
    # Get reference content if it exists
    text_content = []
    if segment.references:
        for ref in segment.references:
            # Find matching PDF metadata by filename
            pdf = next(
                (pdf for pdf in request.pdf_metadata if pdf.filename == ref), None
            )
            if pdf:
                text_content.append(pdf.markdown)

    # Choose template based on whether we have references
    template_name = "prompt_with_references" if text_content else "prompt_no_references"
    template = PodcastPrompts.get_template(template_name)

    # Prepare prompt parameters
    prompt_params = {
        "duration": segment.duration,
        "topic": segment.section,
        "angles": "\n".join([topic.title for topic in segment.topics]),
    }

    # Add text content if we have references
    if text_content:
        prompt_params["text"] = "\n\n".join(text_content)

    prompt = template.render(**prompt_params)

    response: AIMessage = await llm_manager.query_async(
        "iteration",
        [{"role": "user", "content": prompt}],
        f"segment_{idx}",
    )

    prompt_tracker.track(
        f"segment_transcript_{idx}",
        prompt,
        llm_manager.model_configs["iteration"].name,
        response.content,
    )

    return f"segment_transcript_{idx}", response.content


async def process_segments(
    outline: PodcastOutline,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
) -> Dict[str, str]:
    """Process each segment in the outline"""
    # Create tasks for processing each segment
    segment_tasks: List[Coroutine] = []
    for idx, segment in enumerate(outline.segments):
        job_manager.update_status(
            job_id,
            JobStatus.PROCESSING,
            f"Processing segment {idx + 1}/{len(outline.segments)}: {segment.section}",
        )

        task = process_segment(
            segment,
            idx,
            request,
            llm_manager,
            prompt_tracker,
        )
        segment_tasks.append(task)

    # Process all segments in parallel
    results = await asyncio.gather(*segment_tasks)

    # Convert results to dictionary
    return dict(results)


async def generate_dialogue_segment(
    segment: Any,
    idx: int,
    segment_text: str,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
) -> Dict[str, str]:
    """Generate dialogue for a single segment"""
    # Format topics for prompt
    topics_text = "\n".join(
        [
            f"- {topic.title}\n"
            + "\n".join([f"  * {point.description}" for point in topic.points])
            for topic in segment.topics
        ]
    )

    # Generate dialogue using template
    template = PodcastPrompts.get_template("transcript_to_dialogue_prompt")
    prompt = template.render(
        text=segment_text,
        duration=segment.duration,
        descriptions=topics_text,
        speaker_1_name=request.speaker_1_name,
        speaker_2_name=request.speaker_2_name,
    )

    # Query LLM for dialogue
    dialogue_response = await llm_manager.query_async(
        "reasoning",
        [{"role": "user", "content": prompt}],
        f"segment_dialogue_{idx}",
    )

    # Track prompt and response
    prompt_tracker.track(
        f"segment_dialogue_{idx}",
        prompt,
        llm_manager.model_configs["reasoning"].name,
        dialogue_response.content,
    )

    return {"section": segment.section, "dialogue": dialogue_response.content}


async def generate_dialogue(
    segments: Dict[str, str],
    outline: PodcastOutline,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
) -> List[Dict[str, str]]:
    """Generate dialogue for each segment"""
    job_manager.update_status(job_id, JobStatus.PROCESSING, "Generating dialogue")

    # Create tasks for generating dialogue for each segment
    dialogue_tasks = []
    for idx, segment in enumerate(outline.segments):
        segment_name = f"segment_transcript_{idx}"
        seg_response = segments.get(segment_name)

        if not seg_response:
            logger.warning(f"Segment {segment_name} not found in segment transcripts")
            continue

        # Update prompt tracker with segment response
        segment_text = seg_response
        prompt_tracker.update_result(segment_name, segment_text)

        # Update status
        job_manager.update_status(
            job_id,
            JobStatus.PROCESSING,
            f"Converting segment {idx + 1}/{len(outline.segments)} to dialogue",
        )

        task = generate_dialogue_segment(
            segment,
            idx,
            segment_text,
            request,
            llm_manager,
            prompt_tracker,
        )
        dialogue_tasks.append(task)

    # Process all dialogues in parallel
    dialogues = await asyncio.gather(*dialogue_tasks)

    return list(dialogues)


def revise_dialogue(
    segment_dialogues: List[Dict[str, str]],
    outline_json: Dict,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
) -> str:
    """Iteratively revise and combine dialogue segments into a cohesive conversation"""
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, "Revising dialogue segments"
    )

    # Start with the first segment's dialogue
    current_dialogue = segment_dialogues[0]["dialogue"]
    prompt_tracker.update_result(
        "segment_dialogue_0",
        current_dialogue,
    )

    # Iteratively revise and combine with subsequent segments
    for idx in range(1, len(segment_dialogues)):
        job_manager.update_status(
            job_id,
            JobStatus.PROCESSING,
            f"Revising segment {idx + 1}/{len(segment_dialogues)}",
        )

        next_section = segment_dialogues[idx]["dialogue"]
        prompt_tracker.update_result(f"segment_dialogue_{idx}", next_section)
        current_section = segment_dialogues[idx]["section"]

        template = PodcastPrompts.get_template("revise_dialogue_prompt")
        prompt = template.render(
            outline=json.dumps(outline_json),
            dialogue_transcript=current_dialogue,
            next_section=next_section,
            current_section=current_section,
        )

        revised: AIMessage = llm_manager.query_sync(
            "iteration",
            [{"role": "user", "content": prompt}],
            f"revise_dialogue_{idx}",
        )

        prompt_tracker.track(
            f"revise_dialogue_{idx}",
            prompt,
            llm_manager.model_configs["iteration"].name,
            revised.content,
        )

        current_dialogue = revised.content

    return current_dialogue


# TODO: i dont like how this is returning a dict and not an AIMessage
def create_final_conversation(
    dialogue: str,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
) -> Dict:
    """Convert the dialogue into structured Conversation format"""
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, "Formatting final conversation"
    )

    schema = Conversation.model_json_schema()
    template = PodcastPrompts.get_template("podcast_dialogue_prompt")
    prompt = template.render(
        speaker_1_name=request.speaker_1_name,
        speaker_2_name=request.speaker_2_name,
        text=dialogue,
        schema=json.dumps(schema, indent=2),
    )

    # We accumulate response as it comes in then cast
    conversation_json: str = llm_manager.stream_sync(
        "json",
        [{"role": "user", "content": prompt}],
        "create_final_conversation",
        json_schema=schema,
    )

    prompt_tracker.track(
        "create_final_conversation",
        prompt,
        llm_manager.model_configs["json"].name,
        conversation_json,
    )

    return dict(conversation_json)


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

            # Summarize PDFs
            summarized_pdfs = await summarize_pdfs(
                request.pdf_metadata, job_id, llm_manager, prompt_tracker
            )

            # Generate initial outline
            raw_outline = generate_raw_outline(
                summarized_pdfs,
                request,
                llm_manager,
                prompt_tracker,
                job_id,
            )

            # Convert to structured format
            outline_json = generate_structured_outline(
                raw_outline, request, llm_manager, prompt_tracker, job_id
            )
            outline = PodcastOutline.model_validate(outline_json)

            # Process segments
            segments = await process_segments(
                outline, request, llm_manager, prompt_tracker, job_id
            )

            # Generate dialogue
            segment_dialogues = await generate_dialogue(
                segments, outline, request, llm_manager, prompt_tracker, job_id
            )

            # Combine transcripts
            conversation = revise_dialogue(
                segment_dialogues, outline_json, llm_manager, prompt_tracker, job_id
            )

            # Create final conversation
            result = create_final_conversation(
                conversation, request, llm_manager, prompt_tracker, job_id
            )
            final_conversation = Conversation.model_validate(result)

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
