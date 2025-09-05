# Dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Copy only what's needed to install
COPY pyproject.toml README.md ./
COPY miqa_offline ./miqa_offline
COPY run-miqa.py ./run-miqa.py

# Install your package (creates the `miqa-offline` CLI)
RUN pip install --no-cache-dir .

# Run the same command users run locally
ENTRYPOINT ["miqa-offline"]
