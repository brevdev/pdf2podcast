import jinja2
from typing import Dict

MONOLOGUE_SUMMARY_PROMPT_STR = """
Please provide a targeted analysis of the following financial document, focusing on: {{ focus }}

<document>
{{text}}
</document>

Requirements for the analysis:
1. Essential Financial Information:
   - Core financial metrics
   - Performance indicators
   - Growth rates and trends
   - Market projections
   - Strategic updates

2. Document Context:
   - Document type and purpose
   - Relevant entities
   - Time period covered
   - Key stakeholders

3. Data Accuracy:
   - Preserve exact numerical values
   - Maintain specific dates
   - Keep precise financial terminology
   - Include verbatim risk disclosures when relevant

4. Text Conversion Requirements:
   - Write all numbers in word form (e.g., "one billion" not "1B")
   - Express currency as "[amount] [unit]" (e.g., "fifty million dollars")
   - Write percentages in spoken form (e.g., "twenty five percent")
   - Spell out mathematical operations (e.g., "increased by" not "+")
   - Use proper Unicode characters

Format the analysis using markdown with clear headers and bullet points. Be focused and specific"""

MONOLOGUE_MULTI_DOC_SYNTHESIS_PROMPT_STR = """
Create a structured monologue outline synthesizing the following document summaries. The monologue should be 30-45 seconds long.

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
   - Prioritize topics according to focus instructions
   - Identify key financial metrics and trends
   - Analyze potential stakeholder concerns
   - Draw connections between documents and focus areas

2. Structure Requirements
   - Create a clear narrative flow
   - Balance depth vs breadth of coverage
   - Ensure logical topic transitions
   - Maintain financial accuracy and precision

3. Time Management
   - Allocate time based on topic importance
   - Allow for natural pacing and emphasis
   - Include brief pauses for key points
   - Stay within total duration

4. Text Formatting Requirements:
   - Write numbers in word form
   - Format currency as "[amount] [unit]"
   - Express percentages in spoken form
   - Write out mathematical operations

Output a structured outline that synthesizes insights across all documents. This should be a concise, actionable summary."""

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
- Duration: 30 seconds (~90 words)
- Speaker: {{ speaker_1_name }}
- Structure: Follow the outline while maintaining:
  * Opening (5-7 words)
  * Key points from outline (60-70 words)
  * Supporting evidence (15-20 words)
  * Conclusion (10-15 words)

Requirements:
1. Speech Pattern
   - Use broadcast-style delivery
   - Natural pauses and emphasis
   - Professional but conversational tone
   - Clear source attribution

2. Content Structure
   - Follow the provided outline
   - Maintain logical flow between points
   - Support key claims with evidence
   - End with a clear takeaway

3. Text Formatting:
   - All numbers in word form
   - Currency as "[amount] [unit]"
   - Percentages in spoken form
   - Mathematical operations written out
   - Proper Unicode characters

Create a concise, engaging monologue that follows the outline while delivering essential financial information."""

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

Please output the JSON following the provided schema, maintaining all financial details and proper formatting. The output should use proper Unicode characters directly, not escaped sequences. Do not output anything besides the JSON."""

PROMPT_TEMPLATES = {
    "monologue_summary_prompt": MONOLOGUE_SUMMARY_PROMPT_STR,
    "monologue_multi_doc_synthesis_prompt": MONOLOGUE_MULTI_DOC_SYNTHESIS_PROMPT_STR,
    "monologue_transcript_prompt": MONOLOGUE_TRANSCRIPT_PROMPT_STR,
    "monologue_dialogue_prompt": MONOLOGUE_DIALOGUE_PROMPT_STR,
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
