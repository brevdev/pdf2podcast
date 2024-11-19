from typing import Dict
import time
import logging
from .storage import StorageManager
from .prompt_types import ProcessingStep, PromptTracker as PromptTrackerModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PromptTracker:
    """Track prompts and responses and save them to storage"""

    def __init__(self, job_id: str, user_id: str, storage_manager: StorageManager):
        self.job_id = job_id
        self.user_id = user_id
        self.steps: Dict[str, ProcessingStep] = {}
        self.storage_manager = storage_manager

    def track(self, step_name: str, prompt: str, model: str, response: str = None):
        """Track a processing step"""
        self.steps[step_name] = ProcessingStep(
            step_name=step_name,
            prompt=prompt,
            response=response if response else "",
            model=model,
            timestamp=time.time(),
        )
        if response:
            self._save()
        logger.info(f"Tracked step {step_name} for {self.job_id}")

    def update_result(self, step_name: str, response: str):
        """Update the response for an existing step"""
        if step_name in self.steps:
            self.steps[step_name].response = response
            self._save()
            logger.info(f"Updated response for step {step_name}")
        else:
            logger.warning(f"Step {step_name} not found in prompt tracker")

    def _save(self):
        """Save the current state to storage"""
        tracker = PromptTrackerModel(steps=list(self.steps.values()))
        self.storage_manager.store_file(
            self.user_id,
            self.job_id,
            tracker.model_dump_json().encode(),
            f"{self.job_id}_prompt_tracker.json",
            "application/json",
        )
        logger.info(
            f"Stored prompt tracker for {self.job_id} in minio. Length: {len(self.steps)}"
        )
