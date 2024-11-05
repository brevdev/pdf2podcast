import io
import json
from minio import Minio
from minio.error import S3Error
from shared.shared_types import TranscriptionParams
import os
import logging

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

    def store_audio(
        self,
        job_id: str,
        audio_content: bytes,
        filename: str,
        transcription_params: TranscriptionParams,
    ):
        try:
            object_name = f"{job_id}/{filename}"
            self.client.put_object(
                self.bucket_name,
                object_name,
                io.BytesIO(audio_content),
                len(audio_content),
                content_type="audio/mpeg",
            )
            logger.info(f"Stored audio for {job_id} in MinIO as {object_name}")
        except S3Error as e:
            logger.error(f"Failed to store audio in MinIO: {e}")
            raise

    def get_audio(self, job_id: str, filename: str):
        try:
            object_name = f"{job_id}/{filename}"
            result = self.client.get_object(self.bucket_name, object_name).read()
            logger.info(f"Retrieved audio for {job_id} from MinIO as {object_name}")
            return result
        except S3Error as e:
            logger.error(f"Failed to get audio from MinIO: {e}")
            raise

    def list_files(self):
        """List all audio files stored in MinIO"""
        try:
            # List all objects (no prefix to get everything)
            objects = self.client.list_objects(self.bucket_name)
            files = []
            
            for obj in objects:
                try:
                    # Get the metadata for each file
                    stat = self.client.stat_object(self.bucket_name, obj.object_name)
                    
                    # Extract job_id from the path (first part of the path)
                    job_id = obj.object_name.split('/')[0]
                    
                    files.append({
                        "job_id": job_id,
                        "filename": obj.object_name.split('/')[-1],
                        "created_at": obj.last_modified.isoformat(),
                        "transcription_params": json.loads(
                            stat.metadata.get("transcription_params", "{}")
                        ) if stat.metadata else {}
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing object {obj.object_name}: {str(e)}")
                    continue
                    
            return files
        except Exception as e:
            logger.error(f"Failed to list files from MinIO: {str(e)}")
            raise