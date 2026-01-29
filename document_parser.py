"""
Document parser for BSI compliance documents.
Extracts controls and mappings from PDF and Excel files.
"""

import re
import pandas as pd
import pdfplumber
from io import BytesIO


def parse_uploaded_file(uploaded_file, doc_type: str) -> dict:
    """
    Parse an uploaded file and extract controls/mappings.
    """
    filename = uploaded_file.name.lower()
    
    try:
        if filename.endswith('.pdf'):
            return parse_bsi_zuordnung_pdf(uploaded_file, doc_type)
        elif filename.endswith(('.xlsx', '.xls')):
            return parse_excel(uploaded_file, doc_type)
        elif filename.endswith('.csv'):
            return parse_csv(uploaded_file, doc_type)
        else:
            return {"success": False, "error": f"Unsupported file type: {filename}"}
    except Exception as e:
        return {"success": False, "error": str(e), "raw_text": ""}


def parse_bsi_zuordnung_pdf(uploaded_file, doc_type: str) -> dict:
    """
    Parse BSI Zuordnungstabelle PDF - specifically designed for this document format.
    The PDF has a two-column layout: ISO controls on left, BSI controls on right.
    """
    controls = []
    mappings = []
    all_text = []
    seen_bsi = set()
    seen_mappings = set()
    
    # ISO Annex A control pattern: A.5.1, A.8.12, etc.
    iso_pattern = re.compile(r'A\.(\d+)\.(\d+)')
    
    # BSI patterns
    bsi_module_pattern = re.compile(r'\b([A-Z]{2,5}\.\d+(?:\.\d+)?)\b')  # ISMS.1, ORP.4, NET.1.1
    bsi_req_pattern = re.compile(r'\b([A-Z]{2,5}\.\d+(?:\.\d+)?\.A\d+)\b')  # ISMS.1.A3, ORP.4.A2
    
    with pdfplumber.open(BytesIO(uploaded_file.read())) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_text.append(text)
    
    full_text = "\n".join(all_text)
    
    # Split into sections by ISO control
    # Look for patterns like "A.5.1 " or "A.8.12 "
    sections = re.split(r'(A\.\d+\.\d+\s)', full_text)
    
    current_iso = None
    
    for i, section in enumerate(sections):
        # Check if this is an ISO control marker
        iso_match = re.match(r'A\.(\d+)\.(\d+)\s*$', section.strip())
        if iso_match:
            current_iso = f"A.{iso_match.group(1)}.{iso_match.group(2)}"
            continue
        
        if current_iso and section.strip():
            # Find all BSI controls in this section
            bsi_reqs = bsi_req_pattern.findall(section)
            bsi_modules = bsi_module_pattern.findall(section)
            
            # Add BSI requirements as controls
            for bsi_ctrl in bsi_reqs:
                if bsi_ctrl not in seen_bsi:
                    seen_bsi.add(bsi_ctrl)
                    # Extract category from control ID
                    category_match = re.match(r'([A-Z]+)', bsi_ctrl)
                    category = category_match.group(1) if category_match else ""
                    
                    controls.append({
                        "control_id": bsi_ctrl,
                        "title": f"BSI {bsi_ctrl}",
                        "category": category
                    })
                
                # Add mapping
                mapping_key = (current_iso, bsi_ctrl)
                if mapping_key not in seen_mappings:
                    seen_mappings.add(mapping_key)
                    mappings.append({
                        "source": current_iso,
                        "target": bsi_ctrl
                    })
            
            # Also add module-level controls if not already covered
            for bsi_mod in bsi_modules:
                # Skip if it's actually a requirement (has .A in it)
                if '.A' in bsi_mod:
                    continue
                if bsi_mod not in seen_bsi:
                    seen_bsi.add(bsi_mod)
                    category_match = re.match(r'([A-Z]+)', bsi_mod)
                    category = category_match.group(1) if category_match else ""
                    
                    controls.append({
                        "control_id": bsi_mod,
                        "title": f"BSI Module {bsi_mod}",
                        "category": category
                    })
    
    # Also try a simpler line-by-line approach for the main ISO/BSI table
    lines = full_text.split('\n')
    current_iso = None
    
    for line in lines:
        # Check for ISO control at start of line
        iso_start = re.match(r'^A\.(\d+)\.(\d+)\s+(.+)', line)
        if iso_start:
            current_iso = f"A.{iso_start.group(1)}.{iso_start.group(2)}"
            rest_of_line = iso_start.group(3)
            
            # Find BSI controls in the rest of the line
            for bsi_ctrl in bsi_req_pattern.findall(rest_of_line):
                mapping_key = (current_iso, bsi_ctrl)
                if mapping_key not in seen_mappings:
                    seen_mappings.add(mapping_key)
                    mappings.append({
                        "source": current_iso,
                        "target": bsi_ctrl
                    })
                    
                    if bsi_ctrl not in seen_bsi:
                        seen_bsi.add(bsi_ctrl)
                        category_match = re.match(r'([A-Z]+)', bsi_ctrl)
                        controls.append({
                            "control_id": bsi_ctrl,
                            "title": f"BSI {bsi_ctrl}",
                            "category": category_match.group(1) if category_match else ""
                        })
        
        elif current_iso:
            # Continuation lines - look for BSI controls
            for bsi_ctrl in bsi_req_pattern.findall(line):
                mapping_key = (current_iso, bsi_ctrl)
                if mapping_key not in seen_mappings:
                    seen_mappings.add(mapping_key)
                    mappings.append({
                        "source": current_iso,
                        "target": bsi_ctrl
                    })
                    
                    if bsi_ctrl not in seen_bsi:
                        seen_bsi.add(bsi_ctrl)
                        category_match = re.match(r'([A-Z]+)', bsi_ctrl)
                        controls.append({
                            "control_id": bsi_ctrl,
                            "title": f"BSI {bsi_ctrl}",
                            "category": category_match.group(1) if category_match else ""
                        })
    
    return {
        "success": True,
        "controls": controls,
        "mappings": mappings,
        "raw_text": full_text[:10000]
    }


def parse_excel(uploaded_file, doc_type: str) -> dict:
    """Parse an Excel file for controls and mappings."""
    controls = []
    mappings = []
    
    xlsx = pd.ExcelFile(BytesIO(uploaded_file.read()))
    
    patterns = {
        "iso": re.compile(r'(A\.(\d+)\.(\d+)(?:\.(\d+))?)'),
        "bsi": re.compile(r'(([A-Z]{2,5})\.(\d+)(?:\.(\d+))?(?:\.A(\d+))?)'),
        "c5": re.compile(r'(([A-Z]{2,4})-(\d{2}))'),
    }
    
    for sheet_name in xlsx.sheet_names:
        df = pd.read_excel(xlsx, sheet_name=sheet_name)
        
        iso_col = None
        target_col = None
        
        for col in df.columns:
            col_str = str(col).upper()
            if 'ISO' in col_str or '27001' in col_str:
                iso_col = col
            elif 'BSI' in col_str or 'GRUNDSCHUTZ' in col_str or 'C5' in col_str or 'CRITERIA' in col_str:
                target_col = col
        
        if iso_col and target_col:
            for _, row in df.iterrows():
                iso_val = str(row[iso_col]) if pd.notna(row[iso_col]) else ""
                target_val = str(row[target_col]) if pd.notna(row[target_col]) else ""
                
                iso_matches = patterns["iso"].findall(iso_val)
                
                if "BSI" in doc_type:
                    target_matches = patterns["bsi"].findall(target_val)
                else:
                    target_matches = patterns["c5"].findall(target_val)
                
                for iso_m in iso_matches:
                    iso_id = iso_m[0]
                    for target_m in target_matches:
                        target_id = target_m[0]
                        mappings.append({"source": iso_id, "target": target_id})
                        
                        category = target_m[1] if len(target_m) > 1 else ""
                        if not any(c["control_id"] == target_id for c in controls):
                            controls.append({
                                "control_id": target_id,
                                "title": f"Control {target_id}",
                                "category": category
                            })
    
    seen_mappings = set()
    unique_mappings = []
    for m in mappings:
        key = (m["source"], m["target"])
        if key not in seen_mappings:
            seen_mappings.add(key)
            unique_mappings.append(m)
    
    return {
        "success": True,
        "controls": controls,
        "mappings": unique_mappings,
        "raw_text": f"Parsed {len(xlsx.sheet_names)} sheets"
    }


def parse_csv(uploaded_file, doc_type: str) -> dict:
    """Parse a CSV file for controls and mappings."""
    df = pd.read_csv(BytesIO(uploaded_file.read()))
    
    controls = []
    mappings = []
    
    iso_col = None
    target_col = None
    
    for col in df.columns:
        col_str = str(col).upper()
        if 'ISO' in col_str or '27001' in col_str or 'SOURCE' in col_str:
            iso_col = col
        elif 'BSI' in col_str or 'C5' in col_str or 'TARGET' in col_str:
            target_col = col
    
    if iso_col and target_col:
        for _, row in df.iterrows():
            iso_val = str(row[iso_col]).strip() if pd.notna(row[iso_col]) else ""
            target_val = str(row[target_col]).strip() if pd.notna(row[target_col]) else ""
            
            if iso_val and target_val and iso_val != 'nan' and target_val != 'nan':
                mappings.append({"source": iso_val, "target": target_val})
                
                if not any(c["control_id"] == target_val for c in controls):
                    controls.append({
                        "control_id": target_val,
                        "title": f"Control {target_val}",
                        "category": ""
                    })
    
    return {
        "success": True,
        "controls": controls,
        "mappings": mappings,
        "raw_text": f"Parsed {len(df)} rows, columns: {list(df.columns)}"
    }


def extract_mappings_from_text(text: str) -> list[dict]:
    """Extract mappings from plain text."""
    mappings = []
    
    iso_pattern = re.compile(r'(A\.(\d+)\.(\d+))')
    bsi_pattern = re.compile(r'([A-Z]{2,5}\.\d+(?:\.\d+)?\.A\d+)')
    
    lines = text.split('\n')
    for line in lines:
        iso_matches = iso_pattern.findall(line)
        bsi_matches = bsi_pattern.findall(line)
        
        for iso_m in iso_matches:
            for bsi_m in bsi_matches:
                mappings.append({"source": iso_m[0], "target": bsi_m})
    
    return mappings
