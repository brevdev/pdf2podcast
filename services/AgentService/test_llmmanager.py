import asyncio
import os
from shared.otel import OpenTelemetryInstrumentation, OpenTelemetryConfig
import logging
from fastapi import FastAPI
from shared.llmmanager import LLMManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mock_app = FastAPI()
mock_telemetry = OpenTelemetryInstrumentation()
mock_config = OpenTelemetryConfig(
    service_name="test-llm-manager",
    otlp_endpoint="",
    enable_redis=False,
    enable_requests=False,
)
mock_telemetry.initialize(mock_config, mock_app)


async def test_basic_queries():
    """Test both sync and async basic queries"""
    print("\n=== Testing Basic Queries ===")

    manager = LLMManager(api_key=os.getenv("NIM_KEY"), telemetry=mock_telemetry)

    # Test sync query
    print("\nTesting sync query...")
    response = manager.query(
        model_key="reasoning",
        messages=[
            {
                "role": "user",
                "content": "What are the three laws of robotics? Be brief.",
            }
        ],
        query_name="test_sync",
        sync=True,
    )
    print(f"Sync Response: {response}\n")

    # Test async query
    print("Testing async query...")
    response = await manager.query(
        model_key="reasoning",
        messages=[
            {
                "role": "user",
                "content": "What is machine learning? Answer in one sentence.",
            }
        ],
        query_name="test_async",
        sync=False,
    )
    print(f"Async Response: {response}\n")


async def test_parallel_processing():
    """Test processing multiple queries in parallel"""
    print("\n=== Testing Parallel Processing ===")

    manager = LLMManager(api_key=os.getenv("NIM_KEY"), telemetry=mock_telemetry)

    questions = ["What is Python?", "What is JavaScript?", "What is Rust?"]

    async def process_query(question: str, idx: int):
        return await manager.query(
            model_key="reasoning",
            messages=[
                {"role": "user", "content": f"Explain {question} in one sentence."}
            ],
            query_name=f"test_parallel_{idx}",
            sync=False,
        )

    print("\nSending parallel queries...")
    tasks = [process_query(q, i) for i, q in enumerate(questions)]
    responses = await asyncio.gather(*tasks)

    for question, response in zip(questions, responses):
        print(f"\nQuestion: {question}")
        print(f"Response: {response}")


async def test_json_schema():
    """Test JSON schema structured output"""
    print("\n=== Testing JSON Schema ===")

    manager = LLMManager(api_key=os.getenv("NIM_KEY"), telemetry=mock_telemetry)

    # Define a schema for a person's details
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
            "occupation": {"type": "string"},
            "hobbies": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name", "age", "occupation", "hobbies"],
    }

    print("\nTesting structured output...")
    response = manager.query(
        model_key="json",
        messages=[
            {"role": "user", "content": "Generate details for a fictional character."}
        ],
        query_name="test_json",
        json_schema=schema,
        sync=True,
    )
    print(f"Structured Response: {response}")


async def main_test():
    """Run all tests"""
    try:
        # Test basic queries
        await test_basic_queries()

        # Test parallel processing
        await test_parallel_processing()

        # Test JSON schema
        await test_json_schema()

    except Exception as e:
        print(f"\nError occurred: {str(e)}")


if __name__ == "__main__":
    # Ensure NIM_KEY is set
    asyncio.run(main_test())
