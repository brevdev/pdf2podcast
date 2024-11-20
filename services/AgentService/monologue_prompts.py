import jinja2
from typing import Dict

MONOLOGUE_SUMMARY_PROMPT_STR = """
You are presenting NVIDIA earning reports and analyses to a broad audience. Please provide a {{ level_of_detail }}-detail summary of the following financial document.

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

4. Text Conversion Requirements:
  - Write all numbers in word form (e.g., "one billion" not "1B")
  - Express currency as "[amount] [unit]" (e.g., "fifty million dollars")
  - Write percentages in spoken form (e.g., "twenty five percent")
  - Spell out mathematical operations (e.g., "increased by" not "+")
  - Use proper Unicode characters

{% if level_of_detail == "light" %}
Focus on essential insights and core messages for quick strategic understanding.
{% elif level_of_detail == "medium" %}
Balance depth and accessibility while maintaining key financial context.
{% else %}
Provide thorough analysis while ensuring clarity in complex financial narratives.
{% endif %}
You are presenting to the entire company at a company meeting. Speak in a way that is engaging and informative, adding technicalities as needed to highlight performance, and speak in the first person.
"""

MONOLOGUE_MULTI_DOC_SYNTHESIS_PROMPT_STR = """
Create a structured monologue outline synthesizing the following document summaries.
{% if level_of_detail == "light" %}
Focus on essential highlights and critical strategic implications.
{% elif level_of_detail == "medium" %}
Provide balanced coverage of key findings and their interconnections.
{% else %}
Deliver comprehensive analysis with detailed supporting context.
{% endif %}

Focus Areas & Key Topics:
{% if focus_instructions %}
{{focus_instructions}}
{% else %}
Use your judgment to identify and prioritize the most important financial themes, metrics, and insights across all documents.
{% endif %}

Available Source Documents:
{{documents}}

Requirements:
1. Content Strategy
{% if level_of_detail == "light" %}
   - Concentrate on critical insights
   - Focus on immediate implications
   - Address core stakeholder priorities
{% elif level_of_detail == "medium" %}
   - Balance key themes and supporting data
   - Examine relevant trends
   - Consider stakeholder perspectives
   - Highlight important connections
{% else %}
   - Deep dive into complex patterns
   - Thorough analysis of implications
   - Multiple stakeholder considerations
   - Comprehensive synthesis
{% endif %}

2. Structure Requirements
{% if level_of_detail == "light" %}
   - Clear, direct narrative
   - Essential context only
   - Focused transitions
{% elif level_of_detail == "medium" %}
   - Balanced narrative flow
   - Relevant supporting details
   - Natural topic progression
{% else %}
   - Rich narrative development
   - Detailed supporting evidence
   - Sophisticated theme integration
   - Nuanced transitions
{% endif %}

3. Delivery Approach
{% if level_of_detail == "light" %}
   - Emphasis on key messages
   - Strategic pacing
   - Clear takeaways
{% elif level_of_detail == "medium" %}
   - Balanced information flow
   - Natural rhythm
   - Effective emphasis points
{% else %}
   - Comprehensive coverage
   - Dynamic pacing
   - Layered emphasis
   - Thoughtful reflection points
{% endif %}

4. Text Formatting Requirements:
   - Write numbers in word form
   - Format currency as "[amount] [unit]"
   - Express percentages in spoken form
   - Write out mathematical operations

Create an outline that effectively synthesizes insights across all documents.
{% if level_of_detail == "light" %}
Prioritize clarity and immediate relevance.
{% elif level_of_detail == "medium" %}
Balance comprehensiveness with accessibility.
{% else %}
Provide thorough analysis while maintaining engagement.
{% endif %}"""

MONOLOGUE_TRANSCRIPT_PROMPT_STR = """
Create a focused financial update based on this outline and source documents.

Outline:
{{ raw_outline }}

Available Source Documents:
{% for doc in documents %}
<document>
<is_important>true</is_important>
<path>{{doc.filename}}</path>
<summary>
{{doc.summary}}
</summary>
</document>
{% endfor %}

Focus Areas: {{ focus }}

Parameters:
- Level of detail: {{ level_of_detail }}
- Speaker: {{ speaker_1_name }}
{% if level_of_detail == "light" %}
- Structure: Concise opening, essential points, key evidence, clear conclusion
{% elif level_of_detail == "medium" %}
- Structure: Clear opening, key points with context, supporting evidence, comprehensive conclusion
{% else %}
- Structure: Detailed opening, thorough analysis, extensive evidence, nuanced conclusion
{% endif %}

Requirements:
1. Speech Pattern
{% if level_of_detail == "light" %}
   - Direct and impactful delivery
   - Strategic emphasis
   - Clear attribution of key points
{% elif level_of_detail == "medium" %}
   - Natural, engaging delivery
   - Balanced emphasis
   - Clear sourcing and context
{% else %}
   - Rich, detailed delivery
   - Layered emphasis structure
   - Comprehensive attribution
{% endif %}

2. Content Structure
{% if level_of_detail == "light" %}
   - Essential narrative elements
   - Core supporting points
   - Clear conclusions
{% elif level_of_detail == "medium" %}
   - Developed narrative flow
   - Balanced supporting evidence
   - Contextual conclusions
{% else %}
   - Complex narrative development
   - Multiple evidence layers
   - Nuanced implications
{% endif %}

3. Text Formatting:
   - All numbers in word form
   - Currency as "[amount] [unit]"
   - Percentages in spoken form
   - Mathematical operations written out

Create a monologue that effectively communicates financial information appropriate to the detail level."""

MONOLOGUE_DIALOGUE_PROMPT_STR = """You are tasked with converting a financial monologue into a structured JSON format. You have:

1. Speaker information:
   - Speaker: {{ speaker_1_name }} (mapped to "speaker-1")

2. The original monologue:
{{ text }}

3. Required output schema:
{{ schema }}

Your task is to:
- Convert the monologue exactly into the specified JSON format 
- Preserve all content without any omissions
- Map all content to "speaker-1"
- Maintain all financial data accuracy

{% if level_of_detail == "light" %}
Focus on essential data points while ensuring accuracy and clarity.
{% elif level_of_detail == "medium" %}
Balance completeness with accessibility while maintaining precision.
{% else %}
Ensure thorough preservation of details and nuanced information.
{% endif %}

You absolutely must, without exception:
- Use proper Unicode characters directly (e.g., use ' instead of \\u2019)
- Ensure all apostrophes, quotes, and special characters are properly formatted
- Do not escape Unicode characters in the output

You absolutely must, without exception:
- Convert all numbers and symbols to spoken form:
  * Numbers should be spelled out (e.g., "one billion" instead of "1B")
  * Currency should be expressed as "[amount] [unit of currency]" (e.g., "fifty million dollars" instead of "$50M")
  * Mathematical symbols should be spoken (e.g., "increased by" instead of "+")
  * Percentages should be spoken as "percent" (e.g., "twenty five percent" instead of "25%")
- Convert all financial acronyms (e.g., GAAP, EBITDA) to their spelled out, spoken form (e.g., "GAP" instead of "GAAP").

Please output the JSON following the provided schema, maintaining all financial details and proper formatting. The output should use proper Unicode characters directly, not escaped sequences. Do not output anything besides the JSON."""

MONOLOGUE_LENGTH_ADJUSTMENT_PROMPT_STR = """You are an expert financial podcast editor skilled at preserving key information while adjusting content length. Review and adjust this financial monologue:

{{ text }}

You are adjusting this for a {{ level_of_detail }} detail level which requires:
{% if level_of_detail == "light" %}
A concise, focused delivery that maintains impact while being brief enough to fit in ninety seconds. Focus on the most critical insights and headline-worthy updates.
{% elif level_of_detail == "medium" %}
A balanced narrative that fits within two and a half minutes to three minutes. Preserve key details and supporting context while maintaining a brisk, engaging pace.
{% else %}
A comprehensive but carefully edited narrative that fits within five minutes. Include rich detail and thorough analysis while ensuring every sentence adds value.
{% endif %}

Editing Requirements:
1. Content Priorities
{% if level_of_detail == "light" %}
- Keep only the most impactful insights
- Focus on headline metrics and major shifts
- Maintain only essential context
{% elif level_of_detail == "medium" %}
- Preserve core narrative and key developments
- Keep primary supporting evidence
- Retain important contextual elements
- Keep some secondary claims and evidence as well
{% else %}
- Maintain detailed analysis where valuable
- Keep rich supporting evidence
- Preserve nuanced market context
- Keep deep dives and in-depth comparisons
{% endif %}

2. Engagement Principles:
- Start with a hook that captures attention
- Use dynamic pacing to maintain interest
- Create natural flow between topics
- End with clear, memorable takeaways

3. Technical Requirements:
- Preserve all financial accuracy
- Maintain spoken number format
- Maintain spoken, spelled-out acronym format
- Keep attribution and source references
- Output as plain text without any markdown formatting
- Use natural speech patterns suitable for speaking aloud
- Avoid any special formatting characters or symbols

Your task is to edit this monologue to be naturally delivered within the target time while keeping it engaging and informative. Focus on smooth transitions and natural speech patterns, as well as a natural ending.

Return only the edited monologue as plain text, exactly as it would be spoken aloud. Do not include any markdown, formatting, or special characters."""

PROMPT_TEMPLATES = {
    "monologue_summary_prompt": MONOLOGUE_SUMMARY_PROMPT_STR,
    "monologue_multi_doc_synthesis_prompt": MONOLOGUE_MULTI_DOC_SYNTHESIS_PROMPT_STR,
    "monologue_transcript_prompt": MONOLOGUE_TRANSCRIPT_PROMPT_STR,
    "monologue_dialogue_prompt": MONOLOGUE_DIALOGUE_PROMPT_STR,
    "monologue_length_adjustment_prompt": MONOLOGUE_LENGTH_ADJUSTMENT_PROMPT_STR
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
