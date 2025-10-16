import copy
import logging
from logging.config import dictConfig
from typing import Any, Dict

from uvicorn.config import LOGGING_CONFIG as UVICORN_LOGGING_CONFIG


_NOISY_LOGGERS = {
    "telegram": logging.INFO,
    "telegram.bot": logging.INFO,
    "httpcore": logging.INFO,
    "PIL": logging.INFO,
    "PIL.Image": logging.INFO,
    "PIL.PngImagePlugin": logging.INFO,
}


def configure_logging(debug: bool = False) -> None:
    """Configure application logging for both uvicorn and gunicorn contexts."""
    log_level = "DEBUG" if debug else "INFO"

    logging_config: Dict[str, Any] = copy.deepcopy(UVICORN_LOGGING_CONFIG)

    # Prefer consistent stdout logging without color codes for easier aggregation
    logging_config["formatters"]["default"][
        "fmt"
    ] = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    logging_config["formatters"]["default"]["use_colors"] = False
    logging_config["formatters"]["access"][
        "fmt"
    ] = '%(asctime)s | %(levelname)s | %(client_addr)s - "%(request_line)s" %(status_code)s'

    logging_config["handlers"]["default"]["stream"] = "ext://sys.stdout"
    logging_config["handlers"]["access"]["stream"] = "ext://sys.stdout"

    logging_config["loggers"]["uvicorn"]["level"] = log_level
    logging_config["loggers"]["uvicorn.error"]["level"] = log_level
    logging_config["loggers"]["uvicorn.access"]["level"] = "INFO"

    # Ensure gunicorn master process messages share the same handler formatting
    logging_config["loggers"]["gunicorn.error"] = {
        "handlers": ["default"],
        "level": log_level,
        "propagate": False,
    }
    logging_config["loggers"]["gunicorn.access"] = {
        "handlers": ["access"],
        "level": "INFO",
        "propagate": False,
    }

    logging_config["root"] = {"handlers": ["default"], "level": log_level}

    dictConfig(logging_config)

    # Keep noisy third-party libraries polite by default
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.INFO)

    for logger_name, level in _NOISY_LOGGERS.items():
        logging.getLogger(logger_name).setLevel(level)
