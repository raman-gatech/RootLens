"""Browser regression tests for the incident creation dialog."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import Page, Route, expect


@pytest.fixture(scope="session")
def dashboard_url() -> Iterator[str]:
    """Run a real ASGI server while browser requests to incident APIs are mocked."""

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = os.environ.copy()
    environment.update(
        ROOTLENS_DATABASE_URL="postgresql+asyncpg://rootlens:rootlens@127.0.0.1:1/rootlens",
        ROOTLENS_TELEMETRY_ENABLED="false",
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "rootlens.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=environment,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            if process.poll() is not None:
                raise RuntimeError("dashboard test server exited during startup")
            try:
                with urlopen(f"{url}/health/live", timeout=0.25) as response:
                    if response.status == 200:
                        break
            except URLError:
                time.sleep(0.1)
        else:
            raise RuntimeError("dashboard test server did not become ready")
        yield f"{url}/dashboard"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.e2e
def test_close_and_cancel_never_submit_incident_form(page: Page, dashboard_url: str) -> None:
    submitted_requests: list[str] = []

    def handle_incidents(route: Route) -> None:
        if route.request.method == "POST":
            submitted_requests.append(route.request.post_data or "")
        route.fulfill(status=200, content_type="application/json", body="[]")

    page.route("**/api/v1/incidents**", handle_incidents)
    page.goto(dashboard_url)
    dialog = page.locator("#incident-dialog")

    page.get_by_role("button", name="New incident").click()
    expect(dialog).to_be_visible()
    page.get_by_role("button", name="Close create incident dialog").click()
    expect(dialog).to_be_hidden()
    assert submitted_requests == []

    page.get_by_role("button", name="New incident").click()
    expect(dialog).to_be_visible()
    page.get_by_role("button", name="Cancel").click()
    expect(dialog).to_be_hidden()
    assert submitted_requests == []

    page.get_by_role("button", name="New incident").click()
    page.get_by_label("Title").fill("Browser-created incident")
    page.get_by_role("button", name="Create", exact=True).click()
    expect(dialog).to_be_hidden()
    assert len(submitted_requests) == 1
    assert json.loads(submitted_requests[0])["title"] == "Browser-created incident"
