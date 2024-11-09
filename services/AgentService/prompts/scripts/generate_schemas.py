# tests/generate_schemas.py
import json
import sys
from pathlib import Path

# Get the absolute path to the root directory
root_dir = Path(__file__).resolve().parents[4]
sys.path.append(str(root_dir))

from shared.shared.shared_types import Conversation, PodcastOutline

def generate_schemas(output_dir: Path):
    """Generate JSON schemas from Pydantic models."""
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate and save PodcastOutline schema
    podcast_schema = PodcastOutline.model_json_schema()
    with open(output_dir / "podcast_outline.json", "w") as f:
        json.dump(podcast_schema, f, indent=2)
    print("Generated podcast_outline.json")
    
    # Generate and save Conversation schema
    conversation_schema = Conversation.model_json_schema()
    with open(output_dir / "conversation.json", "w") as f:
        json.dump(conversation_schema, f, indent=2)
    print("Generated conversation.json")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        output_dir = Path(sys.argv[1])
    else:
        output_dir = Path(__file__).parent / "schemas"
    
    generate_schemas(output_dir)