# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV PYTHONPATH=/app/backend

# Set work directory
WORKDIR /app

# Install system dependencies
# gcc and python3-dev for building some wheels
# libav* for audio/video processing (livekit-agents/av)
# libgomp1 for onnxruntime (silero vad)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libavdevice-dev \
    libavfilter-dev \
    libavformat-dev \
    libavcodec-dev \
    libswresample-dev \
    libswscale-dev \
    libavutil-dev \
    pkg-config \
    libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 1. Copy agent code
COPY agent/ .

# 2. Copy shared abckend logic
# This is required for 'from app.config import...' to work
COPY backend/app ./backend/app

# Install dependencies
# If building from the agent-only repo, requirements.txt is at the root
COPY agent/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# IMPORTANT: The agent depends on the 'backend' folder for 'app.*' modules.
# Ensure the backend folder is copied or mounted.
# If you are building from the split repo, you must ensure a 'backend'
# folder exists in your build context.
# COPY backend /app/backend  <-- Uncomment if you copy/clone backend here

# Run the agent
CMD ["python", "agent.py", "dev"]
