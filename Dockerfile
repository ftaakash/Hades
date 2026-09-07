FROM python:3.11-slim

WORKDIR /workspace

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# CDB must be mounted or cloned at runtime (repo is a separate dependency)
# docker run --mount type=bind,src=/path/to/cdb,dst=/cdb ...

ENV PYTHONPATH=/workspace:/cdb

CMD ["bash"]
