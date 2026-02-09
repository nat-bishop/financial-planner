"""2FA session manager — in-memory coordination between background sync tasks and HTTP endpoints.

When a browser provider detects a 2FA challenge during sync, it creates a TwoFASession
and suspends on `wait_for_code()`. The frontend polls `/sync/status`, sees `awaiting_2fa`,
and submits the code via `POST /sync/{id}/2fa`, which calls `submit_code()` to unblock
the waiting task.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

TWO_FA_TIMEOUT = 600  # 10 minutes
TWO_FA_MAX_ATTEMPTS = 3


class TwoFAError(Exception):
    """Base 2FA error."""


class TwoFATimeoutError(TwoFAError):
    """Code not submitted within timeout."""


@dataclass
class TwoFAChallenge:
    """Describes a 2FA challenge detected by a browser provider."""

    method: str  # "sms", "email", "authenticator", "unknown"
    prompt: str  # Human-readable message, e.g. "Enter the code sent to ***1234"
    methods_available: list[str] = field(default_factory=list)


@dataclass
class TwoFASession:
    """Coordination bridge for a single 2FA interaction.

    Created by the background sync task, consumed by the HTTP endpoint.
    """

    sync_log_id: int
    provider: str
    challenge: TwoFAChallenge
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    _code: str | None = field(default=None)
    _attempts: int = field(default=0)

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def max_attempts_exceeded(self) -> bool:
        return self._attempts >= TWO_FA_MAX_ATTEMPTS

    async def wait_for_code(self, timeout: float = TWO_FA_TIMEOUT) -> str:
        """Block until a code is submitted or timeout expires.

        Returns the submitted code.
        Raises TwoFATimeoutError if no code is submitted in time.
        """
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except TimeoutError:
            raise TwoFATimeoutError(
                f"2FA code not submitted within {timeout}s"
            ) from None

        assert self._code is not None
        return self._code

    def submit_code(self, code: str) -> None:
        """Submit a 2FA code, unblocking wait_for_code()."""
        self._code = code
        self._attempts += 1
        self._event.set()

    def reset(self) -> None:
        """Reset for retry (e.g., after wrong code). Clears event and code."""
        self._event.clear()
        self._code = None


# Module-level registry keyed by sync_log_id
_active_sessions: dict[int, TwoFASession] = {}


def create_session(
    sync_log_id: int,
    provider: str,
    challenge: TwoFAChallenge,
) -> TwoFASession:
    """Create and register a 2FA session."""
    session = TwoFASession(
        sync_log_id=sync_log_id,
        provider=provider,
        challenge=challenge,
    )
    _active_sessions[sync_log_id] = session
    log.info("2FA session created for sync_log %d (%s)", sync_log_id, provider)
    return session


def get_session(sync_log_id: int) -> TwoFASession | None:
    """Get an active 2FA session by sync_log_id."""
    return _active_sessions.get(sync_log_id)


def remove_session(sync_log_id: int) -> None:
    """Remove a 2FA session (cleanup)."""
    removed = _active_sessions.pop(sync_log_id, None)
    if removed:
        log.info("2FA session removed for sync_log %d", sync_log_id)
