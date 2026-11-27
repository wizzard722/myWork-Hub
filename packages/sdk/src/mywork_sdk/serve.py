"""Starter voor services in een container zonder shell (gehardende images).

Gebruik: ``python -m mywork_sdk.serve``. Instellingen via omgevingsvariabelen:

- ``MODULE``     Python-module met de FastAPI-``app`` (verplicht), bijv. ``core.main``
- ``ROOT_PATH``  Publiek pad achter de gateway, bijv. ``/api/apps/hello``
- ``PORT``       Poort (standaard 8000)
"""

import os
from collections.abc import Mapping
from typing import Any


def server_options(env: Mapping[str, str]) -> dict[str, Any]:
    module = env.get("MODULE", "").strip()
    if not module:
        raise SystemExit("MODULE is niet gezet (bijv. MODULE=core.main)")
    return {
        "app": f"{module}:app",
        "host": env.get("HOST", "0.0.0.0"),
        "port": int(env.get("PORT", "8000")),
        "root_path": env.get("ROOT_PATH", ""),
        "proxy_headers": True,
        # Alleen de gateway kan de service bereiken; die zet X-Forwarded-*.
        "forwarded_allow_ips": "*",
        "server_header": False,
    }


def main() -> None:
    import uvicorn

    uvicorn.run(**server_options(os.environ))


if __name__ == "__main__":
    main()
