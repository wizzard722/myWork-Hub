# __APP_NAME__

__APP_DESCRIPTION__

App-service voor myWork-Hub, gemaakt met `scripts/new_app.py`.
Ontwikkelhandleiding: [docs/apps.md](../../docs/apps.md).

| | |
| --- | --- |
| App-id | `__APP_ID__` |
| Publiek pad | `/api/apps/__APP_ID__/` |
| API-documentatie | `/api/apps/__APP_ID__/docs` |
| Service (Docker/Kubernetes) | `app-__APP_ID__` |

```bash
uv run pytest apps/__APP_ID__
MODULE=__APP_MODULE__.main uv run python -m mywork_sdk.serve   # lokaal op :8000
```
