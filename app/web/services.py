from dataclasses import dataclass

from app.auth.passport import Passport
from app.core.settings import Settings
from app.jobs.database import Sessions
from app.jobs.folios import Folio
from app.jobs.intake import Reception
from app.jobs.packages import Packages
from app.jobs.queue import Jobs
from app.storage.disk import Storage


@dataclass(frozen=True)
class Services:
    """Objects that the web layer needs, built once when the application starts."""

    settings: Settings
    database: Sessions
    jobs: Jobs
    reception: Reception
    packages: Packages
    folio: Folio
    passport: Passport
    storage: Storage
