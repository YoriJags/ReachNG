"""
OPay/PalmPay/Moniepoint Float Optimizer API.

Routes:
  GET  /float-optimizer/dashboard   — KPIs + agent list + recommendations
  POST /float-optimizer/agents      — add / update an agent record
"""
from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timezone
from database.mongo import get_db
from services.float_optimizer.engine import calculate_recommendation
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/float-optimizer", tags=["float_optimizer"])

COLLECTION = "float_agents"


def _col():
    return get_db()[COLLECTION]


class AgentRecord(BaseModel):
    aggregator: str = ""
    agent_name: str
    platform: str                      # OPay | PalmPay | Moniepoint | etc.
    phone: str = ""
    current_float_ngn: float = 0
    avg_daily_volume_ngn: float = 0
    peak_days: str = ""                # e.g. "Friday, Saturday"


@router.get("/dashboard")
def fo_dashboard():
    agents = list(_col().find().sort("agent_name", 1))
    total_float = 0
    shortfalls  = 0
    total_util  = 0.0
    enriched    = []
    recommendations = []

    for a in agents:
        a["_id"] = str(a["_id"])
        rec = calculate_recommendation(a)
        a["current_float"]      = rec["current_float_ngn"]
        a["recommended_float"]  = rec["recommended_float_ngn"]
        a["utilization_pct"]    = rec["utilization_pct"]
        a["risk"]               = rec["risk"]
        total_float += rec["current_float_ngn"]
        total_util  += rec["utilization_pct"]
        if rec["risk"] == "high":
            shortfalls += 1
        if rec["risk"] in ("high", "medium"):
            recommendations.append({
                "agent_name": a["agent_name"],
                "action":     rec["action"],
                "reason":     f"Utilization: {rec['utilization_pct']}% (peak: {rec['peak_utilization_pct']}%)",
            })
        enriched.append(a)

    count = len(agents)
    return {
        "total_agents":       count,
        "total_float_ngn":    total_float,
        "shortfalls_today":   shortfalls,
        "avg_utilization_pct": round(total_util / count, 1) if count else 0,
        "agents":             enriched,
        "recommendations":    recommendations,
    }


@router.post("/agents", status_code=201)
def fo_add_agent(req: AgentRecord):
    doc = {**req.model_dump(), "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)}
    rec = calculate_recommendation(doc)
    doc["recommendation_snapshot"] = rec
    _col().update_one(
        {"agent_name": req.agent_name, "aggregator": req.aggregator},
        {"$set": doc},
        upsert=True,
    )
    return {**rec, "agent_name": req.agent_name}
