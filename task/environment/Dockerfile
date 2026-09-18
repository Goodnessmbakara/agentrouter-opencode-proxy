FROM python:3.11-slim

WORKDIR /repo

# Copy the full repository at the pinned commit
COPY proxy.py pyproject.toml start.sh ./
COPY task/ task/

# Install all dependencies at build time so nothing needs the network at runtime
RUN pip install --no-cache-dir \
    'fastapi>=0.111' \
    'uvicorn[standard]>=0.30' \
    'httpx>=0.27' \
    'anthropic==0.49.0' \
    pytest

# Set a dummy API key (the mock upstream doesn't check it)
ENV AGENTROUTER_API_KEY=sk-test-dummy-key-for-offline

# Default: run the test harness
CMD ["python", "task/environment/test_harness.py"]
