import argparse
import logging
import sys

from app.core.journal import LogJournal
from app.core.schema.environment import Environment
from app.llm.assembly import Configured
from app.llm.errors import MisconfiguredError
from app.llm.ledger import Memory


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.llm",
        description="Разведка модели по настройкам LLM_* из переменных окружения или файла .env",
    )
    parser.add_argument("command", choices=("probe",), help="probe — замеры шлюза модели")
    parser.add_argument(
        "--parallel", type=int, default=8, help="сколько запросов отправить одновременно"
    )
    parser.add_argument("--env", default=".env", help="файл с переменными окружения")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        Configured(
            Environment(arguments.env), LogJournal(logging.getLogger("llm")), Memory()
        ).probe(arguments.parallel).run(sys.stdout)
    except MisconfiguredError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
