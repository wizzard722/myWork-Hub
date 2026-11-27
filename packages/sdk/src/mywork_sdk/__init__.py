"""myWork-Hub SDK: gedeelde bouwstenen voor de core en alle app-services."""

from mywork_sdk.manifest import AppManifest, EventSpec, load_manifest
from mywork_sdk.service import HealthStatus, create_service

__all__ = ["AppManifest", "EventSpec", "HealthStatus", "create_service", "load_manifest"]
__version__ = "0.1.0"
