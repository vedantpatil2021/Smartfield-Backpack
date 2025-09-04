FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

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
    rsync \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.10 1

RUN python3 -m pip install --upgrade pip setuptools wheel

WORKDIR /app

RUN mkdir -p /app/logs

COPY requirements.txt .

RUN pip3 install --no-cache-dir fastapi uvicorn[standard] toml python-multipart opencv-python

RUN pip3 install --no-cache-dir --verbose parrot-olympe>=7.7.0

RUN apt-get update && apt-get install -y \
    wireless-tools \
    net-tools \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

ENV LD_LIBRARY_PATH=/usr/local/lib/python3.10/dist-packages/olympe_deps:/usr/local/lib:$LD_LIBRARY_PATH
ENV PYTHONPATH=/app:$PYTHONPATH

COPY . .

RUN ls -la /app/ && echo "Mission directory contents:" && ls -la /app/mission/ || echo "Mission directory not found"

RUN useradd -m -u 1000 droneuser && \
    chown -R droneuser:droneuser /app

RUN python3 -c "import olympe; print('Olympe imported successfully')"

USER droneuser

EXPOSE 2177

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:2177/ || exit 1

CMD ["python3", "main.py"]
