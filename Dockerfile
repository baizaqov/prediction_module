FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org -r requirements.txt

COPY app ./app

EXPOSE 8100

# Порт берётся из SERVER_PORT (в кластере общий ConfigMap задаёт 8080, как у всех
# сервисов); локально по умолчанию 8100.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${SERVER_PORT:-8100}"]
