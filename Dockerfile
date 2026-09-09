FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py seed.py ./

ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000

VOLUME ["/app/data", "/app/uploads"]

CMD ["python", "run.py"]
