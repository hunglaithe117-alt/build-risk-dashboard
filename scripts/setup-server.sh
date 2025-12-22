#!/bin/bash
# =============================================================================
# Setup Script for Remote Server
# Prepares the server for running docker-compose.server.yml
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=============================================="
echo "Build Risk Dashboard - Server Setup"
echo -e "==============================================${NC}"

# -----------------------------------------------------------------------------
# 1. Check Docker
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[1/4] Checking Docker...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not found. Please install Docker first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker installed${NC}"

if ! docker compose version &> /dev/null; then
    echo -e "${RED}✗ Docker Compose V2 not found.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose installed${NC}"

# -----------------------------------------------------------------------------
# 2. Configure vm.max_map_count for SonarQube
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[2/4] Configuring kernel parameters for SonarQube...${NC}"

CURRENT_MAP_COUNT=$(sysctl -n vm.max_map_count 2>/dev/null || echo "0")
REQUIRED_MAP_COUNT=262144

if [ "$CURRENT_MAP_COUNT" -lt "$REQUIRED_MAP_COUNT" ]; then
    echo "Setting vm.max_map_count to $REQUIRED_MAP_COUNT"
    sudo sysctl -w vm.max_map_count=$REQUIRED_MAP_COUNT
    
    if ! grep -q "vm.max_map_count" /etc/sysctl.conf 2>/dev/null; then
        echo "vm.max_map_count=$REQUIRED_MAP_COUNT" | sudo tee -a /etc/sysctl.conf
    fi
    echo -e "${GREEN}✓ vm.max_map_count configured${NC}"
else
    echo -e "${GREEN}✓ vm.max_map_count already set ($CURRENT_MAP_COUNT)${NC}"
fi

# -----------------------------------------------------------------------------
# 3. Pre-download Trivy vulnerability database
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[3/5] Pre-downloading Trivy vulnerability database...${NC}"
echo "This may take a few minutes (~600MB)..."

docker run --rm \
    -v trivy_cache:/root/.cache/trivy \
    aquasec/trivy:latest \
    image --download-db-only 2>/dev/null || true

echo -e "${GREEN}✓ Trivy database cached${NC}"

# -----------------------------------------------------------------------------
# 4. Pull Docker images (including scanner images)
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[4/4] Pulling Docker images...${NC}"

# Infrastructure images
docker pull mongo:6
docker pull rabbitmq:3.12-management
docker pull redis:7-alpine
docker pull postgres:15-alpine

# Tool server images
docker pull sonarqube:latest
docker pull aquasec/trivy:latest

# Scanner CLI images (used via docker run for scanning)
echo "Pulling scanner CLI images..."
docker pull sonarsource/sonar-scanner-cli:latest
# trivy image already pulled above

echo -e "${GREEN}✓ All Docker images pulled${NC}"


# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo -e "\n${GREEN}=============================================="
echo "Setup Complete!"
echo -e "==============================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Configure environment:"
echo "   cp .env.server.example .env.server"
echo "   nano .env.server"
echo ""
echo "2. Start services:"
echo "   docker compose -f docker-compose.server.yml --env-file .env.server up -d"
echo ""
echo "3. Wait for SonarQube to start (~2-3 minutes):"
echo "   docker logs -f server-sonarqube"
echo ""
echo "4. Access SonarQube and create token:"
echo "   http://<server-ip>:9000"
echo "   Default: admin / admin"
echo ""
echo "5. On your local machine, forward ports:"
echo "   ./scripts/ssh-forward-server.sh user@<server-ip>"
echo ""
