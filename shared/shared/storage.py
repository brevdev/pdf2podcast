import io
import json
import base64
from minio import Minio
from minio.error import S3Error
from shared.shared_types import TranscriptionParams
import os
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Minio config
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME", "audio-results")


# TODO: use this to wrap redis as well
# TODO: wrap errors in StorageError
# TODO: implement cleanup and delete as well
class StorageManager:
    def __init__(self):
        """Initialize MinIO client and ensure bucket exists"""
        try:
            self.client = Minio(
                os.getenv("MINIO_ENDPOINT", "minio:9000"),
                access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
                secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
                secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
            )

            self.bucket_name = os.getenv("MINIO_BUCKET_NAME", "audio-results")
            self._ensure_bucket_exists()
            logger.info("Successfully initialized MinIO storage")

        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
            raise

    def _ensure_bucket_exists(self):
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
        except Exception as e:
            logger.error(f"Failed to ensure bucket exists: {e}")
            raise

    def store_file(
        self,
        job_id: str,
        content: bytes,
        filename: str,
        content_type: str,
        metadata: dict = None,
    ) -> None:
        """Store any file type in MinIO with metadata"""
        try:
            self.client.put_object(
                self.bucket_name,
                f"{job_id}/{filename}",
                io.BytesIO(content),
                length=len(content),
                content_type=content_type,
                metadata=metadata.model_dump()
                if hasattr(metadata, "model_dump")
                else metadata,
            )
        except Exception as e:
            logger.error(f"Failed to store file {filename} for job {job_id}: {str(e)}")
            raise

    def store_audio(
        self,
        job_id: str,
        audio_content: bytes,
        filename: str,
        transcription_params: TranscriptionParams,
    ):
        """Store audio file with metadata in MinIO"""
        try:
            object_name = f"{job_id}/{filename}"

            # Convert transcription params to JSON string for metadata
            params_json = json.dumps(transcription_params.model_dump())

            # Create metadata dictionary with transcription params
            metadata = {"X-Amz-Meta-Transcription-Params": params_json}

            self.client.put_object(
                self.bucket_name,
                object_name,
                io.BytesIO(audio_content),
                len(audio_content),
                content_type="audio/mpeg",
                metadata=metadata,
            )
            logger.info(
                f"Stored audio for {job_id} in MinIO as {object_name} with metadata"
            )

        except S3Error as e:
            logger.error(f"Failed to store audio in MinIO: {e}")
            raise

    def list_files_metadata(self):
        """List all audio files stored in MinIO with their metadata but without audio content"""
        try:
            objects = self.client.list_objects(self.bucket_name, recursive=True)
            files = []

            for obj in objects:
                if obj.object_name.endswith("/"):
                    continue

                try:
                    stat = self.client.stat_object(self.bucket_name, obj.object_name)
                    path_parts = obj.object_name.split("/")

                    if not path_parts[-1].endswith(".mp3"):
                        continue

                    job_id = path_parts[0]

                    file_info = {
                        "job_id": job_id,
                        "filename": path_parts[-1],
                        "size": stat.size,
                        "created_at": obj.last_modified.isoformat(),
                        "path": obj.object_name,
                        "transcription_params": {},
                    }

                    if stat.metadata:
                        try:
                            params = stat.metadata.get(
                                "X-Amz-Meta-Transcription-Params"
                            )
                            if params:
                                file_info["transcription_params"] = json.loads(params)
                        except json.JSONDecodeError:
                            logger.warning(
                                f"Could not parse transcription params for {obj.object_name}"
                            )

                    files.append(file_info)
                    logger.info(
                        f"Found file: {obj.object_name}, size: {stat.size} bytes"
                    )

                except Exception as e:
                    logger.error(f"Error processing object {obj.object_name}: {str(e)}")
                    continue

            files.sort(key=lambda x: x["created_at"], reverse=True)
            logger.info(
                f"Successfully listed {len(files)} metadata for {len(files)} files from MinIO"
            )
            return files

        except Exception as e:
            logger.error(f"Failed to list files from MinIO: {str(e)}")
            raise

    def get_podcast_audio(self, job_id: str) -> Optional[str]:
        """Get the audio data for a specific podcast by job_id"""
        try:
            # Find the file with matching job_id
            objects = self.client.list_objects(
                self.bucket_name, prefix=f"{job_id}/", recursive=True
            )

            for obj in objects:
                if obj.object_name.endswith(".mp3"):
                    audio_data = self.client.get_object(
                        self.bucket_name, obj.object_name
                    ).read()
                    return base64.b64encode(audio_data).decode("utf-8")

            return None

        except Exception as e:
            logger.error(f"Failed to get audio for job_id {job_id}: {str(e)}")
            raise
