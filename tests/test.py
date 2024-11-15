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
from typing import List


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
        """Monitor status updates via WebSocket with automatic reconnection"""
        while not self.stop_event.is_set():
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    self.websocket = websocket
                    self.reconnect_delay = 1.0  # Reset delay on successful connection
                    print(f"[{self.get_time()}] Connected to status WebSocket")

                    while not self.stop_event.is_set():
                        try:
                            message = await asyncio.wait_for(
                                websocket.recv(), timeout=30
                            )
                            await self._handle_message(message)
                        except asyncio.TimeoutError:
                            # Send ping to keep connection alive
                            try:
                                pong_waiter = await websocket.ping()
                                await pong_waiter
                            except:  # noqa
                                break

            except websockets.exceptions.ConnectionClosed:
                if not self.stop_event.is_set():
                    print(
                        f"[{self.get_time()}] WebSocket connection closed, reconnecting..."
                    )

            except Exception as e:
                if not self.stop_event.is_set():
                    print(f"[{self.get_time()}] WebSocket error: {e}, reconnecting...")

            if not self.stop_event.is_set():
                # Exponential backoff for reconnection
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
            response = requests.get(f"{base_url}/output/{job_id}")
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


def test_saved_podcasts(base_url: str, job_id: str):
    """Test the saved podcasts endpoints"""
    print(
        f"\n[{datetime.now().strftime('%H:%M:%S')}] Testing saved podcasts endpoints..."
    )

    # Test 1: Get all saved podcasts
    print("\nTesting list all podcasts endpoint...")
    response = requests.get(f"{base_url}/saved_podcasts")
    assert response.status_code == 200, f"Failed to get saved podcasts: {response.text}"
    podcasts = response.json()["podcasts"]
    print(f"Found {len(podcasts)} saved podcasts")

    # Verify our new job_id is in the list
    job_ids = [podcast["job_id"] for podcast in podcasts]
    assert (
        job_id in job_ids
    ), f"Recently created job_id {job_id} not found in saved podcasts"
    print(f"Successfully found job_id {job_id} in saved podcasts list")

    # Test 2: Get specific podcast metadata
    print("\nTesting individual podcast metadata endpoint...")
    response = requests.get(f"{base_url}/saved_podcast/{job_id}/metadata")
    assert (
        response.status_code == 200
    ), f"Failed to get podcast metadata: {response.text}"
    metadata = response.json()
    print(f"Retrieved metadata for podcast: {metadata.get('filename', 'unknown')}")
    print(f"Metadata: {json.dumps(metadata, indent=2)}")

    # Test 3: Get specific podcast audio
    print("\nTesting individual podcast audio endpoint...")
    response = requests.get(f"{base_url}/saved_podcast/{job_id}/audio")
    assert response.status_code == 200, f"Failed to get podcast audio: {response.text}"
    audio_data = response.content
    print(f"Successfully retrieved audio data, size: {len(audio_data)} bytes")


def test_api(
    base_url: str, pdf_files: List[str]
):  # Modified to accept pdf_files parameter
    voice_mapping = {
        "speaker-1": "iP95p4xoKVk53GoZ742B",
        "speaker-2": "9BWtsMINqrJLrRacOk9x",
    }

    process_url = f"{base_url}/process_pdf"

    # Update path resolution
    current_dir = os.path.dirname(
        os.path.abspath(__file__)
    )  # This gets /tests directory
    project_root = os.path.dirname(current_dir)  # Go up one level to project root
    samples_dir = os.path.join(project_root, "samples")

    # Rest of the path handling remains the same
    sample_pdf_paths = []
    for pdf_file in pdf_files:
        if os.path.isabs(pdf_file):
            sample_pdf_paths.append(pdf_file)
        else:
            sample_pdf_paths.append(os.path.join(samples_dir, pdf_file))

    # Prepare the payload with updated schema
    transcription_params = {
        "name": "ishan-test",
        "duration": 5,
        "speaker_1_name": "Bob",
        "speaker_2_name": "Kate",
        "voice_mapping": voice_mapping,
        "guide": None,  # Optional guidance for transcription focus
    }

    # Step 1: Submit the PDF files and get job ID
    print(
        f"\n[{datetime.now().strftime('%H:%M:%S')}] Submitting PDFs for processing..."
    )
    print(f"Using voices: {voice_mapping}")

    pdf_files = [open(path, "rb") for path in sample_pdf_paths]
    try:
        files = [
            ("files", (os.path.basename(path), pdf_file, "application/pdf"))
            for path, pdf_file in zip(sample_pdf_paths, pdf_files)
        ]

        response = requests.post(
            process_url,
            files=files,
            data={"transcription_params": json.dumps(transcription_params)},
        )

        assert (
            response.status_code == 202
        ), f"Expected status code 202, but got {response.status_code}"
        job_data = response.json()
        assert "job_id" in job_data, "Response missing job_id"
        job_id = job_data["job_id"]
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Job ID received: {job_id}")

    finally:
        for f in pdf_files:
            f.close()

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

    finally:
        monitor.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process PDF files for audio conversion"
    )
    parser.add_argument("pdf_files", nargs="+", help="PDF files to process")
    parser.add_argument(
        "--api-url",
        default=os.getenv("API_SERVICE_URL", "http://localhost:8002"),
        help="API service URL (default: from API_SERVICE_URL env var or http://localhost:8002)",
    )

    args = parser.parse_args()
    print(f"API URL: {args.api_url}")
    print(f"Processing PDF files: {args.pdf_files}")

    test_api(args.api_url, args.pdf_files)
