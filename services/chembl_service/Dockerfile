FROM python:3.9-slim

WORKDIR /app

# Install required system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Generate Python code from proto files
COPY chembl_service.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. chembl_service.proto

# Copy the rest of the application
COPY . .

# Expose both REST and gRPC ports
EXPOSE 8003 50051

# Start the application
CMD ["python", "app.py"]