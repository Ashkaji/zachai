FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY provision_label_studio.py .

CMD ["python", "-u", "provision_label_studio.py"]
