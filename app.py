"""Compliance Mapping Tool - FastAPI Backend."""

from contextlib import asynccontextmanager
from io import BytesIO
from typing import Optional

from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
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
    unmapped_control_ids: list[dict]
    gap_controls: list[dict]

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
    stmt = stmt.limit(200)

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
        select(Control.id, Control.control_id, Control.title).where(Control.framework_id == source)
    )).all()
    tgt_controls = (await session.execute(
        select(Control.id, Control.control_id, Control.title).where(Control.framework_id == target)
    )).all()

    src_ids = {r[0] for r in src_controls}
    src_map = {r[0]: {"id": r[1], "title": r[2] or ""} for r in src_controls}
    tgt_ids = {r[0] for r in tgt_controls}
    tgt_map = {r[0]: {"id": r[1], "title": r[2] or ""} for r in tgt_controls}

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


@app.get("/api/coverage/export")
async def coverage_export(
    source: int = Query(..., description="Source framework ID"),
    target: int = Query(..., description="Target framework ID"),
    session: AsyncSession = Depends(get_session),
):
    """Download an Excel workbook with mapping summary, full table, and gap list."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

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
    tgt_controls = (await session.execute(
        select(Control.id, Control.control_id, Control.title).where(Control.framework_id == target)
    )).all()

    tgt_ids = {r[0] for r in tgt_controls}
    tgt_map = {r[0]: {"id": r[1], "title": r[2] or ""} for r in tgt_controls}

    table_rows = []
    mapped_src_ids = set()
    mapped_tgt_ids = set()

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
            mapped_src_ids.add(sc.id)
            for tc, conf, st in mapped:
                mapped_tgt_ids.add(tc.id)
                table_rows.append((sc.control_id, sc.title or "", tc.control_id, tc.title or "", st))
        else:
            table_rows.append((sc.control_id, sc.title or "", "", "", "gap"))

    total = len(src_controls)
    mapped_count = len(mapped_src_ids)
    pct = round((mapped_count / total * 100) if total else 0, 1)
    unmapped = [(sc.control_id, sc.title or "") for sc in src_controls if sc.id not in mapped_src_ids]
    gap_targets = [(tgt_map[tid]["id"], tgt_map[tid]["title"]) for tid in tgt_ids if tid not in mapped_tgt_ids]

    wb = Workbook()
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
    thin_border = Border(
        bottom=Side(style="thin", color="C6C6C6"),
    )

    def _style_header(ws, cols):
        for col_idx, val in enumerate(cols, 1):
            cell = ws.cell(row=1, column=col_idx, value=val)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="left")
        ws.freeze_panes = "A2"

    # Sheet 1: Summary
    ws_sum = wb.active
    ws_sum.title = "Summary"
    ws_sum.column_dimensions["A"].width = 25
    ws_sum.column_dimensions["B"].width = 40
    summary_data = [
        ("Source Framework", f"{src_fw.short_name} ({src_fw.version})"),
        ("Target Framework", f"{tgt_fw.short_name} ({tgt_fw.version})"),
        ("Total Source Controls", total),
        ("Mapped Controls", mapped_count),
        ("Unmapped Controls", total - mapped_count),
        ("Coverage", f"{pct}%"),
    ]
    for r, (label, value) in enumerate(summary_data, 1):
        ws_sum.cell(row=r, column=1, value=label).font = Font(bold=True)
        ws_sum.cell(row=r, column=2, value=value)

    # Sheet 2: Full Mapping Table
    ws_table = wb.create_sheet("Mapping Table")
    headers = [src_fw.short_name, "Source Title", tgt_fw.short_name, "Target Title", "Type"]
    _style_header(ws_table, headers)
    gap_fill = PatternFill(start_color="FFF1F1", end_color="FFF1F1", fill_type="solid")
    for r, (s_id, s_title, t_id, t_title, stype) in enumerate(table_rows, 2):
        ws_table.cell(row=r, column=1, value=s_id)
        ws_table.cell(row=r, column=2, value=s_title)
        c3 = ws_table.cell(row=r, column=3, value=t_id or "No mapping")
        ws_table.cell(row=r, column=4, value=t_title)
        ws_table.cell(row=r, column=5, value=stype)
        if stype == "gap":
            for col in range(1, 6):
                ws_table.cell(row=r, column=col).fill = gap_fill
    for col_idx in range(1, 6):
        ws_table.column_dimensions[chr(64 + col_idx)].width = 30

    # Sheet 3: Unmapped Source Controls
    ws_unmapped = wb.create_sheet("Unmapped Controls")
    _style_header(ws_unmapped, ["Control ID", "Title"])
    for r, (ctrl_id, title) in enumerate(unmapped, 2):
        ws_unmapped.cell(row=r, column=1, value=ctrl_id)
        ws_unmapped.cell(row=r, column=2, value=title)
    ws_unmapped.column_dimensions["A"].width = 20
    ws_unmapped.column_dimensions["B"].width = 60

    # Sheet 4: Target Gaps
    ws_gaps = wb.create_sheet("Target Gaps")
    _style_header(ws_gaps, ["Control ID", "Title"])
    for r, (ctrl_id, title) in enumerate(gap_targets, 2):
        ws_gaps.cell(row=r, column=1, value=ctrl_id)
        ws_gaps.cell(row=r, column=2, value=title)
    ws_gaps.column_dimensions["A"].width = 20
    ws_gaps.column_dimensions["B"].width = 60

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"coverage_{src_fw.short_name}_to_{tgt_fw.short_name}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
# AI module skeleton endpoints
# ---------------------------------------------------------------------------

class EmbeddingRequest(BaseModel):
    framework_id: int
    model: str = "text-embedding-3-small"


@app.post("/api/embeddings/generate")
async def generate_embeddings(body: EmbeddingRequest):
    """Placeholder for embedding generation — to be implemented by the AI module."""
    return {
        "status": "not_implemented",
        "message": "Embedding generation will be handled by the AI module. "
                   f"Requested: framework_id={body.framework_id}, model={body.model}",
    }


@app.get("/api/mappings/suggest")
async def suggest_mappings(
    control_id: str = Query(..., description="Source control ID to find suggestions for"),
    framework_id: int = Query(..., description="Target framework ID"),
    top_k: int = Query(5, description="Number of suggestions to return"),
    session: AsyncSession = Depends(get_session),
):
    """AI-powered mapping suggestions via pgvector cosine similarity.

    Returns empty results until embeddings are generated by the AI module.
    """
    source = (await session.execute(
        select(Control).where(Control.control_id == control_id)
    )).scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Source control not found")

    if source.embedding is None:
        return {
            "source_control": control_id,
            "target_framework_id": framework_id,
            "suggestions": [],
            "message": "No embeddings available. Run embedding generation first.",
        }

    try:
        from pgvector.sqlalchemy import Vector
        stmt = (
            select(
                Control.control_id,
                Control.title,
                Control.description,
                Control.embedding.cosine_distance(source.embedding).label("distance"),
            )
            .where(Control.framework_id == framework_id)
            .where(Control.embedding.isnot(None))
            .order_by("distance")
            .limit(top_k)
        )
        rows = (await session.execute(stmt)).all()
        suggestions = [
            {
                "control_id": r[0],
                "title": r[1] or "",
                "description": r[2] or "",
                "confidence": round(1 - r[3], 4),
                "source_type": "ai_suggested",
            }
            for r in rows
        ]
    except Exception:
        suggestions = []

    return {
        "source_control": control_id,
        "target_framework_id": framework_id,
        "suggestions": suggestions,
        "message": "" if suggestions else "No embeddings available. Run embedding generation first.",
    }


# ---------------------------------------------------------------------------
# Static files – served AFTER API routes so /api/* takes priority
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")
