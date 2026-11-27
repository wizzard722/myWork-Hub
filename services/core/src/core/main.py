from core import __version__
from core.registry import router as registry_router
from core.theming import router as theming_router
from mywork_sdk import create_service

app = create_service(name="core", version=__version__)
app.include_router(theming_router)
app.include_router(registry_router)
