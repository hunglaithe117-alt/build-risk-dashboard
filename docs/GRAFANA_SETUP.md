# Hướng Dẫn Cấu Hình Grafana Dashboard

## 📊 Tổng Quan

Grafana được cấu hình tự động khi deploy bằng Docker. Dashboards và datasources được provision sẵn.

## ✅ Auto-Provisioned (Docker Deployment)

Khi sử dụng `docker-compose.prod.yml`, các thành phần sau được tự động cấu hình:

### Data Sources (tự động)
- **Prometheus** - `http://prometheus:9090` (metrics)
- **Loki** - `http://loki:3100` (logs)
- **Infinity** - JSON API plugin (backend queries)

### Dashboards (tự động load)
Từ `monitoring/dashboards/`:
- `build-risk-overview.json` - Stats, risk distribution, recent builds
- `pipeline-monitoring.json` - Celery, queues, infrastructure health
- `business-metrics.json` - Risk trends, API performance
- `model-pipeline-details.json` - Repository processing status
- `dataset-enrichment-details.json` - Dataset enrichment progress

### Plugins (tự động install)
- `yesoreyeram-infinity-datasource` - JSON API queries

## � Truy Cập

| URL | Credentials |
|-----|-------------|
| http://localhost:3001 | `admin` / `GRAFANA_PASS` (từ .env) |

## 📈 Dashboard Previews

### Build Risk Overview
```
┌────────────────────────────────────────────────────────────────────┐
│                    BUILD RISK OVERVIEW                              │
├──────────────┬──────────────┬──────────────┬──────────────┬────────┤
│ Total Builds │ Success Rate │ Active Repos │ High Risk    │ Errors │
├──────────────┴──────────────┴──────────────┴──────────────┴────────┤
│  Risk Distribution (Pie)     │    Recent Builds Table              │
└─────────────────────────────────────────────────────────────────────┘
```

### Pipeline Monitoring
```
┌─────────────────────────────────────────────────────────────────────┐
│ Model Pipeline: QUEUED | FETCHING | INGESTING | PROCESSED | FAILED  │
├─────────────────────────────────────────────────────────────────────┤
│ Dataset Enrichment: VALIDATING | INGESTING | PROCESSING | COMPLETED │
├─────────────────────────────────────────────────────────────────────┤
│ Celery Workers: 3 Online  │  Queue Depths: ingestion:5 processing:2 │
├─────────────────────────────────────────────────────────────────────┤
│ Infrastructure: Redis ✅ | MongoDB ✅ | Trivy ✅ | SonarQube ✅     │
└─────────────────────────────────────────────────────────────────────┘
```

## 🔍 Loki Queries (Logs)

```logql
# All errors
{job="backend"} |= "ERROR"

# Celery tasks
{container=~"prod-celery.*"} | json

# Filter by level
{job="backend"} | json | level = "ERROR"

# Error rate
sum(rate({job="backend"} |= "ERROR" [5m]))
```

## 📊 Prometheus Queries (Metrics)

```promql
# API request rate
sum(rate(http_requests_total[5m])) by (handler)

# API latency P95
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# Build predictions by risk
sum(increase(build_risk_predictions_total[1h])) by (risk_level)

# Error rate percentage
100 * sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
```

## � Infinity Plugin (JSON API)

Để query backend API trực tiếp:

| Endpoint | Mô tả |
|----------|-------|
| `/api/dashboard/summary` | Dashboard metrics |
| `/api/dashboard/recent-builds?limit=20` | Recent builds |
| `/api/monitoring/system` | System health |
| `/api/repositories?page=1&page_size=50` | All repositories |
| `/api/projects?page=1&page_size=50` | All datasets |

**Lưu ý**: Trong Docker, sử dụng `backend:8000` thay vì `localhost:8000`

## 🔐 Embedding Configuration

Đã được cấu hình trong Docker:
```yaml
GF_SECURITY_ALLOW_EMBEDDING: "true"
GF_INSTALL_PLUGINS: yesoreyeram-infinity-datasource
```

## 🛠️ Manual Setup (Non-Docker)

Nếu không dùng Docker, thực hiện thủ công:

### 1. Add Data Sources
```bash
# Prometheus
URL: http://localhost:9090

# Loki  
URL: http://localhost:3100
```

### 2. Install Plugin
```bash
grafana-cli plugins install yesoreyeram-infinity-datasource
systemctl restart grafana-server
```

### 3. Import Dashboards
1. Dashboards → New → Import
2. Upload files từ `monitoring/dashboards/`
3. Set variable `API_BASE` = `http://localhost:8000/api`

## 📚 Related Docs

- [DOCKER_DEPLOYMENT.md](./DOCKER_DEPLOYMENT.md) - Full Docker deployment guide
