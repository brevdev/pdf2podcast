from pydantic import BaseModel
from typing import Optional, Dict, Literal, List


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
    duration: int
    references: List[str]


class PodcastOutline(BaseModel):
    title: str
    segments: List[PodcastSegment]
