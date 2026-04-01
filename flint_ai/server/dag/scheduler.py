"""Cron/interval scheduler for recurring workflow execution."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger("flint.server.dag.scheduler")


class ScheduledWorkflow:
    """A workflow scheduled for recurring execution."""

    def __init__(
        self,
        workflow_id: str,
        cron: Optional[str] = None,
        interval_s: Optional[int] = None,
    ) -> None:
        self.workflow_id = workflow_id
        self.cron = cron
        self.interval_s = interval_s
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.enabled = True


class WorkflowScheduler:
    """Manages recurring workflow execution.

    Supports:
    - Interval-based scheduling (every N seconds)
    - Cron-based scheduling (requires croniter package)
    """

    def __init__(
        self,
        trigger_callback: Callable[[str], Coroutine[Any, Any, Any]],
    ) -> None:
        self._callback = trigger_callback
        self._schedules: Dict[str, ScheduledWorkflow] = {}
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def add(
        self,
        workflow_id: str,
        cron: Optional[str] = None,
        interval_s: Optional[int] = None,
    ) -> None:
        """Add a workflow to the schedule."""
        if not cron and not interval_s:
            raise ValueError("Either cron or interval_s must be specified")

        sched = ScheduledWorkflow(workflow_id, cron=cron, interval_s=interval_s)
        sched.next_run = self._calc_next_run(sched)
        self._schedules[workflow_id] = sched
        logger.info(
            "Scheduled workflow=%s cron=%s interval=%s next=%s",
            workflow_id, cron, interval_s, sched.next_run,
        )

    def remove(self, workflow_id: str) -> None:
        self._schedules.pop(workflow_id, None)

    def _calc_next_run(self, sched: ScheduledWorkflow) -> datetime:
        now = datetime.now(timezone.utc)

        if sched.interval_s:
            if sched.last_run:
                from datetime import timedelta
                return sched.last_run + timedelta(seconds=sched.interval_s)
            return now

        if sched.cron:
            try:
                from croniter import croniter
                cron = croniter(sched.cron, now)
                return cron.get_next(datetime).replace(tzinfo=timezone.utc)
            except ImportError:
                logger.warning(
                    "croniter not installed — cron scheduling disabled. "
                    "Install with: pip install croniter"
                )
                return now
            except Exception as e:
                logger.error("Invalid cron expression %r: %s", sched.cron, e)
                return now

        return now

    async def start(self) -> None:
        """Start the scheduler loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Scheduler started with %d workflows", len(self._schedules))

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _loop(self) -> None:
        """Main scheduler loop — checks every second for due workflows."""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                for wf_id, sched in list(self._schedules.items()):
                    if not sched.enabled or not sched.next_run:
                        continue
                    if now >= sched.next_run:
                        logger.info("Triggering scheduled workflow=%s", wf_id)
                        try:
                            await self._callback(wf_id)
                            sched.last_run = now
                            sched.next_run = self._calc_next_run(sched)
                        except Exception:
                            logger.exception("Failed to trigger workflow=%s", wf_id)
                            sched.next_run = self._calc_next_run(sched)

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Scheduler loop error")
                await asyncio.sleep(5)

    def list_schedules(self) -> List[Dict[str, Any]]:
        """Return current schedule info."""
        return [
            {
                "workflow_id": s.workflow_id,
                "cron": s.cron,
                "interval_s": s.interval_s,
                "enabled": s.enabled,
                "last_run": s.last_run.isoformat() if s.last_run else None,
                "next_run": s.next_run.isoformat() if s.next_run else None,
            }
            for s in self._schedules.values()
        ]
