#!/bin/bash

set -e

STACK_NAME="mcp-job-finder-server"
REGION="us-west-2"

echo "🚀 Deploying Job Finder MCP Server (Simplified)..."

# Get the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SRC_DIR="$SCRIPT_DIR/../src"

# Deploy CloudFormation stack
echo "☁️  Creating infrastructure..."
aws cloudformation deploy \
  --template-file cloudformation.yaml \
  --stack-name $STACK_NAME \
  --capabilities CAPABILITY_NAMED_IAM \
  --region $REGION \
  --parameter-overrides \
    LogLevel=INFO

# Create Lambda deployment package
echo "📦 Creating minimal Lambda deployment package..."
cd ../src

# Clean up any existing packages
rm -rf awslabs* boto3* botocore* s3transfer* jmespath* urllib3* six* python_dateutil* 2>/dev/null || true
rm -f ../infrastructure/job-finder-lambda.zip

# Create a temporary directory for clean installation
mkdir -p /tmp/lambda-build
cd /tmp/lambda-build

# Install only the MCP handler
python3 -m pip install awslabs-mcp-lambda-handler -t . --upgrade

# Remove all AWS packages (already in Lambda runtime)
rm -rf boto3* botocore* s3transfer* jmespath* urllib3* 2>/dev/null || true

# Copy our source files
cp "$SRC_DIR"/*.py .

# Clean up unnecessary files
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -name "*.pyc" -delete
find . -name "*.pyo" -delete
find . -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true

# Create zip with absolute path
INFRASTRUCTURE_DIR="$SCRIPT_DIR"
zip -r "$INFRASTRUCTURE_DIR/job-finder-lambda.zip" . -q

# Check size
echo "Package size:"
ls -lh "$INFRASTRUCTURE_DIR/job-finder-lambda.zip"

# Clean up temp directory
cd "$INFRASTRUCTURE_DIR"
rm -rf /tmp/lambda-build

# Update Lambda function code
echo "🔄 Updating Lambda function..."
aws lambda update-function-code \
  --function-name $STACK_NAME-mcp-server \
  --zip-file fileb://job-finder-lambda.zip \
  --region $REGION \
  --no-cli-pager > /dev/null

# Wait for function to be ready
echo "⏳ Waiting for Lambda function to be ready..."
aws lambda wait function-updated \
  --function-name $STACK_NAME-mcp-server \
  --region $REGION

echo "✅ Lambda function updated successfully"

# Upload sample job files to S3
echo "⬆️  Uploading job files to S3..."
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' \
  --output text)

echo "📁 Bucket name: $BUCKET_NAME"

# Use absolute path to jobs-data directory
JOBS_DATA_DIR="$(dirname "$PWD")/jobs-data"
echo "📂 Uploading from: $JOBS_DATA_DIR"

if [ -d "$JOBS_DATA_DIR" ]; then
    aws s3 sync "$JOBS_DATA_DIR" s3://$BUCKET_NAME/jobs/ --exclude ".*" --region $REGION
    echo "✅ Job files uploaded successfully"
else
    echo "❌ Error: jobs-data directory not found at $JOBS_DATA_DIR"
    exit 1
fi

# Get outputs from CloudFormation
API_URL=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' \
  --output text)

SSM_PARAMETER=$(aws cloudformation describe-stacks \
  --stack-name $STACK_NAME \
  --region $REGION \
  --query 'Stacks[0].Outputs[?OutputKey==`SSMParameterName`].OutputValue' \
  --output text)

echo "🎉 Deployment successful!"
echo "API URL: $API_URL"
echo "SSM Parameter: $SSM_PARAMETER"

# Clean up
cd ../infrastructure
rm job-finder-lambda.zip
