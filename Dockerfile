FROM python:3.12.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system rootlens \
    && useradd --system --gid rootlens --create-home rootlens

WORKDIR /app

COPY pyproject.toml requirements.lock README.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir --constraint requirements.lock .

USER rootlens

EXPOSE 8000

CMD ["uvicorn", "rootlens.main:app", "--host", "0.0.0.0", "--port", "8000"]
