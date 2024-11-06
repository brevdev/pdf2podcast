FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create config directory
RUN mkdir -p /app/config

# Install Python dependencies
RUN pip install fastapi uvicorn pydantic python-dotenv jinja2 redis minio

# Install flexagent
COPY services/AgentService/flexagent /app/flexagent
WORKDIR /app/flexagent/python
RUN pip install --use-pep517 -e .
WORKDIR /app

COPY shared /shared
RUN pip install /shared

# Copy service files
COPY services/AgentService/main.py ./
COPY services/AgentService/prompts.py ./

EXPOSE 8964

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8964"]