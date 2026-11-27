"""myWork-Hub SDK: gedeelde bouwstenen voor de core en alle app-services."""

from mywork_sdk.auth import HubAuth, HubUser, current_user, require_role
from mywork_sdk.manifest import AppManifest, EventSpec, ToolSpec, load_manifest
from mywork_sdk.service import HealthStatus, create_service

__all__ = [
    "AppManifest",
    "EventSpec",
    "HealthStatus",
    "HubAuth",
    "HubUser",
    "ToolSpec",
    "create_service",
    "current_user",
    "load_manifest",
    "require_role",
]
__version__ = "0.1.0"
