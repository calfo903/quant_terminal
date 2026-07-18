import logging



from fastapi import APIRouter



from app.services.ai_engine.market_sessions import get_sessions



logger = logging.getLogger(__name__)



router = APIRouter()





@router.get("")

async def sessions():

    """Current active forex market session(s) in UTC (Sydney/Tokyo/London/NY)."""

    return get_sessions()
