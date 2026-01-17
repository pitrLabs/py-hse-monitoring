FROM python:3.13-alpine3.23
WORKDIR /app

COPY . /app/

RUN apk update && apk add --no-cache \
    curl gcc g++ make cmake pkgconfig \
    openssl-dev cyrus-sasl-dev \
    bash \
    musl-dev linux-headers

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PATH="/root/.local/bin:$PATH"

RUN uv sync