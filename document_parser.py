"""
Document parser — pluggable registry for importing controls and mappings.

To add a new format:
    1. Write a parse function: (content: bytes, doc_type: str) -> ParseOutput
    2. Register it: register_parser("my_format", [".xlsx", ".csv"], my_parse_fn)

That's it. The upload API picks it up automatically.
"""

import re
from io import BytesIO
from dataclasses import dataclass, field
from typing import Callable, Protocol

import pandas as pd
import pdfplumber


# ---------------------------------------------------------------------------
# Output type — every parser returns this
# ---------------------------------------------------------------------------

@dataclass
class ParseOutput:
    success: bool
    controls: list[dict] = field(default_factory=list)
    mappings: list[dict] = field(default_factory=list)
    raw_text: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "controls": self.controls,
            "mappings": self.mappings,
            "raw_text": self.raw_text,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------

class ParserFn(Protocol):
    def __call__(self, content: bytes, doc_type: str) -> ParseOutput: ...


@dataclass
class RegisteredParser:
    name: str
    extensions: list[str]
    parse_fn: ParserFn
    description: str = ""


_PARSERS: list[RegisteredParser] = []


def register_parser(
    name: str,
    extensions: list[str],
    parse_fn: ParserFn,
    description: str = "",
):
    """Register a parser. Extensions should include the dot, e.g. ['.pdf', '.xlsx']."""
    _PARSERS.append(RegisteredParser(
        name=name,
        extensions=[e.lower() for e in extensions],
        parse_fn=parse_fn,
        description=description,
    ))


def list_parsers() -> list[dict]:
    """Return metadata about all registered parsers (useful for UI dropdowns)."""
    return [
        {"name": p.name, "extensions": p.extensions, "description": p.description}
        for p in _PARSERS
    ]


# ---------------------------------------------------------------------------
# Public entry point — routes call this
# ---------------------------------------------------------------------------

def parse_uploaded_bytes(content: bytes, filename: str, doc_type: str) -> dict:
    """Parse raw file bytes. Finds the right parser by extension, then by doc_type."""
    filename_lower = filename.lower()
    ext = "." + filename_lower.rsplit(".", 1)[-1] if "." in filename_lower else ""

    # First: try to match by doc_type name (explicit user selection)
    for parser in _PARSERS:
        if parser.name.lower() == doc_type.lower():
            try:
                return parser.parse_fn(content, doc_type).to_dict()
            except Exception as e:
                return ParseOutput(success=False, error=str(e)).to_dict()

    # Second: fall back to extension matching
    for parser in _PARSERS:
        if ext in parser.extensions:
            try:
                return parser.parse_fn(content, doc_type).to_dict()
            except Exception as e:
                return ParseOutput(success=False, error=str(e)).to_dict()

    return ParseOutput(success=False, error=f"No parser for: {filename} (type={doc_type})").to_dict()


# ===========================================================================
# Built-in parsers
# ===========================================================================


# ---------------------------------------------------------------------------
# BSI Zuordnungstabelle PDF
# ---------------------------------------------------------------------------

_ISO_PATTERN = re.compile(r"A\.(\d+)\.(\d+)")
_BSI_REQ_PATTERN = re.compile(r"\b([A-Z]{2,5}\.\d+(?:\.\d+)?\.A\d+)\b")
_BSI_MODULE_PATTERN = re.compile(r"\b([A-Z]{2,5}\.\d+(?:\.\d+)?)\b")
_BSI_STD_PATTERN = re.compile(r"(BSI-Standard\s+200-[1-4])")
_CLAUSE_START = re.compile(r"^(\d+(?:\.\d+)*)\s+[A-Z]")

_BSI_MODULE_PREFIXES = {
    "ISMS", "ORP", "CON", "OPS", "APP", "SYS", "IND", "INF", "DER", "NET", "TNA",
}

_BSI_STD_TITLES = {
    "BSI-Std-200-1": "BSI-Standard 200-1: Managementsysteme fuer Informationssicherheit (ISMS)",
    "BSI-Std-200-2": "BSI-Standard 200-2: IT-Grundschutz-Methodik",
    "BSI-Std-200-3": "BSI-Standard 200-3: Risikoanalyse auf der Basis von IT-Grundschutz",
    "BSI-Std-200-4": "BSI-Standard 200-4: Business Continuity Management",
    "BSI-ElemGef": "Elementare Gefaehrdungen (G0) des IT-Grundschutz-Kompendiums",
}


def _parse_bsi_zuordnung_pdf(content: bytes, doc_type: str) -> ParseOutput:
    """
    Parse BSI Zuordnungstabelle PDF.
    Handles both:
      - Clause section (1-10): ISO clauses mapped to BSI-Standard references
      - Annex A section (A.5-A.8): ISO controls mapped to IT-Grundschutz requirements
    """
    controls: list[dict] = []
    mappings: list[dict] = []
    all_text: list[str] = []
    seen_bsi: set[str] = set()
    seen_mappings: set[tuple] = set()

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_text.append(text)

    full_text = "\n".join(all_text)

    def _add_bsi(bsi_ctrl: str, iso_ctrl: str, title: str = "", category: str = ""):
        if bsi_ctrl not in seen_bsi:
            seen_bsi.add(bsi_ctrl)
            if not category:
                cat = re.match(r"([A-Z]+)", bsi_ctrl)
                category = cat.group(1) if cat else ""
            controls.append({
                "control_id": bsi_ctrl,
                "title": title or f"BSI {bsi_ctrl}",
                "category": category,
            })
        key = (iso_ctrl, bsi_ctrl)
        if key not in seen_mappings:
            seen_mappings.add(key)
            mappings.append({"source": iso_ctrl, "target": bsi_ctrl})

    def _extract_std_refs(text_block: str) -> list[str]:
        refs = []
        for m in _BSI_STD_PATTERN.finditer(text_block):
            raw = m.group(1)
            num = re.search(r"200-([1-4])", raw)
            if num:
                ctrl_id = f"BSI-Std-200-{num.group(1)}"
                if ctrl_id not in refs:
                    refs.append(ctrl_id)
        if re.search(r"Elementare\s+Gef", text_block):
            if "BSI-ElemGef" not in refs:
                refs.append("BSI-ElemGef")
        return refs

    for ctrl_id, title in _BSI_STD_TITLES.items():
        if ctrl_id not in seen_bsi:
            seen_bsi.add(ctrl_id)
            controls.append({
                "control_id": ctrl_id,
                "title": title,
                "category": "BSI-Standard",
            })

    # Pass 1: Clause section (ISO clauses 1-10 -> BSI-Standards)
    lines = full_text.split("\n")
    current_clause = None
    clause_buffer: list[str] = []

    def _flush_clause():
        nonlocal current_clause, clause_buffer
        if current_clause and clause_buffer:
            block = " ".join(clause_buffer)
            for std_id in _extract_std_refs(block):
                _add_bsi(std_id, current_clause,
                         _BSI_STD_TITLES.get(std_id, std_id), "BSI-Standard")
        clause_buffer = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("A."):
            _flush_clause()
            current_clause = None
            break

        clause_match = _CLAUSE_START.match(stripped)
        if clause_match:
            _flush_clause()
            clause_num = clause_match.group(1)
            if re.match(r"^\d+\.\d+", clause_num):
                current_clause = clause_num
            clause_buffer = [stripped]
        elif current_clause:
            clause_buffer.append(stripped)

    _flush_clause()

    # Pass 2: Annex A section (A.X.Y -> IT-Grundschutz requirements)
    sections = re.split(r"(A\.\d+\.\d+\s)", full_text)
    current_iso = None
    for section in sections:
        m = re.match(r"A\.(\d+)\.(\d+)\s*$", section.strip())
        if m:
            current_iso = f"A.{m.group(1)}.{m.group(2)}"
            continue
        if current_iso and section.strip():
            for bsi_ctrl in _BSI_REQ_PATTERN.findall(section):
                _add_bsi(bsi_ctrl, current_iso)
            for bsi_mod in _BSI_MODULE_PATTERN.findall(section):
                prefix = bsi_mod.split(".")[0]
                if ".A" not in bsi_mod and prefix in _BSI_MODULE_PREFIXES and bsi_mod not in seen_bsi:
                    seen_bsi.add(bsi_mod)
                    cat = re.match(r"([A-Z]+)", bsi_mod)
                    controls.append({
                        "control_id": bsi_mod,
                        "title": f"BSI Module {bsi_mod}",
                        "category": cat.group(1) if cat else "",
                    })
            for std_id in _extract_std_refs(section):
                _add_bsi(std_id, current_iso,
                         _BSI_STD_TITLES.get(std_id, std_id), "BSI-Standard")

    # Line-by-line fallback for requirement IDs
    current_iso = None
    for line in full_text.split("\n"):
        iso_start = re.match(r"^A\.(\d+)\.(\d+)\s+(.+)", line)
        if iso_start:
            current_iso = f"A.{iso_start.group(1)}.{iso_start.group(2)}"
            for bsi_ctrl in _BSI_REQ_PATTERN.findall(iso_start.group(3)):
                _add_bsi(bsi_ctrl, current_iso)
        elif current_iso:
            for bsi_ctrl in _BSI_REQ_PATTERN.findall(line):
                _add_bsi(bsi_ctrl, current_iso)

    return ParseOutput(
        success=True,
        controls=controls,
        mappings=mappings,
        raw_text=full_text[:10000],
    )


# ---------------------------------------------------------------------------
# Excel parser (C5, generic cross-reference tables)
# ---------------------------------------------------------------------------

_C5_REF_PATTERN = re.compile(r"([A-Z]{2,4})-(\d{2})")
_ISO_ANNEX_PATTERN = re.compile(r"(A\.\d+\.\d+)")
_ISO_CLAUSE_PATTERN = re.compile(r"(\d+\.\d+)")


def _extract_iso_refs(raw: str) -> list[str]:
    """Extract ISO 27001 references from a cell (handles ranges, dashes, etc)."""
    if not raw or raw.strip() in ("-", "n/a", "nan", ""):
        return []
    refs: list[str] = []
    refs.extend(_ISO_ANNEX_PATTERN.findall(raw))
    for clause in _ISO_CLAUSE_PATTERN.findall(raw):
        if clause not in refs and not any(clause in r for r in refs):
            refs.append(clause)
    return refs


def _parse_excel(content: bytes, doc_type: str) -> ParseOutput:
    """Parse Excel for controls and mappings. Handles C5:2020 format."""
    controls: list[dict] = []
    mappings: list[dict] = []
    seen_mappings: set[tuple] = set()

    xlsx = pd.ExcelFile(BytesIO(content))

    target_sheets = [s for s in xlsx.sheet_names if "map" in s.lower() or "reference" in s.lower()]
    if not target_sheets:
        target_sheets = xlsx.sheet_names

    for sheet_name in target_sheets:
        df_raw = pd.read_excel(xlsx, sheet_name=sheet_name, header=None)
        if df_raw.empty or len(df_raw) < 3:
            continue

        header_row = _find_header_row(df_raw)
        if header_row is None:
            continue

        df = pd.read_excel(xlsx, sheet_name=sheet_name, header=header_row)
        seen_cols: dict[str, int] = {}
        new_cols = []
        for c in df.columns:
            name = str(c).strip()
            if name in seen_cols:
                seen_cols[name] += 1
                new_cols.append(f"{name}_{seen_cols[name]}")
            else:
                seen_cols[name] = 0
                new_cols.append(name)
        df.columns = new_cols

        col_map = _detect_columns(df.columns, doc_type)
        if not col_map:
            continue

        ref_col = col_map["ref"]
        title_col = col_map.get("title")
        desc_col = col_map.get("description")
        iso_col = col_map["iso"]

        for _, row in df.iterrows():
            ref_val = _safe_str(row, ref_col)
            iso_val = _safe_str(row, iso_col)
            title_val = _safe_str(row, title_col) if title_col else ""
            desc_val = _safe_str(row, desc_col) if desc_col else ""

            if not ref_val or ref_val == "nan":
                continue

            if "C5" in doc_type or _C5_REF_PATTERN.match(ref_val):
                ctrl_id = ref_val
                cat_match = _C5_REF_PATTERN.match(ref_val)
                category = cat_match.group(1) if cat_match else ""
            else:
                ctrl_id = ref_val
                cat_match = re.match(r"([A-Z]+)", ref_val)
                category = cat_match.group(1) if cat_match else ""

            if not any(c["control_id"] == ctrl_id for c in controls):
                controls.append({
                    "control_id": ctrl_id,
                    "title": title_val or f"Control {ctrl_id}",
                    "description": desc_val,
                    "category": category,
                })

            iso_refs = _extract_iso_refs(iso_val)
            for iso_ref in iso_refs:
                key = (iso_ref, ctrl_id)
                if key not in seen_mappings:
                    seen_mappings.add(key)
                    mappings.append({"source": iso_ref, "target": ctrl_id})

    return ParseOutput(
        success=True,
        controls=controls,
        mappings=mappings,
        raw_text=f"Parsed {len(xlsx.sheet_names)} sheets, {len(controls)} controls, {len(mappings)} mappings",
    )


def _safe_str(row, col) -> str:
    if col is None:
        return ""
    val = row.get(col)
    if val is None:
        return ""
    if isinstance(val, pd.Series):
        val = val.iloc[0]
    if pd.isna(val):
        return ""
    return str(val).strip()


def _find_header_row(df: pd.DataFrame, max_rows: int = 5) -> int | None:
    keywords = ("ref", "title", "criteria", "description")
    best_row = None
    best_score = 0
    for i in range(min(max_rows, len(df))):
        row_values = [str(v).strip().lower() for v in df.iloc[i] if pd.notna(v)]
        score = sum(1 for val in row_values for kw in keywords if kw in val)
        if score > best_score:
            best_score = score
            best_row = i
    return best_row if best_score >= 2 else None


def _detect_columns(columns: list[str], doc_type: str) -> dict | None:
    result: dict = {}
    ref_count = 0

    for col in columns:
        low = col.lower()
        if "ref" in low and "iso" not in low:
            if ref_count == 0:
                result.setdefault("ref", col)
            else:
                result.setdefault("iso", col)
            ref_count += 1
        elif "title" in low:
            result.setdefault("title", col)
        elif any(kw in low for kw in ("criteria", "description", "basic", "requirement")):
            result.setdefault("description", col)
        elif "iso" in low or "27001" in low:
            result.setdefault("iso", col)

    if "ref" in result and "iso" in result:
        return result

    if len(columns) >= 4:
        return {
            "ref": columns[0],
            "title": columns[1],
            "description": columns[2],
            "iso": columns[3],
        }

    return None


# ---------------------------------------------------------------------------
# CSV parser (simple source/target columns)
# ---------------------------------------------------------------------------

def _parse_csv(content: bytes, doc_type: str) -> ParseOutput:
    """Parse a CSV with source/target columns for mappings."""
    df = pd.read_csv(BytesIO(content))
    controls: list[dict] = []
    mappings: list[dict] = []

    iso_col = None
    target_col = None

    for col in df.columns:
        col_upper = str(col).upper()
        if "ISO" in col_upper or "27001" in col_upper or "SOURCE" in col_upper:
            iso_col = col
        elif "BSI" in col_upper or "C5" in col_upper or "TARGET" in col_upper:
            target_col = col

    if iso_col and target_col:
        for _, row in df.iterrows():
            iso_val = str(row[iso_col]).strip() if pd.notna(row[iso_col]) else ""
            target_val = str(row[target_col]).strip() if pd.notna(row[target_col]) else ""

            if iso_val and target_val and iso_val != "nan" and target_val != "nan":
                mappings.append({"source": iso_val, "target": target_val})
                if not any(c["control_id"] == target_val for c in controls):
                    controls.append({
                        "control_id": target_val,
                        "title": f"Control {target_val}",
                        "category": "",
                    })

    return ParseOutput(
        success=True,
        controls=controls,
        mappings=mappings,
        raw_text=f"Parsed {len(df)} rows, columns: {list(df.columns)}",
    )


# ---------------------------------------------------------------------------
# BSI C5:2020 PDF parser
# ---------------------------------------------------------------------------

_C5_CRITERION_PATTERN = re.compile(
    r"\b([A-Z]{2,4}-\d{2})\b"
)
_C5_DOMAINS = {
    "OIS": "Organisation of Information Security",
    "AM": "Asset Management",
    "ATM": "Attack and Threat Management",
    "SIM": "Security Incident Management",
    "COS": "Cryptography and Operational Security",
    "SCC": "Supply Chain and Contractor Management",
    "PI": "Physical Infrastructure",
    "RB": "Regulated Borders",
    "KOS": "Key Management and Operation Security",
    "BCM": "Business Continuity Management",
    "SLA": "Service Levels",
    "SP": "Service Provisioning",
    "SA": "Security Architecture",
    "INF": "Infrastructure and Network",
    "ICT": "ICT Infrastructure",
}


def _parse_c5_pdf(content: bytes, doc_type: str) -> ParseOutput:
    """Parse BSI C5:2020 standalone PDF.

    Extracts criteria IDs (OIS-01, AM-01, …) with titles and descriptions
    by scanning each page for the pattern DOMAIN-NN followed by text content.
    Also extracts ISO 27001 cross-references where present.
    """
    controls: list[dict] = []
    mappings: list[dict] = []
    seen_ids: set[str] = set()
    seen_mappings: set[tuple] = set()
    all_text_parts: list[str] = []

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            # Try table extraction first (C5 uses tables)
            tables = page.extract_tables() or []
            for table in tables:
                for row in table:
                    if not row:
                        continue
                    cells = [str(c).strip() if c else "" for c in row]
                    # First non-empty cell is usually the criterion ID
                    ctrl_id = ""
                    title = ""
                    description = ""
                    iso_refs: list[str] = []

                    for i, cell in enumerate(cells):
                        m = _C5_CRITERION_PATTERN.match(cell)
                        if m and m.group(1) in cell and len(cell) < 20:
                            ctrl_id = m.group(1)
                        elif ctrl_id and not title and len(cell) > 3 and len(cell) < 200:
                            title = cell
                        elif ctrl_id and not description and len(cell) > 10:
                            description = cell[:500]
                        # Look for ISO refs in any cell
                        iso_refs.extend(_ISO_ANNEX_PATTERN.findall(cell))

                    if ctrl_id and ctrl_id not in seen_ids:
                        seen_ids.add(ctrl_id)
                        cat_match = re.match(r"([A-Z]+)", ctrl_id)
                        domain_prefix = cat_match.group(1) if cat_match else ""
                        controls.append({
                            "control_id": ctrl_id,
                            "title": title or f"C5 {ctrl_id}",
                            "description": description,
                            "category": _C5_DOMAINS.get(domain_prefix, domain_prefix),
                        })
                        for iso_ref in set(iso_refs):
                            key = (iso_ref, ctrl_id)
                            if key not in seen_mappings:
                                seen_mappings.add(key)
                                mappings.append({"source": iso_ref, "target": ctrl_id})

            # Also grab raw text for text-based fallback
            text = page.extract_text() or ""
            all_text_parts.append(text)

    # Text-based fallback if tables yielded nothing
    if not controls:
        full_text = "\n".join(all_text_parts)
        lines = full_text.split("\n")
        current_id = None
        current_title = ""
        current_desc_lines: list[str] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^([A-Z]{2,4}-\d{2})\s+(.*)", line)
            if m:
                # Save previous
                if current_id and current_id not in seen_ids:
                    seen_ids.add(current_id)
                    cat_match = re.match(r"([A-Z]+)", current_id)
                    domain_prefix = cat_match.group(1) if cat_match else ""
                    controls.append({
                        "control_id": current_id,
                        "title": current_title,
                        "description": " ".join(current_desc_lines)[:500],
                        "category": _C5_DOMAINS.get(domain_prefix, domain_prefix),
                    })
                current_id = m.group(1)
                current_title = m.group(2)[:200]
                current_desc_lines = []
            elif current_id and len(line) > 10:
                iso_refs = _ISO_ANNEX_PATTERN.findall(line)
                for iso_ref in iso_refs:
                    key = (iso_ref, current_id)
                    if key not in seen_mappings:
                        seen_mappings.add(key)
                        mappings.append({"source": iso_ref, "target": current_id})
                current_desc_lines.append(line)

        if current_id and current_id not in seen_ids:
            cat_match = re.match(r"([A-Z]+)", current_id)
            domain_prefix = cat_match.group(1) if cat_match else ""
            controls.append({
                "control_id": current_id,
                "title": current_title,
                "description": " ".join(current_desc_lines)[:500],
                "category": _C5_DOMAINS.get(domain_prefix, domain_prefix),
            })

    full_text = "\n".join(all_text_parts)
    return ParseOutput(
        success=True,
        controls=controls,
        mappings=mappings,
        raw_text=full_text[:5000],
    )


# ---------------------------------------------------------------------------
# BSI IT-Grundschutz Kompendium module PDF parser (individual module PDFs)
# ---------------------------------------------------------------------------

_BSI_MODULE_ID_RE = re.compile(
    r"^([A-Z]{2,5}\.\d+(?:\.\d+)?)\s+(.+)"
)
_BSI_REQUIREMENT_RE = re.compile(
    r"^([A-Z]{2,5}\.\d+(?:\.\d+)?\.A\d+)\s+(.+?)(?:\s+\[.+?\])?\s*\(([BSH])\)\s*$"
)
_BSI_REQUIREMENT_LOOSE = re.compile(
    r"([A-Z]{2,5}\.\d+(?:\.\d+)?\.A\d+)\s+([^\n]{5,120})"
)
_PROTECTION_LEVEL = {"B": "Basic", "S": "Standard", "H": "High"}


def _parse_bsi_module_pdf(content: bytes, doc_type: str) -> ParseOutput:
    """Parse a BSI IT-Grundschutz Kompendium module PDF (individual module file).

    Extracts requirements (APP.1.1.A1 …) with titles, protection levels (B/S/H),
    and descriptions. No mappings are produced — use the Zuordnungstabelle for those.
    """
    controls: list[dict] = []
    seen_ids: set[str] = set()
    all_text_parts: list[str] = []

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_text_parts.append(text)

    full_text = "\n".join(all_text_parts)
    lines = full_text.split("\n")

    module_id = ""
    module_title = ""
    # Try to detect the module ID from the first few lines
    for line in lines[:20]:
        m = _BSI_MODULE_ID_RE.match(line.strip())
        if m:
            prefix = m.group(1).split(".")[0]
            if prefix in _BSI_MODULE_PREFIXES and ".A" not in m.group(1):
                module_id = m.group(1)
                module_title = m.group(2).strip()
                break

    current_req_id = None
    current_req_title = ""
    current_level = ""
    current_desc_lines: list[str] = []

    def _flush_req():
        if current_req_id and current_req_id not in seen_ids:
            seen_ids.add(current_req_id)
            controls.append({
                "control_id": current_req_id,
                "title": current_req_title,
                "description": " ".join(current_desc_lines)[:600],
                "category": module_id or current_req_id.rsplit(".A", 1)[0],
                "protection_level": _PROTECTION_LEVEL.get(current_level, current_level),
            })

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Strict pattern: "APP.1.1.A1 Title [Role] (B)"
        m = _BSI_REQUIREMENT_RE.match(stripped)
        if m:
            _flush_req()
            current_req_id = m.group(1)
            current_req_title = m.group(2).strip()
            current_level = m.group(3)
            current_desc_lines = []
            continue

        # Loose pattern: "APP.1.1.A1 Title ..." without protection level at end
        m2 = _BSI_REQUIREMENT_LOOSE.match(stripped)
        if m2 and ".A" in m2.group(1):
            _flush_req()
            current_req_id = m2.group(1)
            current_req_title = m2.group(2).strip()
            current_level = ""
            current_desc_lines = []
            continue

        if current_req_id:
            # Stop accumulating description when hitting the next section header
            if re.match(r"^\d+(\.\d+)*\s+[A-Z]", stripped) and len(stripped) < 60:
                _flush_req()
                current_req_id = None
                current_desc_lines = []
            else:
                current_desc_lines.append(stripped)

    _flush_req()

    return ParseOutput(
        success=len(controls) > 0,
        controls=controls,
        mappings=[],
        raw_text=full_text[:5000],
        error="" if controls else "No BSI requirements found. Check that this is a BSI IT-Grundschutz module PDF.",
    )


# ---------------------------------------------------------------------------
# Register built-in parsers
# ---------------------------------------------------------------------------

register_parser(
    name="BSI Zuordnungstabelle",
    extensions=[".pdf"],
    parse_fn=_parse_bsi_zuordnung_pdf,
    description="BSI IT-Grundschutz Zuordnungstabelle (ISO 27001 ↔ BSI mapping PDF)",
)

register_parser(
    name="C5 PDF",
    extensions=[".pdf"],
    parse_fn=_parse_c5_pdf,
    description="BSI C5:2020 standalone criteria PDF (extracts C5 criteria + ISO cross-refs)",
)

register_parser(
    name="BSI IT-Grundschutz Module",
    extensions=[".pdf"],
    parse_fn=_parse_bsi_module_pdf,
    description="BSI IT-Grundschutz Kompendium individual module PDF (e.g. APP.1.1, SYS.1.2)",
)

register_parser(
    name="C5 Cross-Reference",
    extensions=[".xlsx", ".xls"],
    parse_fn=_parse_excel,
    description="BSI C5 or generic Excel cross-reference table",
)

register_parser(
    name="CSV Mapping",
    extensions=[".csv"],
    parse_fn=_parse_csv,
    description="Simple CSV with source/target control ID columns",
)


# ---------------------------------------------------------------------------
# Legacy aliases (so existing imports still work)
# ---------------------------------------------------------------------------

def parse_bsi_zuordnung_pdf(content: bytes, doc_type: str) -> dict:
    return _parse_bsi_zuordnung_pdf(content, doc_type).to_dict()


def parse_excel(content: bytes, doc_type: str) -> dict:
    return _parse_excel(content, doc_type).to_dict()


def parse_csv(content: bytes, doc_type: str) -> dict:
    return _parse_csv(content, doc_type).to_dict()
