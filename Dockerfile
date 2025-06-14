# Use Node.js 18 as base image
FROM node:18-slim

# Install Python and required dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install Node.js dependencies
RUN npm install

# Install the Firebase MCP package globally
RUN npm install -g @gannonh/firebase-mcp

# Copy Python requirements if exists
COPY requirements.txt* ./

# Create and activate virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip in virtual environment
RUN pip install --upgrade pip

# Install Python dependencies if requirements.txt exists
RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/secrets /tmp

# Expose port
EXPOSE 3000

# Create improved start script with better error handling and logging
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "=== Container Startup ==="\n\
echo "Time: $(date)"\n\
echo "Working directory: $(pwd)"\n\
echo "User: $(whoami)"\n\
\n\
# Function to wait for service\n\
wait_for_service() {\n\
  local url=$1\n\
  local max_attempts=30\n\
  local attempt=1\n\
  \n\
  echo "Waiting for service at $url..."\n\
  while [ $attempt -le $max_attempts ]; do\n\
    if curl -f -s "$url" > /dev/null 2>&1; then\n\
      echo "Service is ready!"\n\
      return 0\n\
    fi\n\
    echo "Attempt $attempt/$max_attempts failed, waiting 2 seconds..."\n\
    sleep 2\n\
    attempt=$((attempt + 1))\n\
  done\n\
  \n\
  echo "Service failed to start after $max_attempts attempts"\n\
  return 1\n\
}\n\
\n\
# Cloud Run mounts secrets to /secrets/<secret-name>/\n\
if [ -d "/secrets" ]; then\n\
  echo "=== Setting up secrets ==="\n\
  ls -la /secrets/\n\
  \n\
  # Create app secrets directory\n\
  mkdir -p /app/secrets\n\
  \n\
  # Copy Firebase service account key if it exists\n\
  if [ -f"/secrets/firebase/key"]; then\n\
   cp /secrets/google/key /app/secrets/google-application-credentials.json\n\
    export FIREBASE_SERVICE_ACCOUNT_KEY="/app/secrets/firebase-service-account.json"\n\
    export SERVICE_ACCOUNT_KEY_PATH="/app/secrets/firebase-service-account.json"\n\
    echo "Firebase service account key configured: $FIREBASE_SERVICE_ACCOUNT_KEY"\n\
  fi\n\
  \n\
  # Copy Google application credentials if it exists\n\
  if [ -f "/secrets/google/key" ]; then\n\
    cp /secrets/google-application-credentials /app/secrets/google-application-credentials.json\n\
    export GOOGLE_APPLICATION_CREDENTIALS="/app/secrets/google-application-credentials.json"\n\
    echo "Google application credentials configured: $GOOGLE_APPLICATION_CREDENTIALS"\n\
  fi\n\
  \n\
  # If no separate Google creds, fall back to Firebase key (if that is appropriate for your use case)\n\
  if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ] && [ -f "/app/secrets/firebase-service-account.json" ]; then\n\
    export GOOGLE_APPLICATION_CREDENTIALS="/app/secrets/firebase-service-account.json"\n\
    echo "Using Firebase service account key as fallback for Google credentials"\n\
  fi\n\
else\n\
  echo "=== No secrets directory found ==="\n\
  echo "Using local files if available for development"\n\
  \n\
  # Check for Firebase-specific credentials first\n\
  if [ -f "/app/firebase-service-account.json" ]; then\n\
    export FIREBASE_SERVICE_ACCOUNT_KEY="/app/firebase-service-account.json"\n\
    export SERVICE_ACCOUNT_KEY_PATH="/app/firebase-service-account.json"\n\
    echo "Using local Firebase service account key"\n\
  elif [ -f "/app/serviceAccountKey.json" ]; then\n\
    export FIREBASE_SERVICE_ACCOUNT_KEY="/app/serviceAccountKey.json"\n\
    export SERVICE_ACCOUNT_KEY_PATH="/app/serviceAccountKey.json"\n\
    echo "Using legacy local service account key for Firebase"\n\
  fi\n\
  \n\
  # Check for Google Cloud credentials\n\
  if [ -f "/app/google-application-credentials.json" ]; then\n\
    export GOOGLE_APPLICATION_CREDENTIALS="/app/google-application-credentials.json"\n\
    echo "Using local Google application credentials"\n\
  elif [ -f "/app/serviceKey.json" ]; then\n\
    export GOOGLE_APPLICATION_CREDENTIALS="/app/serviceKey.json"\n\
    echo "Using local serviceKey.json for Google credentials"\n\
  elif [ -f "/app/serviceAccountKey.json" ]; then\n\
    export GOOGLE_APPLICATION_CREDENTIALS="/app/serviceAccountKey.json"\n\
    echo "Fallback: Using serviceAccountKey.json for Google credentials"\n\
  fi\n\
fi\n\
\n\
# Print environment info (without exposing secrets)\n\
echo "=== Environment Configuration ==="\n\
echo "MCP_HTTP_PORT: ${MCP_HTTP_PORT:-3000}"\n\
echo "MCP_TRANSPORT: ${MCP_TRANSPORT:-http}"\n\
echo "GOOGLE_CLOUD_PROJECT: $GOOGLE_CLOUD_PROJECT"\n\
echo "FIREBASE_STORAGE_BUCKET: $FIREBASE_STORAGE_BUCKET"\n\
echo "GOOGLE_APPLICATION_CREDENTIALS: $GOOGLE_APPLICATION_CREDENTIALS"\n\
echo "SERVICE_ACCOUNT_KEY_PATH: $SERVICE_ACCOUNT_KEY_PATH"\n\
echo "FIREBASE_SERVICE_ACCOUNT_KEY: $FIREBASE_SERVICE_ACCOUNT_KEY"\n\
\n\
# Test Python configuration\n\
echo "=== Testing Python Configuration ==="\n\
python3 -c "import sys; print(f\"Python version: {sys.version}\")"\n\
if python3 -c "import firebase_admin" 2>/dev/null; then\n\
  echo "Firebase Admin SDK: ✓"\n\
else\n\
  echo "Firebase Admin SDK: ✗ (not installed)"\n\
fi\n\
\n\
# Start Firebase MCP in background\n\
echo "=== Starting Firebase MCP ==="\n\
MCP_HTTP_PORT=${MCP_HTTP_PORT:-3000} MCP_TRANSPORT=${MCP_TRANSPORT:-http} npx @gannonh/firebase-mcp &\n\
MCP_PID=$!\n\
echo "Firebase MCP started with PID: $MCP_PID"\n\
\n\
# Wait for MCP to be ready\n\
if wait_for_service "http://localhost:${MCP_HTTP_PORT:-3000}/health" || wait_for_service "http://localhost:${MCP_HTTP_PORT:-3000}"; then\n\
  echo "Firebase MCP is ready"\n\
else\n\
  echo "Warning: Firebase MCP health check failed, but continuing..."\n\
fi\n\
\n\
# Function to cleanup background processes\n\
cleanup() {\n\
  echo "=== Cleanup ==="\n\
  if [ ! -z "$MCP_PID" ]; then\n\
    echo "Stopping Firebase MCP (PID: $MCP_PID)"\n\
    kill $MCP_PID 2>/dev/null || true\n\
  fi\n\
  exit 0\n\
}\n\
\n\
# Set up signal handlers\n\
trap cleanup SIGTERM SIGINT\n\
\n\
# Start coordinator\n\
echo "=== Starting Coordinator ==="\n\
python3 -m coordinator &\n\
COORDINATOR_PID=$!\n\
echo "Coordinator started with PID: $COORDINATOR_PID"\n\
\n\
# Wait for coordinator to finish\n\
wait $COORDINATOR_PID\n\
echo "Coordinator finished"\n\
\n\
# Cleanup\n\
cleanup\n\
' > /app/start.sh && chmod +x /app/start.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:${MCP_HTTP_PORT:-3000}/health || exit 1

# Start the application
CMD ["/app/start.sh"]