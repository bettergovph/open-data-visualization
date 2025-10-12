#!/bin/bash

# BetterGovPH Open Data Visualization - Deployment Script
# This script handles deployment of the BetterGovPH visualization platform
# Usage: ./restart.sh [--force]
#   --force: Skip checks and force service restarts

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

# Parse command line arguments
FORCE_RESTART=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_RESTART=true
            shift
            ;;
        *)
            warning "Unknown option: $1"
            shift
            ;;
    esac
done

if [ "$FORCE_RESTART" = true ]; then
    log "🚨 FORCE MODE: Will skip checks and force service restarts"
else
    log "📅 NORMAL MODE: Using standard deployment checks"
fi

log "🚀 Starting BetterGovPH deployment workflow..."

# Step 1: Verify working directory
log "📁 Step 1: Verifying working directory..."
if [ ! -f "Cargo.toml" ]; then
    error "Cargo.toml not found. Are you in the right directory?"
    exit 1
fi

if [ ! -f "visualization.py" ]; then
    error "visualization.py not found. Are you in the right directory?"
    exit 1
fi

if [ ! -d "venv" ]; then
    warning "Python virtual environment not found. Installing dependencies..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

log "✅ Working directory verified"

# Step 2: Build Rust application
log "🔨 Step 2: Building Rust application..."
if ! cargo build --release; then
    error "Rust build failed"
    exit 1
fi
log "✅ Rust application built successfully"

# Step 3: Install Python dependencies
log "🐍 Step 3: Installing Python dependencies..."
pip install -r requirements.txt
log "✅ Python dependencies installed"

# Step 4: Reload systemd daemon
log "🔄 Step 4: Reloading systemd daemon..."
sudo systemctl daemon-reload
log "✅ Systemd daemon reloaded"

# Step 5: Restart services
log "⚙️ Step 5: Restarting services..."

# Stop services first
log "🛑 Stopping visualization.service..."
sudo systemctl stop visualization.service || warning "Failed to stop visualization.service"

log "🛑 Stopping visualization_api.service..."
sudo systemctl stop visualization_api.service || warning "Failed to stop visualization_api.service"

# Wait a moment
sleep 2

# Start services
log "▶️ Starting visualization.service..."
if sudo systemctl start visualization.service; then
    log "✅ visualization.service started successfully"
else
    error "Failed to start visualization.service"
    exit 1
fi

log "▶️ Starting visualization_api.service..."
if sudo systemctl start visualization_api.service; then
    log "✅ visualization_api.service started successfully"
else
    error "Failed to start visualization_api.service"
    exit 1
fi

# Step 6: Verify services are running
log "🔍 Step 6: Verifying services..."
sleep 3

if sudo systemctl is-active --quiet visualization.service; then
    log "✅ visualization.service is running"
else
    error "visualization.service is not running"
    exit 1
fi

if sudo systemctl is-active --quiet visualization_api.service; then
    log "✅ visualization_api.service is running"
else
    error "visualization_api.service is not running"
    exit 1
fi

# Step 7: Test API endpoints (basic health check)
log "🩺 Step 7: Running basic health checks..."

# Test Rust frontend
if curl -s -f http://localhost:8888/ > /dev/null; then
    log "✅ Frontend health check passed"
else
    warning "Frontend health check failed - service may still be starting"
fi

# Test FastAPI backend
if curl -s -f http://localhost:8000/ > /dev/null; then
    log "✅ API health check passed"
else
    warning "API health check failed - service may still be starting"
fi

log "🎉 BetterGovPH deployment completed successfully!"
log "🌐 Frontend: http://localhost:8888"
log "🔌 API: http://localhost:8000"
log "📊 Production: https://visualizations.bettergov.ph"
