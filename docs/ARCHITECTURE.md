# Architecture Notes

How the compliance engine works under the hood, and why we made the choices we did.

---

## The big picture

We're solving two problems:

1. **"Which controls in framework A correspond to which controls in framework B?"** — This is the mapping problem. Security teams deal with multiple standards (ISO 27001, BSI, C5, SOC 2...) and need to know how they overlap.

2. **"Does our business process actually comply with this regulation?"** — This is the compliance checking problem. You have a regulation (like GDPR Article 32) and a description of what your company does, and you need to know if there's a gap.

---

## Mapping: how we compare controls

Simple approach: embed both controls with SBERT (`all-MiniLM-L6-v2`), compute cosine similarity, threshold at 0.5.

Why SBERT and not just keyword matching? Because "A.8.1 - Inventory of assets" and "ORP.1 - Organisation" are related even though they share zero words. Semantic embeddings capture that.

Why not just throw everything at an LLM? Cost and speed. Comparing 114 ISO controls against 200+ BSI controls means 22,800 pairs. At LLM prices that's expensive and slow. SBERT does it in seconds for free.

We still use ARC tuples when comparing *regulation text* (not just control titles). The idea: don't compare raw sentences, first extract what they're actually saying (who must do what), then compare those structured statements. This avoids false matches where two sentences sound similar but one is a definition and the other is an obligation.

---

## Compliance checking: the pipeline

This is the more interesting part. The flow:

### Step 1: Extract structure from regulation text

```
"The controller shall implement appropriate technical measures"
   → type: obligation
   → actor: controller
   → action: implement appropriate technical measures
   → modal: shall (mandatory)
```

We use spaCy for sentence splitting, then rule-based classification to sort statements into:
- **Obligations** (shall/must do X)
- **Prohibitions** (must not do X)
- **Rights** (subject has right to X)
- **Definitions** (term means X)

Why rule-based and not LLM? It's deterministic, instant, and free. For a POC that's fine. In production you'd probably want an LLM for the edge cases that rules miss.

### Step 2: Build an obligation graph

The extracted tuples get assembled into a directed graph:

```
[Organization] --duty--> [implement encryption]
[Organization] --duty--> [notify supervisory authority within 72h]
[Data subject] --right--> [obtain erasure of personal data]
[Organization] --prohibited--> [process data without legal basis]
```

Why a graph and not a flat list? Because obligations relate to each other. "You must notify the authority" connects to "you must detect breaches" — the graph lets us traverse those connections when reasoning about compliance.

### Step 3: Match business process to obligations

Take the business process text, split it into chunks, embed each chunk with SBERT, and find the most similar nodes in the obligation graph.

This gives us: "this chunk of your business process is most relevant to *these* specific obligations."

### Step 4: LLM reasoning

Now we have a focused prompt:

```
Here's what the business does: [chunk]
Here's what the regulation requires: [matched obligations]
Here's what it prohibits: [matched prohibitions]
Here's what these terms mean: [matched definitions]

Is the business compliant? Why or why not?
```

The LLM returns: compliant / non-compliant / undetermined + explanation.

The key insight: we don't ask the LLM to read the entire regulation. We pre-filter to only the relevant parts. This makes the prompt smaller, cheaper, and more accurate (less distraction).

### Fallback: rule-based reasoning

If no LLM is configured, we use heuristics:
- High similarity to a prohibition + no mitigation language → non-compliant
- High similarity to an obligation + positive action verbs → compliant
- Otherwise → undetermined

It's rough but it means the system works without API keys for testing.

---

## SBERT model choice

We use `all-MiniLM-L6-v2`:
- 384-dimensional embeddings
- ~14ms per sentence on CPU
- Good enough for short text (control titles, single sentences)
- Runs inside the container without GPU

For production with longer documents, you'd want something larger or a dedicated embedding service.

---

## Database design

PostgreSQL with pgvector extension. We store embeddings directly in the `controls` table so we can do similarity search in SQL if needed.

The schema is straightforward:
- `frameworks` → holds ISO 27001, BSI, C5 as entities
- `controls` → belongs to a framework, has title + description + embedding
- `mappings` → links two controls with a confidence score and metadata (source type: official / ai_suggested / manual)
- `regulation_documents` → stores full regulation text for compliance checking
- `arc_tuples` → the extracted obligations/definitions/rights from a regulation

Seed data:
- `seed_data.py` → creates the three frameworks + ISO 27001 controls
- `seed_bsi_demo.py` → creates BSI IT-Grundschutz controls + official ISO↔BSI mappings
- `seed_c5_demo.py` → creates 127 C5 controls, adds ISO 27001 descriptions, creates C5↔ISO mappings

---

## Trade-offs we made (and what to change in production)

| What we did | Why | What to do for real |
|-------------|-----|---------------------|
| spaCy rules for classification | Fast, deterministic, no API cost | Add LLM fallback for ambiguous cases |
| SBERT in-process | Simple, no extra service | GPU service or API (for throughput) |
| Sync NLP in async routes | Works fine for 1 user | Wrap in `asyncio.to_thread()` or use Celery |
| PostgreSQL for vectors | One database to manage | Consider Pinecone/Weaviate at scale |
| Pre-seeded control lists | Known-correct data for demo | Parse from official PDFs (or use the Import tab) |
| No auth | POC, single user | Add OAuth/OIDC before any real deployment |
| No LLM response caching | Simpler code | Cache by (regulation_hash + process_hash) |
| Single `app.py` for all routes | Fast iteration | Split into route modules by domain |
| `controls.embedding` not in initial migration | Column added after first cut | Done — migration 002 now handles it |

---

## Extending the system

Both the document parser and LLM provider system use a **registry pattern** — you register a new thing in one place and everything else picks it up.

### Adding a parser (`document_parser.py`)

Write a function `(content: bytes, doc_type: str) -> ParseOutput`, then call `register_parser(...)`. The upload API and the `/api/parsers` endpoint auto-discover it. No need to touch routing code.

### Adding an LLM provider (`llm_providers.py`)

Write a factory (returns client or None) and a reasoning function (takes prompt + client, returns judgment dict). Call `register_provider(...)`. The compliance checker dispatches to it automatically based on the marker attribute.

This means devs can add support for new services (Azure OpenAI, Google Vertex, Anthropic direct, etc.) without modifying the compliance logic or API layer.

### Text extraction from uploaded files (`/api/extract-text`)

Accepts `.pdf`, `.docx`, or `.txt` and returns plain text. Used by the frontend to populate policy/regulation textareas from uploaded files. Stateless — no DB writes. Uses `pdfplumber` for PDF and `python-docx` for Word.

---

## References

- ARC tuple extraction is inspired by Contextual Integrity (Nissenbaum) — formalizing information flows as (sender, receiver, data, condition)
- The RAG compliance approach follows work presented at COLING 2025 on retrieval-augmented compliance reasoning
- BSI IT-Grundschutz Kompendium: bsi.bund.de/grundschutz
- BSI C5:2020: bsi.bund.de/c5
- ISO/IEC 27001:2022
