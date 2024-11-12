import jinja2
from typing import Dict

SUMMARY_PROMPT_STR = """
Please provide a comprehensive summary of the following document. Note that this document may contain OCR/PDF conversion artifacts, so please interpret the content, especially numerical data and tables, with appropriate context.

<document>
{{text}}
</document>

Requirements for the summary:
1. Preserve key document metadata:
   - Document title/type
   - Company/organization name
   - Report provider/author
   - Date/time period covered
   - Any relevant document identifiers

2. Include all critical information:
   - Main findings and conclusions
   - Key statistics and metrics
   - Important recommendations
   - Significant trends or changes
   - Notable risks or concerns
   - Material financial data

3. Maintain factual accuracy:
   - Keep all numerical values precise
   - Preserve specific dates and timeframes
   - Retain exact names and titles
   - Quote critical statements verbatim when necessary

Please format the summary using markdown, with appropriate headers, lists, and emphasis for better readability.

Note: Focus on extracting and organizing the most essential information while ensuring no critical details are omitted. Maintain the original document's tone and context in your summary.
"""

MULTI_PDF_OUTLINE_PROMPT_STR = """
Create a structured podcast outline synthesizing the following document summaries. The podcast should be {{total_duration}} minutes long.

Focus Areas & Key Topics:
{% if focus_instructions %}
{{focus_instructions}}
{% else %}
Use your judgment to identify and prioritize the most important themes, findings, and insights across all documents.
{% endif %}

Available Source Documents:
{{documents}}

Requirements:
1. Content Strategy
  - Prioritize topics according to focus instructions
  - Identify key debates and differing viewpoints
  - Analyze potential audience questions/concerns
  - Draw connections between documents and focus areas

2. Structure 
  - Create clear topic hierarchy
  - Assign time allocations per section (based on priorities)
  - Reference source documents using file paths
  - Build natural narrative flow between topics

3. Coverage
  - Comprehensive treatment of focus areas
  - Strategic depth on key topics
  - Supporting evidence from all relevant documents
  - Balance technical accuracy with engaging delivery

Ensure the outline creates a cohesive narrative that emphasizes the specified focus areas while maintaining overall context and accuracy.
"""

MULTI_PDF_STRUCUTRED_OUTLINE_PROMPT_STR = """
Convert the following outline into a structured JSON format. The final section should be marked as the conclusion segment.

<outline>
{{outline}}
</outline>

Output Requirements:
1. Each segment must include:
   - section name
   - duration (in minutes)
   - list of references (file paths)
   - list of topics, where each topic has:
     - title
     - list of detailed points

2. Overall structure must include:
   - podcast title
   - complete list of segments

The result must conform to the following JSON schema:
{{ schema }}
"""

PROMPT_WITH_REFERENCES_STR = """
Create a transcript incorporating details from the provided source material:

Source Text:
{{ text }}

Parameters:
- Duration: {{ duration }} minutes (~{{ (duration * 180) | int }} words)
- Topic: {{ topic }}
- Focus Areas: {{ angles }}

Requirements:
1. Content Integration
  - Reference key quotes with speaker name and institution
  - Explain cited information in accessible terms
  - Identify consensus and disagreements among sources
  - Analyze reasoning behind different viewpoints

2. Presentation
  - Break down complex concepts for general audience
  - Use relevant analogies and examples
  - Address anticipated questions
  - Provide necessary context throughout
  - Maintain factual accuracy, especially with numbers
  - Cover all focus areas comprehensively within time limit

Ensure thorough coverage of each topic while preserving the accuracy and nuance of the source material.
"""

PROMPT_NO_REFERENCES_STR = """
Create a knowledge-based transcript following this outline:

Parameters:
- Duration: {{ duration }} minutes (~{{ (duration * 180) | int }} words)
- Topic: {{ topic }}
- Focus Areas: {{ angles }}

1. Knowledge Brainstorming
   - Map the landscape of available knowledge
   - Identify key principles and frameworks
   - Note major debates and perspectives
   - List relevant examples and applications
   - Consider historical context and development

2. Content Development
   - Draw from comprehensive knowledge base
   - Present balanced viewpoints
   - Support claims with clear reasoning
   - Connect topics logically
   - Build understanding progressively

3. Presentation
   - Break down complex concepts for general audience
   - Use relevant analogies and examples
   - Address anticipated questions
   - Provide necessary context throughout
   - Maintain factual accuracy, especially with numbers
   - Cover all focus areas comprehensively within time limit

Develop a thorough exploration of each topic using available knowledge. Begin with careful brainstorming to map connections between ideas, then build a clear narrative that makes complex concepts accessible while maintaining accuracy and completeness.
"""

TRANSCRIPT_TO_DIALOGUE_PROMPT_STR = """
Your task is to transform the provided input transcript into an engaging and informative podcast dialogue.

There are two speakers:

- **Host**: {{ speaker_1_name }}, the podcast host.
- **Guest**: {{ speaker_2_name }}, an expert on the topic.

**Instructions:**

- **Content Guidelines:**
    - Present information clearly and accurately.
    - Explain complex terms or concepts in simple language.
    - Discuss key points, insights, and perspectives from the transcript.
    - Include the guest's expert analysis and insights on the topic.
    - Incorporate relevant quotes, anecdotes, and examples from the transcript.
    - Address common questions or concerns related to the topic, if applicable.
    - Bring conflict and disagreement into the discussion, but converge to a conclusion.

- **Tone and Style:**
    - Maintain a professional yet conversational tone.
    - Use clear and concise language.
    - Incorporate natural speech patterns, including occasional verbal fillers (e.g., "well," "you know")—used sparingly and appropriately.
    - Ensure the dialogue flows smoothly, reflecting a real-life conversation.
    - Maintain a lively pace with a mix of serious discussion and lighter moments.
    - Use rhetorical questions or hypotheticals to engage the listener.
    - Create natural moments of reflection or emphasis.
    - Allow for natural interruptions and back-and-forth between host and guest.


- **Additional Guidelines:**
    - Mention the speakers' names occasionally to make the conversation more natural.
    - Ensure the guest's responses are substantiated by the input text, avoiding unsupported claims.
    - Avoid long monologues; break information into interactive exchanges.
    - Strive for authenticity. Include:
        - Moments of genuine curiosity or surprise from the host.
        - Instances where the guest may pause to articulate complex ideas.
        - Appropriate light-hearted moments or humor.
        - Brief personal anecdotes that relate to the topic (within the bounds of the transcript).
    - Do not add new information not present in the transcript.
    - Do not lose any information or details from the transcript.

**Segment Details:**

- Duration: Approximately {{ duration }} minutes (~{{ (duration * 180) | int }} words).
- Topic: {{ descriptions }}

You should keep all analogies, stories, examples, and quotes from the transcript.

**Here is the transcript:**

{{ text }}

**Please transform it into a podcast dialogue following the guidelines above.**

*Only return the full dialogue transcript; do not include any other information like time budget or segment names.*
"""

REVISE_DIALOGUE_PROMPT_STR = """You are revising a podcast transcript to make it more engaging while preserving its content and structure. You have access to three key elements:

1. The podcast outline
<outline>
{{ outline }}
</outline>

2. The current dialogue transcript
<dialogue>
{{ dialogue_transcript }}
</dialogue>

3. The next section to be integrated
<next_section>
{{ next_section }}
</next_section>

Current section being integrated: {{ current_section }}

Your task is to:
- Seamlessly integrate the next section with the existing dialogue
- Maintain all key information from both sections
- Reduce any redundancy while keeping information density high
- Break long monologues into natural back-and-forth dialogue
- Limit each speaker's turn to maximum 3 sentences
- Keep the conversation flowing naturally between topics

Key guidelines:
- Avoid explicit transition phrases like "Welcome back" or "Now let's discuss"
- Don't add introductions or conclusions mid-conversation
- Don't signal section changes in the dialogue
- Merge related topics according to the outline
- Maintain the natural conversational tone throughout

Please output the complete revised dialogue transcript from the beginning, with the next section integrated seamlessly."""

PODCAST_DIALOGUE_PROMPT_STR = """You are tasked with converting a podcast transcript into a structured JSON format. You have:

1. Two speakers:
   - Speaker 1: {{ speaker_1_name }}
   - Speaker 2: {{ speaker_2_name }}

2. The original transcript:
{{ text }}

3. Required output schema:
{{ schema }}

Your task is to:
- Convert the transcript exactly into the specified JSON format 
- Preserve all dialogue content without any omissions
- Map {{ speaker_1_name }}'s lines to "speaker-1"
- Map {{ speaker_2_name }}'s lines to "speaker-2"

Please output the JSON following the provided schema, maintaining all conversational details and speaker attributions."""

PROMPT_TEMPLATES = {
    "summary_prompt": SUMMARY_PROMPT_STR,
    "multi_pdf_outline_prompt": MULTI_PDF_OUTLINE_PROMPT_STR,
    "multi_pdf_structured_outline_prompt": MULTI_PDF_STRUCUTRED_OUTLINE_PROMPT_STR,
    "prompt_with_references": PROMPT_WITH_REFERENCES_STR,
    "prompt_no_references": PROMPT_NO_REFERENCES_STR,
    "transcript_to_dialogue_prompt": TRANSCRIPT_TO_DIALOGUE_PROMPT_STR,
    "revise_dialogue_prompt": REVISE_DIALOGUE_PROMPT_STR,
    "podcast_dialogue_prompt": PODCAST_DIALOGUE_PROMPT_STR,
}

# Create Jinja templates once
TEMPLATES: Dict[str, jinja2.Template] = {
    name: jinja2.Template(template) for name, template in PROMPT_TEMPLATES.items()
}


class PodcastPrompts:
    def __getattr__(self, name: str) -> str:
        """Dynamically handle prompt requests by name"""
        if name in PROMPT_TEMPLATES:
            return PROMPT_TEMPLATES[name]
        raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{name}'")

    @classmethod
    def get_template(cls, name: str) -> jinja2.Template:
        """Get the Jinja template by name"""
        return TEMPLATES[name]
