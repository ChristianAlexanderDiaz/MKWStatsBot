# =============================================================================
# MKW Stats Bot - Railway-compatible Docker Configuration
# =============================================================================

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PaddleOCR and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core libraries for PaddleOCR
    libgomp1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1-mesa-glx \
    libgthread-2.0-0 \
    # Additional OpenCV dependencies
    libopencv-dev \
    libgeos-dev \
    # Build tools
    build-essential \
    gcc \
    g++ \
    pkg-config \
    # Network tools
    wget \
    curl \
    # Tesseract (if you still need it alongside PaddleOCR)
    tesseract-ocr \
    tesseract-ocr-eng \
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DISPLAY="" \
    QT_QPA_PLATFORM="offscreen" \
    MPLBACKEND="Agg" \
    OPENCV_IO_ENABLE_JASPER="false" \
    OPENCV_IO_ENABLE_OPENEXR="false" \
    # PaddleOCR model source
    PADDLE_HOME=/app/.paddleocr \
    HUB_HOME=/app/.paddlehub

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies in the correct order
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    # Install PaddlePaddle first (CPU version for Railway)
    pip install --no-cache-dir paddlepaddle==2.6.0 && \
    # Install core dependencies
    pip install --no-cache-dir \
        discord.py>=2.0.0 \
        numpy>=1.19.0,<2.0.0 \
        Pillow>=8.0.0 \
        python-dotenv>=0.19.0 \
        psycopg2-binary>=2.9.0 \
        aiohttp>=3.8.0 && \
    # Install OpenCV headless FIRST (before any other OpenCV variants)
    pip install --no-cache-dir opencv-contrib-python-headless==4.8.1.78 && \
    # Install PaddleOCR
    pip install --no-cache-dir "paddleocr>=2.7.0" && \
    # Install remaining requirements
    pip install --no-cache-dir -r requirements.txt || true && \
    # Clean up any non-headless OpenCV that might have been installed
    pip uninstall -y opencv-python opencv-contrib-python 2>/dev/null || true

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p output .paddleocr .paddlehub

# Verify installations
RUN python -c "import cv2; print(f'✅ OpenCV headless version: {cv2.__version__}')" && \
    python -c "import paddle; print(f'✅ PaddlePaddle version: {paddle.__version__}')" && \
    python -c "from paddleocr import PaddleOCR; print('✅ PaddleOCR import successful')"

# Test basic OpenCV functionality
RUN python -c "import numpy as np; import cv2; test = np.zeros((10,10,3), dtype=np.uint8); _ = cv2.cvtColor(test, cv2.COLOR_BGR2GRAY); print('✅ OpenCV functionality test passed')"

# Use Railway's PORT if provided, otherwise default to 8000
ARG PORT=8000
ENV PORT=$PORT
EXPOSE $PORT

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import cv2; from paddleocr import PaddleOCR; print('Health check passed')" || exit 1

# Run the Discord bot
CMD ["python", "main.py"]