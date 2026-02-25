"""
Document parser for BSI compliance documents.
Extracts controls and mappings from PDF and Excel files.

All public functions accept raw bytes (not Flask/FastAPI file objects)
so they work from both the upload API and the CLI seed script.
"""

import re
from io import BytesIO

import pandas as pd
import pdfplumber


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_uploaded_bytes(content: bytes, filename: str, doc_type: str) -> dict:
    """Parse raw file bytes and return controls/mappings."""
    filename = filename.lower()
    try:
        if filename.endswith(".pdf"):
            return parse_bsi_zuordnung_pdf(content, doc_type)
        elif filename.endswith((".xlsx", ".xls")):
            return parse_excel(content, doc_type)
        elif filename.endswith(".csv"):
            return parse_csv(content, doc_type)
        else:
            return {"success": False, "error": f"Unsupported file type: {filename}"}
    except Exception as e:
        return {"success": False, "error": str(e), "raw_text": ""}


# ---------------------------------------------------------------------------
# BSI Zuordnungstabelle PDF parser
# ---------------------------------------------------------------------------

_ISO_PATTERN = re.compile(r"A\.(\d+)\.(\d+)")
_BSI_REQ_PATTERN = re.compile(r"\b([A-Z]{2,5}\.\d+(?:\.\d+)?\.A\d+)\b")
_BSI_MODULE_PATTERN = re.compile(r"\b([A-Z]{2,5}\.\d+(?:\.\d+)?)\b")
_BSI_STD_PATTERN = re.compile(r"(BSI-Standard\s+200-[1-4])")
_CLAUSE_START = re.compile(r"^(\d+(?:\.\d+)*)\s+[A-Z]")

_BSI_STD_TITLES = {
    "BSI-Std-200-1": "BSI-Standard 200-1: Managementsysteme fuer Informationssicherheit (ISMS)",
    "BSI-Std-200-2": "BSI-Standard 200-2: IT-Grundschutz-Methodik",
    "BSI-Std-200-3": "BSI-Standard 200-3: Risikoanalyse auf der Basis von IT-Grundschutz",
    "BSI-Std-200-4": "BSI-Standard 200-4: Business Continuity Management",
    "BSI-ElemGef": "Elementare Gefaehrdungen (G0) des IT-Grundschutz-Kompendiums",
}


def parse_bsi_zuordnung_pdf(content: bytes, doc_type: str) -> dict:
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
        """Extract BSI-Standard control IDs from a text block."""
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

    # Pre-create BSI-Standard controls
    for ctrl_id, title in _BSI_STD_TITLES.items():
        if ctrl_id not in seen_bsi:
            seen_bsi.add(ctrl_id)
            controls.append({
                "control_id": ctrl_id,
                "title": title,
                "category": "BSI-Standard",
            })

    # --- Pass 1: Parse clause section (ISO clauses 1-10 -> BSI-Standards) ---
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

    # --- Pass 2: Annex A section (A.X.Y -> IT-Grundschutz requirements) ---
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
                if ".A" not in bsi_mod and bsi_mod not in seen_bsi:
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

    return {
        "success": True,
        "controls": controls,
        "mappings": mappings,
        "raw_text": full_text[:10000],
    }


# ---------------------------------------------------------------------------
# C5 / generic Excel parser
# ---------------------------------------------------------------------------

_C5_REF_PATTERN = re.compile(r"([A-Z]{2,4})-(\d{2})")
_ISO_ANNEX_PATTERN = re.compile(r"(A\.\d+\.\d+)")
_ISO_CLAUSE_PATTERN = re.compile(r"(\d+\.\d+)")


def _extract_iso_refs(raw: str) -> list[str]:
    """
    Extract individual ISO 27001 references from a cell that may contain:
      - Specific controls: 'A.5.1', 'A.8.12'
      - Clause ranges: '4.1 - 10.2'
      - Multiple values separated by newlines or commas
      - Dashes meaning 'no mapping'
    """
    if not raw or raw.strip() in ("-", "n/a", "nan", ""):
        return []

    refs: list[str] = []
    # Annex A controls
    refs.extend(_ISO_ANNEX_PATTERN.findall(raw))
    # Clause references (non-Annex), e.g. "6.2", "4.3"
    for clause in _ISO_CLAUSE_PATTERN.findall(raw):
        full = clause
        if full not in refs and not any(full in r for r in refs):
            refs.append(full)
    return refs


def parse_excel(content: bytes, doc_type: str) -> dict:
    """
    Parse an Excel file for controls and mappings.
    Handles C5:2020 format (merged title row, actual headers on row 2).
    """
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
        # Deduplicate column names: rename duplicate by appending _N
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

            # Determine control format
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

    return {
        "success": True,
        "controls": controls,
        "mappings": mappings,
        "raw_text": f"Parsed {len(xlsx.sheet_names)} sheets, {len(controls)} controls, {len(mappings)} mappings",
    }


def _safe_str(row, col) -> str:
    """Safely extract a string value from a row, handling NaN and Series."""
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
    """Scan the first few rows to find the actual header row by best keyword match count."""
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
    """Map column names to semantic roles."""
    result: dict = {}
    ref_count = 0

    for col in columns:
        low = col.lower()
        if "ref" in low and "iso" not in low:
            if ref_count == 0:
                result.setdefault("ref", col)
            else:
                # Second "Ref" column is likely ISO ref (C5 format)
                result.setdefault("iso", col)
            ref_count += 1
        elif "title" in low:
            result.setdefault("title", col)
        elif "criteria" in low or "description" in low or "basic" in low:
            result.setdefault("description", col)
        elif "iso" in low or "27001" in low:
            result.setdefault("iso", col)

    if "ref" in result and "iso" in result:
        return result

    # Positional fallback: col0=ref, col1=title, col2=desc, col3=iso
    if len(columns) >= 4:
        return {
            "ref": columns[0],
            "title": columns[1],
            "description": columns[2],
            "iso": columns[3],
        }

    return None


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------

def parse_csv(content: bytes, doc_type: str) -> dict:
    """Parse a CSV file for controls and mappings."""
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

    return {
        "success": True,
        "controls": controls,
        "mappings": mappings,
        "raw_text": f"Parsed {len(df)} rows, columns: {list(df.columns)}",
    }
