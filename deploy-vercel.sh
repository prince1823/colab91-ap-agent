#!/bin/bash

# Quick deployment script for Vercel
# Usage: ./deploy-vercel.sh [--prod]

set -e

echo "🚀 Starting Vercel deployment..."

# Check if Vercel CLI is installed
if ! command -v vercel &> /dev/null; then
    echo "❌ Vercel CLI is not installed."
    echo "Install it with: npm i -g vercel"
    exit 1
fi

# Check if logged in
if ! vercel whoami &> /dev/null; then
    echo "❌ Not logged in to Vercel."
    echo "Login with: vercel login"
    exit 1
fi

# Build frontend first
echo "📦 Building frontend..."
cd frontend
npm install
npm run build
cd ..

# Deploy to Vercel
if [ "$1" == "--prod" ]; then
    echo "🚀 Deploying to production..."
    vercel --prod
else
    echo "🚀 Deploying to preview..."
    vercel
fi

echo "✅ Deployment complete!"
echo "💡 Don't forget to set environment variables in Vercel Dashboard"

