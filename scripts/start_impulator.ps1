# PowerShell script to start IMPULATOR Microservices on Windows
# This script is intended to be run from the project root directory

Write-Host "Setting up IMPULATOR Microservices" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan

function Write-Section {
    param (
        [string]$Message
    )
    Write-Host
    Write-Host "===> $Message" -ForegroundColor Green
    Write-Host
}

# Check if Docker is running
Write-Section "Checking Docker"
try {
    docker info | Out-Null
    Write-Host "Docker is running." -ForegroundColor Green
}
catch {
    Write-Host "Docker is not running. Please start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

# Check if Docker Compose is installed
try {
    docker-compose --version | Out-Null
    Write-Host "Docker Compose is installed." -ForegroundColor Green
}
catch {
    Write-Host "Docker Compose is not found. Please ensure Docker Desktop is properly installed." -ForegroundColor Red
    exit 1
}

# Navigate to Docker directory
Set-Location -Path "docker"

# Stop any running containers
Write-Section "Stopping any running containers"
docker-compose down

# Remove existing volumes
Write-Section "Removing existing volumes"
$volumes = "docker_postgresql_data", "docker_mongodb_data", "docker_redis_data", "docker_rabbitmq_data"
foreach ($volume in $volumes) {
    try {
        docker volume rm $volume 2>$null
    }
    catch {
        # Ignore errors if volume doesn't exist
    }
}

# Start PostgreSQL container
Write-Section "Starting PostgreSQL container"
docker-compose up -d postgresql

# Wait for PostgreSQL to start
Write-Host "Waiting for PostgreSQL to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# Initialize the database schema
Write-Section "Initializing database schema"
$schemaPath = (Get-Location).Path + "\..\database\schema.sql"
$schemaPath = $schemaPath.Replace("\", "/") # Convert to Unix-like path for Docker

# Copy schema to container and execute
docker cp ..\database\schema.sql postgresql:/tmp/schema.sql
docker exec -it postgresql psql -U impulsor -d impulsor_db -f /tmp/schema.sql

# Check if schema was created successfully
Write-Host "Verifying database schema..." -ForegroundColor Yellow
docker exec -it postgresql psql -U impulsor -d impulsor_db -c "\dt"

# Create test user
Write-Section "Creating test user"
docker exec -it postgresql psql -U impulsor -d impulsor_db -c "
INSERT INTO Users (id, username, email, password_hash, role)
VALUES ('test_user', 'Test User', 'test@example.com', '`$2b`$10`$d9Jyv2p7HbsRzstRWM/U7uDYFW.ov1lxIGjctkk8qW7bPYc2S8Evy', 'user')
ON CONFLICT (username) DO NOTHING;
"

# Start all services
Write-Section "Starting all microservices"
docker-compose up -d

# Check if all containers are running
Write-Section "Checking container status"
docker-compose ps

# Display URLs for accessing services
Write-Section "Service URLs"
Write-Host "API Gateway:           http://localhost:8000" -ForegroundColor Cyan
Write-Host "Compound Service:      http://localhost:8001" -ForegroundColor Cyan
Write-Host "Analysis Service:      http://localhost:8002" -ForegroundColor Cyan
Write-Host "ChEMBL Service:        http://localhost:8003" -ForegroundColor Cyan
Write-Host "Visualization Service: http://localhost:8004" -ForegroundColor Cyan
Write-Host "RabbitMQ Management:   http://localhost:15672 (guest/guest)" -ForegroundColor Cyan

Write-Section "Setup Complete"
Write-Host "IMPULATOR microservices are now running." -ForegroundColor Green
Write-Host "Use the API Gateway at http://localhost:8000 to interact with the system." -ForegroundColor Green
Write-Host "To stop all services, run: docker-compose down" -ForegroundColor Yellow