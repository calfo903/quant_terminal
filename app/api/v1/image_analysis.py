from fastapi import APIRouter, UploadFile, File, HTTPException, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

from app.services.image_analysis.analyzer import chart_analyzer

from app.services.learning.tracker import HistoryTracker

from app.core.config import settings

from app.core.ratelimit import limit_analyze

import logging



logger = logging.getLogger(__name__)

router = APIRouter()



ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}





def _allowed_image_bytes(data: bytes) -> bool:

    """Validate the actual file content via magic bytes.

    `content_type` is client-supplied and trivially spoofable, so we check

    the real bytes (PNG / JPEG / WEBP) before handing them to the CV pipeline.

    """

    if len(data) < 4:

        return False

    if data[:4] == b"\x89PNG":  # PNG

        return True

    if data[:3] == b"\xff\xd8\xff":  # JPEG

        return True

    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":  # WEBP

        return True

    return False





@router.post("/analyze", dependencies=[Depends(limit_analyze)])

async def analyze_image(file: UploadFile = File(...), session: AsyncSession = Depends(get_db)):

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024



    # Reject oversized uploads BEFORE streaming the bytes into memory.

    size = getattr(file, "size", None)

    if size is None:

        cl = file.headers.get("content-length")

        size = int(cl) if (cl and cl.isdigit()) else None

    if size is not None and size > max_bytes:

        raise HTTPException(413, f"File too large (max {settings.MAX_UPLOAD_SIZE_MB}MB)")



    if file.content_type not in ALLOWED_TYPES:

        raise HTTPException(400, f"Unsupported type: {file.content_type}")



    contents = await file.read()



    # Defense-in-depth: the client can lie about Content-Length / content-type.

    if len(contents) > max_bytes:

        raise HTTPException(413, f"File too large (max {settings.MAX_UPLOAD_SIZE_MB}MB)")

    if not _allowed_image_bytes(contents):

        raise HTTPException(400, "File content is not a supported image (PNG/JPEG/WEBP)")



    try:

        result = await chart_analyzer.analyze(contents)



        await HistoryTracker.log_image_analysis(

            session=session,

            image_bytes=contents,

            analysis_result=result,

            model_version="v3.2"

        )



        return result

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Image analysis failed: {e}", exc_info=True)

        raise HTTPException(500, f"Analysis failed: {str(e)}")
