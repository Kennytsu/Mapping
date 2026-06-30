# Next Steps

Prioritised list of what to build next, split by effort and impact.

---

## High priority — before any real deployment

### 1. Authentication
There is currently no auth. Anyone with the URL can read, write, and delete everything.

Options ranked by effort:
- **OAuth2 / OIDC** — integrate with your company's identity provider (Azure AD, Okta). FastAPI has built-in OAuth2 support.
- **API key auth** — simpler, sufficient for an internal tool. Add a middleware that checks `Authorization: Bearer <key>`.
- **Basic auth** — one username/password for the whole team. Fastest to ship, least secure.

Files to touch: `app.py` (add dependency/middleware), `static/app.js` (pass token on requests).

### 2. Async NLP
spaCy and SBERT run synchronously in FastAPI async routes. One heavy request blocks all others.

Fix: wrap NLP calls in `asyncio.to_thread()`:

```python
result = await asyncio.to_thread(process_regulation, text)
```

Or move NLP to a background task queue (Celery + Redis) for proper decoupling.

Files to touch: `app.py` routes that call `compliance_checker`, `mapping_engine`, `arc_pipeline`.

---

## Medium priority — quality and usability

### 3. Bulk control description enrichment
ISO 27001 controls only have titles in the DB — no descriptions — which degrades SBERT mapping quality. Add an endpoint and UI to bulk-update descriptions from a CSV or pasted text.

```
POST /api/frameworks/{id}/enrich-descriptions
Body: [{"control_id": "A.5.1", "description": "..."}]
```

The UI could be a simple CSV upload or textarea in the Import tab.

### 4. Mapping review workflow
AI-suggested mappings have no approval step. A compliance person should be able to accept, reject, or edit each proposed mapping before it becomes "official".

Suggest adding:
- A `status` field on mappings: `proposed | accepted | rejected`
- A review queue view (filter by `status = proposed`)
- Bulk accept/reject with a comment

### 5. LLM response caching
The same compliance check prompt costs the same every time. Cache by `hash(regulation_text + business_text + llm_provider)` in Redis or a DB table.

### 6. Export to compliance register
Users should be able to export a full gap report (framework, unmapped controls, suggested actions) as a formatted PDF or Excel file — not just raw CSV.

---

## Lower priority — nice to have

### 7. Split app.py into route modules
`app.py` is ~2000 lines. For a team working in parallel this becomes a merge conflict problem. Split by domain:

```
routes/
  frameworks.py
  controls.py
  mappings.py
  coverage.py
  regulations.py
  ai_mapping.py
```

FastAPI's `APIRouter` makes this straightforward.

### 8. Version tracking UI
The `version_changes` DB table and `/api/versions/` endpoints exist and work. The UI tab was removed to simplify the prototype but the backend is ready. This is useful for tracking when frameworks publish new versions (e.g. ISO 27001:2022 vs ISO 27001:2013).

### 9. Larger embedding model
`all-MiniLM-L6-v2` (384 dimensions) is fast but limited on longer control descriptions. For production with rich descriptions, consider:
- `all-mpnet-base-v2` — 768 dimensions, better quality, ~3× slower on CPU
- `text-embedding-3-small` (OpenAI) — API-based, no GPU needed, excellent quality

If you switch models, the stored embeddings in the DB become invalid and need re-computing.

### 10. Multi-user / tenant support
Right now all data is shared globally. For a real product you'd want:
- User accounts with the frameworks they care about
- Private mappings per user or team
- Audit log (who created/modified which mapping)

---

## Architecture improvements (for scale)

| What | Why | How |
|------|-----|-----|
| Vector database | pgvector works but Weaviate/Pinecone scale better | Replace `controls.embedding` queries with dedicated vector DB |
| GPU inference | SBERT on CPU is ~14ms/sentence, fine for POC | Add GPU node or use embedding API service |
| Celery task queue | Decouple long NLP jobs from request cycle | Replace sync NLP calls with Celery tasks + result polling |
| API versioning | `/api/v1/` prefix before any external integrations | FastAPI `prefix` on all routers |
| Rate limiting | Prevent abuse of LLM endpoints | `slowapi` or API gateway |
