import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


@router.get("/{asset_path:path}")
async def read_asset(asset_path: str) -> FileResponse:
    root = Path(os.getenv("ASSET_ROOT", "assets")).resolve()
    candidate = (root / asset_path).resolve()
    if root not in candidate.parents or not candidate.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(candidate)
