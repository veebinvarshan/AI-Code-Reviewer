FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
# main.py looks for ../frontend relative to itself, i.e. /frontend
COPY frontend/ /frontend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/api/health').raise_for_status()" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
