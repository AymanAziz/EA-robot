FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 papertrade
WORKDIR /app
COPY pyproject.toml requirements.txt requirements.lock.txt ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini .env.example ./
COPY .streamlit ./.streamlit
RUN python -m pip install --no-cache-dir -r requirements.lock.txt \
    && python -m pip install --no-cache-dir --no-deps . && mkdir -p /app/var \
    && chown -R papertrade:papertrade /app
USER papertrade
CMD ["papertrade", "run-once"]
