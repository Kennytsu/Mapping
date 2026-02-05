FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py database.py document_parser.py ./
COPY static/ ./static/

ENV PORT=5000
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

EXPOSE 5000

CMD ["python", "app.py"]
