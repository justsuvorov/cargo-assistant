from typing import final


@final
class ReportError(Exception):
    """Result that cannot be laid out by the form, such as a card without a verdict for a row."""

    __slots__ = ()
