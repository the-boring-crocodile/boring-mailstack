# Playwright for browser checks (tests/browser); base image pinned by digest.
FROM mcr.microsoft.com/playwright/python@sha256:98e88016a5705def757564f70469e80161c4e4dbf787bbe35a710fabb70bb7da
RUN pip install --break-system-packages --no-cache-dir playwright==1.55.0 && python3 -c "import playwright"
