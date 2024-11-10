import json
import os

def get_transform(vars, context):
    """
    Transform function for promptfoo that extracts the output field from evaluation results JSON
    while preserving other variables.
    
    Args:
        vars (dict): Variables passed from promptfoo config
        context (dict): Additional context from promptfoo
        
    Returns:
        dict: Transformed variables including the extracted output
    """
    try:
        # Remove 'file://' prefix if present and get absolute path
        file_path = vars['text'].replace('file://', '')
        
        # Read and parse the JSON file directly without joining paths
        with open(file_path, 'r') as f:
            data = json.load(f)
            
        # Extract the output and return all vars with transformed text
        return {
            **vars,
            'text': data['results']['results'][0]['response']['output']
        }
        
    except Exception as e:
        print(f"Error transforming variables: {e}")
        return {
            **vars,
            'error': f'Failed to transform variables: {str(e)}'
        }