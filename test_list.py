import requests
import json
from datetime import datetime


def format_timestamp(timestamp_str):
    """Format the ISO timestamp into a more readable format"""
    dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    return dt.strftime("%B %d, %Y at %I:%M %p")


def list_saved_podcasts():
    try:
        print("\nAttempting to connect to API...")
        response = requests.get("http://localhost:8002/saved_podcasts")
        response.raise_for_status()

        data = response.json()
        podcasts = data.get("podcasts", [])

        if not podcasts:
            print("\nNo saved podcasts found in API response.")

        print("\nSaved Podcasts:")
        print("-" * 80)

        for podcast in podcasts:
            created_at = format_timestamp(podcast["created_at"])
            print(f"Job ID: {podcast['job_id']}")
            print(f"Filename: {podcast['filename']}")
            print(f"Created: {created_at}")
            print("Transcription Parameters:")
            print(json.dumps(podcast["transcription_params"], indent=2))
            print("-" * 80)

        print(f"\nTotal podcasts found: {len(podcasts)}")

    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to the API service. Is it running?")
    except requests.exceptions.HTTPError as e:
        print(f"Error: API request failed with status {e.response.status_code}")
        print(f"Details: {e.response.text}")
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    list_saved_podcasts()
