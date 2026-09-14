FROM python:3.12-slim

WORKDIR /app

# Install bash for CSPR script syntax validation
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agentic_studio ./agentic_studio
COPY scripts ./scripts

ENV PORT=8080
ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["sh", "-c", "uvicorn agentic_studio.api.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
