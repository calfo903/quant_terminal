import logging

from fastapi import APIRouter, Query, Depends

from typing import Optional



from app.services.mlops.news import news_service

from app.core.ratelimit import limit_news



logger = logging.getLogger(__name__)



router = APIRouter()





@router.get("")

async def latest_news(

    limit: int = Query(20, ge=1, le=100),

    category: Optional[str] = Query(None, description="crypto|forex|commodity|macro"),

    _: None = Depends(limit_news),

):

    """Latest important financial news, FinBERT-scored and ranked by importance.



    Degrades to a curated offline set when no live feed is configured/reachable.

    """

    return await news_service.get_latest(limit=limit, category=category)
