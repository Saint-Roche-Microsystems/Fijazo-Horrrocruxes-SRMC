FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VERSION=2.1.1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# Instala Poetry
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

# Instala dependencias (capa cacheable)
COPY pyproject.toml poetry.lock* README.md ./
COPY src ./src
RUN poetry install --only main --no-interaction --no-ansi

EXPOSE 8000

CMD ["uvicorn", "fijazo_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
