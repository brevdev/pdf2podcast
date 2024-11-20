import requests
import os
import json as json
import time
from datetime import datetime
from threading import Thread, Event
import websockets
import asyncio
from urllib.parse import urljoin
import argparse
from typing import List, Tuple

# Add global TEST_USER_ID
TEST_USER_ID = "test-userid"


class StatusMonitor:
    def __init__(self, base_url, job_id):
        self.base_url = base_url
        self.job_id = job_id
        self.ws_url = self._get_ws_url(base_url)
        self.stop_event = Event()
        self.services = {"pdf", "agent", "tts"}
        self.last_statuses = {service: None for service in self.services}
        self.tts_completed = Event()
        self.websocket = None
        self.reconnect_delay = 1.0
        self.max_reconnect_delay = 30.0
        self.ready_event = asyncio.Event()

    def _get_ws_url(self, base_url):
        """Convert HTTP URL to WebSocket URL"""
        if base_url.startswith("https://"):
            ws_base = "wss://" + base_url[8:]
        else:
            ws_base = "ws://" + base_url[7:]
        return urljoin(ws_base, f"/ws/status/{self.job_id}")

    def get_time(self):
        return datetime.now().strftime("%H:%M:%S")

    def start(self):
        """Start the WebSocket monitoring in a separate thread"""
        self.thread = Thread(target=self._run_async_loop)
        self.thread.start()

    def stop(self):
        """Stop the WebSocket monitoring"""
        self.stop_event.set()
        self.thread.join()

    def _run_async_loop(self):
        """Run the asyncio event loop in a separate thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._monitor_status())

    async def _monitor_status(self):
        while not self.stop_event.is_set():
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    self.websocket = websocket
                    self.reconnect_delay = 1.0
                    print(f"[{self.get_time()}] Connected to status WebSocket")

                    while not self.stop_event.is_set():
                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(), timeout=30
                            )

                            # Handle ready check message
                            try:
                                data = json.loads(message)
                                if data.get("type") == "ready_check":
                                    await websocket.send("ready")
                                    print(
                                        f"[{self.get_time()}] Sent ready acknowledgment"
                                    )
                                    continue
                            except json.JSONDecodeError:
                                pass

                            await self._handle_message(message)
                        except asyncio.TimeoutError:
                            try:
                                pong_waiter = await websocket.ping()
                                await pong_waiter
                            except Exception:
                                break

            except websockets.exceptions.ConnectionClosed:
                self.ready_event.clear()
                if not self.stop_event.is_set():
                    print(
                        f"[{self.get_time()}] WebSocket connection closed, reconnecting..."
                    )

            except Exception as e:
                self.ready_event.clear()
                if not self.stop_event.is_set():
                    print(f"[{self.get_time()}] WebSocket error: {e}, reconnecting...")

            if not self.stop_event.is_set():
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(
                    self.reconnect_delay * 1.5, self.max_reconnect_delay
                )

    async def _handle_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            service = data.get("service")
            status = data.get("status")
            msg = data.get("message", "")

            if service in self.services:
                current_status = f"{service}: {status} - {msg}"
                if current_status != self.last_statuses[service]:
                    print(f"[{self.get_time()}] {current_status}")
                    self.last_statuses[service] = current_status

                    if status == "failed":
                        print(f"[{self.get_time()}] Job failed in {service}: {msg}")
                        self.stop_event.set()

                    if service == "tts" and status == "completed":
                        self.tts_completed.set()
                        self.stop_event.set()

        except json.JSONDecodeError:
            print(f"[{self.get_time()}] Received invalid JSON: {message}")
        except Exception as e:
            print(f"[{self.get_time()}] Error processing message: {e}")


def get_output_with_retry(base_url: str, job_id: str, max_retries=5, retry_delay=1):
    """Retry getting output with exponential backoff"""
    for attempt in range(max_retries):
        try:
            response = requests.get(
                f"{base_url}/output/{job_id}", params={"userId": TEST_USER_ID}
            )
            if response.status_code == 200:
                return response.content
            elif response.status_code == 404:
                wait_time = retry_delay * (2**attempt)
                print(
                    f"[datetime.now().strftime('%H:%M:%S')] Output not ready yet, retrying in {wait_time:.1f}s..."
                )
                time.sleep(wait_time)
                continue
            else:
                response.raise_for_status()
        except requests.RequestException as e:
            print(f"[datetime.now().strftime('%H:%M:%S')] Error getting output: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(retry_delay * (2**attempt))

    raise TimeoutError("Failed to get output after maximum retries")


def test_saved_podcasts(base_url: str, job_id: str, max_retries=5, retry_delay=5):
    """Test the saved podcasts endpoints with retry logic"""
    print(
        f"\n[{datetime.now().strftime('%H:%M:%S')}] Testing saved podcasts endpoints..."
    )

    # Test 1: Get all saved podcasts with retry
    print("\nTesting list all podcasts endpoint...")
    for attempt in range(max_retries):
        response = requests.get(
            f"{base_url}/saved_podcasts", params={"userId": TEST_USER_ID}
        )
        assert (
            response.status_code == 200
        ), f"Failed to get saved podcasts: {response.text}"
        podcasts = response.json()["podcasts"]
        print(f"Found {len(podcasts)} saved podcasts")

        # Check if our job_id is in the list
        job_ids = [podcast["job_id"] for podcast in podcasts]
        if job_id in job_ids:
            print(f"Successfully found job_id {job_id} in saved podcasts list")
            break
        elif attempt < max_retries - 1:
            wait_time = retry_delay * (2**attempt)
            print(
                f"Job ID not found yet, retrying in {wait_time:.1f}s... (attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(wait_time)
            continue
        else:
            assert False, f"Recently created job_id {job_id} not found in saved podcasts after {max_retries} attempts"

    # Test 2: Get specific podcast metadata
    print("\nTesting individual podcast metadata endpoint...")
    response = requests.get(
        f"{base_url}/saved_podcast/{job_id}/metadata", params={"userId": TEST_USER_ID}
    )
    assert (
        response.status_code == 200
    ), f"Failed to get podcast metadata: {response.text}"
    metadata = response.json()
    print(f"Retrieved metadata for podcast: {metadata.get('filename', 'unknown')}")
    print(f"Metadata: {json.dumps(metadata, indent=2)}")

    # Test 3: Get specific podcast audio
    print("\nTesting individual podcast audio endpoint...")
    response = requests.get(
        f"{base_url}/saved_podcast/{job_id}/audio", params={"userId": TEST_USER_ID}
    )
    assert response.status_code == 200, f"Failed to get podcast audio: {response.text}"
    audio_data = response.content
    print(f"Successfully retrieved audio data, size: {len(audio_data)} bytes")


def test_api(
    base_url: str,
    pdf_files_with_types: List[Tuple[str, str]],
    monologue: bool = False,
    vdb: bool = False,
):
    voice_mapping = {
        "speaker-1": "iP95p4xoKVk53GoZ742B",
    }

    if not monologue:
        voice_mapping["speaker-2"] = "9BWtsMINqrJLrRacOk9x"

    process_url = f"{base_url}/process_pdf"

    # Update path resolution
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    samples_dir = os.path.join(project_root, "samples")

    sample_pdf_paths_with_types = []
    for pdf_file, file_type in pdf_files_with_types:
        if os.path.isabs(pdf_file):
            sample_pdf_paths_with_types.append((pdf_file, file_type))
        else:
            sample_pdf_paths_with_types.append(
                (os.path.join(samples_dir, pdf_file), file_type)
            )

    # Prepare the payload with updated schema and userId
    transcription_params = {
        "name": "ishan-test",
        "duration": 5,
        "speaker_1_name": "Bob",
        "voice_mapping": voice_mapping,
        "guide": None,
        "monologue": monologue,
        "userId": TEST_USER_ID,
        "vdb_task": vdb,
    }

    if not monologue:
        transcription_params["speaker_2_name"] = "Kate"

    # Step 1: Submit the PDF files and get job ID
    print(
        f"\n[{datetime.now().strftime('%H:%M:%S')}] Submitting PDFs for processing..."
    )
    print(f"Using voices: {voice_mapping}")

    # Prepare multipart form data
    form_data = []
    file_types = []

    # Add each file to the form data
    for path, file_type in sample_pdf_paths_with_types:
        with open(path, "rb") as pdf_file:
            content = pdf_file.read()
            form_data.append(
                ("files", (os.path.basename(path), content, "application/pdf"))
            )
            file_types.append(file_type)

    # Add the file types as separate form fields
    for file_type in file_types:
        form_data.append(("file_types", (None, file_type)))

    # Add transcription parameters
    form_data.append(("transcription_params", (None, json.dumps(transcription_params))))

    try:
        response = requests.post(process_url, files=form_data)

        assert (
            response.status_code == 202
        ), f"Expected status code 202, but got {response.status_code}. Response: {response.text}"
        job_data = response.json()
        assert "job_id" in job_data, "Response missing job_id"
        job_id = job_data["job_id"]
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Job ID received: {job_id}")

    except Exception as e:
        print(f"Error during PDF submission: {e}")
        raise

    # Step 2: Start monitoring status via WebSocket
    monitor = StatusMonitor(base_url, job_id)
    monitor.start()

    try:
        # Wait for TTS completion or timeout
        max_wait = 40 * 60
        if not monitor.tts_completed.wait(timeout=max_wait):
            raise TimeoutError(f"Test timed out after {max_wait} seconds")

        # If we get here, TTS completed successfully
        print(
            f"\n[{datetime.now().strftime('%H:%M:%S')}] TTS processing completed, retrieving audio file..."
        )

        # Get the final output with retry logic
        audio_content = get_output_with_retry(base_url, job_id)

        # Save the audio file
        output_path = os.path.join(current_dir, "output.mp3")
        with open(output_path, "wb") as f:
            f.write(audio_content)
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] Audio file saved as '{output_path}'"
        )

        # Test saved podcasts endpoints with the newly created job_id
        test_saved_podcasts(base_url, job_id)

        # Test RAG endpoint if vdb flag is enabled
        if vdb:
            print("\nTesting RAG endpoint...")
            test_query = "What is the main topic of this document?"
            rag_response = requests.post(
                f"{base_url}/query_vector_db",
                json={"query": test_query, "k": 3, "job_id": job_id},
            )
            assert (
                rag_response.status_code == 200
            ), f"RAG endpoint failed: {rag_response.text}"
            rag_results = rag_response.json()
            print(f"RAG Query: '{test_query}'")
            print(f"RAG Results: {json.dumps(rag_results, indent=2)}")

    finally:
        monitor.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process PDF files for audio conversion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        Examples:
        # Process single file (defaults to context)
        python test.py file1.pdf

        # Process single file as target
        python test.py file1.pdf target

        # Process multiple files with explicit types
        python test.py file1.pdf target file2.pdf context file3.pdf context

        # Process multiple files (defaulting to context)
        python test.py file1.pdf target file2.pdf file3.pdf
        """,
    )

    parser.add_argument(
        "files",
        nargs="+",
        help="PDF files and their types (optional). Format: <file> [type] <file> [type] ...",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("API_SERVICE_URL", "http://localhost:8002"),
        help="API service URL (default: from API_SERVICE_URL env var or http://localhost:8002)",
    )
    parser.add_argument(
        "--monologue",
        action="store_true",
        help="Generate a monologue instead of a dialogue",
    )
    parser.add_argument(
        "--vdb",
        action="store_true",
        help="Enable Vector Database processing",
    )

    args = parser.parse_args()

    # Process the files argument to pair files with their types
    pdf_files_with_types = []
    i = 0
    while i < len(args.files):
        pdf_file = args.files[i]
        # Check if next argument is a type specification
        if i + 1 < len(args.files) and args.files[i + 1] in ["target", "context"]:
            file_type = args.files[i + 1]
            i += 2
        else:
            file_type = "context"  # default type
            i += 1
        pdf_files_with_types.append((pdf_file, file_type))

    print(f"API URL: {args.api_url}")
    print(f"Processing PDF files: {pdf_files_with_types}")
    print(f"Monologue mode: {args.monologue}")
    print(f"VDB mode: {args.vdb}")
    print(f"Using test user ID: {TEST_USER_ID}")

    test_api(args.api_url, pdf_files_with_types, args.monologue, args.vdb)
