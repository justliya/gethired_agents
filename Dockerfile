# Use Node.js 18 as base image
FROM node:18-slim

# Install Python and required dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    nginx \
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

# Create nginx config
RUN echo 'server {\n\
    listen 3000;\n\
    \n\
    location /mcp {\n\
        proxy_pass http://localhost:8001;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
    }\n\
    \n\
    location / {\n\
        proxy_pass http://localhost:8003;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
    }\n\
}' > /etc/nginx/sites-available/default

# Expose port
EXPOSE 3000

# Create start script with nginx
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "=== Container Startup ==="\n\
echo "PORT: ${PORT:-3000}"\n\
\n\
# Setup secrets\n\
if [ -d "/secrets" ]; then\n\
  mkdir -p /app/secrets\n\
  [ -f "/secrets/firebase/key" ] && cp /secrets/firebase/key /app/secrets/firebase-service-account.json\n\
  [ -f "/secrets/google/key" ] && cp /secrets/google/key /app/secrets/google-application-credentials.json\n\
fi\n\
\n\
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-/app/secrets/firebase-service-account.json}"\n\
export MCP_HTTP_PORT=8001\n\
export SPEAKER_PORT=8003\n\
\n\
# Update nginx to listen on PORT\n\
sed -i "s/listen 3000;/listen ${PORT:-3000};/" /etc/nginx/sites-available/default\n\
\n\
# Start nginx\n\
nginx -g "daemon off;" &\n\
NGINX_PID=$!\n\
\n\
# Start MCP on internal port\n\
MCP_HTTP_PORT=8001 npx @gannonh/firebase-mcp &\n\
MCP_PID=$!\n\
\n\
# Start coordinator on internal port\n\
python3 -m coordinator --port 8003 --host 0.0.0.0 &\n\
COORD_PID=$!\n\
\n\
# Wait for any process to exit\n\
wait -n\n\
\n\
# Kill all processes if one dies\n\
kill $NGINX_PID $MCP_PID $COORD_PID 2>/dev/null\n\
' > /app/start.sh && chmod +x /app/start.sh

CMD ["/app/start.sh"]