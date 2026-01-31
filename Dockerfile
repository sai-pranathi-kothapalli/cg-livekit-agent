# LiveKit Agent Worker
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents ./agents
COPY services ./services
COPY agent.py .

ENV PYTHONUNBUFFERED=1

# Worker expects backend on path when run; for Docker, backend is a separate service.
# Set LIVEKIT_AGENT_DISPATCH or run with backend mounted/copied if needed.
CMD ["python", "agent.py", "start"]
