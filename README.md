# Compliance Mapping Tool

Maps controls between ISO 27001, BSI IT-Grundschutz, and C5 compliance frameworks.

## Quick Start

```bash
pip install -r requirements.txt
python data_loader.py      # Load initial data
streamlit run app.py       # Start the app
```

App runs at `http://localhost:8501`

---

## How It Works

### Data Flow

```
                    ┌─────────────────────┐
                    │  BSI PDF / Excel    │
                    │  (upload new docs)  │
                    └──────────┬──────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────┐
│                  Document Parser                      │
│  - Extracts control IDs (A.5.1, ISMS.1.A1, OIS-01)  │
│  - Finds mappings in tables                          │
│  - Regex patterns for ISO, BSI, C5 formats          │
└──────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────┐
│                  SQLite Database                      │
│  - frameworks: ISO27001, BSI, C5                     │
│  - controls: all individual requirements             │
│  - mappings: links between controls                  │
└──────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────┐
│                  Streamlit UI                         │
│  - Search controls                                   │
│  - View mappings                                     │
│  - Coverage analysis                                 │
└──────────────────────────────────────────────────────┘
```

### Document Parsing

When you upload a BSI document (PDF or Excel), the parser:

1. **Scans for control IDs** using regex patterns:
   - ISO: `A.5.1`, `A.8.2.1`
   - BSI: `ISMS.1.A1`, `ORP.4.A2`
   - C5: `OIS-01`, `IDM-04`

2. **Extracts tables** (PDF) or **columns** (Excel) to find mappings

3. **Shows preview** before importing so you can verify

4. **Imports to database** when you confirm

---

## Features

### 1. Upload Documents (NEW)
Go to **Upload Documents** page to:
- Upload BSI Zuordnungstabelle PDF (new editions)
- Upload C5 cross-reference Excel
- Preview extracted data before importing
- Add manual mappings if parsing fails

### 2. Control Lookup
Search any control ID to see equivalent controls in other frameworks.

### 3. Coverage Analysis
Compare frameworks to see:
- Coverage percentage
- Unmapped controls
- Gap analysis

### 4. Version Migration
Track changes between BSI Kompendium versions.

---

## Adding New Data

### Option 1: Upload Document
1. Go to "Upload Documents" page
2. Select document type (BSI mapping, C5 mapping, etc.)
3. Upload PDF or Excel file
4. Review extracted controls and mappings
5. Click "Import to Database"

### Option 2: Manual Entry
1. Go to "Upload Documents" page
2. Scroll to "Manual Mapping Entry"
3. Enter source control (e.g., `A.5.1`)
4. Enter target control (e.g., `ISMS.1.A1`)
5. Select target framework
6. Click "Add Mapping"

### Option 3: CSV Import
Create a CSV with columns:
```csv
ISO,BSI
A.5.1,ISMS.1.A1
A.5.2,ORP.1.A1
```
Upload as "Custom Mapping Table"

---

## Project Structure

```
Mapping/
├── app.py              # Streamlit UI
├── database.py         # SQLite layer
├── document_parser.py  # PDF/Excel parsing
├── data_loader.py      # Initial data loading
├── compliance.db       # Database
└── requirements.txt
```

---

## Data Sources

Initial data based on:
- [BSI Zuordnungstabelle](https://www.bsi.bund.de/SharedDocs/Downloads/DE/BSI/Grundschutz/IT-GS-Kompendium/Zuordnung_ISO_und_IT_Grundschutz_Edit_6.pdf)
- [C5 Cross-Reference](https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/CloudComputing/ComplianceControlsCatalogue/2020/C5_2020_Reference_Tables_ISO27001.html)

When BSI releases new editions (2024, 2025...), upload the new PDFs to update the mappings.
