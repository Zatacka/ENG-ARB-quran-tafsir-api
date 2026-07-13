FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md LICENSE DATA_NOTICE.md ./
COPY app ./app
COPY catalog ./catalog
COPY scripts ./scripts
COPY dataset ./dataset

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && python scripts/prepare_data.py \
    && python scripts/validate_data.py \
    && rm -rf dataset

RUN useradd --create-home --uid 10001 apiuser
USER apiuser

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
