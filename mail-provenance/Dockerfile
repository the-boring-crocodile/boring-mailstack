FROM python:3.13-alpine@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a

RUN mkdir -p /config

WORKDIR /app

COPY provenance.py /app/provenance.py

ENTRYPOINT ["python", "/app/provenance.py"]
