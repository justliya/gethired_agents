FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy package for MCP dependencies
COPY package*.json ./

# Install Node.js dependencies if package.json exists
RUN if [ -f "package.json" ]; then npm install; fi

# Install the Firebase MCP package globally if needed
RUN npm install -g @gannonh/firebase-mcp 

# Copy Python requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Create user
RUN adduser --disabled-password --gecos "" appuser

# Copy application files
COPY . .

RUN mkdir -p /app/config


RUN chown -R appuser:appuser /app


USER appuser


ENV PYTHONPATH=/app
ENV PATH="/home/appuser/.local/bin:$PATH"
ENV PORT=8080


RUN echo '#!/bin/bash\n\
if [ ! -z "$SERVICEACCOUNTKEY" ]; then\n\
    echo "$SERVICEACCOUNTKEY" > /app/config/serviceAccountKey.json\n\
fi\n\
python -m coordinator' > /app/start.sh && chmod +x /app/start.sh

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:$PORT/health || exit 1

# Start application using the startup script
CMD ["/bin/bash", "/app/start.sh"]