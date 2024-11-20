from pydantic import BaseModel, Field
from typing import Optional, Dict, Literal, List, Annotated


class SavedPodcast(BaseModel):
    job_id: str
    filename: str
    created_at: str
    size: int
    transcription_params: Optional[Dict] = {}


class SavedPodcastWithAudio(SavedPodcast):
    audio_data: str


class DialogueEntry(BaseModel):
    text: str
    speaker: Literal["speaker-1", "speaker-2"]


class Conversation(BaseModel):
    scratchpad: str
    dialogue: List[DialogueEntry]


class SegmentPoint(BaseModel):
    description: str


class SegmentTopic(BaseModel):
    title: str
    points: List[SegmentPoint]


class PodcastSegment(BaseModel):
    section: str
    topics: List[SegmentTopic]
    references: Annotated[List[str], Field(min_length=0, max_length=2)]


class PodcastOutline(BaseModel):
    title: str
    segments: List[PodcastSegment]
