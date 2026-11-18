# ----------------------------------------------------
# Stage 1: Build React Frontend
# ----------------------------------------------------
FROM node:20-slim AS frontend-builder
WORKDIR /build

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ----------------------------------------------------
# Stage 2: Python 3.11 ARM64 Backend & FFmpeg
# ----------------------------------------------------
FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies for dlib, opencv, ffmpeg and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    ffmpeg \
    fonts-montserrat \
    fonts-dejavu \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir dlib face-recognition

# Copy backend code and configuration
COPY backend/ ./backend/
COPY config/ ./config/
COPY .env .

# Copy compiled frontend from Stage 1 into backend static directory
COPY --from=frontend-builder /build/dist ./frontend/dist

# Expose ports
EXPOSE 8000

# Run FastAPI server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
