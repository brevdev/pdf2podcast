import requests
import json
import os
from shared.shared_types import TranscriptionRequest, PDFMetadata

def test_transcribe_api():
    # API endpoint
    AGENT_SERVICE_URL = os.getenv(
        "AGENT_SERVICE_URL", "http://localhost:8964/transcribe"
    )

    # Create a proper TranscriptionRequest
    pdf_metadata = PDFMetadata(
        filename="sample.pdf",
        markdown="Sample markdown content",
        summary=""
    )

    request = TranscriptionRequest(
        # TranscriptionParams fields
        name="Test Podcast",
        duration=30,  # Duration in minutes
        speaker_1_name="Host",
        speaker_2_name="Guest",
        voice_mapping={
            "speaker-1": "iP95p4xoKVk53GoZ742B",  # Example voice ID
            "speaker-2": "9BWtsMINqrJLrRacOk9x"   # Example voice ID
        },
        guide="Sample focus instructions",  # Optional
        
        # TranscriptionRequest specific fields
        pdf_metadata=[pdf_metadata],
        job_id="test-job-123"
    )
    
    # Send POST request
    response = requests.post(AGENT_SERVICE_URL, json=request.model_dump())

    # Check if the request was successful
    assert (
        response.status_code == 202
    ), f"Expected status code 202, but got {response.status_code}. Response: {response.text}"

    # Parse the JSON response
    try:
        result = response.json()
        assert "job_id" in result, "Response should contain job_id"
    except json.JSONDecodeError:
        assert False, "Response is not valid JSON"

    print(f"Job created with ID: {result['job_id']}")

if __name__ == "__main__":
    test_transcribe_api()
    print("All tests passed!")
