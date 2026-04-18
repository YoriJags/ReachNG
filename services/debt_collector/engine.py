"""
Informal Debt Collector — escalating B2B debt recovery via WhatsApp.

60-day escalation sequence:
  Day 1   → polite reminder (Stage 1)
  Day 7   → firm follow-up (Stage 2)
  Day 14  → serious tone, reference outstanding amount (Stage 3)
  Day 21  → escalation warning, mention legal route (Stage 4)
  Day 30  → final notice, demand letter drafted (Stage 5)
  Day 60+ → legal demand letter output for filing

Claude writes each message in context of:
  - debtor name + business
  - original amount + days overdue
  - prior contact history
  - business relationship (client/supplier/contractor)
"""
import anthropic
from config import get_settings
import structlog

log = structlog.get_logger()

ESCALATION_STAGES = [
    {"day": 1,  "stage": "reminder",    "tone": "friendly",   "label": "Friendly Reminder"},
    {"day": 7,  "stage": "follow_up",   "tone": "firm",       "label": "Firm Follow-Up"},
    {"day": 14, "stage": "serious",     "tone": "serious",    "label": "Serious Notice"},
    {"day": 21, "stage": "warning",     "tone": "warning",    "label": "Escalation Warning"},
    {"day": 30, "stage": "final",       "tone": "final",      "label": "Final Notice"},
    {"day": 60, "stage": "legal",       "tone": "legal",      "label": "Legal Demand"},
]

_SYSTEM = """You are a Nigerian business debt recovery specialist writing WhatsApp messages \
on behalf of a creditor business to recover unpaid debts from debtors.

Nigerian business debt recovery context:
- Most B2B debt in Nigeria is informal — no court judgment, just a business relationship gone sour
- WhatsApp is the primary channel for business communication
- Tone escalates gradually — starting friendly, becoming firm, then legal
- Nigerian debtors respond to: relationship (mutual respect), urgency (time pressure), and social proof (others paid)
- Avoid anything that sounds like a threat of violence — focus on legal process and reputational consequence
- Stage 5 (final notice): always mention that records will be shared with credit bureaus and business associations
- Stage 6 (legal demand): output a formal demand letter, not a WhatsApp message

Rules:
1. Always address the debtor by name — never "Dear Sir/Madam"
2. State the exact amount and original due date every time
3. Never be rude or threatening — be firm and professional
4. WhatsApp messages: max 5 sentences
5. Legal demand letter: formal format with date, reference, and clear 7-day ultimatum"""


def get_stage_for_days_overdue(days_overdue: int) -> dict:
    """Return the correct escalation stage based on days overdue."""
    applicable = [s for s in ESCALATION_STAGES if s["day"] <= days_overdue]
    return applicable[-1] if applicable else ESCALATION_STAGES[0]


def generate_recovery_message(
    creditor_name: str,
    debtor_name: str,
    debtor_business: str,
    amount_ngn: float,
    description: str,
    original_due_date: str,
    days_overdue: int,
    relationship_context: str = "",
    prior_responses: str = "",
) -> dict:
    """
    Generate a debt recovery message at the correct escalation stage.
    Returns: {stage, tone, message, is_legal_letter}
    """
    stage = get_stage_for_days_overdue(days_overdue)
    is_legal = stage["stage"] == "legal"

    if is_legal:
        prompt = f"""Draft a formal legal demand letter for:

CREDITOR: {creditor_name}
DEBTOR: {debtor_name} ({debtor_business})
AMOUNT OWED: ₦{amount_ngn:,.0f}
FOR: {description}
ORIGINAL DUE DATE: {original_due_date}
DAYS OVERDUE: {days_overdue}
PRIOR COMMUNICATION: {prior_responses or 'Multiple WhatsApp messages sent over 60 days with no payment'}

Format: Nigerian formal business letter. Include today as DATE, a REFERENCE NUMBER (DC-{days_overdue}-REF), \
creditor details, debt details, and a 7-day ultimatum before legal proceedings. \
State that non-payment will result in: (1) filing at the Magistrate Court, \
(2) reporting to CAC-registered credit bureaus, (3) notification to the debtor's industry association."""
    else:
        prompt = f"""Write a WhatsApp debt recovery message. Stage: {stage['label']} ({stage['tone']} tone).

CREDITOR (sender): {creditor_name}
DEBTOR (recipient): {debtor_name} at {debtor_business}
AMOUNT OWED: ₦{amount_ngn:,.0f}
FOR: {description}
ORIGINAL DUE DATE: {original_due_date}
DAYS OVERDUE: {days_overdue}
BUSINESS RELATIONSHIP: {relationship_context or 'Business transaction'}
PRIOR RESPONSES: {prior_responses or 'No response to previous messages'}

Write the WhatsApp message only. No explanation. Max 5 sentences.
{
"For Stage 3+ (serious/warning/final): mention that non-payment will escalate to formal legal demand and credit bureau reporting." if stage["day"] >= 14 else ""
}"""

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    message = response.content[0].text.strip()
    log.info("debt_recovery_message_generated",
             debtor=debtor_name, days_overdue=days_overdue, stage=stage["stage"])

    return {
        "stage":          stage["stage"],
        "stage_label":    stage["label"],
        "tone":           stage["tone"],
        "days_overdue":   days_overdue,
        "amount_ngn":     amount_ngn,
        "message":        message,
        "is_legal_letter": is_legal,
    }
