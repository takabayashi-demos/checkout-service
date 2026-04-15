# checkout-service

Walmart checkout and order processing service

## Tech Stack
- **Language**: java
- **Team**: commerce
- **Platform**: Walmart Global K8s

## Quick Start
```bash
docker build -t checkout-service:latest .
docker run -p 8080:8080 checkout-service:latest
curl http://localhost:8080/health
```

## API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /ready | Readiness probe |
| GET | /metrics | Prometheus metrics |
# PR 1 - 2026-04-15T18:47:13
