from shared.shared_types import (
    JobStatus,
    Conversation,
    PDFMetadata,
    TranscriptionRequest,
)
from shared.llmmanager import LLMManager
from shared.job import JobStatusManager
from typing import List, Dict
import ujson as json
import logging
from shared.prompt_tracker import PromptTracker
from monologue_prompts import FinancialSummaryPrompts
from langchain_core.messages import AIMessage
import asyncio


async def monologue_summarize_pdf(
    pdf_metadata: PDFMetadata, llm_manager: LLMManager, prompt_tracker: PromptTracker
) -> AIMessage:
    """Summarize a single PDF document"""
    template = FinancialSummaryPrompts.get_template("monologue_summary_prompt")
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


async def monologue_summarize_pdfs(
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
        *[monologue_summarize_pdf(pdf, llm_manager, prompt_tracker) for pdf in pdfs]
    )

    for pdf, summary in zip(pdfs, summaries):
        pdf.summary = summary.content
        prompt_tracker.update_result(f"summarize_{pdf.filename}", pdf.summary)
        logger.info(f"Successfully summarized {pdf.filename}")

    return pdfs


async def monologue_generate_raw_outline(
    summarized_pdfs: List[PDFMetadata],
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
    job_manager: JobStatusManager,
) -> str:
    """Generate initial raw outline from summarized PDFs"""
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, "Generating initial outline"
    )

    # Format documents as a string list for consistency with podcast flow
    documents = [f"Document: {pdf.filename}\n{pdf.summary}" for pdf in summarized_pdfs]

    template = FinancialSummaryPrompts.get_template(
        "monologue_multi_doc_synthesis_prompt"
    )
    prompt = template.render(
        focus_instructions=request.guide if request.guide else None,
        documents="\n\n".join(documents),
    )

    raw_outline: AIMessage = await llm_manager.query_async(
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


async def monologue_generate_monologue(
    raw_outline: str,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
    job_manager: JobStatusManager,
) -> str:
    """Generate monologue transcript"""
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, "Creating monologue transcript"
    )

    template = FinancialSummaryPrompts.get_template("monologue_transcript_prompt")
    prompt = template.render(
        raw_outline=raw_outline,
        documents=request.pdf_metadata,
        focus=request.guide
        if request.guide
        else "key financial metrics and performance indicators",
        speaker_1_name=request.speaker_1_name,
    )

    monologue: AIMessage = await llm_manager.query_async(
        "reasoning",
        [{"role": "user", "content": prompt}],
        "create_monologue",
    )

    prompt_tracker.track(
        "create_monologue",
        prompt,
        llm_manager.model_configs["reasoning"].name,
        monologue.content,
    )

    return monologue.content


async def monologue_create_final_conversation(
    monologue: str,
    request: TranscriptionRequest,
    llm_manager: LLMManager,
    prompt_tracker: PromptTracker,
    job_id: str,
    job_manager: JobStatusManager,
) -> Conversation:
    """Convert the monologue into structured Conversation format"""
    job_manager.update_status(
        job_id, JobStatus.PROCESSING, "Formatting final conversation"
    )

    schema = Conversation.model_json_schema()
    template = FinancialSummaryPrompts.get_template("monologue_dialogue_prompt")
    prompt = template.render(
        speaker_1_name=request.speaker_1_name,
        text=monologue,
        schema=json.dumps(schema, indent=2),
    )

    conversation_json: Dict = await llm_manager.query_async(
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
