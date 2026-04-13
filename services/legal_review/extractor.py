"""
Legal clause extractor — reads a contract PDF and pulls out every clause that matters.
Built on top of Data Liberation's PDF ingestion. Claude does the legal reasoning.
"""
import io
import anthropic
import json as _json
from config import get_settings
import structlog

log = structlog.get_logger()

_CLAUSE_SYSTEM = """You are a senior Nigerian commercial lawyer with 20 years of experience at top Lagos law firms.
You read contracts and extract every clause that matters to the client — precisely, without embellishment.
You flag risk language immediately. You are direct and specific. You cite exact clause numbers and page references where visible."""

CLAUSE_CATEGORIES = [
    "parties",
    "effective_date_and_term",
    "payment_terms",
    "termination",
    "liability_and_indemnity",
    "intellectual_property",
    "confidentiality",
    "governing_law_and_jurisdiction",
    "dispute_resolution",
    "force_majeure",
    "representations_and_warranties",
    "red_flags",
]


def _extract_pdf_text(content: bytes) -> str:
    """Extract full text from PDF bytes."""
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    text_parts.append(f"[Page {page_num}]\n{text}")
        return "\n\n".join(text_parts)
    except ImportError:
        return content.decode("latin-1", errors="replace")


def extract_clauses(contract_text: str, filename: str) -> dict:
    """
    Pass contract text to Claude Sonnet — returns structured clause extraction.
    Returns dict with each clause category as a key.
    """
    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)

    # Truncate to ~80k chars to stay within context — most contracts are under this
    truncated = contract_text[:80_000]
    was_truncated = len(contract_text) > 80_000

    prompt = f"""Analyse this contract and extract the following clause categories.
For each category, provide:
- "found": true/false (whether the clause exists)
- "summary": 1-3 sentence plain English summary of what the clause says
- "exact_quote": the most important verbatim sentence or phrase from the clause (or null if not found)
- "page_ref": page number if visible (or null)
- "risk_level": "low" | "medium" | "high" | "critical" (how risky is this clause for the signing party)
- "risk_note": specific concern if risk_level is medium/high/critical (or null)

Categories to extract:
{_json.dumps(CLAUSE_CATEGORIES, indent=2)}

Also include:
- "red_flags": list of any unusual, one-sided, or dangerous clauses not captured above
- "overall_risk": "low" | "medium" | "high" | "critical"
- "overall_summary": 2-3 sentence plain English summary of what this contract is and its main implications

CONTRACT ({filename}){" [NOTE: document was truncated at 80,000 characters]" if was_truncated else ""}:
---
{truncated}
---

Return ONLY valid JSON. No preamble. No markdown fences."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
        system=_CLAUSE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        clauses = _json.loads(raw.strip())
    except Exception as e:
        log.warning("clause_parse_failed", filename=filename, error=str(e))
        clauses = {"parse_error": True, "raw": raw[:500]}

    log.info("clauses_extracted", filename=filename, was_truncated=was_truncated)
    return clauses
