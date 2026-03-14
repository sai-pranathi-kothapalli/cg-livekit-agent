# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

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

# Install dependencies
# Copy only requirements first for better caching
COPY agent/requirements.txt /app/agent/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/agent/requirements.txt

# Copy the agent and backend code
# The agent depends on 'app.*' modules from the backend
COPY agent /app/agent
COPY backend /app/backend

# Set the working directory to the agent folder
WORKDIR /app/agent

# Run the agent
# The mode 'dev' is used to connect to LiveKit Cloud
CMD ["python", "agent.py", "dev"]
