# =============================================================================
# MKW Stats Bot - Simplified Railway Dockerfile
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    libgeos-dev \
    build-essential \
    gcc \
    g++ \
    wget \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV QT_QPA_PLATFORM=offscreen
ENV MPLBACKEND=Agg

# Copy and install requirements
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install paddlepaddle==3.0.0b2 && \
    pip install -r requirements.txt

# Copy application
COPY . .

# Create directories
RUN mkdir -p output .paddleocr

# Simple verification
RUN python -c "import paddle; print('PaddlePaddle OK')"

# Run the bot
CMD ["python", "main.py"]