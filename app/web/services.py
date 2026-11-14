from dataclasses import dataclass

from app.auth.exchange import Tokens
from app.auth.passport import Passport
from app.auth.seal import Seal
from app.core.settings import Settings
from app.jobs.database import Sessions
from app.jobs.folios import Folio
from app.jobs.packages import Packages
from app.jobs.queue import Jobs
from app.jobs.workspaces import Workspaces
from app.storage.disk import Storage


@dataclass(frozen=True)
class Services:
    """Objects that the web layer needs, built once when the application starts."""

    settings: Settings
    database: Sessions
    jobs: Jobs
    workspaces: Workspaces
    packages: Packages
    folio: Folio
    passport: Passport
    session: Passport
    seal: Seal
    tokens: Tokens
    storage: Storage
