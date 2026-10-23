import logging
import sys
from pythonjsonlogger import jsonlogger

def configure_logging(level: str = "INFO"):
    log = logging.getLogger()
    log.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        "%({levelname)s)s %(asctime)s %(name)s %(message)s",
        rename_fields={"levelname": "level", "asctime": "timestamp"},
    )
    handler.setFormatter(formatter)
    log.handlers = []
    log.addHandler(handler)

