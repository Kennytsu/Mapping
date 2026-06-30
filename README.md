# Compliance Mapping Tool

Maps security controls between ISO 27001, BSI IT-Grundschutz, and C5. Uses NLP to extract obligations from regulation text, then an LLM to check if a business process actually meets them.

## Setup

You need Docker Desktop running. That's it.

```bash
docker-compose up --build
docker exec mapping-app-1 python seed_data.py
docker exec mapping-app-1 python seed_bsi_demo.py
docker exec mapping-app-1 python seed_c5_demo.py
```

Open http://localhost:8001.

## What does this thing actually do?

Three main jobs:

1. **Control mapping** — You have ISO 27001 controls and BSI controls. The tool finds which ones overlap using semantic similarity (SBERT). You can also upload official mapping tables (Excel/PDF) to import known mappings directly.

2. **Compliance checking** — Paste regulation text + a business process description. The system extracts what the regulation *requires* (obligations, prohibitions, rights), then asks an LLM whether the business process satisfies those requirements.

3. **Tracking** — Each mapping gets a status (implemented / partial / not implemented), an owner, evidence notes. So you can use it as a living compliance register.

## How the backend works

The compliance check pipeline has a few stages. Here's the short version:

```
Regulation text
  → split into sentences (spaCy)
  → classify each sentence: is it a definition? an obligation? a right?
  → store as structured "ARC tuples"
  → build a graph of who-must-do-what

Business process text
  → split into chunks
  → for each chunk, find the most relevant obligations from the graph (cosine similarity)
  → bundle the chunk + matched obligations + definitions into a prompt
  → send to LLM → get back "compliant / non-compliant / undetermined" + explanation
```

The files that do this:

- `arc_pipeline.py` — sentence splitting + classification + tuple extraction
- `dynamic_layer.py` — builds the obligation graph from tuples
- `static_layer.py` — pulls out term definitions (so the LLM knows what "personal data" means legally)
- `compliance_checker.py` — orchestrates the matching and LLM call
- `mapping_engine.py` — compares two regulations to find overlapping controls

## LLM providers

Set `LLM_PROVIDER` in `.env`. Options:

| Provider | What you need |
|----------|---------------|
| `bedrock` | AWS credentials + model ID (Claude Sonnet 4.6) |
| `openai` | API key |
| `watsonx` | IBM Cloud API key + project ID |
| `ollama` | Local Ollama running |
| `rule_based` | Nothing — uses heuristics, less accurate but free |

## File layout

```
app.py                  ← all API routes live here
database.py             ← SQLAlchemy models
document_parser.py      ← pluggable parser registry (add new formats here)
llm_providers.py        ← pluggable LLM registry (add new providers here)
arc_pipeline.py         ← extracts structured data from regulation text
static_layer.py         ← term/definition extraction
dynamic_layer.py        ← obligation graph construction
compliance_checker.py   ← the actual compliance reasoning
mapping_engine.py       ← auto-generates control mappings via SBERT
seed_data.py            ← populates ISO 27001 framework + controls
seed_bsi_demo.py        ← populates BSI controls + official mappings
seed_c5_demo.py         ← populates C5 controls + ISO descriptions + C5↔ISO mappings
docker-compose.yml      ← runs app + PostgreSQL
static/                 ← frontend (single HTML page + JS + CSS)
tests/                  ← pytest suite (~154 tests)
```

## Database

PostgreSQL with pgvector. Main tables:

- `frameworks` — ISO 27001, BSI IT-Grundschutz, C5
- `controls` — individual controls with embeddings
- `mappings` — links between controls (with confidence score + status)
- `regulation_documents` — full regulation text for compliance checking
- `arc_tuples` — extracted obligations/definitions/rights

## Running tests

```bash
python -m pytest tests/ -x -q
```

## What's NOT done (POC scope)

- No auth. Anyone with the URL can access everything.
- NLP runs synchronously — fine for one user, will block under load.
- No caching of LLM responses (same check = same cost every time).
- Document parser handles specific formats (BSI Zuordnungstabelle PDF, C5 criteria PDF, BSI IT-Grundschutz module PDF, structured Excel). It won't magically parse any random PDF.

## UI structure

The frontend has five tabs:

| Tab | What it does |
|-----|-------------|
| **Lookup** | Search any control by ID/title, view its description and existing mappings |
| **Coverage** | Pick two frameworks → shows mapping coverage %, gaps, and next-step actions |
| **Mappings** | Full mapping table with sort/filter/export — populated after a coverage analysis |
| **Import** | Upload official docs (BSI PDFs, Excel, CSV) to add controls and mappings to the DB |
| **AI Mapping** | Generate new mappings: either between existing frameworks (SBERT) or from raw regulation text (ARC pipeline) |

## Adding stuff

**New LLM provider** — open `llm_providers.py` and add three things:

```python
def _my_provider_factory():
    # return a client object, or None if not configured
    ...

def _my_provider_reason(prompt: str, client) -> dict:
    # call the API, return {"judgment": "...", "explanation": "..."}
    ...

register_provider("my_provider", _my_provider_factory, _my_provider_reason, "_is_my_provider")
```

Then set `LLM_PROVIDER=my_provider` in `.env`. Done. No other files need changing.

**New document parser** — open `document_parser.py` and add:

```python
def _parse_my_format(content: bytes, doc_type: str) -> ParseOutput:
    # parse the bytes, return ParseOutput(success=True, controls=[...], mappings=[...])
    ...

register_parser(
    name="My Format",
    extensions=[".xlsx"],
    parse_fn=_parse_my_format,
    description="Description shown in the upload dropdown",
)
```

The upload API and `/api/parsers` endpoint pick it up automatically.

**New framework** — either write a seed script (copy `seed_bsi_demo.py`), or use the upload tab with a properly formatted Excel/CSV.
