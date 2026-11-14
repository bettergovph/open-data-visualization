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

# Step 2: Pull latest changes from git
log "📥 Step 2: Pulling latest changes from git..."
# Stash any local changes first
git stash
# Fetch latest changes
git fetch origin
# Reset to match remote exactly (handles force pushes and history rewrites)
if ! git reset --hard origin/main; then
    error "Git reset failed"
    exit 1
fi
log "✅ Git pull completed"

# Step 3: Build Rust application
log "🔨 Step 3: Building Rust application..."
if ! cargo build --release; then
    error "Rust build failed"
    exit 1
fi
log "✅ Rust application built successfully"

# Step 4: Install Python dependencies
log "🐍 Step 4: Installing Python dependencies..."
pip install -r requirements.txt
log "✅ Python dependencies installed"

# Step 5: Install loopback-only service units and update the shared Nginx proxy
log "🔒 Step 5: Installing localhost-only service units..."
if ! sudo install -m 644 deployment/visualization.service /etc/systemd/system/visualization.service || \
   ! sudo install -m 644 deployment/visualization_api.service /etc/systemd/system/visualization_api.service; then
    error "Could not install the systemd service files"
    exit 1
fi

if ! bash deployment/configure_shared_nginx_proxy.sh; then
    error "Failed to update the existing shared Nginx proxy"
    exit 1
fi

# Reload systemd daemon so it picks up the installed unit files
log "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload
log "✅ Systemd daemon reloaded"

# Step 6: Restart services
log "⚙️ Step 6: Restarting services..."

# Clear Python bytecode cache to ensure fresh code is loaded
log "🧹 Clearing Python bytecode cache..."
find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
log "✅ Python cache cleared"

# Restart services explicitly
log "🔁 Restarting visualization.service (Rust frontend)..."
if sudo systemctl restart visualization.service; then
    log "✅ visualization.service restart command completed"
else
    error "Failed to restart visualization.service"
    exit 1
fi

log "🔁 Restarting visualization_api.service (FastAPI backend)..."
if sudo systemctl restart visualization_api.service; then
    log "✅ FastAPI restart command completed for visualization_api.service"
else
    error "Failed to restart FastAPI service visualization_api.service"
    exit 1
fi

# Step 7: Verify services are running
log "🔍 Step 7: Verifying services..."
sleep 3

if sudo systemctl is-active --quiet visualization.service; then
    log "✅ visualization.service is running"
else
    error "visualization.service is not running"
    exit 1
fi

if sudo systemctl is-active --quiet visualization_api.service; then
    API_PID=$(sudo systemctl show --property=MainPID --value visualization_api.service)
    API_STARTED=$(sudo systemctl show --property=ActiveEnterTimestamp --value visualization_api.service)
    log "✅ FastAPI service is active (MainPID: ${API_PID:-unknown}; active since: ${API_STARTED:-unknown})"
else
    error "FastAPI service visualization_api.service is not active"
    exit 1
fi

# Step 8: Test API endpoints (basic health check)
log "🩺 Step 8: Running basic health checks..."

# Test Rust frontend
if curl --connect-timeout 5 --max-time 15 -s -f http://127.0.0.1:8888/ > /dev/null; then
    log "✅ Frontend health check passed"
else
    warning "Frontend health check failed - service may still be starting"
fi

if curl --connect-timeout 5 --max-time 15 -s -f http://127.0.0.1:8001/ > /dev/null; then
    log "✅ FastAPI health check passed"
else
    error "FastAPI health check failed on localhost:8001"
    sudo systemctl --no-pager --full status visualization_api.service || true
    exit 1
fi

log "🎉 BetterGovPH deployment completed successfully!"
log "🌐 Frontend: http://127.0.0.1:8888 (localhost only)"
log "🔌 FastAPI: http://127.0.0.1:8001 (localhost only)"
log "📊 Production: https://visualizations.bettergov.ph"
