# Compliance Mapping Tool

Maps controls between ISO 27001, BSI IT-Grundschutz, and C5 compliance frameworks.

## Quick Start

### Option 1: Run with Python

```bash
pip install -r requirements.txt
python app.py
```

App runs at **http://localhost:5000**

### Option 2: Run with Podman

```bash
# Build the image
podman build -t compliance-mapping .

# Run the container
podman run -d -p 5000:5000 --name compliance-app compliance-mapping
```

App runs at **http://localhost:5000**

To stop: `podman stop compliance-app`

---

## Features

### 1. Control Lookup
Search any control ID (e.g., `A.5.1`) to see equivalent controls in other frameworks.

### 2. Upload Documents
Upload BSI mapping PDFs or Excel files to import new controls and mappings.

---

## Project Structure

```
Mapping/
├── app.py              # Flask backend API
├── database.py         # SQLite operations
├── document_parser.py  # PDF/Excel parsing
├── static/
│   ├── index.html      # Frontend HTML
│   ├── style.css       # Styles
│   └── app.js          # Frontend JavaScript
├── Containerfile       # Podman container definition
├── compliance.db       # Database (auto-created)
└── requirements.txt    # Python dependencies
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/frameworks` | List all frameworks |
| GET | `/api/controls?q=search` | Search controls |
| GET | `/api/mappings/{control_id}` | Get mappings for a control |
| POST | `/api/upload` | Upload and parse a document |
| POST | `/api/import` | Import parsed data to database |

---

## How the PDF Parsing Works

The BSI Zuordnungstabelle PDF has a two-column structure with ISO controls on the left and BSI controls on the right:

```
A.5.1 Policies for information security
    ISMS.1.A3 Erstellung einer Leitlinie zur Informationssicherheit
    ORP.1.A1 Festlegung von Verantwortlichkeiten
    ISMS.1.A1 Übernahme der Gesamtverantwortung
A.5.2 Information security roles...
    ISMS.1.A4 Benennung eines Informationssicherheitsbeauftragten
```

### Parsing Steps

**Step 1: Extract text from PDF**

Uses `pdfplumber` to extract all text from each page:

```python
with pdfplumber.open(pdf_file) as pdf:
    for page in pdf.pages:
        text = page.extract_text()
```

**Step 2: Detect ISO controls using regex**

Matches patterns like `A.5.1`, `A.8.12`:

```python
iso_pattern = re.compile(r'A\.(\d+)\.(\d+)')
```

**Step 3: Detect BSI controls using regex**

Matches patterns like `ISMS.1.A3`, `ORP.4.A2`, `NET.1.1.A5`:

```python
bsi_req_pattern = re.compile(r'\b([A-Z]{2,5}\.\d+(?:\.\d+)?\.A\d+)\b')
```

**Step 4: Associate BSI controls with current ISO control**

- When parser sees `A.5.1`, it sets `current_iso = "A.5.1"`
- Every BSI control found until the next ISO control gets mapped to it
- Result: `A.5.1 → ISMS.1.A3`, `A.5.1 → ORP.1.A1`, etc.

**Step 5: Deduplicate**

- Uses `seen_mappings` set to avoid duplicate mappings
- Uses `seen_bsi` set to avoid duplicate controls

### Data Flow

```
┌─────────────────────────────────────┐
│     BSI PDF / Excel Upload          │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│        Document Parser              │
│  - pdfplumber extracts text         │
│  - Regex finds ISO controls (A.X.Y) │
│  - Regex finds BSI controls         │
│  - Creates control-to-control maps  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│        SQLite Database              │
│  - frameworks table                 │
│  - controls table                   │
│  - mappings table                   │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     Flask API + HTML/JS UI          │
│  - Search controls                  │
│  - View cross-framework mappings    │
└─────────────────────────────────────┘
```

---

## Data Sources

- [BSI Zuordnungstabelle (ISO to IT-Grundschutz)](https://www.bsi.bund.de/SharedDocs/Downloads/DE/BSI/Grundschutz/IT-GS-Kompendium/Zuordnung_ISO_und_IT_Grundschutz_Edit_6.pdf)
- [C5 Cross-Reference Tables](https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/CloudComputing/ComplianceControlsCatalogue/2020/C5_2020_Reference_Tables_ISO27001.html)

When BSI releases new editions, upload the new PDFs to update mappings.
