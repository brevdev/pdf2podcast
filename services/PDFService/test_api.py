import requests
import os
import time
from typing import Optional
from shared.shared_types import StatusResponse

PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "http://localhost:8003")
POLL_INTERVAL = 2  # seconds
MAX_WAIT_TIME = 3600  # seconds


def poll_job_status(job_id: str) -> Optional[dict]:
    """Poll the job status until completion or failure"""
    start_time = time.time()

    while time.time() - start_time < MAX_WAIT_TIME:
        try:
            response = requests.get(f"{PDF_SERVICE_URL}/status/{job_id}")
            status_data = StatusResponse.model_validate(response.json())
            # print(f"Polling status... Response: {status_data}")

            # Check the job status from the response
            if status_data.status == "JobStatus.COMPLETED":
                return status_data
            elif status_data.status == "JobStatus.FAILED":
                print(f"Job failed: {status_data.message}")
                return None
            elif status_data.status == "JobStatus.PROCESSING":
                print(f"Job still processing... {status_data.message}")
                time.sleep(POLL_INTERVAL)
                continue
            else:
                print(f"Unknown status: {status_data.status}")
                time.sleep(POLL_INTERVAL)

        except requests.RequestException as e:
            print(f"Error polling status: {e}")
            return None

    print("Error: Job timed out")
    return None


def test_convert_pdf_endpoint():
    # Path to a sample PDF file for testing
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sample_pdf_path = os.path.join(current_dir, "../../PNP_Proof.pdf")

    # Ensure the sample PDF file exists
    if not os.path.exists(sample_pdf_path):
        print(f"Error: Sample PDF file not found at {sample_pdf_path}")
        return False

    # Submit the conversion job
    try:
        with open(sample_pdf_path, "rb") as pdf_file:
            files = {"file": ("sample.pdf", pdf_file, "application/pdf")}
            response = requests.post(f"{PDF_SERVICE_URL}/convert", files=files)

        if response.status_code != 202:
            print(f"Error: Request failed with status code {response.status_code}")
            return False

        job_data = response.json()
        job_id = job_data.get("job_id")
        if not job_id:
            print("Error: No job_id in response")
            return False

        print("Starting job polling...")
        # Poll for job completion
        status_data = poll_job_status(job_id)
        if not status_data:
            return False

        print(f"Job completed. Status data: {status_data}")

        # Get the output
        output = get_job_output(job_id)
        if not output:
            print("Failed to get output")
            return False

        print("Successfully retrieved output")

        # Validate output content
        print("Validating output content...")
        if len(output) < 10:  # Basic check for minimum content
            print("Error: Output content seems too short")
            return False

        print("Success: PDF conversion test passed!")
        print("Response content:")
        print(
            output[:500] + "..." if len(output) > 500 else output
        )  # Print first 500 chars
        return True

    except requests.RequestException as e:
        print(f"Error during request: {e}")
        return False


def get_job_output(job_id: str) -> Optional[str]:
    """Get the markdown output for a completed job"""
    try:
        response = requests.get(f"{PDF_SERVICE_URL}/output/{job_id}")
        if response.status_code != 200:
            print(f"Error getting output: {response.status_code}")
            if response.status_code == 404:
                print(
                    "Job result not found. This might mean the job is still processing."
                )
            return None
        return response.text
    except requests.RequestException as e:
        print(f"Error getting output: {e}")
        return None


def test_convert_pdf_endpoint_invalid_file():
    files = {"file": ("test.txt", b"This is not a PDF file", "text/plain")}
    try:
        response = requests.post(f"{PDF_SERVICE_URL}/convert", files=files)

        if response.status_code != 400:
            print(f"Error: Expected 400 status code, got {response.status_code}")
            return False

        print("Success: Invalid file test passed!")
        return True

    except requests.RequestException as e:
        print(f"Error during request: {e}")
        return False


def test_health_endpoint():
    try:
        response = requests.get(f"{PDF_SERVICE_URL}/health")

        if response.status_code != 200:
            print(f"Error: Health check failed with status code {response.status_code}")
            return False

        health_data = response.json()
        if health_data.get("status") != "healthy":
            print(
                f"Error: Service unhealthy: {health_data.get('error', 'Unknown error')}"
            )
            return False

        print("Success: Health check passed!")
        return True

    except requests.RequestException as e:
        print(f"Error checking health: {e}")
        return False


if __name__ == "__main__":
    print("Running PDF Service API tests...")

    print("\nTest 1: Health check")
    test_health_endpoint()

    print("\nTest 2: Valid PDF conversion")
    test_convert_pdf_endpoint()

    print("\nTest 3: Invalid file handling")
    test_convert_pdf_endpoint_invalid_file()
