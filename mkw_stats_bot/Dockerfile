# =============================================================================
# MKW Stats Bot - Railway-compatible Docker Configuration  
# =============================================================================
# This replicates Railway's headless environment for OpenCV/PaddleOCR testing

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for headless OpenCV and Tesseract
RUN apt-get update && apt-get install -y \
    # Tesseract OCR
    tesseract-ocr \
    tesseract-ocr-eng \
    # Essential build tools
    build-essential \
    pkg-config \
    # OpenCV headless dependencies (NO GUI libraries)
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgthread-2.0-0 \
    # Network and compression tools
    wget \
    curl \
    unzip \
    # Clean up to reduce image size
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && which tesseract && tesseract --version

# Set environment variables for headless operation (same as Railway)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DISPLAY=""
ENV QT_QPA_PLATFORM="offscreen"
ENV MPLBACKEND="Agg"
ENV OPENCV_IO_ENABLE_JASPER="false" 
ENV OPENCV_IO_ENABLE_OPENEXR="false"
ENV PADDLE_PDX_MODEL_SOURCE="BOS"

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python packages with proper OpenCV handling
RUN pip install --no-cache-dir --upgrade pip

# Install base dependencies first
RUN pip install --no-cache-dir \
    discord.py>=2.0.0 \
    numpy>=1.19.0 \
    Pillow>=8.0.0 \
    python-dotenv>=0.19.0 \
    psycopg2-binary>=2.9.0 \
    aiohttp>=3.8.0

# Install PaddleOCR (this will install opencv-python GUI version as dependency)
RUN pip install --no-cache-dir paddleocr>=2.7.0 paddlepaddle==2.6.0

# Copy application code BEFORE final OpenCV cleanup
COPY . .

# CRITICAL FIX: Remove GUI OpenCV and install headless version AFTER all dependencies
# This prevents the libGL.so.1 errors that occur in Railway
RUN pip uninstall -y opencv-python opencv-contrib-python || true
RUN pip install --no-cache-dir --force-reinstall opencv-contrib-python-headless>=4.5.0

# Verify OpenCV installation works in headless environment
RUN python -c "import cv2; print(f'✅ OpenCV version: {cv2.__version__}')"
RUN python -c "import numpy as np; import cv2; test = np.zeros((10,10,3), dtype=np.uint8); _ = cv2.cvtColor(test, cv2.COLOR_BGR2GRAY); print('✅ OpenCV functionality test passed')"

# Create output directory for OCR debug images
RUN mkdir -p output

# Test that PaddleOCR can initialize in this environment
RUN python -c "from paddleocr import PaddleOCR; ocr = PaddleOCR(lang='en', use_angle_cls=False, use_gpu=False); print('✅ PaddleOCR initialization successful')"

# Expose port (Railway will override this)
EXPOSE 8000

# Health check to verify dependencies are working
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import cv2; from paddleocr import PaddleOCR" || exit 1

# Run the application
CMD ["python", "main.py"]
