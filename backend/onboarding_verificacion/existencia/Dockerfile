# Imagen del backend de verificación de existencia (FastAPI).
FROM python:3.11-slim

WORKDIR /app

# Dependencias primero (mejor caché de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código del submódulo
COPY . .

# Railway inyecta $PORT; uvicorn debe escuchar en 0.0.0.0:$PORT
ENV PORT=8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
