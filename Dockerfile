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
EXPOSE 8003

# Create improved start script with better error handling and logging
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "=== Container Startup ==="\n\
echo "Time: $(date)"\n\
echo "Working directory: $(pwd)"\n\
echo "User: $(whoami)"\n\
echo "PORT environment variable: ${PORT:-8003}"\n\
\n\
# Use PORT env var from Cloud Run\n\
export PORT=${PORT:-8003}\n\
export SPEAKER_PORT=${PORT}\n\
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
echo "PORT: ${PORT}"\n\
echo "SPEAKER_PORT: ${SPEAKER_PORT}"\n\
echo "SPEAKER_HOST: ${SPEAKER_HOST:-0.0.0.0}"\n\
echo "GOOGLE_CLOUD_PROJECT: $GOOGLE_CLOUD_PROJECT"\n\
echo "FIREBASE_STORAGE_BUCKET: $FIREBASE_STORAGE_BUCKET"\n\
echo "GOOGLE_APPLICATION_CREDENTIALS set: $([ ! -z \"$GOOGLE_APPLICATION_CREDENTIALS\" ] && echo \"yes\" || echo \"no\")"\n\
\n\
# Start Firebase MCP in the background\n\
echo "=== Starting Firebase MCP ==="\n\
npx @gannonh/firebase-mcp &\n\
MCP_PID=$!\n\
echo "Firebase MCP started with PID: $MCP_PID"\n\
\n\
# Give MCP a moment to start\n\
sleep 5\n\
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
echo "=== Starting Job Search Agents Coordinator on port ${SPEAKER_PORT} ==="\n\
exec python3 -m jobsearch_agents.coordinator --port ${SPEAKER_PORT} --host ${SPEAKER_HOST:-0.0.0.0}\n\
' > /app/start.sh && chmod +x /app/start.sh

# Start the application
CMD ["/app/start.sh"]