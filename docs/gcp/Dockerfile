# Dockerfile for Gooaye transcription on GCP
# Optimized for GPU transcription with faster-whisper

FROM nvidia/cuda:12.1-cudnn8-runtime-ubuntu22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-pip \
    python3.11-venv \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Download Whisper model during build (so it's cached in the image)
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu')"

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p data/audio data/transcripts

# Default command
CMD ["python3", "run_pipeline.py"]
