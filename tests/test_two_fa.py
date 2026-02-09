"""Tests for 2FA session manager and relay integration."""

import asyncio

import pytest

from app.services.two_fa import (
    TWO_FA_MAX_ATTEMPTS,
    TwoFAChallenge,
    TwoFASession,
    TwoFATimeoutError,
    _active_sessions,
    create_session,
    get_session,
    remove_session,
)


@pytest.fixture(autouse=True)
def _clear_sessions():
    """Ensure session registry is clean before each test."""
    _active_sessions.clear()
    yield
    _active_sessions.clear()


def _make_challenge(method: str = "sms") -> TwoFAChallenge:
    return TwoFAChallenge(
        method=method,
        prompt="Enter the code sent to ***1234",
        methods_available=[method],
    )


class TestTwoFASession:
    """Unit tests for TwoFASession dataclass."""

    @pytest.mark.asyncio
    async def test_wait_and_submit(self):
        """submit_code unblocks wait_for_code and returns correct code."""
        session = TwoFASession(sync_log_id=1, provider="nelnet", challenge=_make_challenge())

        async def submit_later():
            await asyncio.sleep(0.05)
            session.submit_code("123456")

        task = asyncio.create_task(submit_later())  # noqa: RUF006
        code = await session.wait_for_code(timeout=2.0)

        assert code == "123456"
        assert session.attempts == 1

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Raises TwoFATimeoutError when no code submitted within timeout."""
        session = TwoFASession(sync_log_id=1, provider="nelnet", challenge=_make_challenge())

        with pytest.raises(TwoFATimeoutError, match="not submitted"):
            await session.wait_for_code(timeout=0.1)

    @pytest.mark.asyncio
    async def test_reset_and_retry(self):
        """reset() clears event, allowing a second wait_for_code."""
        session = TwoFASession(sync_log_id=1, provider="nelnet", challenge=_make_challenge())

        # First round
        async def submit_first():
            await asyncio.sleep(0.05)
            session.submit_code("111111")

        task = asyncio.create_task(submit_first())  # noqa: RUF006
        code1 = await session.wait_for_code(timeout=2.0)
        assert code1 == "111111"

        # Reset for retry
        session.reset()
        assert session.attempts == 1  # attempts preserved
        assert session._code is None

        # Second round
        async def submit_second():
            await asyncio.sleep(0.05)
            session.submit_code("222222")

        task = asyncio.create_task(submit_second())  # noqa: RUF006
        code2 = await session.wait_for_code(timeout=2.0)
        assert code2 == "222222"
        assert session.attempts == 2

    def test_max_attempts(self):
        """max_attempts_exceeded becomes True after N submits."""
        session = TwoFASession(sync_log_id=1, provider="nelnet", challenge=_make_challenge())

        for i in range(TWO_FA_MAX_ATTEMPTS):
            assert not session.max_attempts_exceeded
            session.submit_code(f"{i:06d}")

        assert session.max_attempts_exceeded
        assert session.attempts == TWO_FA_MAX_ATTEMPTS


class TestSessionRegistry:
    """Test module-level session registry."""

    def test_create_get_remove(self):
        """Full lifecycle: create, get, remove."""
        challenge = _make_challenge()
        session = create_session(42, "nelnet", challenge)

        assert session.sync_log_id == 42
        assert session.provider == "nelnet"

        # Get returns same session
        fetched = get_session(42)
        assert fetched is session

        # Remove
        remove_session(42)
        assert get_session(42) is None

    def test_get_nonexistent(self):
        """get_session returns None for unknown ID."""
        assert get_session(999) is None

    def test_remove_nonexistent(self):
        """remove_session is safe for unknown ID."""
        remove_session(999)  # Should not raise


class TestTwoFAEndpoints:
    """Test 2FA HTTP endpoints via test client."""

    @pytest.mark.asyncio
    async def test_submit_code_success(self, client):
        """POST /sync/{id}/2fa succeeds with active session."""
        session = create_session(1, "nelnet", _make_challenge())

        response = await client.post("/sync/1/2fa", json={"code": "123456"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert data["attempts"] == 1
        assert session._code == "123456"

    @pytest.mark.asyncio
    async def test_submit_code_no_session(self, client):
        """POST /sync/{id}/2fa returns 404 when no session exists."""
        response = await client.post("/sync/999/2fa", json={"code": "123456"})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_code_max_attempts(self, client):
        """POST /sync/{id}/2fa returns 400 after max attempts."""
        session = create_session(1, "nelnet", _make_challenge())

        # Exhaust attempts
        for _ in range(TWO_FA_MAX_ATTEMPTS):
            session.submit_code("wrong")

        response = await client.post("/sync/1/2fa", json={"code": "123456"})
        assert response.status_code == 400
        assert "Maximum attempts" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_2fa_status(self, client):
        """GET /sync/{id}/2fa returns challenge details."""
        create_session(1, "nelnet", _make_challenge())

        response = await client.get("/sync/1/2fa")

        assert response.status_code == 200
        data = response.json()
        assert data["sync_log_id"] == 1
        assert data["method"] == "sms"
        assert data["prompt"] == "Enter the code sent to ***1234"
        assert data["max_attempts"] == TWO_FA_MAX_ATTEMPTS

    @pytest.mark.asyncio
    async def test_get_2fa_status_no_session(self, client):
        """GET /sync/{id}/2fa returns 404 when no session exists."""
        response = await client.get("/sync/999/2fa")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_code_empty_rejected(self, client):
        """POST /sync/{id}/2fa rejects empty code (validation)."""
        create_session(1, "nelnet", _make_challenge())

        response = await client.post("/sync/1/2fa", json={"code": ""})
        assert response.status_code == 422  # Pydantic validation
