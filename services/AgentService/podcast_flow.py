from shared.shared_types import (
    JobStatus,
    Conversation,
    PDFMetadata,
    TranscriptionRequest,
    PodcastOutline,
)
from shared.llmmanager import LLMManager
from shared.job import JobStatusManager
from typing import List, Dict, Any, Coroutine
import ujson as json
import logging
from shared.prompt_tracker import PromptTracker
from podcast_prompts import PodcastPrompts
from langchain_core.messages import AIMessage
import asyncio


async def podcast_summarize_pdf(
    pdf_metadata: PDFMetadata, llm_manager: LLMManager, prompt_tracker: PromptTracker
) -> AIMessage:
    """Summarize a single PDF document"""
    template = PodcastPrompts.get_template("podcast_summary_prompt")
    prompt = template.render(text=pdf_metadata.markdown)

    summary_response: AIMessage = await llm_manager.query_async(
        "reasoning",
        [{"role": "user", "content": prompt}],
        f"summarize_{pdf_metadata.filename}",
    )
    prompt_tracker.track(
        f"summarize_{pdf_metadata.filename}",
        prompt,
        llm_manager.model_configs["reasoning"].name,
    )
    return summary_response


async def podcast_summarize_pdfs(
    pdfs: List[PDFMetadata],
    job_id: str,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_manager: JobStatusManager,
    logger: logging.Logger,
) -> List[PDFMetadata]:
    """Summarize all PDFs in the request"""
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, f"Summarizing {len(pdfs)} PDFs"
    )

    summaries: List[AIMessage] = await asyncio.gather(
        *[podcast_summarize_pdf(pdf, llm_manager, prompt_tracker) for pdf in pdfs]
    )

    for pdf, summary in zip(pdfs, summaries):
        pdf.summary = summary.content
        prompt_tracker.update_result(f"summarize_{pdf.filename}", pdf.summary)
        logger.info(f"Successfully summarized {pdf.filename}")

    return pdfs


def podcast_generate_raw_outline(
    summarized_pdfs: List[PDFMetadata],
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
    job_manager: JobStatusManager,
    logger: logging.Logger,
) -> str:
    """Generate initial raw outline from summarized PDFs"""
    # Prepare document summaries in XML format
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, "Generating initial outline"
    )
    documents = []
    for pdf in summarized_pdfs:
        doc_str = f"""
        <document>
        <is_important>true</is_important>
        <path>{pdf.filename}</path>
        <summary>
        {pdf.summary}
        </summary>
        </document>"""
        documents.append(doc_str)

    template = PodcastPrompts.get_template("podcast_multi_pdf_outline_prompt")
    prompt = template.render(
        total_duration=request.duration,
        focus_instructions=request.guide if request.guide else None,
        documents="\n\n".join(documents),
    )
    raw_outline: AIMessage = llm_manager.query_sync(
        "reasoning",
        [{"role": "user", "content": prompt}],
        "raw_outline",
    )

    prompt_tracker.track(
        "raw_outline",
        prompt,
        llm_manager.model_configs["reasoning"].name,
        raw_outline.content,
    )

    return raw_outline.content


def podcast_generate_structured_outline(
    raw_outline: str,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
    job_manager: JobStatusManager,
    logger: logging.Logger,
) -> PodcastOutline:
    """Convert raw outline to structured format"""
    job_manager.update_status(
        job_id,
        JobStatus.PROCESSING,
        "Converting raw outline to structured format",
    )

    # Force the model to only reference valid filenames
    valid_filenames = [pdf.filename for pdf in request.pdf_metadata]
    schema = PodcastOutline.model_json_schema()
    schema["$defs"]["PodcastSegment"]["properties"]["references"]["items"] = {
        "type": "string",
        "enum": valid_filenames,
    }

    schema = PodcastOutline.model_json_schema()
    template = PodcastPrompts.get_template(
        "podcast_multi_pdf_structured_outline_prompt"
    )
    prompt = template.render(
        outline=raw_outline,
        schema=json.dumps(schema, indent=2),
        valid_filenames=[pdf.filename for pdf in request.pdf_metadata],
    )
    outline: Dict = llm_manager.query_sync(
        "json",
        [{"role": "user", "content": prompt}],
        "outline",
        json_schema=schema,
    )
    prompt_tracker.track(
        "outline", prompt, llm_manager.model_configs["json"].name, json.dumps(outline)
    )
    return PodcastOutline.model_validate(outline)


async def podcast_process_segment(
    segment: Any,
    idx: int,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
) -> tuple[str, str]:
    """Process a single segment"""
    # Get reference content if it exists
    text_content = []
    if segment.references:
        for ref in segment.references:
            # Find matching PDF metadata by filename
            pdf = next(
                (pdf for pdf in request.pdf_metadata if pdf.filename == ref), None
            )
            if pdf:
                text_content.append(pdf.markdown)

    # Choose template based on whether we have references
    template_name = (
        "podcast_prompt_with_references"
        if text_content
        else "podcast_prompt_no_references"
    )
    template = PodcastPrompts.get_template(template_name)

    # Prepare prompt parameters
    prompt_params = {
        "duration": segment.duration,
        "topic": segment.section,
        "angles": "\n".join([topic.title for topic in segment.topics]),
    }

    # Add text content if we have references
    if text_content:
        prompt_params["text"] = "\n\n".join(text_content)

    prompt = template.render(**prompt_params)

    response: AIMessage = await llm_manager.query_async(
        "iteration",
        [{"role": "user", "content": prompt}],
        f"segment_{idx}",
    )

    prompt_tracker.track(
        f"segment_transcript_{idx}",
        prompt,
        llm_manager.model_configs["iteration"].name,
        response.content,
    )

    return f"segment_transcript_{idx}", response.content


async def podcast_process_segments(
    outline: PodcastOutline,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
    job_manager: JobStatusManager,
    logger: logging.Logger,
) -> Dict[str, str]:
    """Process each segment in the outline"""
    # Create tasks for processing each segment
    segment_tasks: List[Coroutine] = []
    for idx, segment in enumerate(outline.segments):
        job_manager.update_status(
            job_id,
            JobStatus.PROCESSING,
            f"Processing segment {idx + 1}/{len(outline.segments)}: {segment.section}",
        )

        task = podcast_process_segment(
            segment,
            idx,
            request,
            llm_manager,
            prompt_tracker,
        )
        segment_tasks.append(task)

    # Process all segments in parallel
    results = await asyncio.gather(*segment_tasks)

    # Convert results to dictionary
    return dict(results)


async def podcast_generate_dialogue_segment(
    segment: Any,
    idx: int,
    segment_text: str,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
) -> Dict[str, str]:
    """Generate dialogue for a single segment"""
    # Format topics for prompt
    topics_text = "\n".join(
        [
            f"- {topic.title}\n"
            + "\n".join([f"  * {point.description}" for point in topic.points])
            for topic in segment.topics
        ]
    )

    # Generate dialogue using template
    template = PodcastPrompts.get_template("podcast_transcript_to_dialogue_prompt")
    prompt = template.render(
        text=segment_text,
        duration=segment.duration,
        descriptions=topics_text,
        speaker_1_name=request.speaker_1_name,
        speaker_2_name=request.speaker_2_name,
    )

    # Query LLM for dialogue
    dialogue_response = await llm_manager.query_async(
        "reasoning",
        [{"role": "user", "content": prompt}],
        f"segment_dialogue_{idx}",
    )

    # Track prompt and response
    prompt_tracker.track(
        f"segment_dialogue_{idx}",
        prompt,
        llm_manager.model_configs["reasoning"].name,
        dialogue_response.content,
    )

    return {"section": segment.section, "dialogue": dialogue_response.content}


async def podcast_generate_dialogue(
    segments: Dict[str, str],
    outline: PodcastOutline,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
    job_manager: JobStatusManager,
    logger: logging.Logger,
) -> List[Dict[str, str]]:
    """Generate dialogue for each segment"""
    job_manager.update_status(job_id, JobStatus.PROCESSING, "Generating dialogue")

    # Create tasks for generating dialogue for each segment
    dialogue_tasks = []
    for idx, segment in enumerate(outline.segments):
        segment_name = f"segment_transcript_{idx}"
        seg_response = segments.get(segment_name)

        if not seg_response:
            logger.warning(f"Segment {segment_name} not found in segment transcripts")
            continue

        # Update prompt tracker with segment response
        segment_text = seg_response
        prompt_tracker.update_result(segment_name, segment_text)

        # Update status
        job_manager.update_status(
            job_id,
            JobStatus.PROCESSING,
            f"Converting segment {idx + 1}/{len(outline.segments)} to dialogue",
        )

        task = podcast_generate_dialogue_segment(
            segment,
            idx,
            segment_text,
            request,
            llm_manager,
            prompt_tracker,
        )
        dialogue_tasks.append(task)

    # Process all dialogues in parallel
    dialogues = await asyncio.gather(*dialogue_tasks)

    return list(dialogues)


def podcast_combine_dialogues(
    segment_dialogues: List[Dict[str, str]],
    outline: PodcastOutline,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
    job_manager: JobStatusManager,
    logger: logging.Logger,
) -> str:
    """Iteratively combine dialogue segments into a cohesive conversation"""
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, "Combining dialogue segments"
    )

    # Start with the first segment's dialogue
    current_dialogue = segment_dialogues[0]["dialogue"]
    prompt_tracker.update_result(
        "segment_dialogue_0",
        current_dialogue,
    )

    # Iteratively combine with subsequent segments
    for idx in range(1, len(segment_dialogues)):
        job_manager.update_status(
            job_id,
            JobStatus.PROCESSING,
            f"Combining segment {idx + 1}/{len(segment_dialogues)} with existing dialogue",
        )

        next_section = segment_dialogues[idx]["dialogue"]
        prompt_tracker.update_result(f"segment_dialogue_{idx}", next_section)
        current_section = segment_dialogues[idx]["section"]

        template = PodcastPrompts.get_template("podcast_combine_dialogues_prompt")
        prompt = template.render(
            outline=outline.model_dump_json(),
            dialogue_transcript=current_dialogue,
            next_section=next_section,
            current_section=current_section,
        )

        combined: AIMessage = llm_manager.query_sync(
            "iteration",
            [{"role": "user", "content": prompt}],
            f"combine_dialogues_{idx}",
        )

        prompt_tracker.track(
            f"combine_dialogues_{idx}",
            prompt,
            llm_manager.model_configs["iteration"].name,
            combined.content,
        )

        current_dialogue = combined.content

    return current_dialogue


def podcast_create_final_conversation(
    dialogue: str,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
    job_manager: JobStatusManager,
    logger: logging.Logger,
) -> Conversation:
    """Convert the dialogue into structured Conversation format"""
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, "Formatting final conversation"
    )

    schema = Conversation.model_json_schema()
    template = PodcastPrompts.get_template("podcast_dialogue_prompt")
    prompt = template.render(
        speaker_1_name=request.speaker_1_name,
        speaker_2_name=request.speaker_2_name,
        text=dialogue,
        schema=json.dumps(schema, indent=2),
    )

    # We accumulate response as it comes in then cast
    conversation_json: Dict = llm_manager.stream_sync(
        "json",
        [{"role": "user", "content": prompt}],
        "create_final_conversation",
        json_schema=schema,
    )

    prompt_tracker.track(
        "create_final_conversation",
        prompt,
        llm_manager.model_configs["json"].name,
        json.dumps(conversation_json),
    )

    return Conversation.model_validate(conversation_json)
