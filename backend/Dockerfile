FROM python:3.11-slim

# The app code lives at /app/backend/ so that 'from backend.xxx import ...' works
WORKDIR /app

# OS deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        libffi-dev \
        libssl-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 1. Install PyTorch CPU-only FIRST to avoid pulling CUDA drivers
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
        torch==2.3.1+cpu \
        --index-url https://download.pytorch.org/whl/cpu

# 2. Install sentence-transformers (will use the CPU torch above)
RUN pip install --no-cache-dir sentence-transformers==3.0.1

# 3. Install the rest of the backend dependencies
RUN pip install --no-cache-dir \
        fastapi \
        "uvicorn[standard]" \
        websockets \
        pydantic \
        "pydantic-settings" \
        langchain \
        langchain-openai \
        langchain-community \
        langgraph \
        openai \
        chromadb \
        rank-bm25 \
        sqlalchemy \
        asyncpg \
        "psycopg2-binary" \
        redis \
        celery \
        tenacity \
        httpx \
        beautifulsoup4 \
        pymupdf \
        pandas \
        matplotlib \
        structlog \
        "opentelemetry-sdk" \
        "opentelemetry-exporter-otlp" \
        thefuzz \
        python-multipart \
        hypothesis \
        pytest \
        pytest-asyncio

# 4. Pre-download the embedding model so it's baked into the image
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" || true

# Copy the backend source into /app/backend/
# This way 'from backend.config import ...' resolves to /app/backend/config.py
COPY . /app/backend/

EXPOSE 8080

CMD ["uvicorn", "backend.entrypoint:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "8080"]
