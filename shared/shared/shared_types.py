from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Literal
from enum import Enum


class ServiceType(str, Enum):
    PDF = "pdf"
    AGENT = "agent"
    TTS = "tts"


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class StatusUpdate(BaseModel):
    job_id: str
    status: JobStatus
    message: Optional[str] = None
    service: Optional[ServiceType] = None
    timestamp: Optional[float] = None
    data: Optional[dict] = None


class StatusResponse(BaseModel):
    status: str
    result: Optional[str] = None
    error: Optional[str] = None
    message: Optional[str] = None


class TranscriptionParams(BaseModel):
    name: str = Field(..., description="Name of the podcast")
    duration: int = Field(..., description="Duration in minutes")
    speaker_1_name: str = Field(..., description="Name of the first speaker")
    speaker_2_name: str = Field(..., description="Name of the second speaker")
    model: str = Field(..., description="Model name/path to use for transcription")
    voice_mapping: Dict[str, str] = Field(
        ...,
        description="Mapping of speaker IDs to voice IDs",
        example={
            "speaker-1": "iP95p4xoKVk53GoZ742B",
            "speaker-2": "9BWtsMINqrJLrRacOk9x",
        },
    )


class SavedPodcast(BaseModel):
    job_id: str
    filename: str
    created_at: str
    size: int
    transcription_params: Optional[Dict] = {}


class SavedPodcastWithAudio(SavedPodcast):
    audio_data: str


# Transcript schema
class DialogueEntry(BaseModel):
    text: str
    speaker: Literal["speaker-1", "speaker-2"]


class Conversation(BaseModel):
    scratchpad: str
    dialogue: List[DialogueEntry]


# Prompt tracker schema
class ProcessingStep(BaseModel):
    step_name: str
    prompt: str
    response: str
    model: str
    timestamp: float


class PromptTracker(BaseModel):
    steps: List[ProcessingStep]
