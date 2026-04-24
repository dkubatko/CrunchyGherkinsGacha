"""Fair-order buffer for roll-lifecycle button callbacks.

Telegram's inline ``CallbackQuery`` does not carry a client-side click
timestamp, and ``Application(concurrent_updates=True)`` dispatches every
incoming update into its own asyncio task immediately. The consequence is
that two near-simultaneous clicks on the same rolled item race for the
database ``FOR UPDATE`` row lock, and the "winner" is determined by Python
scheduler jitter in the handler preamble — not by who clicked first.

This module introduces a small in-memory buffer that sits in front of
``handle_claim`` / ``handle_lock`` / ``handle_reroll``. All three actions
are serialized per ``roll_key = f"{roll_type}:{roll_id}"`` so that a
reroll arriving 50 ms after a claim on the same roll resolves in true
click order. Ordering key is ``(update_id, server_receipt_ns)``:

* ``update_id`` is assigned by **Telegram's servers** and is the closest
  proxy to click order available without a MiniApp.
* ``server_receipt_ns`` is only a tiebreaker for updates arriving in the
  same Telegram batch with equal IDs (shouldn't happen, but defensive).

The buffer lives on ``application.bot_data`` and is safe in-process:
the ``bot`` service runs as a single process (the ``api`` service's 5
Gunicorn workers do NOT receive Telegram updates).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Optional

from telegram import Update
from telegram.ext import ContextTypes

from utils.schemas import User

logger = logging.getLogger(__name__)

ActionKind = Literal["claim", "lock", "reroll"]
ActionProcessor = Callable[["PendingAction"], Awaitable[None]]


@dataclass
class PendingAction:
    """A queued roll-lifecycle callback awaiting fair-ordered processing."""

    action: ActionKind
    roll_key: str
    update_id: int
    receipt_ns: int
    update: Update
    context: ContextTypes.DEFAULT_TYPE
    user: User
    processor: ActionProcessor
    future: asyncio.Future = field(
        default_factory=lambda: asyncio.get_running_loop().create_future()
    )

    @property
    def sort_key(self) -> tuple[int, int]:
        return (self.update_id, self.receipt_ns)


@dataclass
class _RollSlot:
    """Per-``roll_key`` mutable state held inside the buffer."""

    queue: list[PendingAction] = field(default_factory=list)
    drain_task: Optional[asyncio.Task] = None
    window_deadline_ns: Optional[int] = None
    first_seen_ns: Optional[int] = None
    dedup_keys: set[tuple[int, str]] = field(default_factory=set)  # (user_id, action)


class RollActionBuffer:
    """Per-``roll_key`` fair-ordering buffer for claim/lock/reroll callbacks."""

    def __init__(self, window_ms: int = 250) -> None:
        self._window_ns = window_ms * 1_000_000
        self._slots: dict[str, _RollSlot] = {}
        self._lock = asyncio.Lock()

    async def submit(self, pending: PendingAction) -> bool:
        """Enqueue a pending action. Returns ``False`` if dropped as duplicate.

        When ``True`` is returned, the caller should ``await pending.future``
        to block until processing has actually completed.
        """
        user_tag = _user_tag(pending.user)
        async with self._lock:
            slot = self._slots.setdefault(pending.roll_key, _RollSlot())
            dedup_key = (pending.user.user_id, pending.action)
            if dedup_key in slot.dedup_keys:
                logger.info(
                    "[roll %s] DROP duplicate %s from %s (update_id=%d)",
                    pending.roll_key,
                    pending.action,
                    user_tag,
                    pending.update_id,
                )
                pending.future.set_result(None)
                return False

            slot.dedup_keys.add(dedup_key)

            now_ns = time.monotonic_ns()
            is_first = slot.first_seen_ns is None
            if is_first:
                # Anchor on the pending's own stamp so the first entry reads
                # as t+0ms in drain logs (receipt_ns is stamped in the handler,
                # fractionally earlier than now_ns here).
                slot.first_seen_ns = pending.receipt_ns
                slot.window_deadline_ns = pending.receipt_ns + self._window_ns

            offset_ms = (now_ns - (slot.first_seen_ns or now_ns)) / 1_000_000
            slot.queue.append(pending)

            if is_first:
                logger.info(
                    "[roll %s] QUEUE %s by %s (update_id=%d, t+0ms — window opens, drain in %dms)",
                    pending.roll_key,
                    pending.action,
                    user_tag,
                    pending.update_id,
                    self._window_ns // 1_000_000,
                )
            else:
                logger.info(
                    "[roll %s] QUEUE %s by %s (update_id=%d, t+%.0fms)",
                    pending.roll_key,
                    pending.action,
                    user_tag,
                    pending.update_id,
                    offset_ms,
                )

            if slot.drain_task is None or slot.drain_task.done():
                slot.drain_task = asyncio.create_task(self._drain(pending.roll_key))

            return True

    async def _drain(self, roll_key: str) -> None:
        """Wait out the buffer window, then process entries in sort-key order."""
        try:
            # Phase 1: sleep until the window deadline to let concurrent clicks accumulate.
            while True:
                async with self._lock:
                    slot = self._slots.get(roll_key)
                    if slot is None or not slot.queue:
                        return
                    deadline = slot.window_deadline_ns or 0
                now_ns = time.monotonic_ns()
                remaining_ns = deadline - now_ns
                if remaining_ns <= 0:
                    break
                await asyncio.sleep(remaining_ns / 1_000_000_000)

            # Phase 2: drain in order. New clicks arriving while we run this loop
            # are appended to slot.queue and will be processed in subsequent
            # iterations (re-sorted each time) without overlap.
            while True:
                async with self._lock:
                    slot = self._slots.get(roll_key)
                    if slot is None or not slot.queue:
                        # All done — clean up the slot entirely so a fresh
                        # window starts for the next click.
                        if slot is not None:
                            self._slots.pop(roll_key, None)
                        return
                    slot.queue.sort(key=lambda p: p.sort_key)
                    self._log_drain_order(roll_key, slot)
                    next_action = slot.queue.pop(0)

                # Process outside the buffer lock so other clicks can still enqueue.
                # Dedup key stays registered for the duration of processing, so a
                # user clicking while their own previous click is in-flight gets
                # silently dropped (matches the old @prevent_concurrency behavior).
                try:
                    await self._invoke(next_action)
                finally:
                    async with self._lock:
                        slot2 = self._slots.get(roll_key)
                        if slot2 is not None:
                            slot2.dedup_keys.discard(
                                (next_action.user.user_id, next_action.action)
                            )
        except Exception:
            logger.exception("Drain loop crashed for %s", roll_key)
            # Fail any remaining futures so callers don't hang forever.
            async with self._lock:
                slot = self._slots.pop(roll_key, None)
                if slot:
                    for p in slot.queue:
                        if not p.future.done():
                            p.future.set_exception(RuntimeError("drain-loop-crashed"))

    def _log_drain_order(self, roll_key: str, slot: _RollSlot) -> None:
        first = slot.first_seen_ns or 0
        parts = []
        for i, p in enumerate(slot.queue, start=1):
            delta_ms = ((p.receipt_ns - first) / 1_000_000) if first else 0
            parts.append(
                f"#{i} {p.action} by {_user_tag(p.user)} "
                f"update_id={p.update_id} t+{delta_ms:.0f}ms"
            )
        logger.info(
            "[roll %s] DRAIN ORDER (%d pending): %s",
            roll_key,
            len(slot.queue),
            " | ".join(parts) if parts else "(empty)",
        )

    async def _invoke(self, pending: PendingAction) -> None:
        user_tag = _user_tag(pending.user)
        start_ns = time.monotonic_ns()
        logger.info(
            "[roll %s] PROCESS %s by %s (update_id=%d)",
            pending.roll_key,
            pending.action,
            user_tag,
            pending.update_id,
        )
        try:
            await pending.processor(pending)
            if not pending.future.done():
                pending.future.set_result(None)
            elapsed_ms = (time.monotonic_ns() - start_ns) / 1_000_000
            logger.info(
                "[roll %s] DONE %s by %s (update_id=%d, took %.0fms)",
                pending.roll_key,
                pending.action,
                user_tag,
                pending.update_id,
                elapsed_ms,
            )
        except Exception as exc:
            logger.exception(
                "[roll %s] FAIL %s by %s (update_id=%d): %s",
                pending.roll_key,
                pending.action,
                user_tag,
                pending.update_id,
                exc,
            )
            if not pending.future.done():
                pending.future.set_exception(exc)


def _user_tag(user: User) -> str:
    """Readable identifier for log output."""
    name = (
        getattr(user, "display_name", None)
        or getattr(user, "username", None)
        or "?"
    )
    return f"@{name}({user.user_id})"


# ---------------------------------------------------------------------------
# bot_data helpers
# ---------------------------------------------------------------------------

_BOT_DATA_KEY = "roll_action_buffer"


def get_buffer(bot_data: dict[str, Any]) -> RollActionBuffer:
    """Fetch (or lazily create) the shared ``RollActionBuffer``."""
    buf = bot_data.get(_BOT_DATA_KEY)
    if buf is None:
        # Import here to avoid a circular import at module load time.
        from settings.constants import ROLL_ACTION_BUFFER_WINDOW_MS

        buf = RollActionBuffer(window_ms=ROLL_ACTION_BUFFER_WINDOW_MS)
        bot_data[_BOT_DATA_KEY] = buf
    return buf
