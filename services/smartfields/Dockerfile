FROM python:3.11-alpine

WORKDIR /app

# Install lightweight dependencies and build tools
RUN apk add --no-cache \
    curl \
    gcc \
    g++ \
    make \
    musl-dev \
    linux-headers \
    libffi-dev \
    openssl-dev \
    iproute2 \
    conntrack-tools \
    && pip install --upgrade pip setuptools wheel

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 2188

CMD ["python", "main.py"]