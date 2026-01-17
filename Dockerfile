FROM python:3.13-alpine3.23
WORKDIR /app

COPY . /app/

RUN apt-get update && apt-get install -y \
    curl gcc g++ make cmake pkg-config \
    libssl-dev libsasl2-dev \
    bash

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PATH="/root/.local/bin:$PATH"

RUN uv sync