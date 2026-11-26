"""Coordinate background consensus for one web app and its selected repository."""

import asyncio
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from . import library

type State = Literal["idle", "running", "finalized", "not_finalized", "conflict", "failed"]


@dataclass(frozen=True)
class FinalizationStatus:
    state: State = "idle"
    pending: bool = False
    tip: str | None = None
    warnings: tuple[str, ...] = ()
    error: str | None = None


class WebFinalization:
    """Only the ASGI event loop touches this state. Only Git runs in a thread."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.status = FinalizationStatus()
        self.worker: asyncio.Task[None] | None = None

    def request(self) -> FinalizationStatus:
        # Reserve a worker before returning 202. Arrivals during its round may
        # represent a newer commit, so remember one follow-up rather than dropping them.
        if self.worker is None:
            self.status = FinalizationStatus("running")
            self.worker = asyncio.create_task(self._drain())
        else:
            self.status = replace(self.status, pending=True)
        return self.status

    async def _drain(self) -> None:
        try:
            while True:
                # Run Git off the event loop so both status and action requests remain responsive.
                try:
                    result = await asyncio.to_thread(library.finalize, self.directory)
                    if isinstance(result, library.Success):
                        value = result.value
                        outcome = FinalizationStatus(
                            "finalized" if value.finalized else "not_finalized",
                            tip=value.tip,
                            warnings=value.warnings,
                        )
                    else:
                        outcome = FinalizationStatus(
                            "conflict"
                            if result.reason == library.FailureReason.CONFLICT_CHANGE
                            else "failed",
                            error=result.reason.value,
                        )
                except Exception:
                    logging.getLogger(__name__).exception("Web finalization failed")
                    outcome = FinalizationStatus("failed", error="unexpected_error")

                # No await between checking pending and publishing the result:
                # a trigger either joins this loop or starts the next worker.
                if not self.status.pending:
                    self.status = outcome
                    return
                self.status = FinalizationStatus("running")
        finally:
            self.worker = None

    async def finish(self) -> None:
        if self.worker is not None:
            await self.worker
