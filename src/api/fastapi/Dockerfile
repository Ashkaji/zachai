FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY api/fastapi/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/fastapi/main.py .
COPY api/fastapi/keycloak_admin.py .
COPY api/fastapi/golden_set.py .
COPY api/fastapi/editor_ticket.py .
COPY bpmn/project-lifecycle.bpmn ./bpmn/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
