from fastapi import FastAPI, BackgroundTasks, HTTPException
from shared.shared_types import ServiceType, JobStatus
from shared.job import JobStatusManager
import flexagent as fa
from flexagent.backend import BackendConfig
from flexagent.engine import Value
from pydantic import BaseModel
from pathlib import Path
from dataclasses import dataclass
from typing import List, Literal, Dict, Optional, Any
import json
import os
import logging
import time
from prompts import (
    RAW_OUTLINE_PROMPT,
    OUTLINE_PROMPT,
    SEGMENT_TRANSCRIPT_PROMPT,
    DEEP_DIVE_PROMPT,
    RAW_PODCAST_DIALOGUE_PROMPT_v2,
    FUSE_OUTLINE_PROMPT,
    REVISE_PROMPT,
    PODCAST_DIALOGUE_PROMPT,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Data Models
class DialogueEntry(BaseModel):
    text: str
    speaker: Literal["speaker-1", "speaker-2"]


class Conversation(BaseModel):
    scratchpad: str
    dialogue: List[DialogueEntry]


class PodcastSegment(BaseModel):
    section: str
    descriptions: List[str]
    duration: int


class PodcastOutline(BaseModel):
    title: str
    segments: List[PodcastSegment]


class TranscriptionRequest(BaseModel):
    markdown: str
    duration: int = 20
    speaker_1_name: str = "Bob"
    speaker_2_name: str = "Kate"
    model: str = "meta/llama-3.1-405b-instruct"
    job_id: str


@dataclass
class ModelConfig:
    name: str
    api_base: str
    backend_type: str = "nim"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelConfig":
        return cls(
            name=data["name"],
            api_base=data["api_base"],
            backend_type=data.get("backend_type", "nim"),
        )


class LLMManager:
    DEFAULT_CONFIGS = {
        "reasoning": {
            "name": "meta/llama-3.1-405b-instruct",
            "api_base": "https://integrate.api.nvidia.com/v1",
            "backend_type": "nim",
        },
        "subsegments": {
            "name": "meta/llama-3.1-405b-instruct",
            "api_base": "https://integrate.api.nvidia.com/v1",
            "backend_type": "nim",
        },
        "json": {
            "name": "meta/llama-3.1-70b-instruct",
            "api_base": "https://nim-pc8kmx5ae.brevlab.com/v1",
            "backend_type": "nim",
        },
    }

    def __init__(self, api_key: str, config_path: Optional[str] = None):
        self.api_key = api_key
        self._llm_cache: Dict[str, fa.ops.LLM] = {}
        self.model_configs = self._load_configurations(config_path)

    def _load_configurations(
        self, config_path: Optional[str]
    ) -> Dict[str, ModelConfig]:
        """Load model configurations from JSON file if provided, otherwise use defaults"""
        configs = self.DEFAULT_CONFIGS.copy()

        if config_path:
            try:
                config_path = Path(config_path)
                if config_path.exists():
                    with config_path.open() as f:
                        custom_configs = json.load(f)
                    configs.update(custom_configs)
                else:
                    logger.warning(
                        f"Config file {config_path} not found, using default configurations"
                    )
            except Exception as e:
                logger.error(f"Error loading config file: {e}")
                logger.warning("Using default configurations")

        return {key: ModelConfig.from_dict(config) for key, config in configs.items()}

    def get_llm(self, model_key: str) -> fa.ops.LLM:
        """Get or create an LLM instance for the specified model key"""
        if model_key not in self.model_configs:
            raise ValueError(f"Unknown model key: {model_key}")

        if model_key not in self._llm_cache:
            config = self.model_configs[model_key]
            backend = BackendConfig(
                backend_type=config.backend_type,
                model_name=config.name,
                api_key=self.api_key,
                api_base=config.api_base,
            )
            self._llm_cache[model_key] = fa.ops.LLM().to(backend)

        return self._llm_cache[model_key]

    def query(
        self,
        model_key: str,
        messages: List[Dict[str, str]],
        json_schema: Optional[Dict] = None,
        sync: bool = True,
        retries: int = 5,
    ) -> Any:
        """Send a query to the specified model with retry logic"""
        llm = self.get_llm(model_key)

        for attempt in range(retries):
            try:
                extra_body = (
                    {"nvext": {"guided_json": json_schema}} if json_schema else None
                )
                response = llm(messages, extra_body=extra_body)
                return response.get() if sync else response

            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{retries} failed: {str(e)}")
                if attempt == retries - 1:
                    raise Exception(
                        f"Failed to get response after {retries} attempts"
                    ) from e
                time.sleep(3)


# FastAPI Application
app = FastAPI(debug=True)
job_manager = JobStatusManager(ServiceType.AGENT)


def process_transcription(job_id: str, request: TranscriptionRequest):
    try:
        llm_manager = LLMManager(
            api_key=os.getenv("NIM_KEY"),
            config_path=os.getenv("MODEL_CONFIG_PATH"),  # Add this line
        )
        # Initialize processing
        job_manager.update_status(
            job_id, JobStatus.PROCESSING, "Initializing processing"
        )
        schema = PodcastOutline.model_json_schema()

        # Generate initial outline
        job_manager.update_status(
            job_id, JobStatus.PROCESSING, "Generating initial outline"
        )
        prompt = RAW_OUTLINE_PROMPT.render(
            text=request.markdown, duration=request.duration
        )
        raw_outline = llm_manager.query(
            "reasoning", [{"role": "user", "content": prompt}]
        )

        # Convert to structured format
        job_manager.update_status(
            job_id, JobStatus.PROCESSING, "Converting raw outline to structured format"
        )
        prompt = OUTLINE_PROMPT.render(
            text=raw_outline, schema=json.dumps(schema, indent=2)
        )
        outline = llm_manager.query(
            "json", [{"role": "user", "content": prompt}], json_schema=schema
        )
        outline_json = json.loads(outline)

        # Process segments
        longest_segment_idx = max(
            range(len(outline_json["segments"])),
            key=lambda i: outline_json["segments"][i]["duration"],
        )

        segments = []
        sub_outline = {}
        for idx, segment in enumerate(outline_json["segments"]):
            job_manager.update_status(
                job_id,
                JobStatus.PROCESSING,
                f"Processing segment {idx + 1}/{len(outline_json['segments'])}: {segment['section']}",
            )

            if idx == longest_segment_idx:
                ret = deep_dive_segment(
                    job_id, request.markdown, segment, llm_manager, schema
                )
                segments.append(ret[0])
                sub_outline = ret[1]
            else:
                prompt = SEGMENT_TRANSCRIPT_PROMPT.render(
                    text=request.markdown,
                    duration=segment["duration"],
                    topic=segment["section"],
                    angles="\n".join(segment["descriptions"]),
                )
                segments.append(
                    llm_manager.query(
                        "reasoning", [{"role": "user", "content": prompt}], sync=False
                    )
                )

        # Generate dialogue
        segment_transcripts = []
        for idx, segment in enumerate(outline_json["segments"]):
            job_manager.update_status(
                job_id,
                JobStatus.PROCESSING,
                f"Converting segment {idx + 1}/{len(outline_json['segments'])} to dialogue",
            )
            prompt = RAW_PODCAST_DIALOGUE_PROMPT_v2.render(
                text=segments[idx].get(),
                duration=segment["duration"],
                descriptions=segment["descriptions"],
                speaker_1_name=request.speaker_1_name,
                speaker_2_name=request.speaker_2_name,
            )
            segment_transcripts.append(
                llm_manager.query(
                    "reasoning", [{"role": "user", "content": prompt}], sync=False
                )
            )

        # Combine transcripts
        job_manager.update_status(job_id, JobStatus.PROCESSING, "Combining segments")
        full_transcript = "\n".join([segment.get() for segment in segments])
        conversation = "\n".join([segment.get() for segment in segment_transcripts])

        # Fuse outline
        job_manager.update_status(job_id, JobStatus.PROCESSING, "Fusing outline")
        prompt = FUSE_OUTLINE_PROMPT.render(
            overall_outline=outline, sub_outline=sub_outline
        )
        full_outline = llm_manager.query(
            "reasoning", [{"role": "user", "content": prompt}]
        )

        # Revise dialogue
        job_manager.update_status(job_id, JobStatus.PROCESSING, "Revising dialogue")
        prompt = REVISE_PROMPT.render(
            raw_transcript=full_transcript,
            dialogue_transcript=conversation,
            outline=full_outline,
        )
        conversation = llm_manager.query(
            "reasoning", [{"role": "user", "content": prompt}]
        )

        # Convert to final JSON format
        schema = Conversation.model_json_schema()
        job_manager.update_status(
            job_id, JobStatus.PROCESSING, "Converting to final format"
        )
        prompt = PODCAST_DIALOGUE_PROMPT.render(
            text=conversation,
            schema=json.dumps(schema, indent=2),
            speaker_1_name=request.speaker_1_name,
            speaker_2_name=request.speaker_2_name,
        )
        final_conversation = llm_manager.query(
            "json", [{"role": "user", "content": prompt}], json_schema=schema
        )

        # Store result
        result = json.loads(final_conversation)
        job_manager.set_result(job_id, json.dumps(result).encode())
        job_manager.update_status(
            job_id, JobStatus.COMPLETED, "Transcription completed successfully"
        )

    except Exception as e:
        logger.error(f"Error processing job {job_id}: {str(e)}")
        job_manager.update_status(job_id, JobStatus.FAILED, str(e))
        raise


def deep_dive_segment(
    job_id: str,
    text: str,
    segment: Dict[str, str],
    llm_manager: LLMManager,
    schema: Dict,
) -> tuple[Value, Dict]:
    status_msg = f"Performing deep dive analysis of segment: {segment['section']}"
    job_manager.update_status(job_id, JobStatus.PROCESSING, status_msg)
    logger.info(f"Job {job_id}: {status_msg}")

    prompt = DEEP_DIVE_PROMPT.render(
        text=text, topic=segment["descriptions"], duration=segment["duration"]
    )
    outline = llm_manager.query("reasoning", [{"role": "user", "content": prompt}])

    prompt = OUTLINE_PROMPT.render(text=outline, schema=json.dumps(schema, indent=2))
    outline_json = json.loads(
        llm_manager.query(
            "json", [{"role": "user", "content": prompt}], json_schema=schema
        )
    )

    segments = []
    for subsegment in outline_json["segments"]:
        job_manager.update_status(
            job_id,
            JobStatus.PROCESSING,
            f"Processing subsegment: {subsegment['section']}",
        )
        prompt = SEGMENT_TRANSCRIPT_PROMPT.render(
            text=text,
            duration=subsegment["duration"],
            topic=subsegment["section"],
            angles="\n".join(subsegment["descriptions"]),
        )
        segments.append(
            llm_manager.query(
                "subsegments", [{"role": "user", "content": prompt}], sync=False
            )
        )

    texts = [segment.get() for segment in segments]
    return (Value("\n".join(texts)), outline_json)


# API Endpoints
@app.post("/transcribe", status_code=202)
def transcribe(request: TranscriptionRequest, background_tasks: BackgroundTasks):
    job_manager.create_job(request.job_id)
    background_tasks.add_task(process_transcription, request.job_id, request)
    return {"job_id": request.job_id}


@app.get("/status/{job_id}")
def get_status(job_id: str):
    return job_manager.get_status(job_id)


@app.get("/output/{job_id}")
def get_output(job_id: str):
    result = job_manager.get_result(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return json.loads(result.decode())


@app.get("/transcribe/health")
def health():
    return {
        "status": "healthy",
        "version": fa.__version__,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8964)
