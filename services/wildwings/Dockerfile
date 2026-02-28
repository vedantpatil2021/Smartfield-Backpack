FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-venv \
    python3-pip \
    python3.10-dev \
    curl \
    wget \
    git \
    build-essential \
    cmake \
    pkg-config \
    libssl-dev \
    libffi-dev \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libsdl2-dev \
    libglfw3-dev \
    libgl1-mesa-dev \
    libegl1-mesa-dev \
    libgles2-mesa-dev \
    libx11-dev \
    libxrandr-dev \
    libxinerama-dev \
    libxcursor-dev \
    libxi-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libgstreamer-plugins-bad1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libjson-c-dev \
    libcurl4-gnutls-dev \
    libprotobuf-dev \
    libprotobuf-c-dev \
    protobuf-compiler \
    protobuf-c-compiler \
    wireless-tools \
    net-tools \
    iproute2 \
    rsync \
    # Add video/camera libraries
    v4l-utils \
    libv4l-dev \
    # Add X11 utilities for display
    x11-utils \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Set Python alternatives
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1
RUN python3 -m pip install --upgrade pip setuptools wheel

WORKDIR /app

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/mission /app/mission/images

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python packages
RUN pip3 install --no-cache-dir -r requirements.txt
RUN pip3 install --no-cache-dir --verbose parrot-olympe>=7.7.0

# Set library paths for Olympe
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.10/dist-packages/olympe_deps:/usr/local/lib:$LD_LIBRARY_PATH
ENV PYTHONPATH=/app:$PYTHONPATH

# Copy application code
COPY . .

RUN chmod +x /app/launch.sh

# Create user and set permissions
RUN useradd -m -u 1000 droneuser && \
    chown -R droneuser:droneuser /app

# Environment variables
ENV OLYMPE_LOG_LEVEL=WARNING
ENV PYTHONUNBUFFERED=1
ENV QT_X11_NO_MITSHM=1

# Test Olympe import
RUN python3 -c "import olympe; print('Olympe imported successfully')"

USER droneuser

EXPOSE 2199

# Use the wrapper script as entry point
CMD ["python3", "main.py"]