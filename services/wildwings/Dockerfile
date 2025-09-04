FROM continuumio/miniconda3:latest

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies required for drone operations and video display
RUN apt-get update && apt-get install -y \
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
 xvfb \
 x11-utils \
 qtbase5-dev \
 libqt5gui5 \
 libqt5core5a \
 libqt5widgets5 \
 python3-pyqt5 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create directories for mission data and logs with full permissions
RUN mkdir -p /app/logs /app/missions /app/mission && \
    chmod -R 777 /app/logs /app/missions /app/mission

# Copy requirements first for better layer caching
COPY requirements.txt .

# Create conda environment with basic Python and common packages
RUN conda create --name wildwing python=3.11 -c conda-forge -y && \
    conda clean -afy

# Install packages via pip from requirements.txt in the conda environment
RUN /opt/conda/envs/wildwing/bin/pip install --no-cache-dir -r requirements.txt

# Make RUN commands use the new environment
SHELL ["conda", "run", "-n", "wildwing", "/bin/bash", "-c"]

# Set environment variables for olympe and display
ENV LD_LIBRARY_PATH=/opt/conda/envs/wildwing/lib/python3.11/site-packages/olympe_deps:/usr/local/lib:$LD_LIBRARY_PATH
ENV PYTHONPATH=/app:$PYTHONPATH
ENV DISPLAY=:99
ENV QT_QPA_PLATFORM=xcb

# Create user first
RUN useradd -m -u 1000 droneuser

# Copy application files
COPY . .

# Set permissions for all app files and ensure droneuser can write to missions and logs directories
RUN chown -R droneuser:droneuser /app && \
    chmod -R 777 /app && \
    chmod -R 777 /app/missions /app/logs /app/mission

# Test olympe import
RUN python -c "import olympe; print('Olympe imported successfully')"

USER droneuser

EXPOSE 2199

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:2199/ || exit 1

# Start Xvfb for video display and run the application
CMD ["bash", "-c", "mkdir -p /app/logs /app/missions /app/mission && chmod -R 777 /app/logs /app/missions /app/mission && Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 & conda run -n wildwing python main.py"]