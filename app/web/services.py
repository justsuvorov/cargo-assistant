from dataclasses import dataclass

from app.auth.passport import Passport
from app.core.settings import Settings
from app.jobs.database import Sessions
from app.jobs.intake import Reception
from app.jobs.queue import Jobs


@dataclass(frozen=True)
class Services:
    """Objects that the web layer needs, built once when the application starts."""

    settings: Settings
    database: Sessions
    jobs: Jobs
    reception: Reception
    passport: Passport
