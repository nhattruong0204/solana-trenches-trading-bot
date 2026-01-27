#!/bin/bash
# ==============================================================================
# Quick Deployment Script for LightNode VPS
# ==============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
VPS_IP="38.54.15.53"
VPS_USER="root"
REMOTE_DIR="/opt/solana-trading-bot"
SSH_KEY="$HOME/.ssh/lightnode_vps"
SSH_OPTS="-i $SSH_KEY"

# Functions
print_step() {
    echo -e "${GREEN}==>${NC} $1"
}

print_error() {
    echo -e "${RED}ERROR:${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}WARNING:${NC} $1"
}

check_file() {
    if [ ! -f "$1" ]; then
        print_error "File not found: $1"
        exit 1
    fi
}

# Main script
main() {
    clear
    echo "===================================="
    echo "  Solana Trading Bot Deployment"
    echo "===================================="
    echo ""

    # Check if VPS_IP is set
    if [ -z "$VPS_IP" ]; then
        echo -n "Enter your VPS IP address: "
        read VPS_IP
    fi

    # Verify required files
    print_step "Checking required files..."
    check_file ".env"
    check_file "wallet_tracker_session.session"
    check_file "docker-compose.yml"
    check_file "Dockerfile"

    # Create deployment package
    print_step "Creating deployment package..."
    tar -czf /tmp/trading-bot-deploy.tar.gz \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.venv' \
        --exclude='node_modules' \
        --exclude='.pytest_cache' \
        --exclude='trading_state.json' \
        --exclude='*.session' \
        --exclude='*.session-journal' \
        .

    print_step "Transferring files to VPS..."

    # Create remote directory
    ssh ${SSH_OPTS} ${VPS_USER}@${VPS_IP} "mkdir -p ${REMOTE_DIR}/data"

    # Transfer files (excluding session files - they're created on VPS)
    scp ${SSH_OPTS} /tmp/trading-bot-deploy.tar.gz ${VPS_USER}@${VPS_IP}:${REMOTE_DIR}/
    scp ${SSH_OPTS} .env ${VPS_USER}@${VPS_IP}:${REMOTE_DIR}/
    # NOTE: Session files are NOT transferred - they must be created on VPS to avoid IP conflicts

    # Setup on VPS
    print_step "Setting up on VPS..."
    ssh ${SSH_OPTS} ${VPS_USER}@${VPS_IP} << 'ENDSSH'
cd /opt/solana-trading-bot

# Extract files
echo "Extracting files..."
tar -xzf trading-bot-deploy.tar.gz
rm trading-bot-deploy.tar.gz

# Set permissions
echo "Setting permissions..."
chmod 600 .env
chmod 600 wallet_tracker_session.session
chmod 755 data

# Build and start
echo "Building Docker image..."
docker compose build

echo "Starting bot..."
docker compose up -d

echo "Waiting for container to start..."
sleep 5

# Show status
echo ""
echo "Container Status:"
docker compose ps

echo ""
echo "Recent Logs:"
docker compose logs --tail=20
ENDSSH

    # Cleanup
    rm /tmp/trading-bot-deploy.tar.gz

    echo ""
    print_step "Deployment complete!"
    echo ""
    echo "To view logs: ssh ${VPS_USER}@${VPS_IP} 'cd ${REMOTE_DIR} && docker compose logs -f'"
    echo "To check status: ssh ${VPS_USER}@${VPS_IP} 'cd ${REMOTE_DIR} && docker compose ps'"
    echo ""
}

# Handle errors
trap 'print_error "Deployment failed!"; exit 1' ERR

# Run main function
main "$@"
