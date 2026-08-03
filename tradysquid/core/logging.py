import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .config import redact

class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))

def configure_logging(log_dir: Path, level: str = 'INFO') -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = RedactingFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    for name, minimum in [('tradysquid.log', logging.INFO), ('errors.log', logging.ERROR), ('audit.log', logging.INFO)]:
        handler = RotatingFileHandler(log_dir / name, maxBytes=2_000_000, backupCount=5, encoding='utf-8')
        handler.setLevel(minimum); handler.setFormatter(formatter); root.addHandler(handler)
