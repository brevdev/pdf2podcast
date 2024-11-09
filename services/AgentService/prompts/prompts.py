import jinja2

# Raw string prompts
RAW_OUTLINE_PROMPT_STR = """I want to make the following paper into a podcast transcript for {{ duration }} minutes, to help audience understand background, innovation, impact and future work. 

Come up the structure of the podcast.
                                 
{{ text }}
                                     
Innovation should be the focus of the podcast, and the most important part of the podcast, with enough details."""

OUTLINE_PROMPT_STR = """Given the free form outline, convert in into a structured outline without losing any information.                                 

{{ text }}
                                                           
The result must conform to the following JSON schema:\n{{ schema }}\n\n"""

SEGMENT_TRANSCRIPT_PROMPT_STR = """Make a transcript given the text:

{{ text }}
                                            
The transcript is about {{ duration }} minutes, approximately {{ (duration * 180) | int }} words.
The transcript's subject is {{ topic }}, and should focus on the following topics: {{ angles }}
                                            
Explain all concepts clearly, assuming no prior knowledge
Use analogies, stories, or examples to illustrate points
Address potential questions or counterarguments
Provide context and background information throughout
Make sure the details, numbers are accurate and comprehensive
                                            
Dive deep into each topic, and provide enough details given the time budget, don't leave any stone unturned."""

DEEP_DIVE_PROMPT_STR = """You will be given some content, short ideas or thoughts about the content.

Your task is to expand the content into a detailed and comprehensive explanation, with enough details and examples.

Here is the content

{{text}}
                                   
The topic will be around
                                   
{{topic}}
                                   
Dive deep into each topic, come up with an outline with topics and subtopics to help fully understand the content.
Expand the topics, don't add any other topics. Allocate time budget for each topic. Total time budget should be {{ duration }} minutes.
Focus on the most important topics and ideas, and allocate more time budget to them.
Avoid introduction and conclusion in the outline, focus on expanding into subtopics."""

TRANSCRIPT_PROMPT_STR = """Given the transcript of different segments,combine and optimize the transcript to make the flow more natural.
The content should be strictly following the transcript, and only optimize the flow. Keep all the details, and storytelling contents.

{% for segment, duration in segments %}

Time budget: {{ duration }} minutes, approximately {{ (duration * 180) | int }} words.
{{ segment }}                                    

{% endfor %}
                                    
Only return the full transcript, no need to include any other information like time budget or segment name."""

RAW_PODCAST_DIALOGUE_PROMPT_V2_STR = """Your task is to transform the provided input transcript into a lively, engaging, and informative podcast dialogue. 

There are two speakers, speaker-1 and speaker-2.
speaker-1's name is {{ speaker_1_name }}, and speaker-2's name is {{ speaker_2_name }}.

Given the following conversation, make introductions for both speakers at beginning of the conversation.
During the conversation, occasionally mention the speaker's name to refer to them, to make the conversation more natural.
Incorporate natural speech patterns, including occasional verbal fillers (e.g., "um," "well," "you know")
Use casual language and ensure the dialogue flows smoothly, reflecting a real-life conversation
The fillers should be used naturally, not in every sentence, and not in a robotic way but related to topic and conversation context.
                                          
Maintain a lively pace with a mix of serious discussion and lighter moments
Use rhetorical questions or hypotheticals to involve the listener
Create natural moments of reflection or emphasis
     
Allow for natural interruptions and back-and-forth between host and guest
Ensure the guest's responses are substantiated by the input text, avoiding unsupported claims                                   
Avoid long sentences from either speaker, break them into conversations between two speakers.
Throughout the script, strive for authenticity in the conversation. Include:
   - Moments of genuine curiosity or surprise from the host
   - Instances where the guest might briefly struggle to articulate a complex idea
   - Light-hearted moments or humor when appropriate
   - Brief personal anecdotes or examples that relate to the topic (within the bounds of the input text)
                 
Don't lose any information or details in the transcript. It is only format conversion, so strictly follow the transcript.
                                                 
This segment is about {{ duration }} minutes, approximately {{ (duration * 180) | int }} words.
The topic is {{ descriptions }}
                                          
You should keep all analogies, stories, examples, and quotes from the transcript.

Here is the transcript:
{{text}}
                                          
Only return the full dialogue transcript, no need to include any other information like time budget or segment name.
Don't add introduction and ending to the dialogue unless it is provided in the transcript."""

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
