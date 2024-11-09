from shared.shared_types import ServiceType
from shared.otel import OpenTelemetryInstrumentation
import redis
import time
import json
import threading


class JobStatusManager:
    def __init__(
        self,
        service_type: ServiceType,
        telemetry: OpenTelemetryInstrumentation,
        redis_url="redis://redis:6379",
    ):
        self.telemetry = telemetry
        self.redis = redis.Redis.from_url(redis_url, decode_responses=False)
        self.service_type = service_type
        self._lock = threading.Lock()

    def create_job(self, job_id: str):
        with self.telemetry.tracer.start_as_current_span("job.create_job") as span:
            span.set_attribute("job_id", job_id)
            update = {
                "job_id": job_id,
                "status": "pending",
                "message": "Job created",
                "service": self.service_type,
                "timestamp": time.time(),
            }
            # Encode the update dict as JSON bytes
            self.redis.hset(
                f"status:{job_id}:{self.service_type}",
                mapping={k: str(v).encode() for k, v in update.items()},
            )
            self.redis.publish("status_updates:all", json.dumps(update).encode())

    def update_status(self, job_id: str, status: str, message: str):
        with self.telemetry.tracer.start_as_current_span("job.update_status") as span:
            span.set_attribute("job_id", job_id)
            update = {
                "job_id": job_id,
                "status": status,
                "message": message,
                "service": self.service_type,
                "timestamp": time.time(),
            }
            # Encode the update dict as JSON bytes
            self.redis.hset(
                f"status:{job_id}:{self.service_type}",
                mapping={k: str(v).encode() for k, v in update.items()},
            )
            self.redis.publish("status_updates:all", json.dumps(update).encode())

    def set_result(self, job_id: str, result: bytes):
        with self.telemetry.tracer.start_as_current_span("job.set_result") as span:
            span.set_attribute("job_id", job_id)
            self.redis.set(f"result:{job_id}:{self.service_type}", result)

    def set_result_with_expiration(self, job_id: str, result: bytes, ex: int):
        with self.telemetry.tracer.start_as_current_span(
            "job.set_result_with_expiration"
        ) as span:
            span.set_attribute("job_id", job_id)
            self.redis.set(f"result:{job_id}:{self.service_type}", result, ex=ex)

    def get_result(self, job_id: str):
        with self.telemetry.tracer.start_as_current_span("job.get_result") as span:
            span.set_attribute("job_id", job_id)
            result = self.redis.get(f"result:{job_id}:{self.service_type}")
            return result if result else None

    def get_status(self, job_id: str):
        with self.telemetry.tracer.start_as_current_span("job.get_status") as span:
            span.set_attribute("job_id", job_id)
            # Get raw bytes and decode manually
            status = self.redis.hgetall(f"status:{job_id}:{self.service_type}")
            if not status:
                raise ValueError("Job not found")
            # Decode bytes to strings for each field
            return {k.decode(): v.decode() for k, v in status.items()}

    def cleanup_old_jobs(self, max_age=3600):
        current_time = time.time()
        removed = 0
        pattern = f"status:*:{self.service_type}"
        for key in self.redis.scan_iter(match=pattern):
            status = self.redis.hgetall(key)
            try:
                timestamp = float(status[b"timestamp"].decode())
                if timestamp < current_time - max_age:
                    self.redis.delete(key)
                    job_id = key.split(b":")[1].decode()
                    self.redis.delete(f"result:{job_id}:{self.service_type}")
                    removed += 1
            except (KeyError, ValueError):
                # Handle malformed status entries
                continue
        return removed
