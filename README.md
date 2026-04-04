# Calsync

FastAPI backend for the Calsync email coordination agent.

## Run locally

```bash
uvicorn app.main:app --reload
```

## Webhook endpoints

- `GET /webhooks/health`
- `POST /webhooks/events`
