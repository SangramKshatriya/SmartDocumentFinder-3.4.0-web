FROM python:3.11-slim-bookworm

# ---------------------------------------------------------
# Python / Qt configuration
# ---------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    QT_QPA_PLATFORM=offscreen \
    TESSERACT_CMD=/usr/bin/tesseract

WORKDIR /app

# ---------------------------------------------------------
# System dependencies
# ---------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    portaudio19-dev \
    libglib2.0-0 \
    libdbus-1-3 \
    libfontconfig1 \
    libegl1 \
    libgl1 \
    libnss3 \
    libx11-xcb1 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    tesseract-ocr-mar \
    tesseract-ocr-guj \
    tesseract-ocr-tam \
    tesseract-ocr-tel \
    tesseract-ocr-kan \
    tesseract-ocr-mal \
    tesseract-ocr-ben \
    tesseract-ocr-pan \
    tesseract-ocr-ori \
    tesseract-ocr-asm \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------
COPY requirements.txt requirements-dev.txt ./

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install -r requirements-dev.txt

# ---------------------------------------------------------
# Application source
# ---------------------------------------------------------
COPY . .

# ---------------------------------------------------------
# Basic build validation
# ---------------------------------------------------------
RUN python -m compileall -q .

# ---------------------------------------------------------
# Run complete unit-test suite during image build
# ---------------------------------------------------------
RUN pytest -q

# ---------------------------------------------------------
# Runtime directories
# ---------------------------------------------------------
RUN mkdir -p /documents /app/data

VOLUME ["/documents", "/app/data"]

# ---------------------------------------------------------
# Default container action
# ---------------------------------------------------------
# Render starts the browser-facing Flask app. The desktop app remains available via `python app.py`.
EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120 web_app:app"]