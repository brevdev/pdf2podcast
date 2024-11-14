import requests
import sys
import ujson as json
import time
from pathlib import Path
from shared.shared_types import StatusResponse


def test_pdf_conversion(pdf_path: str, api_url: str = "http://localhost:8003"):
    """
    Test the PDF conversion endpoint by uploading a PDF file and displaying the markdown result.

    Args:
        pdf_path: Path to the PDF file to convert
        api_url: Base URL of the API service
    """
    # First check if the service is healthy
    try:
        health_response = requests.get(f"{api_url}/health")
        health_response.raise_for_status()
        print("Health check response:", json.dumps(health_response.json(), indent=2))
    except requests.exceptions.RequestException as e:
        print(f"Error checking service health: {e}")
        sys.exit(1)

    # Check if file exists
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"Error: File {pdf_path} does not exist")
        sys.exit(1)

    # Prepare the file for upload
    files = {"file": (pdf_file.name, open(pdf_file, "rb"), "application/pdf")}

    try:
        # Make the conversion request
        print(f"\nUploading {pdf_file.name} for conversion...")
        response = requests.post(f"{api_url}/convert", files=files)
        response.raise_for_status()

        # Get the task ID
        result = response.json()
        task_id = result["task_id"]
        print(f"Task ID: {task_id}")
        print("Waiting for conversion to complete...")

        # Poll the status endpoint until the task is complete
        while True:
            status_response = requests.get(f"{api_url}/status/{task_id}")

            try:
                status_data = StatusResponse.model_validate(status_response.json())
                print(
                    f"Status check response: Code={status_response.status_code}, Data={status_data}"
                )

                if status_response.status_code == 200:
                    # Task completed successfully
                    result = status_data.result
                    if result:
                        print(f"Successfully received markdown result: {result}")
                        return True
                    print(f"No result found in response data: {status_data}")
                    return False
                elif status_response.status_code == 202:
                    # Task still processing
                    print("Task still processing, waiting 2 seconds...")
                    time.sleep(2)
                else:
                    error_msg = status_data.error
                    print(f"Error response received: {error_msg}")
                    return False
            except Exception as e:
                print(f"Error checking status: {str(e)}")
                return False

    except requests.exceptions.RequestException as e:
        print(f"Error during conversion: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response content: {e.response.text}")
    finally:
        # Ensure the file is closed
        files["file"][1].close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python test_pdf_api.py <path_to_pdf_file>")
        sys.exit(1)

    test_pdf_conversion(sys.argv[1], "http://localhost:8003")
