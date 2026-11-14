from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse("/sessions")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
