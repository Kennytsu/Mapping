"""Compliance Mapping Tool - FastAPI Backend."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, func, or_, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    init_db, get_session,
    Framework, Control, Mapping, VersionChange,
)
from document_parser import parse_uploaded_bytes


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class FrameworkOut(BaseModel):
    id: int
    name: str
    short_name: str
    version: str
    description: str
    is_active: bool
    control_count: int = 0

class ControlOut(BaseModel):
    id: int
    framework_id: int
    control_id: str
    title: str
    description: str
    category: str
    framework_short_name: str = ""

class MappingOut(BaseModel):
    control_id: str
    title: str
    description: str
    category: str
    framework_short_name: str
    confidence: float
    source_type: str
    source_document: str

class MappingDetail(BaseModel):
    source: ControlOut
    mappings: list[MappingOut]

class CoverageOut(BaseModel):
    source_framework: str
    target_framework: str
    total_source_controls: int
    mapped_controls: int
    unmapped_controls: int
    coverage_percentage: float
    unmapped_control_ids: list[str]
    gap_controls: list[str]

class VersionChangeOut(BaseModel):
    id: int
    old_version: str
    new_version: str
    change_type: str
    old_control_id: str
    new_control_id: str
    description: str
    category: str

class ParseResult(BaseModel):
    success: bool
    controls: list[dict] = []
    mappings: list[dict] = []
    raw_text: str = ""
    error: str = ""

class ImportRequest(BaseModel):
    doc_type: str = ""
    source_framework_id: int = 0
    target_framework_id: int = 0
    document_year: str = ""
    source_document: str = ""
    controls: list[dict] = []
    mappings: list[dict] = []

class ImportResult(BaseModel):
    success: bool
    controls_added: int = 0
    mappings_added: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    await init_db()
    yield

app = FastAPI(
    title="Compliance Mapping Tool",
    description="Map controls between ISO 27001, BSI IT-Grundschutz, and C5",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/api/frameworks", response_model=list[FrameworkOut])
async def list_frameworks(session: AsyncSession = Depends(get_session)):
    stmt = (
        select(
            Framework,
            func.count(Control.id).label("control_count"),
        )
        .outerjoin(Control, Framework.id == Control.framework_id)
        .group_by(Framework.id)
    )
    rows = (await session.execute(stmt)).all()
    return [
        FrameworkOut(
            id=fw.id,
            name=fw.name,
            short_name=fw.short_name,
            version=fw.version,
            description=fw.description or "",
            is_active=fw.is_active,
            control_count=cnt,
        )
        for fw, cnt in rows
    ]


@app.get("/api/controls", response_model=list[ControlOut])
async def search_controls(
    q: str = "",
    framework_id: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Control, Framework.short_name)
        .join(Framework, Control.framework_id == Framework.id)
    )
    if framework_id:
        stmt = stmt.where(Control.framework_id == framework_id)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Control.control_id.ilike(pattern),
                Control.title.ilike(pattern),
                Control.description.ilike(pattern),
            )
        )
        exact_first = case(
            (func.lower(Control.control_id) == q.lower(), 0),
            else_=1,
        )
        stmt = stmt.order_by(exact_first, Control.control_id)
    else:
        stmt = stmt.order_by(Control.control_id)
    stmt = stmt.limit(100)

    rows = (await session.execute(stmt)).all()
    return [
        ControlOut(
            id=c.id,
            framework_id=c.framework_id,
            control_id=c.control_id,
            title=c.title or "",
            description=c.description or "",
            category=c.category or "",
            framework_short_name=sn,
        )
        for c, sn in rows
    ]


@app.get("/api/mappings/{control_id}", response_model=MappingDetail)
async def get_mappings(
    control_id: str,
    framework_id: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Control).where(Control.control_id == control_id)
    if framework_id:
        stmt = stmt.where(Control.framework_id == framework_id)
    source = (await session.execute(stmt)).scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Control not found")

    fw = (await session.execute(
        select(Framework.short_name).where(Framework.id == source.framework_id)
    )).scalar_one()

    source_out = ControlOut(
        id=source.id,
        framework_id=source.framework_id,
        control_id=source.control_id,
        title=source.title or "",
        description=source.description or "",
        category=source.category or "",
        framework_short_name=fw,
    )

    # Bidirectional: find mappings where this control is source OR target
    stmt = (
        select(Control, Framework.short_name, Mapping.confidence, Mapping.source_type, Mapping.source_document)
        .join(
            Mapping,
            or_(
                and_(Mapping.source_control_id == source.id, Mapping.target_control_id == Control.id),
                and_(Mapping.target_control_id == source.id, Mapping.source_control_id == Control.id),
            ),
        )
        .join(Framework, Control.framework_id == Framework.id)
        .where(Control.id != source.id)
    )
    rows = (await session.execute(stmt)).all()

    mappings_out = [
        MappingOut(
            control_id=c.control_id,
            title=c.title or "",
            description=c.description or "",
            category=c.category or "",
            framework_short_name=sn,
            confidence=conf,
            source_type=st,
            source_document=sd or "",
        )
        for c, sn, conf, st, sd in rows
    ]

    return MappingDetail(source=source_out, mappings=mappings_out)


@app.get("/api/coverage", response_model=CoverageOut)
async def coverage_analysis(
    source: int = Query(..., description="Source framework ID"),
    target: int = Query(..., description="Target framework ID"),
    session: AsyncSession = Depends(get_session),
):
    src_fw = (await session.execute(
        select(Framework).where(Framework.id == source)
    )).scalar_one_or_none()
    tgt_fw = (await session.execute(
        select(Framework).where(Framework.id == target)
    )).scalar_one_or_none()
    if not src_fw or not tgt_fw:
        raise HTTPException(404, "Framework not found")

    src_controls = (await session.execute(
        select(Control.id, Control.control_id).where(Control.framework_id == source)
    )).all()
    tgt_controls = (await session.execute(
        select(Control.id, Control.control_id).where(Control.framework_id == target)
    )).all()

    src_ids = {r[0] for r in src_controls}
    src_map = {r[0]: r[1] for r in src_controls}
    tgt_ids = {r[0] for r in tgt_controls}
    tgt_map = {r[0]: r[1] for r in tgt_controls}

    mapped_src = set()
    mapped_tgt = set()

    stmt = select(Mapping.source_control_id, Mapping.target_control_id).where(
        or_(
            and_(Mapping.source_control_id.in_(src_ids), Mapping.target_control_id.in_(tgt_ids)),
            and_(Mapping.target_control_id.in_(src_ids), Mapping.source_control_id.in_(tgt_ids)),
        )
    )
    pairs = (await session.execute(stmt)).all()
    for s, t in pairs:
        if s in src_ids:
            mapped_src.add(s)
            mapped_tgt.add(t)
        else:
            mapped_src.add(t)
            mapped_tgt.add(s)

    total = len(src_controls)
    mapped = len(mapped_src)

    return CoverageOut(
        source_framework=src_fw.short_name,
        target_framework=tgt_fw.short_name,
        total_source_controls=total,
        mapped_controls=mapped,
        unmapped_controls=total - mapped,
        coverage_percentage=round((mapped / total * 100) if total else 0, 1),
        unmapped_control_ids=[src_map[i] for i in src_ids if i not in mapped_src],
        gap_controls=[tgt_map[i] for i in tgt_ids if i not in mapped_tgt],
    )


@app.get("/api/versions/{framework_short_name}/transitions")
async def version_transitions(
    framework_short_name: str,
    session: AsyncSession = Depends(get_session),
):
    """List available version transitions for a framework."""
    fw = (await session.execute(
        select(Framework).where(Framework.short_name == framework_short_name)
    )).scalar_one_or_none()
    if not fw:
        raise HTTPException(404, "Framework not found")

    stmt = (
        select(
            VersionChange.old_version,
            VersionChange.new_version,
            func.count(VersionChange.id).label("change_count"),
        )
        .where(VersionChange.framework_id == fw.id)
        .group_by(VersionChange.old_version, VersionChange.new_version)
        .order_by(VersionChange.old_version)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"old_version": old, "new_version": new, "change_count": cnt}
        for old, new, cnt in rows
    ]


@app.get("/api/versions/{framework_short_name}/changes", response_model=list[VersionChangeOut])
async def version_changes(
    framework_short_name: str,
    old: str = Query("", alias="from"),
    new: str = Query("", alias="to"),
    session: AsyncSession = Depends(get_session),
):
    fw = (await session.execute(
        select(Framework).where(Framework.short_name == framework_short_name)
    )).scalar_one_or_none()
    if not fw:
        raise HTTPException(404, "Framework not found")

    stmt = select(VersionChange).where(VersionChange.framework_id == fw.id)
    if old:
        stmt = stmt.where(VersionChange.old_version == old)
    if new:
        stmt = stmt.where(VersionChange.new_version == new)
    stmt = stmt.order_by(VersionChange.change_type, VersionChange.old_control_id)

    rows = (await session.execute(stmt)).scalars().all()
    return [
        VersionChangeOut(
            id=r.id,
            old_version=r.old_version,
            new_version=r.new_version,
            change_type=r.change_type,
            old_control_id=r.old_control_id or "",
            new_control_id=r.new_control_id or "",
            description=r.description or "",
            category=r.category or "",
        )
        for r in rows
    ]


class VersionChangeCreate(BaseModel):
    old_version: str
    new_version: str
    change_type: str
    old_control_id: str = ""
    new_control_id: str = ""
    description: str = ""
    category: str = ""


@app.post("/api/versions/{framework_short_name}/changes")
async def add_version_changes(
    framework_short_name: str,
    changes: list[VersionChangeCreate],
    session: AsyncSession = Depends(get_session),
):
    """Bulk-add version change records."""
    fw = (await session.execute(
        select(Framework).where(Framework.short_name == framework_short_name)
    )).scalar_one_or_none()
    if not fw:
        raise HTTPException(404, "Framework not found")

    added = 0
    for ch in changes:
        session.add(VersionChange(
            framework_id=fw.id,
            old_version=ch.old_version,
            new_version=ch.new_version,
            change_type=ch.change_type,
            old_control_id=ch.old_control_id,
            new_control_id=ch.new_control_id,
            description=ch.description,
            category=ch.category,
        ))
        added += 1

    await session.commit()
    return {"added": added}


@app.get("/api/coverage/table")
async def coverage_table(
    source: int = Query(..., description="Source framework ID"),
    target: int = Query(..., description="Target framework ID"),
    session: AsyncSession = Depends(get_session),
):
    """Full mapping table between two frameworks (for export/display)."""
    src_fw = (await session.execute(
        select(Framework).where(Framework.id == source)
    )).scalar_one_or_none()
    tgt_fw = (await session.execute(
        select(Framework).where(Framework.id == target)
    )).scalar_one_or_none()
    if not src_fw or not tgt_fw:
        raise HTTPException(404, "Framework not found")

    src_controls = (await session.execute(
        select(Control).where(Control.framework_id == source).order_by(Control.control_id)
    )).scalars().all()

    rows = []
    for sc in src_controls:
        mapped = (await session.execute(
            select(Control, Mapping.confidence, Mapping.source_type)
            .join(
                Mapping,
                or_(
                    and_(Mapping.source_control_id == sc.id, Mapping.target_control_id == Control.id),
                    and_(Mapping.target_control_id == sc.id, Mapping.source_control_id == Control.id),
                ),
            )
            .where(Control.framework_id == target)
        )).all()

        if mapped:
            for tc, conf, st in mapped:
                rows.append({
                    "source_id": sc.control_id,
                    "source_title": sc.title or "",
                    "target_id": tc.control_id,
                    "target_title": tc.title or "",
                    "confidence": conf,
                    "source_type": st,
                })
        else:
            rows.append({
                "source_id": sc.control_id,
                "source_title": sc.title or "",
                "target_id": "",
                "target_title": "",
                "confidence": 0,
                "source_type": "gap",
            })

    return {
        "source_framework": src_fw.short_name,
        "target_framework": tgt_fw.short_name,
        "rows": rows,
    }


@app.post("/api/upload", response_model=ParseResult)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form("BSI Zuordnungstabelle"),
):
    content = await file.read()
    filename = file.filename or ""
    result = parse_uploaded_bytes(content, filename, doc_type)
    return ParseResult(**result)


@app.post("/api/import", response_model=ImportResult)
async def import_data(
    body: ImportRequest,
    session: AsyncSession = Depends(get_session),
):
    controls_added = 0
    mappings_added = 0

    src_fw_id = body.source_framework_id
    tgt_fw_id = body.target_framework_id
    source_doc = body.source_document or body.doc_type

    if src_fw_id and tgt_fw_id:
        src_fw = (await session.execute(
            select(Framework).where(Framework.id == src_fw_id)
        )).scalar_one_or_none()
        tgt_fw = (await session.execute(
            select(Framework).where(Framework.id == tgt_fw_id)
        )).scalar_one_or_none()
    else:
        doc_type = body.doc_type
        if "BSI" in doc_type and "C5" not in doc_type:
            short = "BSI"
        elif "C5" in doc_type:
            short = "C5"
        else:
            short = "ISO27001"
        tgt_fw = (await session.execute(
            select(Framework).where(Framework.short_name == short)
        )).scalar_one_or_none()
        src_fw = (await session.execute(
            select(Framework).where(Framework.short_name == "ISO27001")
        )).scalar_one_or_none()

    if not src_fw or not tgt_fw:
        return ImportResult(success=False, error="Source or target framework not found.")

    for ctrl in body.controls:
        existing = (await session.execute(
            select(Control).where(
                Control.framework_id == tgt_fw.id,
                Control.control_id == ctrl["control_id"],
            )
        )).scalar_one_or_none()
        if not existing:
            session.add(Control(
                framework_id=tgt_fw.id,
                control_id=ctrl["control_id"],
                title=ctrl.get("title", ""),
                category=ctrl.get("category", ""),
            ))
            controls_added += 1
    await session.flush()

    all_controls = (await session.execute(
        select(Control.id, Control.control_id, Control.framework_id)
    )).all()
    lookup = {(r[1], r[2]): r[0] for r in all_controls}

    for m in body.mappings:
        s_id = lookup.get((m["source"], src_fw.id))
        t_id = lookup.get((m["target"], tgt_fw.id))

        if not s_id and m["source"]:
            existing = (await session.execute(
                select(Control).where(
                    Control.framework_id == src_fw.id,
                    Control.control_id == m["source"],
                )
            )).scalar_one_or_none()
            if not existing:
                ctrl = Control(
                    framework_id=src_fw.id,
                    control_id=m["source"],
                    title=m["source"],
                    category="",
                )
                session.add(ctrl)
                await session.flush()
                s_id = ctrl.id
                lookup[(m["source"], src_fw.id)] = s_id
            else:
                s_id = existing.id

        if s_id and t_id:
            existing = (await session.execute(
                select(Mapping).where(
                    Mapping.source_control_id == s_id,
                    Mapping.target_control_id == t_id,
                )
            )).scalar_one_or_none()
            if not existing:
                session.add(Mapping(
                    source_control_id=s_id,
                    target_control_id=t_id,
                    confidence=1.0,
                    source_type="official",
                    source_document=source_doc,
                ))
                mappings_added += 1

    await session.commit()
    return ImportResult(success=True, controls_added=controls_added, mappings_added=mappings_added)


# ---------------------------------------------------------------------------
# Static files – served AFTER API routes so /api/* takes priority
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")
