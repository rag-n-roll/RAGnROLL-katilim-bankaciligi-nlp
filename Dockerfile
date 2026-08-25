FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RAGNROLL_DB_PATH=/app/runtime/ragnroll.sqlite3 \
    RAGNROLL_RUNTIME_ROOT=/app/runtime \
    RAGNROLL_BOOTSTRAP_DATASET=/app/bootstrap/campaigns.json

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && python -c 'from importlib.util import find_spec; assert find_spec("dspy") is None; assert find_spec("gepa") is None'

COPY --chown=app:app src/ ./src/
COPY --chown=app:app scripts/ ./scripts/
COPY --chown=app:app configs/ ./configs/
COPY --chown=app:app data/ontology/ ./data/ontology/
# Runtime bütünlük kapısı yalnız beyan edilen eğitim lineage girdilerini doğrular.
COPY --chown=app:app \
    data/model_training_data/classifier_dataset_final.jsonl \
    data/model_training_data/ner_dataset_final.jsonl \
    data/model_training_data/training_dataset_manifest.json \
    ./data/model_training_data/
COPY --chown=app:app data/model_training_data/dspy_prompt_examples.manifest.json ./data/model_training_data/dspy_prompt_examples.manifest.json
COPY --chown=app:app data/processed/campaigns.json ./bootstrap/campaigns.json
COPY --chown=app:app prompts/ ./prompts/
COPY --chown=app:app models/ ./models/
RUN mkdir -p /app/runtime /app/chroma_db \
    && chown app:app /app/runtime /app/chroma_db

USER app
EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["python", "-m", "scripts.container_entrypoint"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
