# SonarQube & Trivy Remote Deployment Guide

Hướng dẫn cấu hình chạy SonarQube và Trivy trên server riêng.

## Development Workflow (Recommended)

```
┌─────────────────────────────────────┐
│     Local (Dev Machine)             │
│  Frontend :3000  Backend :8000      │
│  Redis :6379     MongoDB :27017     │
│  Celery (default queues only)       │
└──────────────┬──────────────────────┘
               │ SSH -R 6379,27017
               ▼
┌─────────────────────────────────────┐
│       Remote Scanner Server         │
│  SonarQube :9000    Trivy           │
│  Celery Worker (trivy_scan,         │
│  sonar_scan queues)                 │
└─────────────────────────────────────┘
```

---

## Quick Start

### 1. Scanner Server Setup

```bash
# SSH to scanner server
ssh user@scanner-server

# Clone project
git clone https://github.com/your-repo/build-risk-dashboard.git
cd build-risk-dashboard

# Copy env
cp .env.scanner.example .env.scanner
nano .env.scanner  # Edit với IP local của bạn

# Start services
docker compose -f docker-compose.scanner.yml --env-file .env.scanner up -d

# Wait for SonarQube (2-3 mins on first start)
docker logs -f sonarqube
```

### 2. Local Machine Setup

**Terminal 1: SSH Tunnel**
```bash
ssh -R 6379:localhost:6379 -R 27017:localhost:27017 user@scanner-server -N
```

**Terminal 2: Backend**
```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 3: Celery (default queues only)**
```bash
cd backend
uv run celery -A app.celery_app worker -Q pipeline.default,import_repo,data_processing,export,collect_workflow_logs
```

**Terminal 4: Frontend**
```bash
cd frontend
npm run dev
```

### 3. Local `.env` Configuration

```env
# SonarQube - point to scanner server
SONAR_HOST_URL=http://SCANNER_SERVER_IP:9000
SONAR_TOKEN=your-token-here

# Or if using SSH tunnel to forward port 9000
# ssh -L 9000:localhost:9000 user@scanner-server -N
SONAR_HOST_URL=http://localhost:9000

# Trivy runs on scanner server
TRIVY_ENABLED=true
TRIVY_ASYNC_THRESHOLD=1000
```

---

## SSH Tunnel Commands

### Forward all ports (run on local):
```bash
# Forward SonarQube to local + Expose Redis/MongoDB to scanner
ssh -L 9000:localhost:9000 \
    -R 6379:localhost:6379 \
    -R 27017:localhost:27017 \
    user@scanner-server -N
```

### Keep tunnel alive with autossh:
```bash
# Install autossh first
brew install autossh  # macOS

autossh -M 0 -f -N \
    -L 9000:localhost:9000 \
    -R 6379:localhost:6379 \
    -R 27017:localhost:27017 \
    user@scanner-server
```

---

## Scanner Server .env.scanner

```env
# Main server connection (via SSH tunnel)
MAIN_SERVER_REDIS_URL=redis://localhost:6379/0
MAIN_SERVER_MONGODB_URL=mongodb://localhost:27017/buildguard

# SonarQube token
SONAR_TOKEN=your-token-here
```

---

## SonarQube Initial Setup

1. Access: `http://SCANNER_IP:9000`
2. Login: `admin` / `admin` (change on first login)
3. Generate token: **My Account → Security → Generate Token**
4. Create webhook: **Administration → Configuration → Webhooks**
   - URL: `http://YOUR_LOCAL_IP:8000/api/sonar/webhook`

---

## Verify Connection

```bash
# Test SonarQube API
curl -u admin:TOKEN http://SCANNER_IP:9000/api/system/status

# Check Celery worker on scanner
docker logs celery-scanner

# Check queues
cd backend && uv run celery -A app.celery_app inspect active_queues
```

---

## Resource Requirements

| Component | RAM | CPU | Disk |
|-----------|-----|-----|------|
| SonarQube | 4GB+ | 2 cores | 50GB |
| Trivy | 2GB | 1 core | 20GB |
| Celery Worker | 2GB | 2 cores | - |
