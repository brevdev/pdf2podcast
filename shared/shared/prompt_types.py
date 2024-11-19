from pydantic import BaseModel
from typing import List


class ProcessingStep(BaseModel):
    step_name: str
    prompt: str
    response: str
    model: str
    timestamp: float


class PromptTracker(BaseModel):
    steps: List[ProcessingStep]
