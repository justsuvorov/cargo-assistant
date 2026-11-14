from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from starlette.datastructures import FormData

from app.auth.identity import Identity
from app.jobs.errors import MissingProfileError, NotReadyError
from app.jobs.folios import Gaps
from app.jobs.models import Job, Policy
from app.jobs.queue import Snapshot
from app.policy.schema.profile import Profile, Wording
from app.web.security import identity, policy_of, services

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
_UNDEFINED = date.min.isoformat()


def changes(form: FormData, key: str, index: int) -> dict[str, str]:
    names = {field: f"{field}|{key}|{index}" for field in ("text", "point", "effective")}
    return {
        field: str(form[name]).strip()
        for field, name in names.items()
        if name in form and (field != "effective" or form[name])
    }


def merged(form: FormData, profile: Profile) -> Profile:
    return Profile.model_validate(
        {
            **profile.model_dump(),
            "number": str(form.get("number", "")).strip(),
            "insurer": str(form.get("insurer", "")).strip(),
            "issued": str(form.get("issued", "")).strip() or _UNDEFINED,
            "clauses": {
                key: tuple(
                    Wording.model_validate({**wording.model_dump(), **changes(form, key, index)})
                    for index, wording in enumerate(wordings)
                )
                for key, wordings in profile.clauses.items()
            },
        }
    )


async def context(
    request: Request, who: Identity, policy_id: int, notice: str
) -> dict[str, object]:
    policy = await policy_of(request, who, policy_id)
    shown: dict[str, object] = {
        "page": "policies",
        "policy": policy,
        "notice": notice,
        "job": None,
        "version": None,
        "undefined": _UNDEFINED,
    }
    if policy.job_id is not None:
        async with services(request).database.session() as session:
            job = await session.get(Job, policy.job_id)
        shown["job"] = Snapshot.of(job) if job is not None else None
    try:
        version = await services(request).folio.latest(policy_id)
    except MissingProfileError:
        return shown
    return {**shown, "version": version, "gaps": Gaps(version.profile).names()}


async def body(
    request: Request, who: Identity, policy_id: int, notice: str = "", status: int = 200
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "policy.html",
        await context(request, who, policy_id, notice),
        status_code=status,
    )


@router.get("/policies", response_class=HTMLResponse)
async def policies(request: Request, who: Annotated[Identity, Depends(identity)]) -> HTMLResponse:
    async with services(request).database.session() as session:
        found = (
            await session.scalars(
                select(Policy).where(Policy.owner == who.id()).order_by(Policy.id.desc())
            )
        ).all()
    return templates.TemplateResponse(
        request,
        "policies.html",
        {
            "page": "policies",
            "policies": found,
        },
    )


@router.get("/policies/{policy_id}", response_class=HTMLResponse)
async def policy(
    policy_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> HTMLResponse:
    return await body(request, who, policy_id)


@router.get("/policies/{policy_id}/body", response_class=HTMLResponse)
async def fragment(
    policy_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "policy_body.html", await context(request, who, policy_id, "")
    )


@router.post("/policies/{policy_id}/rebuild")
async def rebuild(
    policy_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> RedirectResponse:
    await policy_of(request, who, policy_id)
    await services(request).packages.rebuild(policy_id)
    return RedirectResponse(f"/policies/{policy_id}", status_code=303)


@router.post("/policies/{policy_id}/profile", response_model=None)
async def edit(
    policy_id: int, request: Request, who: Annotated[Identity, Depends(identity)]
) -> RedirectResponse | HTMLResponse:
    await policy_of(request, who, policy_id)
    form = await request.form()
    current = (await services(request).folio.latest(policy_id)).profile
    try:
        saved = merged(form, current)
    except ValidationError as error:
        first = error.errors()[0]
        place = ".".join(str(part) for part in first["loc"])
        return await body(
            request, who, policy_id, f"Правки не приняты: {place}: {first['msg']}", status=422
        )
    await services(request).folio.draft(policy_id, saved)
    return RedirectResponse(f"/policies/{policy_id}", status_code=303)


@router.post("/policies/{policy_id}/approve", response_model=None)
async def approve(
    policy_id: int,
    request: Request,
    version: int,
    who: Annotated[Identity, Depends(identity)],
) -> RedirectResponse | HTMLResponse:
    await policy_of(request, who, policy_id)
    try:
        await services(request).folio.approve(policy_id, version, who.name())
    except NotReadyError as error:
        return await body(request, who, policy_id, str(error), status=409)
    return RedirectResponse(f"/policies/{policy_id}", status_code=303)
