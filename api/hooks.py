"""
Hook Generator API — Content Intelligence service line.
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from tools.hooks import generate_hooks_with_research, get_hook_library, research_trending_hooks

router = APIRouter(prefix="/hooks", tags=["Hooks"])


class HookRequest(BaseModel):
    vertical: str = Field(..., max_length=100)
    topic: str = Field(..., max_length=200)
    platform: str = Field(default="instagram", max_length=50)
    count: int = Field(default=8, ge=1, le=20)
    competitor_handles: list[str] = Field(default=[], max_length=20)
    client_brief: str | None = Field(default=None, max_length=2000)
    client_name: str = Field(default="default", max_length=100)


@router.post("/generate")
async def generate(req: HookRequest):
    """
    Research trending hooks in the vertical, then generate count viral hooks for the topic.
    Pulls real trending examples from Instagram as style reference first.
    """
    result = await generate_hooks_with_research(
        vertical=req.vertical,
        topic=req.topic,
        platform=req.platform,
        count=req.count,
        competitor_handles=req.competitor_handles or None,
        client_brief=req.client_brief,
        client_name=req.client_name,
    )
    return result


@router.get("/library")
async def hook_library(client_name: str | None = None, vertical: str | None = None, limit: int = 20):
    """Retrieve previously generated hooks from the library."""
    return get_hook_library(client_name=client_name, vertical=vertical, limit=limit)


@router.get("/trending/{vertical}")
async def trending_hooks(vertical: str):
    """What hooks are already performing in this vertical on Instagram right now."""
    examples = await research_trending_hooks(vertical, max_posts=30)
    return {"vertical": vertical, "trending_hooks": examples, "count": len(examples)}
