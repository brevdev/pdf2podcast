import os
import json
import requests
import time

TEST_USER_ID = "test-userid"
API_SERVICE_URL=os.getenv("API_SERVICE_URL", "http://localhost:8002")

transcription_params = {
    "name": "transcript-test",
    "duration": 1,
    "speaker_1_name": "Bob",
    "guide": None,
    "userId": TEST_USER_ID,
    "vdb_task": False,
}

target_files = [
    'jpm-context.pdf',
    'hsbc-context.pdf'
]

context_files = [
    'gs-context.pdf',
    'citi-context.pdf'
]

# Prepare multipart form data
form_data = []

# Update path resolution
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
samples_dir = os.path.join(project_root, "samples")

# Process target files
for pdf_file in target_files:
    if not os.path.isabs(pdf_file):
        pdf_file = os.path.join(samples_dir, pdf_file)

    with open(pdf_file, "rb") as f:
        content = f.read()
        form_data.append(
            (
                "target_files",
                (os.path.basename(pdf_file), content, "application/pdf"),
            )
        )

# Process context files
for pdf_file in context_files:
    if not os.path.isabs(pdf_file):
        pdf_file = os.path.join(samples_dir, pdf_file)

    with open(pdf_file, "rb") as f:
        content = f.read()
        form_data.append(
            (
                "context_files",
                (os.path.basename(pdf_file), content, "application/pdf"),
            )
        )

# Add transcription parameters
form_data.append(("transcription_params", (None, json.dumps(transcription_params))))

###
response = requests.post(f'{API_SERVICE_URL}/run/pdf_to_transcript', files=form_data)
print(response.json())

job_id = response.json()['job_id']

for i in range(10):
    time.sleep(10)
    response = requests.get(
        f'{API_SERVICE_URL}/results/transcript/{job_id}',
        params={"userId": TEST_USER_ID}
    )
    print(response.text)

###