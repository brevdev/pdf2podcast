import jinja2
from typing import Dict

MONOLOGUE_SUMMARY_PROMPT_STR = """
You are presenting NVIDIA earning reports and analyses at a company meeting. Please provide a {{ level_of_detail }}-detail summary of the following financial document.

<document>
{{text}}
</document>

Requirements for the analysis:
1. Essential Financial Information:
{% if level_of_detail == "light" %}
  - High-level business trends and trajectory
  - Strategic highlights and key shifts
  - Critical performance indicators
{% elif level_of_detail == "medium" %}
  - Core financial metrics and trends
  - Performance patterns and deviations
  - Strategic initiatives and progress
  - Market position indicators
{% else %}
  - Comprehensive financial analysis
  - Detailed performance breakdowns
  - Multi-dimensional trend analysis
  - Strategic developments and implications
  - Market dynamics and competitive positioning
{% endif %}

2. Document Context:
{% if level_of_detail == "light" %}
  - Core context and relevance
  - Primary stakeholder implications
  - Essential timeline elements
{% elif level_of_detail == "medium" %}
  - Document purpose and scope
  - Key stakeholder considerations
  - Contextual background
  - Relevant timelines and milestones
{% else %}
  - In-depth contextual analysis
  - Stakeholder impact assessment
  - Historical context and precedents
  - Forward-looking implications
  - Related strategic considerations
{% endif %}

3. Data Accuracy:
{% if level_of_detail == "light" %}
  - Focus on pivotal metrics
  - Key milestone dates
  - Essential financial terminology
{% elif level_of_detail == "medium" %}
  - Significant numerical data
  - Important timeline elements
  - Relevant financial terms
  - Key risk considerations
{% else %}
  - Comprehensive data validation
  - Detailed timeline tracking
  - Technical terminology precision
  - Risk factor analysis
  - Source verification
{% endif %}

{% if level_of_detail == "light" %}
Focus on essential insights and core messages for quick strategic understanding.
{% elif level_of_detail == "medium" %}
Balance depth and accessibility while maintaining key financial context.
{% else %}
Provide thorough analysis while ensuring clarity in complex financial narratives.
{% endif %}
"""

MONOLOGUE_OUTLINE_PROMPT_STR = """
Create a structured outline based on the following focus areas and document summaries.

Focus Instructions:
{{focus}}

Available Source Documents:
{% for doc in documents %}
<document>
<is_important>true</is_important>
<filename>{{doc.filename}}</filename>
<summary>{{doc.summary}}</summary>
</document>
{% endfor %}

Requirements:
1. Structure
- Create distinct segments based on the focus instructions
- Each segment should include:
  * A clear title
  * Key topics to cover
  * List of documents filenames, from the source documents, to use as reference.

2. Content Organization
{% if level_of_detail == "light" %}
   - Keep segments brief and focused
   - Emphasize critical insights
   - Target 2-3 key topics per segment
{% elif level_of_detail == "medium" %}
   - Balance detail and brevity
   - Include supporting context
   - Target 3-4 key topics per segment
{% else %}
   - Provide comprehensive coverage
   - Include detailed analysis
   - Target 4-5 key topics per segment
{% endif %}

The outline should follow the structure and flow specified in the focus instructions while incorporating relevant information from all documents.
"""

OUTLINE_JSON_FORMATTER_PROMPT_STR = """
Convert this outline into a structured JSON format following the provided schema.

Outline:
{{outline}}

Schema:
{{schema}}

Requirements:
Structure
- Follow the provided schema exactly
- Preserve all segment information:
  * Titles
  * Key points
  * Document references
  * Target durations

Output only the formatted JSON following the provided schema: {{ schema }}"""

SEGMENT_TRANSCRIPT_PROMPT_STR = """
Create a spoken transcript for this outline segment using the referenced documents.

Segment Information:
{{segment}}

Referenced Documents:
{% for doc in referenced_docs %}
<document>
<is_important>true</is_important>
<filename>{{doc.filename}}</filename>
<summary>{{doc.summary}}</summary>
</document>
{% endfor %}

Parameters:
- Level of detail: {{ level_of_detail }}
- Speaker: {{ speaker_1_name }}

Requirements:
1. Content Structure
{% if level_of_detail == "light" %}
   - Direct and concise delivery
   - Essential points only
   - Clear transitions
{% elif level_of_detail == "medium" %}
   - Balanced detail and flow
   - Key supporting evidence
   - Natural transitions
{% else %}
   - Rich detail and context
   - Comprehensive evidence
   - Sophisticated transitions
{% endif %}

2. Speaking Style
- Natural, conversational tone
- Clear pronunciation of financial terms
- Appropriate pacing for target length
- Smooth transitions from previous segments

You absolutely must, without exception:
- Convert all numbers and symbols to spoken form:
  * Numbers should be spelled out (e.g., "one billion" instead of "1B")
  * Currency should be expressed as "[amount] [unit of currency]" (e.g., "fifty million dollars" instead of "$50M")
  * Mathematical symbols should be spoken (e.g., "increased by" instead of "+")
  * Percentages should be spoken as "percent" (e.g., "twenty five percent" instead of "25%")
- Convert all financial acronyms (e.g., GAAP, EBITDA) to their spelled out, spoken form (e.g., "GAP" instead of "GAAP").

Create a transcript segment that flows naturally with the rest of the presentation while effectively communicating the financial information."""

TRANSCRIPT_MERGER_PROMPT_STR = """
Merge these segment transcripts into a cohesive presentation while maintaining natural flow and transitions.

Segments:
{{segments}}

Requirements:
1. Structure
{% if level_of_detail == "light" %}
   - Quick, impactful transitions
   - Maintain momentum
   - Clear progression
{% elif level_of_detail == "medium" %}
   - Smooth, natural transitions
   - Balanced pacing
   - Logical flow
{% else %}
   - Sophisticated transitions
   - Dynamic pacing
   - Complex narrative structure
{% endif %}

2. Content Integration
- Ensure smooth flow between segments
- Maintain consistent voice and tone
- Add transitional phrases where needed
- Preserve all key financial information

You absolutely must, without exception:
- Convert all numbers and symbols to spoken form:
  * Numbers should be spelled out (e.g., "one billion" instead of "1B")
  * Currency should be expressed as "[amount] [unit of currency]" (e.g., "fifty million dollars" instead of "$50M")
  * Mathematical symbols should be spoken (e.g., "increased by" instead of "+")
  * Percentages should be spoken as "percent" (e.g., "twenty five percent" instead of "25%")
- Convert all financial acronyms (e.g., GAAP, EBITDA) to their spelled out, spoken form (e.g., "GAP" instead of "GAAP").

Create a unified transcript that flows naturally while maintaining the integrity of each segment."""

TRANSCRIPT_LENGTH_ADJUSTMENT_PROMPT_STR = """
Adjust this transcript to match the target length while preserving key information:

{{ text }}

Target length for {{ level_of_detail }} detail level:
{% if level_of_detail == "light" %}
Ninety seconds - focus on headlines and critical updates
{% elif level_of_detail == "medium" %}
Two and a half to three minutes - balance key details and context
{% else %}
Five minutes - maintain rich detail while ensuring efficiency
{% endif %}

Editing Requirements:
1. Content Priorities
{% if level_of_detail == "light" %}
- Essential insights only
- Headline metrics
- Critical context
{% elif level_of_detail == "medium" %}
- Key developments
- Primary evidence
- Important context
{% else %}
- Detailed analysis
- Rich evidence
- Market context
{% endif %}

You absolutely must, without exception:
- Convert all numbers and symbols to spoken form:
  * Numbers should be spelled out (e.g., "one billion" instead of "1B")
  * Currency should be expressed as "[amount] [unit of currency]" (e.g., "fifty million dollars" instead of "$50M")
  * Mathematical symbols should be spoken (e.g., "increased by" instead of "+")
  * Percentages should be spoken as "percent" (e.g., "twenty five percent" instead of "25%")
- Convert all financial acronyms (e.g., GAAP, EBITDA) to their spelled out, spoken form (e.g., "GAP" instead of "GAAP").

Return only the edited transcript as it would be spoken."""

TRANSCRIPT_FORMATTING_PROMPT_STR = """Convert this transcript into the specified JSON format:

Speaker information:
- Speaker: {{ speaker_1_name }} (mapped to "speaker-1")

Transcript:
{{ text }}

Output schema:
{{ schema }}

Requirements:
- Preserve all content exactly
- Map all content to "speaker-1"
- Maintain all formatting standards

You absolutely must, without exception:
- Convert all numbers and symbols to spoken form:
  * Numbers should be spelled out (e.g., "one billion" instead of "1B")
  * Currency should be expressed as "[amount] [unit of currency]" (e.g., "fifty million dollars" instead of "$50M")
  * Mathematical symbols should be spoken (e.g., "increased by" instead of "+")
  * Percentages should be spoken as "percent" (e.g., "twenty five percent" instead of "25%")
- Convert all financial acronyms (e.g., GAAP, EBITDA) to their spelled out, spoken form (e.g., "GAP" instead of "GAAP").

Output only the formatted JSON."""

PROMPT_TEMPLATES = {
    "monologue_summary_prompt": MONOLOGUE_SUMMARY_PROMPT_STR,
    "monologue_outline_prompt": MONOLOGUE_OUTLINE_PROMPT_STR,
    "outline_json_formatter": OUTLINE_JSON_FORMATTER_PROMPT_STR,
    "segment_transcript_prompt": SEGMENT_TRANSCRIPT_PROMPT_STR,
    "transcript_merger_prompt": TRANSCRIPT_MERGER_PROMPT_STR,
    "transcript_length_adjustment_prompt": TRANSCRIPT_LENGTH_ADJUSTMENT_PROMPT_STR,
    "transcript_formatting_prompt": TRANSCRIPT_FORMATTING_PROMPT_STR
}

# Create Jinja templates once
TEMPLATES: Dict[str, jinja2.Template] = {
    name: jinja2.Template(template) for name, template in PROMPT_TEMPLATES.items()
}


class FinancialSummaryPrompts:
    def __getattr__(self, name: str) -> str:
        """Dynamically handle prompt requests by name"""
        if name in PROMPT_TEMPLATES:
            return PROMPT_TEMPLATES[name]
        raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{name}'")

    @classmethod
    def get_template(cls, name: str) -> jinja2.Template:
        """Get the Jinja template by name"""
        return TEMPLATES[name]
