FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install OS dependencies (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy script and dependencies
COPY run-miqa.py ./
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set default command
ENTRYPOINT ["python", "-u", "run-miqa.py"]

