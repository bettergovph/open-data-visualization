#!/bin/bash

# BetterGovPH Open Data Visualization - Update Scripts
# This script updates the deployment scripts on the target server
# Usage: ./update_scripts.sh

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

log "🔧 Starting BetterGovPH deployment scripts update..."

# Verify we're in the right directory
if [ ! -d "deployment" ]; then
    error "deployment/ directory not found"
    exit 1
fi

# List of scripts to update
scripts_to_update=(
    "restart.sh"
    "pre_push_check.sh"
)

log "📋 Scripts to update: ${scripts_to_update[*]}"

# Make scripts executable
for script in "${scripts_to_update[@]}"; do
    if [ -f "deployment/$script" ]; then
        chmod +x "deployment/$script"
        log "✅ Made deployment/$script executable"
    else
        warning "Script deployment/$script not found"
    fi
done

# Verify scripts are executable
for script in "${scripts_to_update[@]}"; do
    if [ -x "deployment/$script" ]; then
        log "✅ deployment/$script is executable"
    else
        error "deployment/$script is not executable"
        exit 1
    fi
done

# Test script syntax (basic check)
for script in "${scripts_to_update[@]}"; do
    if bash -n "deployment/$script" 2>/dev/null; then
        log "✅ deployment/$script syntax is valid"
    else
        error "deployment/$script has syntax errors"
        exit 1
    fi
done

log "🎉 All deployment scripts updated successfully!"
log "📝 Scripts are now executable and ready for deployment"
exit 0
