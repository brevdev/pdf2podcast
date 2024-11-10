import json

def get_transform(vars, context):
    """
    Transform function for promptfoo that extracts just the output field from evaluation results JSON.
    
    Args:
        vars (dict): Variables passed from promptfoo config
        context (dict): Additional context from promptfoo
        
    Returns:
        dict: Transformed variables including the extracted output
    """
    try:
        # Read the JSON file content - it will be in vars['text']
        data = json.loads(vars['text'])
        
        # Navigate through the JSON structure to find the output
        results = data['results']
        if isinstance(results, dict) and 'results' in results:
            for result in results['results']:
                if 'response' in result and 'output' in result['response']:
                    # Return the original vars dict with our new transformed text
                    return {
                        **vars,
                        'text': result['response']['output']
                    }
                    
        raise ValueError("Could not find output in the JSON structure")
        
    except Exception as e:
        print(f"Error transforming variables: {e}")
        return {
            **vars,
            'error': f'Failed to transform variables: {str(e)}'
        }