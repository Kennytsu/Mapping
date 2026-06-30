FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    python -m spacy download en_core_web_sm

COPY app.py database.py document_parser.py llm_providers.py seed_data.py seed_bsi_demo.py seed_c5_demo.py ./
COPY arc_pipeline.py static_layer.py dynamic_layer.py compliance_checker.py mapping_engine.py ./
COPY static/ ./static/
COPY alembic/ ./alembic/
COPY alembic.ini ./

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
