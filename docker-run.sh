#!/bin/bash
# ==============================================================================
# Solana Trading Bot - Docker Management Script
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║         SOLANA TRADING BOT - DOCKER DEPLOYMENT              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Ensure data directory exists
ensure_data_dir() {
    if [ ! -d "data" ]; then
        mkdir -p data
        touch data/trading_state.json
        touch data/trading_bot.log
        echo "{}" > data/trading_state.json
    fi
}

# Check prerequisites
check_prerequisites() {
    # Check if .env exists
    if [ ! -f .env ]; then
        print_warning ".env file not found!"
        echo ""
        echo "Creating .env from template..."
        if [ -f .env.example ]; then
            cp .env.example .env
        elif [ -f .env.docker ]; then
            cp .env.docker .env
        fi
        echo ""
        print_error "Please edit .env and add your Telegram credentials:"
        echo "   $ nano .env"
        echo ""
        echo "Then run this script again."
        exit 1
    fi

    # Check if session file exists
    if [ ! -f wallet_tracker_session.session ]; then
        print_error "Session file not found!"
        echo ""
        echo "The bot needs an authenticated Telegram session."
        echo "Please run the authentication script first to create the session:"
        echo "   $ cd /home/truong/sol_wallet_tracker"
        echo "   $ python fetch_history.py"
        echo ""
        echo "Then copy the session file:"
        echo "   $ cp wallet_tracker_session.session trading_bot/"
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  up, start     Start the trading bot container"
    echo "  down, stop    Stop the trading bot container"
    echo "  restart       Restart the trading bot container"
    echo "  logs          Show container logs (follow mode)"
    echo "  status        Show container status and recent logs"
    echo "  build         Rebuild the Docker image"
    echo "  shell         Open shell in running container"
    echo "  clean         Stop and remove all containers/images"
    echo "  validate      Validate configuration"
    echo "  test          Run tests in container"
    echo "  help          Show this help message"
    echo ""
}

# Main action handler
ACTION=${1:-help}

case $ACTION in
    up|start)
        print_header
        check_prerequisites
        ensure_data_dir
        echo "🚀 Starting trading bot in Docker..."
        docker compose up -d
        echo ""
        print_success "Bot started!"
        echo ""
        echo "📊 View logs:"
        echo "   $ ./docker-run.sh logs"
        echo ""
        echo "🔍 Check status:"
        echo "   $ ./docker-run.sh status"
        ;;
    
    down|stop)
        print_header
        echo "🛑 Stopping trading bot..."
        docker compose down
        print_success "Bot stopped!"
        ;;
    
    restart)
        print_header
        echo "🔄 Restarting trading bot..."
        docker compose restart
        print_success "Bot restarted!"
        ;;
    
    logs)
        echo "📋 Showing bot logs (Ctrl+C to exit)..."
        echo ""
        docker compose logs -f
        ;;
    
    status)
        print_header
        echo "📊 Container Status:"
        echo ""
        docker compose ps
        echo ""
        echo "📈 Recent logs:"
        echo ""
        docker compose logs --tail=30
        ;;
    
    build)
        print_header
        ensure_data_dir
        echo "🔨 Building Docker image..."
        docker compose build --no-cache
        print_success "Build complete!"
        ;;
    
    shell)
        echo "🐚 Opening shell in container..."
        docker compose exec trading-bot /bin/bash || \
            docker compose run --rm trading-bot /bin/bash
        ;;
    
    clean)
        print_header
        echo "🧹 Cleaning up Docker resources..."
        docker compose down -v --rmi local
        docker system prune -f
        print_success "Cleanup complete!"
        ;;
    
    validate)
        print_header
        check_prerequisites
        echo "🔍 Validating configuration..."
        docker compose run --rm trading-bot python main.py validate
        ;;
    
    test)
        print_header
        echo "🧪 Running tests..."
        docker compose run --rm trading-bot pytest tests/ -v
        ;;
    
    help|--help|-h)
        print_header
        show_usage
        ;;
    
    *)
        print_error "Unknown command: $ACTION"
        echo ""
        show_usage
        exit 1
        ;;
esac
        ;;
    
    *)
        echo "Usage: $0 {up|down|restart|logs|status|build|shell|clean}"
        echo ""
        echo "Commands:"
        echo "  up/start   - Start the bot"
        echo "  down/stop  - Stop the bot"
        echo "  restart    - Restart the bot"
        echo "  logs       - View logs (live)"
        echo "  status     - Check bot status"
        echo "  build      - Rebuild Docker image"
        echo "  shell      - Open shell in container"
        echo "  clean      - Remove all Docker resources"
        exit 1
        ;;
esac
