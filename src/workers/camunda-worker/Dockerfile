FROM python:3.11-slim

WORKDIR /app

COPY workers/camunda-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY workers/camunda-worker/provision_label_studio.py workers/camunda-worker/lora_pipeline.py workers/camunda-worker/deploy_bpmn.py workers/camunda-worker/run_workers.py workers/camunda-worker/README.md ./
COPY bpmn ./bpmn

CMD ["python", "-u", "run_workers.py"]
