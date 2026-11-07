# 1. Lightweight official Python 3.11 Linux image
FROM python:3.11-slim

# 2. Set working folder inside container
WORKDIR /app

# 3. Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy your renamed server file
COPY main.py .

# 5. Document port 8000
EXPOSE 8000

# 6. Run main:app on 0.0.0.0
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]