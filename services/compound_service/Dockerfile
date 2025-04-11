FROM python:3.9-slim

WORKDIR /app

# Install required system dependencies for RDKit and gRPC
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libglib2.0-0 \
    libxrender1 \
    libxext6 \
    libsm6 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ChEMBL service proto file and generate Python code
COPY chembl_service.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chembl_service.proto

# Copy the rest of the application
COPY . .

# Expose the service port
EXPOSE 8001

# Start the application
CMD ["python", "app.py"]