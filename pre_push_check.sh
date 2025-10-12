#!/bin/bash

# BetterGovPH Open Data Visualization - Pre-push Check Script
# This script performs pre-deployment checks before pushing to production
# Usage: ./pre_push_check.sh

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

log "🔍 Starting BetterGovPH pre-push checks..."

# Check 1: Verify we're in the right directory
if [ ! -f "Cargo.toml" ] || [ ! -f "visualization.py" ] || [ ! -f "requirements.txt" ]; then
    error "Not in the correct project directory. Missing required files."
    exit 1
fi
log "✅ Project structure verified"

# Check 2: Verify Rust code compiles
log "🔨 Checking Rust compilation..."
if ! cargo check --quiet; then
    error "Rust code has compilation errors"
    exit 1
fi
log "✅ Rust code compiles successfully"

# Check 3: Verify Python syntax
log "🐍 Checking Python syntax..."
python_files=$(find . -name "*.py" -not -path "./venv/*" -not -path "./target/*")
for file in $python_files; do
    if ! python3 -m py_compile "$file" 2>/dev/null; then
        error "Python syntax error in: $file"
        exit 1
    fi
done
log "✅ Python syntax is valid"

# Check 4: Verify requirements.txt is up to date
log "📦 Checking Python dependencies..."
if [ -f "requirements.txt" ]; then
    # Check if we can import key modules
    python3 -c "
import sys
sys.path.insert(0, '.')
try:
    import fastapi
    import uvicorn
    import asyncpg
    import pydantic
    print('✅ Core Python dependencies available')
except ImportError as e:
    print('❌ Missing dependency:', e)
    sys.exit(1)
"
else
    error "requirements.txt not found"
    exit 1
fi

# Check 5: Verify systemd service files exist
log "⚙️ Checking systemd service files..."
if [ ! -f "deployment/visualization.service" ] || [ ! -f "deployment/visualization_api.service" ]; then
    error "Systemd service files missing in deployment/ directory"
    exit 1
fi
log "✅ Systemd service files present"

# Check 6: Verify nginx configuration exists
log "🌐 Checking nginx configuration..."
if [ ! -f "deployment/visualizations_nginx.conf" ]; then
    error "Nginx configuration file missing in deployment/ directory"
    exit 1
fi
log "✅ Nginx configuration present"

# Check 7: Verify .env.example exists (but not .env)
log "🔐 Checking environment configuration..."
if [ ! -f "altgovph.env" ]; then
    warning "Environment template not found"
else
    log "✅ Environment template present"
fi

if [ -f ".env" ]; then
    warning ".env file found - ensure it contains real credentials and is in .gitignore"
fi

# Check 8: Verify git status is clean (optional warning)
log "📝 Checking git status..."
if [ -n "$(git status --porcelain)" ]; then
    warning "Git working directory is not clean. Uncommitted changes detected."
    info "Run 'git status' to see what files need to be committed."
else
    log "✅ Git working directory is clean"
fi

# Check 9: Verify deployment scripts exist
log "🚀 Checking deployment scripts..."
required_scripts=("restart.sh" "pre_push_check.sh")
for script in "${required_scripts[@]}"; do
    if [ ! -f "deployment/$script" ]; then
        error "Required deployment script missing: deployment/$script"
        exit 1
    fi
done
log "✅ Deployment scripts present"

log "🎉 All pre-push checks passed!"
log "🚀 Ready for deployment to BetterGovPH servers"
exit 0
