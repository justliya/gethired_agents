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
echo "PORT environment variable: ${PORT:-3000}"\n\
\n\
# Use PORT env var from Cloud Run for MCP\n\
export PORT=${PORT:-3000}\n\
export MCP_HTTP_PORT=${PORT}\n\
export SPEAKER_PORT=8001\n\
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
  if [ -f "/secrets/firebase/key" ]; then\n\
    cp /secrets/firebase/key /app/secrets/firebase-service-account.json\n\
    export FIREBASE_SERVICE_ACCOUNT_KEY="/app/secrets/firebase-service-account.json"\n\
    export SERVICE_ACCOUNT_KEY_PATH="/app/secrets/firebase-service-account.json"\n\
    echo "Firebase service account key configured"\n\
  fi\n\
  \n\
  # Copy Google application credentials if it exists\n\
  if [ -f "/secrets/google/key" ]; then\n\
    cp /secrets/google/key /app/secrets/google-application-credentials.json\n\
    export GOOGLE_APPLICATION_CREDENTIALS="/app/secrets/google-application-credentials.json"\n\
    echo "Google application credentials configured"\n\
  fi\n\
  \n\
  # If no separate Google creds, fall back to Firebase key\n\
  if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ] && [ -f "/app/secrets/firebase-service-account.json" ]; then\n\
    export GOOGLE_APPLICATION_CREDENTIALS="/app/secrets/firebase-service-account.json"\n\
    echo "Using Firebase service account key as fallback for Google credentials"\n\
  fi\n\
else\n\
  echo "=== No secrets directory found ==="\n\
  echo "Using local files if available for development"\n\
fi\n\
\n\
# Print environment info (without exposing secrets)\n\
echo "=== Environment Configuration ==="\n\
echo "PORT (for MCP): ${PORT}"\n\
echo "MCP_HTTP_PORT: ${MCP_HTTP_PORT}"\n\
echo "SPEAKER_PORT (coordinator): ${SPEAKER_PORT}"\n\
echo "MCP_TRANSPORT: ${MCP_TRANSPORT:-http}"\n\
echo "GOOGLE_CLOUD_PROJECT: $GOOGLE_CLOUD_PROJECT"\n\
echo "FIREBASE_STORAGE_BUCKET: $FIREBASE_STORAGE_BUCKET"\n\
echo "GOOGLE_APPLICATION_CREDENTIALS set: $([ ! -z \"$GOOGLE_APPLICATION_CREDENTIALS\" ] && echo \"yes\" || echo \"no\")"\n\
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
# Start Firebase MCP on the PORT that Cloud Run expects\n\
echo "=== Starting Firebase MCP on port ${MCP_HTTP_PORT} ==="\n\
MCP_HTTP_PORT=${MCP_HTTP_PORT} MCP_TRANSPORT=${MCP_TRANSPORT:-http} npx @gannonh/firebase-mcp &\n\
MCP_PID=$!\n\
echo "Firebase MCP started with PID: $MCP_PID"\n\
\n\
# Wait for MCP to be ready\n\
if wait_for_service "http://localhost:${MCP_HTTP_PORT}/health" || wait_for_service "http://localhost:${MCP_HTTP_PORT}"; then\n\
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
  if [ ! -z "$COORDINATOR_PID" ]; then\n\
    echo "Stopping Coordinator (PID: $COORDINATOR_PID)"\n\
    kill $COORDINATOR_PID 2>/dev/null || true\n\
  fi\n\
  exit 0\n\
}\n\
\n\
# Set up signal handlers\n\
trap cleanup SIGTERM SIGINT\n\
\n\
# Start coordinator on internal port 8001\n\
echo "=== Starting Coordinator on port ${SPEAKER_PORT} ==="\n\
python3 -m coordinator --port ${SPEAKER_PORT} --host 0.0.0.0 &\n\
COORDINATOR_PID=$!\n\
echo "Coordinator started with PID: $COORDINATOR_PID"\n\
\n\
# Keep the container running and forward signals\n\
wait $MCP_PID $COORDINATOR_PID\n\
' > /app/start.sh && chmod +x /app/start.sh

# Start the application
CMD ["/app/start.sh"]