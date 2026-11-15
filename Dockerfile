FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY brain ./brain
COPY omar_core ./omar_core
EXPOSE 8080
CMD ["uvicorn", "omar_core.app:app", "--host", "0.0.0.0", "--port", "8080"]
