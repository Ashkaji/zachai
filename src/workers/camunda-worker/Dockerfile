FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY provision_label_studio.py lora_pipeline.py run_workers.py README.md ./

CMD ["python", "-u", "run_workers.py"]
