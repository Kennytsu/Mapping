# Handover Notes

This document is for whoever picks up this project next.

---

## What this is

A prototype compliance mapping tool built for IBM. It helps security and compliance teams work across multiple frameworks — ISO 27001, BSI IT-Grundschutz, C5:2020 — by:

- Showing which controls overlap between frameworks
- Identifying gaps (controls with no mapping)
- Using AI to propose new mappings where none exist
- Checking whether an existing policy document already covers unmapped controls

It was built as a working prototype, not a production system. The focus was on demonstrating the full pipeline end-to-end with real frameworks and real data.

---

## Current state

**What works:**

- Control lookup across all three frameworks with descriptions
- Coverage analysis: pick two frameworks, see % mapped, where gaps are
- AI-assisted mapping using SBERT semantic similarity (fast, free, runs in the container)
- Policy gap check using the ARC pipeline (for unstructured text like policy documents)
- Importing new framework documents: BSI module PDFs, C5 criteria PDF, Excel, CSV
- File upload (PDF/DOCX/TXT) to populate policy and regulation text fields
- Full mapping table with filter by type/confidence, CSV and Excel export
- Description quality warning — alerts users when a framework has sparse descriptions that will reduce mapping accuracy
- LLM pluggable registry: Bedrock (Claude Sonnet 4.6), watsonx.ai, OpenAI, Ollama, or rule-based fallback

**Known gaps (by design for POC):**

- No authentication. Anyone with the URL has full access.
- NLP (spaCy + SBERT) runs in the same process as the API. Fine for one user, will block under load.
- ISO 27001 descriptions are partially seeded — the full standard is proprietary (ISO charges for it). Mappings against ISO will be lower quality until descriptions are enriched.
- No LLM response caching. Same compliance check = same API cost each time.
- `app.py` handles all routes in one file. Works fine at this scale, but would need splitting for a real product.

---

## Repo structure

```
app.py                  All API routes
database.py             SQLAlchemy ORM models + async session setup
document_parser.py      Pluggable parser registry (add new formats here)
llm_providers.py        Pluggable LLM registry (add new providers here)
arc_pipeline.py         Extracts structured obligations from regulation text
static_layer.py         Term/definition extraction (static knowledge layer)
dynamic_layer.py        Eventic graph construction (dynamic knowledge layer)
compliance_checker.py   Orchestrates the full compliance reasoning pipeline
mapping_engine.py       Regulation-to-regulation mapping via ARC + SBERT
seed_data.py            Seeds ISO 27001 framework and controls
seed_bsi_demo.py        Seeds BSI IT-Grundschutz controls and official mappings
seed_c5_demo.py         Seeds C5:2020 controls, ISO descriptions, and C5↔ISO mappings
docker-compose.yml      App + PostgreSQL (pgvector)
static/                 Frontend: single HTML page, app.js, style.css
alembic/                Database migrations
tests/                  pytest suite
docs/                   This folder
data/demo/              Demo files for testing the policy check
```

---

## Key design decisions to be aware of

**Registry pattern for parsers and LLM providers.** Both `document_parser.py` and `llm_providers.py` use a registry. Adding a new format or provider is a few lines in one file — no routing code changes needed. See `docs/ARCHITECTURE.md` for details.

**SBERT for structured controls, ARC for unstructured text.** The framework-to-framework mapping uses SBERT directly on control titles and descriptions. The policy gap check and regulation-text mapping use the ARC pipeline first (to extract semantic structure) then SBERT. This split is intentional — see `docs/ARCHITECTURE.md` for the reasoning.

**Mapping quality depends on description richness.** A mapping between "A.5.1" and "OIS-01" is only as good as the descriptions stored for those controls. The UI now warns users when a framework has sparse descriptions. The fix is to import the full framework document via the Import tab.

---

## How to run

See `README.md`. Short version:

```bash
cp .env.example .env          # fill in API keys
docker-compose up --build
docker exec mapping-app-1 alembic upgrade head
docker exec mapping-app-1 python seed_data.py
docker exec mapping-app-1 python seed_bsi_demo.py
docker exec mapping-app-1 python seed_c5_demo.py
```

App runs at http://localhost:8001. API docs at http://localhost:8001/docs.

---

## Enriching ISO 27001 descriptions

ISO 27001:2022 is a paid standard. Our seed data only has control IDs and titles. To get better mapping quality:

1. Obtain the standard through your organisation's license
2. Use the API to update descriptions directly:

```bash
PATCH /api/mappings/{mapping_id}
# or add a bulk-update endpoint — see next steps doc
```

Or write a seed script following the pattern of `seed_c5_demo.py` that reads from a local file you have legitimate access to.

---

## Contacts / context

- Built as an IBM prototype, June 2026
- GitHub: https://github.com/Kennytsu/Mapping
