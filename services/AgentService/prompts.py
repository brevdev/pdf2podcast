import jinja2

# Raw string prompts
RAW_OUTLINE_PROMPT_STR = """I want to make the following paper into a concise 30-second audio script that captures the single most important innovation or finding. Focus on one key takeaway that will grab the audience's attention.

{{ text }}

The output must be extremely focused - remember this is only 30 seconds. Avoid any unnecessary background or future work unless absolutely critical to understanding the main point."""

OUTLINE_PROMPT_STR = """Given the free form outline, convert in into a structured outline without losing any information.                                 

{{ text }}
                                                           
The result must conform to the following JSON schema:\n{{ schema }}\n\n"""

SEGMENT_TRANSCRIPT_PROMPT_STR = """Create a 30-second script (approximately 90 words) for the following text:

{{ text }}

The script should focus on: {{ topic }}
Key angles to cover: {{ angles }}

Guidelines for 30-second format:
- Start with an attention-grabbing statement
- Focus on ONE main idea or finding
- Use simple, clear language
- Include only the most essential details
- End with a memorable takeaway
- Avoid technical jargon unless absolutely necessary

Remember: This must fit in 30 seconds - be ruthlessly concise while maintaining clarity."""

DEEP_DIVE_PROMPT_STR = """You will be given content to compress into a 30-second explanation (approximately 90 words).

Content:
{{text}}

Topic focus:
{{topic}}

Create a laser-focused outline that:
- Identifies the single most important point
- Breaks it down into 2-3 key supporting details
- Removes all non-essential information
- Ensures everything mentioned can be properly explained in 30 seconds

Total time: {{ duration }} seconds (approximately 90 words)."""

TRANSCRIPT_PROMPT_STR = """Given the transcript of different segments,combine and optimize the transcript to make the flow more natural.
The content should be strictly following the transcript, and only optimize the flow. Keep all the details, and storytelling contents.

{% for segment, duration in segments %}

Time budget: {{ duration }} minutes, approximately {{ (duration * 180) | int }} words.
{{ segment }}                                    

{% endfor %}
                                    
Only return the full transcript, no need to include any other information like time budget or segment name."""

RAW_PODCAST_DIALOGUE_PROMPT_V2_STR = """Transform the provided input into a punchy 30-second dialogue between two speakers.

Speakers: {{ speaker_1_name }} and {{ speaker_2_name }}

Guidelines for 30-second format:
- Start with a hook - no lengthy introductions
- Focus on ONE key point or revelation
- Use short, snappy exchanges
- Include max 1-2 brief examples or analogies
- End with a clear takeaway
- Keep individual speaking turns to 1-2 sentences maximum

Topic: {{ descriptions }}
Target length: {{ duration }} seconds (approximately 90 words)

Input text:
{{text}}

Remember: Every word must earn its place in a 30-second script."""

FUSE_OUTLINE_PROMPT_STR = """You are given two outlines, one is overall outline, another is sub-outline for one section in the overall outline.
You need to fuse the two outlines into a new outline, to represent the whole podcast without losing any descriptions in sub sections.
Ignore the time budget in the sub-outline, and use the time budget in the overall outline.
Overall outline:
{{ overall_outline }}

Sub-outline:
{{ sub_outline }}

Output the new outline with the tree structure."""

REVISE_PROMPT_STR = """You are given a podcast dialogue transcript, and a raw transcript of the podcast.
You are only allowed to copy information from the raw dialogue transcript to make the conversation more natural and engaging, but exactly follow the outline.
                                
Outline:
{{ outline}}

Here is the dialogue transcript:
{{ dialogue_transcript }}

You need also to break long sentences from either speaker into conversations between two speakers, by inserting more dialogue entries and verbal fillers (e.g., "um")
Don't let a single speaker talk more than 2 sentences, and break the conversation into multiple exchanges between two speakers.
                                
Don't make any explict transition between sections, this is one podcast, and the sections are connected.
Don't use words like "Welcome back" or "Now we are going to talk about" etc.
Don't make introductions in the middle of the conversation.
Merge related topics according to outline and don't repeat same things in different place.
                                
Don't lose any information or details from the raw transcript, only make the conversation flow more natural."""

PODCAST_DIALOGUE_PROMPT_STR = """Given a podcast transcript between two speakers, convert it into a structured JSON format.
- Only do conversion
- Don't miss any information in the transcript

There are two speakers, speaker-1 and speaker-2.
speaker-1's name is {{ speaker_1_name }}, and speaker-2's name is {{ speaker_2_name }}.
                                          
Here is the original transcript:
{{ text }}
                                          
The result must conform to the following JSON schema:\n{{ schema }}\n\n"""

# Wrap raw strings in Jinja templates
RAW_OUTLINE_PROMPT = jinja2.Template(RAW_OUTLINE_PROMPT_STR)
OUTLINE_PROMPT = jinja2.Template(OUTLINE_PROMPT_STR)
SEGMENT_TRANSCRIPT_PROMPT = jinja2.Template(SEGMENT_TRANSCRIPT_PROMPT_STR)
DEEP_DIVE_PROMPT = jinja2.Template(DEEP_DIVE_PROMPT_STR)
TRANSCRIPT_PROMPT = jinja2.Template(TRANSCRIPT_PROMPT_STR)
RAW_PODCAST_DIALOGUE_PROMPT_v2 = jinja2.Template(RAW_PODCAST_DIALOGUE_PROMPT_V2_STR)
FUSE_OUTLINE_PROMPT = jinja2.Template(FUSE_OUTLINE_PROMPT_STR)
REVISE_PROMPT = jinja2.Template(REVISE_PROMPT_STR)
PODCAST_DIALOGUE_PROMPT = jinja2.Template(PODCAST_DIALOGUE_PROMPT_STR)


# Class to hold all prompts
class PodcastPrompts:
    def raw_outline_prompt(self):
        return RAW_OUTLINE_PROMPT_STR

    def outline_prompt(self):
        return OUTLINE_PROMPT_STR

    def segment_transcript_prompt(self):
        return SEGMENT_TRANSCRIPT_PROMPT_STR

    def deep_dive_prompt(self):
        return DEEP_DIVE_PROMPT_STR

    def transcript_prompt(self):
        return TRANSCRIPT_PROMPT_STR

    def raw_podcast_dialogue_prompt_v2(self):
        return RAW_PODCAST_DIALOGUE_PROMPT_V2_STR

    def fuse_outline_prompt(self):
        return FUSE_OUTLINE_PROMPT_STR

    def revise_prompt(self):
        return REVISE_PROMPT_STR

    def podcast_dialogue_prompt(self):
        return PODCAST_DIALOGUE_PROMPT_STR
