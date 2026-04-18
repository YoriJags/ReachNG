"""
Fleet Dispatcher Engine — Claude analyses breakdown messages and generates
approval drafts. The "10 seconds" demo that closes fleet deals.
"""
import json
import anthropic
from config import get_settings
import structlog

log = structlog.get_logger()


def analyse_breakdown(
    raw_message: str,
    truck_plate: str,
    driver_name: str,
    location: str,
    amount_requested_ngn: int,
    incident_history: list[dict],
) -> dict:
    """
    Claude reads a driver's breakdown message and returns a structured assessment.

    Returns:
        issue_summary: one-line description of the problem
        legitimacy: "high" | "medium" | "low" (how credible the request is)
        legitimacy_reason: brief explanation
        recommended_amount_ngn: what to approve (may differ from requested)
        recommended_action: "approve" | "partial_approve" | "call_driver" | "reject"
        eta_impact: estimated delay in hours
        draft_approval_message: WhatsApp text to send to driver if approved
        draft_eta_update: WhatsApp text to send to client about delay
        flags: list of any red flags
    """
    history_text = ""
    if incident_history:
        lines = []
        for h in incident_history[-3:]:  # last 3 incidents
            lines.append(
                f"- {h.get('date','')[:10]}: {h.get('issue','')} "
                f"(₦{h.get('amount_approved',0):,} approved, resolved={h.get('resolved',False)})"
            )
        history_text = "Recent incident history:\n" + "\n".join(lines)
    else:
        history_text = "No prior incident history for this truck."

    prompt = f"""You are a Nigerian logistics operations manager reviewing a driver's breakdown report.

Driver message:
"{raw_message}"

Truck: {truck_plate} | Driver: {driver_name} | Location: {location}
Amount requested: ₦{amount_requested_ngn:,}
{history_text}

Assess this breakdown request. Consider:
- Is the amount reasonable for this type of breakdown in Lagos/Nigeria (2026 prices)?
- Does the incident history show any patterns (frequent breakdowns = maintenance issue)?
- Is the location plausible for this route?

Return ONLY valid JSON:
{{
  "issue_summary": "one-line: what broke and where",
  "legitimacy": "high|medium|low",
  "legitimacy_reason": "brief explanation",
  "recommended_amount_ngn": <integer>,
  "recommended_action": "approve|partial_approve|call_driver|reject",
  "eta_impact_hours": <integer>,
  "draft_approval_message": "WhatsApp to driver if approved — confirm, amount, next steps. Nigerian English. Max 3 sentences.",
  "draft_eta_update": "WhatsApp to client about delivery delay. Professional. Max 2 sentences.",
  "flags": []
}}"""

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    try:
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        log.info(
            "breakdown_analysed",
            truck=truck_plate,
            action=result.get("recommended_action"),
            legitimacy=result.get("legitimacy"),
            amount_requested=amount_requested_ngn,
            amount_recommended=result.get("recommended_amount_ngn"),
        )
        return result
    except Exception as e:
        log.warning("breakdown_parse_failed", error=str(e), raw=raw[:200])
        return {
            "issue_summary": raw_message[:80],
            "legitimacy": "medium",
            "legitimacy_reason": "Could not parse automated assessment — review manually.",
            "recommended_amount_ngn": amount_requested_ngn,
            "recommended_action": "call_driver",
            "eta_impact_hours": 3,
            "draft_approval_message": f"Noted {driver_name}. We're looking into this now. Stand by.",
            "draft_eta_update": "There is a slight delay on this delivery. We will update you shortly.",
            "flags": ["assessment_failed"],
        }
