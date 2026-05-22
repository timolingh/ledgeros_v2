FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     DJANGO_SETTINGS_MODULE=config.settings.local

WORKDIR /app

RUN apt-get update     && apt-get install -y --no-install-recommends build-essential libpq-dev     && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
RUN pip install --no-cache-dir -e ".[dev]"

COPY . /app/

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
