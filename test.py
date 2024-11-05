import requests
import os
import json
import time
from datetime import datetime
from threading import Thread, Event
import websockets
import asyncio
from urllib.parse import urljoin


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


def test_api(base_url: str):
    # Define default voice mapping
    voice_mapping = {
        "speaker-1": "iP95p4xoKVk53GoZ742B",  # Example voice ID for speaker 1
        "speaker-2": "9BWtsMINqrJLrRacOk9x",  # Example voice ID for speaker 2
    }

    # API endpoint
    process_url = f"{base_url}/process_pdf"

    # Path to a sample PDF file for testing
    current_dir = os.path.dirname(os.path.abspath(__file__))
    samples_dir = os.path.join(current_dir, "samples")

    # Ensure samples directory exists
    if not os.path.exists(samples_dir):
        raise FileNotFoundError(f"Samples directory not found at {samples_dir}")

    sample_pdf_path = os.path.join(samples_dir, "PNP_Proof.pdf")

    # Ensure the sample PDF file exists
    assert os.path.exists(
        sample_pdf_path
    ), f"Sample PDF file not found at {sample_pdf_path}"

    # Prepare the payload
    transcription_params = {
        "duration": 5,
        "speaker_1_name": "Blackwell",
        "speaker_2_name": "Hopper",
        "model": "meta/llama-3.1-405b-instruct",
        "voice_mapping": voice_mapping,  # Add voice mapping
    }

    # Step 1: Submit the PDF file and get job ID
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Submitting PDF for processing...")
    print(f"Using voices: {voice_mapping}")

    with open(sample_pdf_path, "rb") as pdf_file:
        files = {"file": ("sample.pdf", pdf_file, "application/pdf")}
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

    # Step 2: Start monitoring status via WebSocket
    monitor = StatusMonitor(base_url, job_id)
    monitor.start()

    try:
        # Wait for TTS completion or timeout
        max_wait = 40 * 60  # 20 minutes in seconds
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

    finally:
        monitor.stop()


if __name__ == "__main__":
    base_url = os.getenv("API_SERVICE_URL", "http://localhost:8002")
    print(f"{base_url=}")
    test_api(base_url)
