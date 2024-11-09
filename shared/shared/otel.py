from dataclasses import dataclass
from typing import Optional
import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class OpenTelemetryConfig:
    """Configuration for OpenTelemetry setup."""

    service_name: str
    otlp_endpoint: str = "http://jaeger:4317"
    enable_redis: bool = True
    enable_requests: bool = True
    enable_httpx: bool = True
    enable_urllib3: bool = True


class OpenTelemetryInstrumentation:
    """
    Lightweight OTEL wrapper

    Example usage:
        telemetry = OpenTelemetryInstrumentation()
        app = FastAPI()
        telemetry.initialize(app, "api-service")

        # In code
        with telemetry.tracer.start_as_current_span("operation_name") as span:
            span.set_attribute("key", "value")
    """

    def __init__(self):
        self._tracer: Optional[trace.Tracer] = None
        self._config: Optional[OpenTelemetryConfig] = None

    @property
    def tracer(self) -> trace.Tracer:
        """Get the configured tracer instance."""
        if not self._tracer:
            raise RuntimeError(
                "OpenTelemetry has not been initialized. Call initialize() first."
            )
        return self._tracer

    def initialize(
        self, config: OpenTelemetryConfig, app=None
    ) -> "OpenTelemetryInstrumentation":
        """
        Initialize OpenTelemetry instrumentation with the given configuration.

        Args:
            app: The FastAPI application instance
            config: OpenTelemetryConfig instance containing configuration options

        Returns:
            self for method chaining
        """
        self._config = config
        logger.info(f"Setting up tracing for service: {self._config.service_name}")
        logger.info(f"Container ID: {os.uname().nodename}")
        self._setup_tracing()
        self._instrument_app(app)
        return self

    def _setup_tracing(self) -> None:
        """Set up the OpenTelemetry tracer provider and processors."""
        resource = Resource.create({"service.name": self._config.service_name})

        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(
            OTLPSpanExporter(endpoint=self._config.otlp_endpoint)
        )

        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        self._tracer = trace.get_tracer(self._config.service_name)

    def _instrument_app(self, app=None) -> None:
        """Instrument the FastAPI application and optional components."""
        # Instrument FastAPI
        if app:
            FastAPIInstrumentor.instrument_app(app)

        # Instrument Redis if enabled
        if self._config.enable_redis:
            RedisInstrumentor().instrument()

        # Instrument requests library if enabled
        if self._config.enable_requests:
            RequestsInstrumentor().instrument()

        if self._config.enable_httpx:
            HTTPXClientInstrumentor().instrument()

        if self._config.enable_urllib3:
            URLLib3Instrumentor().instrument()
