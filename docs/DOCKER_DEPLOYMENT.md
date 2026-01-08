# Docker Deployment Guide

Hướng dẫn triển khai Build Risk Dashboard sử dụng Docker Compose.

## 📋 Yêu Cầu

- Docker Engine 24+
- Docker Compose v2+
- 8GB RAM minimum (SonarQube requires 4GB)
- 50GB disk space

## 🚀 Quick Start

### 1. Clone và cấu hình

```bash
# Clone repository
git clone https://github.com/your-org/build-risk-dashboard.git
cd build-risk-dashboard

# Copy env file
cp .env.prod.example .env

# Generate secrets
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env
echo "NEXTAUTH_SECRET=$(openssl rand -hex 32)" >> .env
```

### 2. Cấu hình `.env`

Chỉnh sửa file `.env` với các giá trị thực tế:

```bash
nano .env
```

**Các biến quan trọng:**

| Variable | Mô tả | Ví dụ |
|----------|-------|-------|
| `SECRET_KEY` | Backend JWT secret | `openssl rand -hex 32` |
| `NEXTAUTH_SECRET` | NextAuth secret | `openssl rand -hex 32` |
| `RABBITMQ_PASS` | RabbitMQ password | Strong password |
| `GRAFANA_PASS` | Grafana admin password | Strong password |
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://your-domain/api` |
| `NEXT_PUBLIC_WS_URL` | WebSocket URL | `ws://your-domain/api/ws/events` |
| `GITHUB_TOKENS` | GitHub PATs (comma-separated) | `ghp_xxx,ghp_yyy` |

### 3. Build và khởi động

```bash
# Build images
docker-compose -f docker-compose.prod.yml build

# Start all services
docker-compose -f docker-compose.prod.yml up -d

# Check logs
docker-compose -f docker-compose.prod.yml logs -f
```

### 4. Verify deployment

```bash
# Check all containers are running
docker-compose -f docker-compose.prod.yml ps

# Test health endpoints
curl http://localhost/api/health
curl http://localhost:3001/api/health  # Grafana
```

## 🏗️ Architecture

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                    DOCKER NETWORK                        │
                    │                                                          │
                    │  ┌─────────┐    ┌─────────────┐    ┌─────────────────┐  │
   Port 80 ─────────┼──│  Nginx  │────│  Frontend   │────│    Backend      │  │
                    │  │ (proxy) │    │  (Next.js)  │    │   (FastAPI)     │──┼── Port 8000 (internal)
                    │  └─────────┘    └─────────────┘    └─────────────────┘  │
                    │                                              │           │
                    │                                              ▼           │
                    │  ┌─────────────────────────────────────────────────────┐│
                    │  │                   DATA LAYER                        ││
                    │  │  ┌────────┐  ┌──────────┐  ┌───────┐  ┌──────────┐  ││
                    │  │  │MongoDB │  │ RabbitMQ │  │ Redis │  │PostgreSQL│  ││
                    │  │  │(27017) │  │  (5672)  │  │(6379) │  │ (5432)   │  ││
                    │  │  └────────┘  └──────────┘  └───────┘  └──────────┘  ││
                    │  └─────────────────────────────────────────────────────┘│
                    │                                                          │
                    │  ┌─────────────────────────────────────────────────────┐│
                    │  │                  WORKER LAYER                        ││
                    │  │  ┌──────────────┐  ┌─────────────┐                   ││
                    │  │  │Celery Worker │  │ Celery Beat │                   ││
                    │  │  └──────────────┘  └─────────────┘                   ││
                    │  └─────────────────────────────────────────────────────┘│
                    │                                                          │
                    │  ┌─────────────────────────────────────────────────────┐│
                    │  │                  TOOLS LAYER                         ││
                    │  │  ┌───────────┐  ┌───────┐                            ││
                    │  │  │ SonarQube │  │ Trivy │                            ││
                    │  │  │  (9000)   │  │(4954) │                            ││
                    │  │  └───────────┘  └───────┘                            ││
                    │  └─────────────────────────────────────────────────────┘│
                    │                                                          │
   Port 3001 ───────┼──┌─────────────────────────────────────────────────────┐│
                    │  │                 MONITORING LAYER                     ││
                    │  │  ┌─────────┐ ┌────────┐ ┌───────────┐ ┌───────┐     ││
                    │  │  │ Grafana │ │Promethe│ │   Loki    │ │ Alloy │     ││
                    │  │  │ (3001)  │ │us(9090)│ │  (3100)   │ │(12345)│     ││
                    │  │  └─────────┘ └────────┘ └───────────┘ └───────┘     ││
                    │  └─────────────────────────────────────────────────────┘│
                    └─────────────────────────────────────────────────────────┘
```

## 📁 Services

| Service | Container | Port | Mô tả |
|---------|-----------|------|-------|
| **nginx** | prod-nginx | 80 | Reverse proxy |
| **backend** | prod-backend | 8000 | FastAPI server |
| **frontend** | prod-frontend | 3000 | Next.js app |
| **celery-worker** | prod-celery-worker | - | Background tasks |
| **celery-beat** | prod-celery-beat | - | Scheduled tasks |
| **mongo** | prod-mongo | 27017 | Database |
| **rabbitmq** | prod-rabbitmq | 5672 | Message broker |
| **redis** | prod-redis | 6379 | Cache & results |
| **sonarqube** | prod-sonarqube | 9000 | Code quality |
| **trivy** | prod-trivy | 4954 | Vulnerability scanner |
| **loki** | prod-loki | 3100 | Log aggregation |
| **prometheus** | prod-prometheus | 9090 | Metrics |
| **grafana** | prod-grafana | **3001** | Monitoring UI |
| **alloy** | prod-alloy | 12345 | Log collector |

## 🔧 Commands

### Container Management

```bash
# Start all
docker-compose -f docker-compose.prod.yml up -d

# Stop all
docker-compose -f docker-compose.prod.yml down

# Restart specific service
docker-compose -f docker-compose.prod.yml restart backend

# Scale workers
docker-compose -f docker-compose.prod.yml up -d --scale celery-worker=3

# View logs
docker-compose -f docker-compose.prod.yml logs -f backend celery-worker
```

### Database Operations

```bash
# Backup MongoDB
docker exec prod-mongo mongodump --archive=/data/backup.gz --gzip

# Restore MongoDB
docker exec -i prod-mongo mongorestore --archive --gzip < backup.gz
```

### Monitoring Access

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3001 | `admin` / `GRAFANA_PASS` |
| RabbitMQ | http://localhost:15672 | `RABBITMQ_USER` / `RABBITMQ_PASS` |
| SonarQube | http://localhost:9000 | `admin` / `admin` (change on first login) |

## 📊 Grafana Dashboards

Dashboards được tự động load từ `monitoring/dashboards/`:

- **Build Risk Overview** - Stats, risk distribution, recent builds
- **Pipeline Monitoring** - Pipeline status, Celery workers, infrastructure
- **Business Metrics** - Risk trends, API performance, errors
- **Model Pipeline Details** - Repository processing status
- **Dataset Enrichment Details** - Dataset enrichment progress

## ⚠️ Troubleshooting

### MongoDB không khởi động

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs mongo

# Reset replica set
docker-compose -f docker-compose.prod.yml down -v
docker-compose -f docker-compose.prod.yml up -d
```

### SonarQube out of memory

```bash
# Increase vm.max_map_count (required for Elasticsearch)
sudo sysctl -w vm.max_map_count=262144

# Make permanent
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

### Celery tasks not running

```bash
# Check RabbitMQ connection
docker-compose -f docker-compose.prod.yml logs rabbitmq

# Check worker logs
docker-compose -f docker-compose.prod.yml logs celery-worker

# Verify queues
docker exec prod-rabbitmq rabbitmqctl list_queues
```

### Grafana dashboards not loading

```bash
# Check provisioning
docker-compose -f docker-compose.prod.yml logs grafana

# Verify dashboard files
docker exec prod-grafana ls /etc/grafana/provisioning/dashboards/json/
```

## 🔐 Security Checklist

- [ ] Change all default passwords in `.env`
- [ ] Generate strong `SECRET_KEY` and `NEXTAUTH_SECRET`
- [ ] Restrict ports exposure in production (only 80, 3001)
- [ ] Enable HTTPS with SSL certificates (update nginx.conf)
- [ ] Configure firewall rules
- [ ] Set up regular backups

## 📚 Related Docs

- [GRAFANA_SETUP.md](./GRAFANA_SETUP.md) - Grafana configuration details
- [MODEL_PIPELINE_FLOW.md](../MODEL_PIPELINE_FLOW.md) - Model pipeline documentation
- [DATASET_ENRICHMENT_FLOW.md](../DATASET_ENRICHMENT_FLOW.md) - Dataset enrichment flow
