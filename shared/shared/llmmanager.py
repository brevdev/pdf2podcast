from langchain_nvidia_ai_endpoints import ChatNVIDIA
from typing import List, Dict, Any, Optional
import logging
import json
from shared.otel import OpenTelemetryInstrumentation
from opentelemetry.trace.status import StatusCode
import logging
from typing import Optional
from pathlib import Path
from dataclasses import dataclass



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    """
    Wrapper over Langchain's model configuration

    from langchain_nvidia_ai_endpoints import ChatNVIDIA
    model = ChatNVIDIA(model="meta/llama2-70b", base_url="https://integrate.api.nvidia.com/v1")
    """

    name: str
    api_base: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelConfig":
        return cls(
            name=data["name"],
            api_base=data["api_base"],
        )

class LLMManager:
    DEFAULT_CONFIGS = {
        "reasoning": {
            "name": "meta/llama-3.1-405b-instruct",
            "api_base": "https://integrate.api.nvidia.com/v1",
        },
        "iteration": {
            "name": "meta/llama-3.1-405b-instruct",
            "api_base": "https://integrate.api.nvidia.com/v1",
        },
        "json": {
            "name": "meta/llama-3.1-70b-instruct",
            "api_base": "https://integrate.api.nvidia.com/v1",
        },
    }

    def __init__(
        self,
        api_key: str,
        telemetry: OpenTelemetryInstrumentation,
        config_path: Optional[str] = None,
    ):
        """
        Initialize LLMManager with telemetry
        requires: OpenTelemetryInstrumentation instance for tracing
        """
        try:
            self.api_key = api_key
            self.telemetry = telemetry
            self._llm_cache: Dict[str, ChatNVIDIA] = {}
            self.model_configs = self._load_configurations(config_path)
            logger.info("Successfully initialized LLMManager")
        except Exception as e:
            logger.error(f"Failed to initialize LLMManager: {e}")
            raise

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

    def get_llm(self, model_key: str) -> ChatNVIDIA:
        """Get or create a ChatNVIDIA model for the specified model key"""
        if model_key not in self.model_configs:
            raise ValueError(f"Unknown model key: {model_key}")
        if model_key not in self._llm_cache:
            config = self.model_configs[model_key]
            # Store base model without transformations
            self._llm_cache[model_key] = ChatNVIDIA(
                model=config.name, base_url=config.api_base, nvidia_api_key=self.api_key
            )
        return self._llm_cache[model_key]

    def query(
        self,
        model_key: str,
        messages: List[Dict[str, str]],
        query_name: str,
        json_schema: Optional[Dict] = None,
        sync: bool = True,
        retries: int = 5,
    ) -> Any:
        """Send a query to the specified model with retry logic"""
        with self.telemetry.tracer.start_as_current_span(
            f"agent.query.{query_name}"
        ) as span:
            span.set_attribute("model_key", model_key)
            span.set_attribute("sync", sync)
            span.set_attribute("retries", retries)

            try:
                llm = self.get_llm(model_key)

                if json_schema:
                    llm = llm.with_structured_output(json_schema)

                llm = llm.with_retry(
                    stop_after_attempt=retries, wait_exponential_jitter=True
                )

                if sync:
                    response = llm.invoke(messages)
                else:
                    response = llm.ainvoke(messages)

                return response

            except Exception as e:
                span.set_status(StatusCode.ERROR)
                span.record_exception(e)
                logger.error(f"Query failed: {e}")
                raise Exception(
                    f"Failed to get response after {retries} attempts"
                ) from e