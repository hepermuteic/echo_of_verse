FROM python:3.14-slim
WORKDIR /service
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
COPY app ./app
COPY config/services.example.toml ./config/services.example.toml
ENV EOV_DB_PATH=/service/data/demo.sqlite3
COPY content ./content
EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
