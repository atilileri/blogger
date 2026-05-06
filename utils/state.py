from typing import TypedDict, Annotated, Optional, Literal
import operator

class PipelineState(TypedDict):
    """
    Central state for the Blogger pipeline.
    """
    # Identity
    chat_id: int
    thread_id: str                # str(chat_id), used for LangGraph thread persistence

    # Step 1: Intake
    raw_message: dict             # Full Telegram message object
    user_intent: str
    youtube_urls: list[str]
    website_urls: list[str]

    # Step 2: Transcriptions (parallel output, merged via operator.add)
    transcripts: Annotated[list[dict], operator.add]

    # Step 3: Cleaned texts (parallel output)
    writer_outputs: Annotated[list[dict], operator.add]
    reader_outputs: Annotated[list[dict], operator.add]

    # Step 4: References (HitL 1)
    references: dict              # {"concepts": [], "quotes": [], "topics": []}
    reference_decision: Optional[Literal["approve", "revise", "cancel"]]

    # Step 5: Research (HitL 2)
    research_snippets: list[str]
    research_decision: Optional[Literal["approve", "revise", "cancel"]]

    # Step 6: Creative (HitL 3)
    storylines: list[str]
    chosen_storyline_index: Optional[int]
    blog_json_en: dict            # Structured blog JSON (English)
    blog_json_tr: dict            # Structured blog JSON (Turkish)

    # Step 7: Visuals
    generated_images: list[dict]

    # Step 8: GitOps
    commit_url: str
    status: str                 # "in_progress", "completed", "cancelled", "error"
    error: str
