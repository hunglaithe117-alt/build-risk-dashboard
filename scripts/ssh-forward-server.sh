#!/bin/bash
# =============================================================================
# SSH Port Forward to Remote Server
# Forward all backend services to localhost for local development
# =============================================================================
#
# Usage: ./scripts/ssh-forward-server.sh <user@server-ip>
# Example: ./scripts/ssh-forward-server.sh root@192.168.1.100
#
# After running this script, configure your local backend/.env:
#   MONGODB_URI=mongodb://localhost:27017
#   CELERY_BROKER_URL=amqp://myuser:mypass@localhost:5672//
#   REDIS_URL=redis://localhost:6379/0
#   SONAR_HOST_URL=http://localhost:9000
#   TRIVY_SERVER_URL=http://localhost:4954
#

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

if [ -z "$1" ]; then
    echo "Usage: $0 <user@server-ip>"
    echo "Example: $0 root@192.168.1.100"
    exit 1
fi

SERVER="$1"

echo -e "${BLUE}=============================================="
echo "SSH Port Forward - Server Services"
echo -e "==============================================${NC}"
echo ""
echo -e "${YELLOW}Forwarding ports from ${SERVER}:${NC}"
echo ""
echo "  Database & Messaging:"
echo "    localhost:27017 → MongoDB"
echo "    localhost:5672  → RabbitMQ (AMQP)"
echo "    localhost:15672 → RabbitMQ (Management UI)"
echo "    localhost:6379  → Redis"
echo ""
echo "  Scanning Tools:"
echo "    localhost:9000  → SonarQube"
echo "    localhost:4954  → Trivy Server"
echo ""
echo "  Monitoring:"
echo "    localhost:3001  → Grafana"
echo "    localhost:3100  → Loki"
echo ""
echo -e "${GREEN}Press Ctrl+C to stop forwarding${NC}"
echo ""

# SSH with multiple port forwarding
# -N = Don't execute remote command (just forward)
# -L = Local port forwarding: local_port:remote_host:remote_port
ssh -N \
    -L 27017:localhost:27017 \
    -L 5672:localhost:5672 \
    -L 15672:localhost:15672 \
    -L 6379:localhost:6379 \
    -L 9000:localhost:9000 \
    -L 4954:localhost:4954 \
    -L 3001:localhost:3001 \
    -L 3100:localhost:3100 \
    "$SERVER"
