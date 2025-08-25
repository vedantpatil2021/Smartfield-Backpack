FROM python:3.11-alpine

WORKDIR /app

RUN apk add --no-cache \
    gcc \
    g++ \
    make \
    musl-dev \
    libffi-dev \
    openssl-dev \
    linux-headers \
    curl

RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "subscriber.py"]