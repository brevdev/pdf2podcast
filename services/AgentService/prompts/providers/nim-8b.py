# Note we use 8b in json mode 

import requests
import json
from typing import Dict, Any, Optional

def call_api(prompt: str, options: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Custom provider for chat completions using your existing infrastructure.
    
    Args:
        prompt: The prompt text or JSON string of messages
        options: Configuration options from the YAML file
        context: Test context including variables used
    
    Returns:
        Dict containing output or error
    """
    try:
        # Get configuration from options
        config = options.get('config', {})
        api_base = config.get('api_base', "https://nim-pc8kmx5ae.brevlab.com")
        api_key = config.get('api_key')
        model = config.get('model', "meta/llama-3.1-8b-instruct")
        temperature = config.get('temperature', 0.7)
        max_tokens = config.get('max_tokens', 1000)
        json_schema = config.get('json_schema', "")

        # Setup headers
        headers = {
            "Content-Type": "application/json"
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Handle different prompt formats
        try:
            # Check if prompt is a JSON string containing messages
            messages = json.loads(prompt)
            if isinstance(messages, list):
                chat_messages = messages
            else:
                chat_messages = [{"role": "user", "content": prompt}]
        except json.JSONDecodeError:
            # If not JSON, treat as regular prompt
            chat_messages = [{"role": "user", "content": prompt}]

        # Prepare payload
        payload = {
            "model": model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False  
        }

        if json_schema != "":
            # Remove 'file://' prefix if present
            print(json_schema)
            json_schema_path = "/Users/idhanani/Desktop/notebooklm/backend/services/AgentService/prompts/tests/schemas/podcast_outline.json"
            with open(json_schema_path, 'r') as file:
                json_schema_content = file.read()
                payload["nvext"] = {
                    "guided_json": json_schema_content
                }

        # Make request
        response = requests.post(
            f"{api_base}/v1/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        result = response.json()

        if "choices" in result and len(result["choices"]) > 0:
            output = result["choices"][0]["message"]["content"]
            return {
                "output": output,
                "tokenUsage": result.get("usage", {
                    "total": 0,
                    "prompt": 0,
                    "completion": 0
                })
            }
        else:
            return {
                "error": "No choices in response"
            }

    except requests.exceptions.RequestException as e:
        return {
            "error": f"Request error: {str(e)}\nResponse: {response.text if 'response' in locals() else 'No response'}"
        }
    except Exception as e:
        return {
            "error": f"Unexpected error: {str(e)}"
        }