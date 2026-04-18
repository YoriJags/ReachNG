"""
Staff Moonlighting Detector — identifies employees running parallel jobs
on company time through attendance and output pattern analysis.
"""
import anthropic
from config import get_settings
import structlog

log = structlog.get_logger()

_SYSTEM = """You are an HR intelligence analyst specialising in Nigerian workplace patterns.

You analyse attendance logs and work output data to detect signs that an employee \
may be working a second job during their primary employer's hours.

Nigerian-specific moonlighting patterns to look for:
1. SYSTEMATIC LATE ARRIVALS: Consistently arriving 30-60 mins late, especially Mon/Fri
2. EARLY EXITS: Leaving 30-60 mins early on specific days each week
3. LONG LUNCH BREAKS: 90+ minute lunch breaks when role doesn't require client meetings
4. OUTPUT INCONSISTENCY: High output some days, near-zero on others (split attention)
5. FRIDAY AFTERNOONS: Disproportionate absence/distraction on Friday afternoons
6. REMOTE WORK EXPLOITATION: Work-from-home days with minimal logged activity
7. PHONE USAGE PATTERNS: Constant personal calls during work hours (not verifiable from log, but note if reported)
8. SUDDEN FINANCIAL INDEPENDENCE: Not a log signal, but note if reported by manager
9. COMPETING PRIORITIES: Deadlines consistently missed despite manageable workload
10. AVAILABILITY: Unreachable on WhatsApp during work hours but active on Instagram

Return ONLY valid JSON with the schema in the user prompt."""


def analyse_attendance(
    company: str,
    staff_name: str,
    role: str,
    attendance_log: str,
) -> dict:
    """
    Analyse attendance and output patterns for moonlighting signals.
    Returns risk assessment with specific signals identified.
    """
    prompt = f"""Analyse this staff member's attendance and output log for moonlighting signals.

EMPLOYEE: {staff_name}
ROLE: {role}
COMPANY: {company}

ATTENDANCE LOG:
{attendance_log}

Identify patterns. Consider what is normal for this role type in Lagos.
A developer working from home may have different patterns than a sales rep.

Return JSON with this exact structure:
{{
  "risk_level": "high" | "medium" | "low",
  "confidence": "high" | "medium" | "low",
  "signals": [<list of specific patterns observed — quote from the log>],
  "analysis": "<3-4 sentence interpretation of the patterns>",
  "recommended_actions": [<list of HR actions — observation, conversation, PIP, etc.>],
  "innocent_explanations": [<list of alternative explanations for the patterns>],
  "flag_for_review": <true | false>
}}

Return ONLY valid JSON."""

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw.strip())

    log.info("moonlighting_analysed",
             staff=staff_name, company=company,
             risk=result.get("risk_level"), flag=result.get("flag_for_review"))
    return result
