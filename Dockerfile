FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini .

RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn sarcade.api.app:app --host 0.0.0.0 --port 8000"]
