import logging
from pathlib import Path

from alembic.config import Config

from alembic import command

logger = logging.getLogger(__name__)


def run_migrations(database_url: str) -> None:
    """Применить все непримененные миграции (alembic upgrade head)."""
    project_root = Path(__file__).resolve().parents[3]
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    logger.info("Running alembic upgrade head...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Alembic migrations applied")
