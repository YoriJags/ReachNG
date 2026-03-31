from fastapi import APIRouter, BackgroundTasks
from tools.competitor import discover_competitors, list_competitors, get_competitor_count

router = APIRouter(prefix="/competitors", tags=["Competitors"])


@router.post("/discover")
async def run_discovery(background_tasks: BackgroundTasks, max_results: int = 30):
    """Trigger competitor discovery in the background."""
    background_tasks.add_task(discover_competitors, max_results)
    return {"status": "started", "message": f"Discovering up to {max_results} competitors"}


@router.get("/")
async def get_competitors():
    return {
        "count": get_competitor_count(),
        "competitors": list_competitors(),
    }
