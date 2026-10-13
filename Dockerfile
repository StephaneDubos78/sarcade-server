FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini .

RUN pip install --no-cache-dir -e .

# Web client (browsers, ChromeOS PWA) served at "/". Empty URL = API only.
# Change SARCADE_WEB_CACHEBUST to fetch a newer client without --no-cache.
ARG SARCADE_WEB_URL=https://github.com/StephaneDubos78/sarcade-app/releases/download/web-dev/sarcade-web.tar.gz
ARG SARCADE_WEB_CACHEBUST=0
COPY docker/fetch_web_client.py /tmp/fetch_web_client.py
RUN echo "cachebust ${SARCADE_WEB_CACHEBUST}" && python /tmp/fetch_web_client.py "$SARCADE_WEB_URL" /app/web && rm /tmp/fetch_web_client.py
ENV SARCADE_WEB_ROOT=/app/web

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn sarcade.api.app:app --host 0.0.0.0 --port 8000"]
