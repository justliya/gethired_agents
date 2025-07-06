#!/bin/bash

set -e 
set -o pipefail

echo "=== Job Search AI Assistant Deployment Script ==="

echo "Preparing deployment files..."

echo "All required files found"

echo "Deploying to Google Cloud Run..."

gcloud run deploy job-search-assistant \
  --source . \
  --region "$GOOGLE_CLOUD_LOCATION" \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --allow-unauthenticated \
  --port 8080 \
  --timeout 600 \
  --memory 4Gi \
  --cpu 4 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,GOOGLE_CLOUD_LOCATION=$GOOGLE_CLOUD_LOCATION,GOOGLE_GENAI_USE_VERTEXAI=True,PYTHONPATH=/app,JOB_SEARCH_PORT=8080,SERVICE_ACCOUNT_KEY_PATH=${SERVICE_ACCOUNT_KEY_PATH,FIREBASE_STORAGE_BUCKET=$FIREBASE_STORAGE_BUCKET"

if [ $? -eq 0 ]; then
    echo "Deployment successful!"

    SERVICE_URL=$(gcloud run services describe job-search-assistant \
      --region="$GOOGLE_CLOUD_LOCATION" \
      --format="value(status.url)")

    echo "Test endpoint: $SERVICE_URL/docs"
    echo "Service URL: $SERVICE_URL/run-job-search"
else
    echo "Deployment failed"
    exit 1
fi

echo "Done"