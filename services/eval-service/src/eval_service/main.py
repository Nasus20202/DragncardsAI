from __future__ import annotations

import logging
import os

import uvicorn

from eval_service.config import Settings
from eval_service.mcp_server import mount as mount_mcp
from eval_service.runtime.app import create_app
from eval_service.telemetry import setup_telemetry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    setup_telemetry()
    settings = Settings()
    logger.info(
        "Starting eval-service on %s:%s",
        os.environ.get("HTTP_HOST", settings.http_host),
        os.environ.get("HTTP_PORT", str(settings.http_port)),
    )
    app = create_app(settings=settings)
    # Mounted here rather than in the app factory: the test suites build the
    # app directly and must not start the MCP session manager.
    mount_mcp(app)
    uvicorn.run(
        app,
        host=os.environ.get("HTTP_HOST", settings.http_host),
        port=int(os.environ.get("HTTP_PORT", str(settings.http_port))),
    )


if __name__ == "__main__":
    main()
