from pydantic import BaseModel, ConfigDict


class Trial(BaseModel):
    """Answer to the made-up probe question about whether a cargo falls under a clause."""

    model_config = ConfigDict(extra="forbid")

    covered: bool
    reason: str
