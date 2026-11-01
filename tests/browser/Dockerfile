# Playwright for browser checks (tests/browser); base image pinned by digest.
# The tag names the line the digest belongs to and must match the pip
# package below: without it Dependabot proposed the untagged image's digest,
# an older v1.46.
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy@sha256:640d578aae63cfb632461d1b0aecb01414e4e020864ac3dd45a868dc0eff3078
RUN pip install --break-system-packages --no-cache-dir playwright==1.55.0 && python3 -c "import playwright"
