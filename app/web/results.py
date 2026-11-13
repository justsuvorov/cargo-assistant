from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.auth.identity import Identity
from app.jobs.checking import Folder, Postponed
from app.jobs.models import CheckResult, Correction, Declaration
from app.web.security import identity, services

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
_STATUSES = {"match": "совпадает", "mismatch": "не совпадает", "review": "требует проверки"}
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def seen(request: Request, who: Identity, declaration_id: int) -> Declaration:
    async with services(request).database.session() as session:
        found = await session.get(Declaration, declaration_id)
    if found is None or not who.sees(found.access_group):
        raise HTTPException(status_code=404, detail=f"Декларация {declaration_id} не найдена")
    return found


@router.get("/declarations/{declaration_id}", response_class=HTMLResponse)
async def result(
    declaration_id: int,
    request: Request,
    who: Annotated[Identity, Depends(identity)],
    status: str = "",
) -> HTMLResponse:
    declaration = await seen(request, who, declaration_id)
    query = select(CheckResult).where(CheckResult.declaration_id == declaration_id)
    async with services(request).database.session() as session:
        found = list((await session.scalars(query.order_by(CheckResult.id))).all())
        corrections = {
            (each.line, each.field): each
            for each in await session.scalars(
                select(Correction).where(Correction.declaration_id == declaration_id)
            )
        }
    cards = Folder(services(request).settings.cards()).reconciliation(Postponed())
    titles = (
        {
            card.field(): (card.title(declaration.form), card.subject())
            for card in cards.cards(declaration.form)
        }
        if found
        else {}
    )
    counts = {key: sum(1 for each in found if each.status == key) for key in _STATUSES}
    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "declaration": declaration,
            "status": status if status in _STATUSES else "",
            "statuses": _STATUSES,
            "counts": counts,
            "titles": titles,
            "corrections": corrections,
            "rows": [each for each in found if status not in _STATUSES or each.status == status],
        },
    )


@router.get("/declarations/{declaration_id}/file")
async def download(
    declaration_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> Response:
    declaration = await seen(request, who, declaration_id)
    if not declaration.result_key:
        raise HTTPException(status_code=404, detail="Файл результата ещё не готов")
    name = declaration.result_key.rsplit("/", 1)[-1]
    return Response(
        services(request).storage.read(declaration.result_key),
        media_type=_XLSX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )
