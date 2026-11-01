# Playwright for browser checks (tests/browser); base image pinned by digest.
# The tag names the line the digest belongs to and must match the pip
# package below: without it Dependabot proposed the untagged image's digest,
# an older v1.46.
FROM mcr.microsoft.com/playwright/python:v1.64.1-jammy@sha256:d64f6b212d8ebb4ae25bfaeef820351bf79e562aa5d3c754b072ec16168de010
RUN pip install --break-system-packages --no-cache-dir playwright==1.55.0 && python3 -c "import playwright"
