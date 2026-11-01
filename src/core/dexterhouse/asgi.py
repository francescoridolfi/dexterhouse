# SPDX-License-Identifier: AGPL-3.0-or-later
"""ASGI entry point: HTTP via Django, WebSocket via Channels."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.prod")
django_application = get_asgi_application()

# Channels routing imports models, so it must come after Django is set up.
from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from dexterhouse.apps.events.auth import (  # noqa: E402
    OriginValidatorAllowingNonBrowsers,
    TokenAuthMiddleware,
)
from dexterhouse.apps.events.routing import websocket_urlpatterns  # noqa: E402

websocket_application = AuthMiddlewareStack(TokenAuthMiddleware(URLRouter(websocket_urlpatterns)))

application = ProtocolTypeRouter(
    {
        "http": django_application,
        "websocket": OriginValidatorAllowingNonBrowsers(websocket_application),
    }
)
