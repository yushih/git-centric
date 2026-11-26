"""Exercise the standalone trigger and status while Git is deliberately blocked."""

import asyncio
from threading import Event

import httpx
import pytest
from test_initialization import isolated_git_config, repo  # noqa: F401

from pygc import Failure, FailureReason, Finalization, Success, library
from pygc.web import create_app


async def wait_for_state(client, expected):
    # A bounded wait permits the worker to publish without relying on a fixed sleep.
    async with asyncio.timeout(3):
        while True:
            response = await client.get("/api/finalization")
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            if response.json()["state"] == expected:
                return response.json()
            await asyncio.sleep(0.01)


def test_action_trigger_and_poll_are_independent(repo, monkeypatch):  # noqa: F811
    entered, release = Event(), Event()
    calls = []

    def blocked(directory):
        calls.append(directory)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
            return Failure(FailureReason.STALE_SNAPSHOT, "metadata moved")
        return Success(Finalization(True, "abc", ("peer",), (), ()))

    monkeypatch.setattr(library, "finalize", blocked)

    async def exercise():
        app = create_app(directory=repo)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            # The write completes locally. Neither the action nor a poll starts a round.
            result = await client.post(
                "/api/rpc", json={"jsonrpc": "2.0", "id": 1, "method": "repo.initialize"}
            )
            assert "result" in result.json()
            await wait_for_state(client, "idle")
            assert calls == []
            denied = await client.post("/api/finalization", headers={"origin": "https://other.org"})
            assert denied.status_code == 403
            try:
                accepted = await client.post("/api/finalization")
                assert accepted.status_code == 202 and accepted.json()["state"] == "running"
                assert await asyncio.to_thread(entered.wait, 2)
                # Another action, polls and triggers return while round one is blocked.
                result = await client.post(
                    "/api/rpc",
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "issues.create",
                        "params": {"title": "Two"},
                    },
                )
                assert "result" in result.json()
                for _ in range(3):
                    assert (await client.post("/api/finalization")).json()["pending"]
                assert (await wait_for_state(client, "running"))["pending"]
                assert calls == [repo]
            finally:
                release.set()
            done = await wait_for_state(client, "finalized")
            assert calls == [repo, repo] and not done["pending"] and done["tip"] == "abc"

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "outcome,state",
    [
        (Success(Finalization(False, "abc", (), (), ("no finality",))), "not_finalized"),
        (Failure(FailureReason.CONFLICT_CHANGE, "conflict change"), "conflict"),
        (Failure(FailureReason.GIT_ERROR, "private diagnostic"), "failed"),
    ],
)
def test_terminal_outcomes(repo, monkeypatch, outcome, state):  # noqa: F811
    # Keep the terminal state available to all subsequent polling clients.
    monkeypatch.setattr(library, "finalize", lambda directory: outcome)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(directory=repo)),
            base_url="http://localhost",
        ) as client:
            await client.post("/api/finalization")
            report = await wait_for_state(client, state)
            if isinstance(outcome, Failure):
                assert report["error"] == outcome.reason.value
                assert "private diagnostic" not in str(report)
            else:
                assert report["warnings"] == ["no finality"]

    asyncio.run(exercise())
