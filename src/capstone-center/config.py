import logging
from logging.handlers import RotatingFileHandler

LOG_FORMAT = (
    "%(asctime)s "
    "%(levelname)s "
    "pid=%(process)d "
    "%(name)s "
    "%(pathname)s:%(lineno)d "
    "- %(message)s"
)


