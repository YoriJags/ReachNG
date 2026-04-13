"""
Legal clause extractor — reads a contract PDF and pulls out every clause that matters.
Nigerian law grounded. Contract-type aware. Claude does the legal reasoning.
"""
import io
import anthropic
import json as _json
from config import get_settings
import structlog

log = structlog.get_logger()

# ── Nigerian Law System Prompt ────────────────────────────────────────────────

_CLAUSE_SYSTEM = """You are a senior Nigerian commercial lawyer with 20 years of experience \
at top Lagos law firms including Banwo & Ighodalo, AELEX, and Templars.

You apply Nigerian law exclusively and flag any foreign law contamination.

APPLICABLE LEGAL FRAMEWORK — always analyse against these:
• Contract law: Common law principles as received and applied by Nigerian courts
• Companies and Allied Matters Act (CAMA) 2020 — company execution, share transfers, director duties, company formalities
• Stamp Duties Act — flag whether agreement requires stamp duty and at what rate
• CBN regulations — any FX payment obligation must reference CBN approval; flag unhedged FX exposure
• Labour Act Cap L1 LFN 2004 — for employment/service contracts: notice periods, leave entitlements, termination rights
• Land Use Act Cap L5 LFN 2004 — for leases and property transactions: governor's consent, right of occupancy
• Nigerian Data Protection Regulation (NDPR) 2019 / NDPA 2023 — for any data processing or confidentiality obligations
• Arbitration and Conciliation Act Cap A18 LFN 2004 — flag whether arbitration clause is enforceable in Nigeria; \
note if Lagos Court of Arbitration (LCA), ICC, or LCIA is specified
• Copyright Act Cap C28 LFN 2004 and Patents and Designs Act — for IP clauses
• FIRS tax obligations — withholding tax, VAT on services, thin capitalisation for loan agreements

ALWAYS FLAG:
• English law references ("Companies Act 2006", "English courts", "Laws of England") — these need localisation
• Foreign governing law without commercial justification
• FX payment obligations without CBN approval language
• Missing stamp duty provisions
• Execution clauses that don't comply with CAMA 2020 company execution requirements
• Arbitration seats outside Nigeria without justification
• Non-compete clauses that likely exceed Nigerian courts' reasonableness threshold
• Liquidated damages clauses that may constitute unenforceable penalties under Nigerian law
• Indemnity clauses that attempt to exclude liability for fraud or gross negligence (void under Nigerian law)

You are direct, specific, and cite exact clause numbers and page references where visible.
You never embellish. You flag risk language immediately."""


# ── Contract Type Detection ───────────────────────────────────────────────────

CONTRACT_TYPES = {
    "employment": {
        "label": "Employment / Service Agreement",
        "clauses": [
            "parties", "effective_date_and_term", "remuneration_and_benefits",
            "duties_and_responsibilities", "termination", "post_termination_restrictions",
            "confidentiality", "intellectual_property", "governing_law_and_jurisdiction",
            "dispute_resolution", "data_protection",
        ],
        "red_flag_focus": "Labour Act compliance, non-compete enforceability, wrongful dismissal exposure, PAYE/pension obligations",
    },
    "commercial_lease": {
        "label": "Commercial Lease / Tenancy Agreement",
        "clauses": [
            "parties", "property_description", "lease_term_and_rent",
            "rent_review", "service_charges", "repair_and_maintenance",
            "use_and_alterations", "assignment_and_subletting", "termination_and_forfeiture",
            "governor_consent", "governing_law_and_jurisdiction", "dispute_resolution",
        ],
        "red_flag_focus": "Land Use Act compliance, governor's consent, rent review mechanism, dilapidations liability, forfeiture without notice",
    },
    "shareholders_agreement": {
        "label": "Shareholders Agreement",
        "clauses": [
            "parties", "share_structure_and_capital", "management_and_board",
            "reserved_matters", "pre_emption_rights", "drag_along_tag_along",
            "dividend_policy", "deadlock_resolution", "exit_provisions",
            "confidentiality", "governing_law_and_jurisdiction", "dispute_resolution",
        ],
        "red_flag_focus": "CAMA 2020 compliance, pre-emption rights, drag-along enforceability, deadlock mechanism, SEC regulations for share transfers",
    },
    "loan_agreement": {
        "label": "Loan / Facility Agreement",
        "clauses": [
            "parties", "facility_amount_and_purpose", "interest_rate_and_fees",
            "repayment_schedule", "security_and_collateral", "representations_and_warranties",
            "covenants", "events_of_default", "governing_law_and_jurisdiction",
            "dispute_resolution", "tax_gross_up",
        ],
        "red_flag_focus": "CBN money lending regulations, usury concerns, thin capitalisation, withholding tax on interest, collateral perfection under Nigerian law",
    },
    "service_agreement": {
        "label": "Service / Consultancy Agreement",
        "clauses": [
            "parties", "effective_date_and_term", "scope_of_services",
            "payment_terms", "intellectual_property", "confidentiality",
            "liability_and_indemnity", "termination", "governing_law_and_jurisdiction",
            "dispute_resolution", "data_protection",
        ],
        "red_flag_focus": "IP ownership (work-for-hire vs assignment), uncapped liability, termination for convenience without compensation, VAT treatment",
    },
    "nda": {
        "label": "Non-Disclosure Agreement",
        "clauses": [
            "parties", "definition_of_confidential_information", "obligations_of_confidentiality",
            "permitted_disclosures", "exclusions", "term_and_survival",
            "remedies", "governing_law_and_jurisdiction",
        ],
        "red_flag_focus": "Overly broad definition of confidential information, unlimited survival period, injunctive relief clause enforceability in Nigeria",
    },
    "sale_of_goods": {
        "label": "Sale of Goods / Supply Agreement",
        "clauses": [
            "parties", "goods_description", "price_and_payment",
            "delivery_and_risk", "title_and_retention", "warranties_and_quality",
            "liability_and_indemnity", "termination", "force_majeure",
            "governing_law_and_jurisdiction", "dispute_resolution",
        ],
        "red_flag_focus": "Sale of Goods Act compliance, risk transfer, retention of title enforceability, import/export duty obligations",
    },
    "joint_venture": {
        "label": "Joint Venture Agreement",
        "clauses": [
            "parties", "purpose_and_scope", "contributions_and_funding",
            "management_structure", "profit_sharing", "intellectual_property",
            "confidentiality", "exit_and_dissolution", "governing_law_and_jurisdiction",
            "dispute_resolution",
        ],
        "red_flag_focus": "CAMA 2020 JV requirements, SEC regulations, repatriation of profits (CBN), contribution obligations, dissolution mechanics",
    },
    "general": {
        "label": "Commercial Agreement",
        "clauses": [
            "parties", "effective_date_and_term", "payment_terms", "termination",
            "liability_and_indemnity", "intellectual_property", "confidentiality",
            "governing_law_and_jurisdiction", "dispute_resolution", "force_majeure",
            "representations_and_warranties",
        ],
        "red_flag_focus": "Unusual risk allocation, missing standard protections, foreign law contamination",
    },
}


def detect_contract_type(contract_text: str, filename: str) -> str:
    """
    Quick first-pass Claude call to classify contract type.
    Uses a cheap, fast call — max 200 tokens.
    """
    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)

    sample = contract_text[:8_000]  # First 8k chars is enough to classify

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Cheap + fast for classification
            max_tokens=50,
            messages=[{
                "role": "user",
                "content": f"""Classify this Nigerian contract into exactly one of these types:
employment, commercial_lease, shareholders_agreement, loan_agreement, service_agreement, nda, sale_of_goods, joint_venture, general

Contract filename: {filename}
First section of contract:
---
{sample}
---

Reply with ONLY the type name. Nothing else."""
            }],
        )
        detected = response.content[0].text.strip().lower().replace(" ", "_")
        if detected in CONTRACT_TYPES:
            log.info("contract_type_detected", filename=filename, type=detected)
            return detected
    except Exception as e:
        log.warning("contract_type_detection_failed", filename=filename, error=str(e))

    return "general"


# ── PDF Extraction ────────────────────────────────────────────────────────────

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


# ── Main Extraction ───────────────────────────────────────────────────────────

def extract_clauses(contract_text: str, filename: str) -> dict:
    """
    Two-step extraction:
    1. Detect contract type (fast/cheap — Claude Haiku)
    2. Full clause extraction using type-specific categories (Claude Sonnet)

    Returns dict with each clause category as a key, plus contract_type.
    """
    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)

    # Step 1: Detect contract type
    contract_type = detect_contract_type(contract_text, filename)
    type_config = CONTRACT_TYPES[contract_type]

    # Truncate to ~80k chars — most Nigerian contracts are well under this
    truncated = contract_text[:80_000]
    was_truncated = len(contract_text) > 80_000

    # Step 2: Type-specific full extraction
    clause_list = type_config["clauses"]
    red_flag_focus = type_config["red_flag_focus"]

    prompt = f"""Analyse this {type_config['label']} under Nigerian law and extract the following clause categories.

For each category, provide:
- "found": true/false
- "summary": 1-3 sentence plain English summary of what the clause says (reference Nigerian law where relevant)
- "exact_quote": the most important verbatim sentence or phrase (or null)
- "page_ref": page number if visible (or null)
- "risk_level": "low" | "medium" | "high" | "critical"
- "risk_note": specific concern citing the applicable Nigerian law or regulation (or null)

Clause categories for this {type_config['label']}:
{_json.dumps(clause_list, indent=2)}

Also include:
- "red_flags": list of specific issues — prioritise: {red_flag_focus}
- "nigerian_law_issues": list of any foreign law contamination, missing local formalities, or Nigerian regulatory non-compliance
- "stamp_duty_required": true/false (whether this agreement requires stamping under the Stamp Duties Act)
- "overall_risk": "low" | "medium" | "high" | "critical"
- "overall_summary": 2-3 sentence plain English summary of what this contract is and its main implications under Nigerian law

CONTRACT TYPE: {type_config['label']}
DOCUMENT: {filename}{" [NOTE: document truncated at 80,000 characters]" if was_truncated else ""}
---
{truncated}
---

Return ONLY valid JSON. No preamble. No markdown fences."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
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

    clauses["contract_type"] = contract_type
    clauses["contract_type_label"] = type_config["label"]

    log.info("clauses_extracted",
             filename=filename,
             contract_type=contract_type,
             was_truncated=was_truncated)
    return clauses
