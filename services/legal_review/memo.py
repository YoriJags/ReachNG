"""
Review memo generator — takes extracted clauses and produces a formatted memo
grounded in Nigerian commercial law practice.
"""
import anthropic
from config import get_settings
import structlog

log = structlog.get_logger()

_MEMO_SYSTEM = """You are a senior Nigerian commercial lawyer writing a review memo for a \
partner or senior associate at a Lagos law firm.

Your memos are precise, well-structured, and immediately actionable.
You write in clear professional English — no legalese unless quoting the contract directly.
You apply Nigerian law exclusively: CAMA 2020, Labour Act, Land Use Act, Stamp Duties Act, \
CBN regulations, NDPR/NDPA, Arbitration and Conciliation Act, and Nigerian court precedent.

When flagging issues you always:
- Cite the specific Nigerian law or regulation that applies
- State the practical consequence for the client
- Give a specific recommended action (not "seek legal advice" — that's lazy)

Partners trust your memos to make decisions without reading the raw contract."""

RISK_EMOJI = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🚨"}


def generate_memo(
    filename: str,
    clauses: dict,
    firm_name: str = "",
) -> str:
    """
    Generate a Nigerian-law-grounded review memo from extracted clauses.
    Returns the memo as a formatted string (markdown).
    """
    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)

    overall_risk     = clauses.get("overall_risk", "unknown")
    overall_summary  = clauses.get("overall_summary", "")
    red_flags        = clauses.get("red_flags", [])
    nigerian_issues  = clauses.get("nigerian_law_issues", [])
    stamp_duty       = clauses.get("stamp_duty_required", False)
    contract_type    = clauses.get("contract_type_label", "Commercial Agreement")

    # Build clause summary — works with any clause set (type-specific or general)
    skip_keys = {
        "overall_risk", "overall_summary", "red_flags", "nigerian_law_issues",
        "stamp_duty_required", "contract_type", "contract_type_label",
        "parse_error", "raw",
    }
    clause_lines = []
    for cat, c in clauses.items():
        if cat in skip_keys or not isinstance(c, dict):
            continue
        label   = cat.replace("_", " ").title()
        risk    = c.get("risk_level", "low")
        emoji   = RISK_EMOJI.get(risk, "⚪")
        summary = c.get("summary", "Not found")
        quote   = c.get("exact_quote", "")
        note    = c.get("risk_note", "")
        line = f"**{label}** {emoji} ({risk.upper()})\n{summary}"
        if quote:
            line += f'\n> "{quote}"'
        if note:
            line += f"\n⚠️ {note}"
        clause_lines.append(line)

    red_flag_text = ""
    if red_flags:
        red_flag_text = "\n\n**RED FLAGS:**\n" + "\n".join(f"• {f}" for f in red_flags)

    nigerian_issues_text = ""
    if nigerian_issues:
        nigerian_issues_text = "\n\n**NIGERIAN LAW ISSUES:**\n" + "\n".join(f"• {i}" for i in nigerian_issues)

    stamp_duty_text = "\n\n**STAMP DUTY:** This agreement requires stamping under the Stamp Duties Act." if stamp_duty else ""

    prompt = f"""Write a professional contract review memo for {firm_name or "the firm"}.

Document: {filename}
Contract Type: {contract_type}
Overall Risk: {overall_risk.upper()} {RISK_EMOJI.get(overall_risk, "")}
Summary: {overall_summary}

Extracted clauses:
{"---".join(clause_lines)}
{red_flag_text}
{nigerian_issues_text}
{stamp_duty_text}

Write the memo in this exact structure:

# CONTRACT REVIEW MEMO
**Document:** [filename]
**Contract Type:** [contract type]
**Prepared by:** Digital Associates AI
**Governing Law:** [as specified in contract, or "Nigerian law — Lagos State jurisdiction"]
**Risk Rating:** [overall risk with emoji]
{"**Stamp Duty:** Required — flag for stamping before execution" if stamp_duty else ""}

## Executive Summary
[2-3 sentences: what this contract is, who bears the most risk, the key Nigerian law \
considerations a partner needs to know immediately]

## Key Terms
[Bullet points: parties, term, payment/consideration, key obligations — the essentials a \
partner checks first. Flag anything unusual for Nigerian market practice.]

## Clause Analysis
[For each clause found: one concise paragraph in plain English. Always cite the applicable \
Nigerian law. Flag if a clause departs from Nigerian market standard or creates regulatory risk.]

## Nigerian Law Issues
[Specific issues under Nigerian law only — foreign law contamination, missing CAMA formalities, \
CBN/FIRS/NDPR compliance gaps. Be specific and cite the statute.]

## Red Flags
[Numbered list — most important concerns first. Be specific: cite the clause, state the risk, \
state the consequence under Nigerian law.]

## Recommended Actions
[4-6 numbered action items. Each must be specific and actionable — not "seek advice", but \
"Insert CBN approval language in Clause 5.2 before execution" or "Amend arbitration seat \
from London to Lagos in Clause 14.1 — London seat creates enforcement risk under the \
Arbitration and Conciliation Act".]

---
*This memo was generated by Digital Associates AI and reviewed against Nigerian commercial law \
standards. It should be reviewed by a qualified Nigerian legal practitioner before reliance. \
Digital Associates AI accepts no liability for errors or omissions.*

Keep it tight — this memo should save the associate 2 hours, not add to their reading pile."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        system=_MEMO_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    memo = response.content[0].text.strip()
    log.info("memo_generated",
             filename=filename,
             firm=firm_name,
             contract_type=contract_type,
             overall_risk=overall_risk)
    return memo
