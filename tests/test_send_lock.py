import asyncio
from datetime import timedelta

import httpx
import pytest
from test_snapshots import use_config

from posting.__main__ import make_posting
from posting.collection import RequestModel
from posting.widgets.collection.browser import CollectionTree
from posting.widgets.request.query_editor import ParamsTable
from posting.widgets.request.url_bar import SendRequestButton, UrlBar

SIZE = (140, 40)


class HeldTransport:
    """Stands in for `AsyncClient.send`: each request waits until released."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.gates: dict[str, asyncio.Event] = {}

    async def send(self, request, **kwargs) -> httpx.Response:
        url = str(request.url)
        self.sent.append(url)
        gate = self.gates.setdefault(url, asyncio.Event())
        await gate.wait()
        status = 201 if url.endswith("/a") else 202
        response = httpx.Response(status, json={"url": url}, request=request)
        response.elapsed = timedelta(milliseconds=5)
        return response

    def release(self, url: str) -> None:
        self.gates.setdefault(url, asyncio.Event()).set()


@pytest.fixture
def collection(tmp_path):
    for name in ("a", "b"):
        path = tmp_path / f"{name}.posting.yaml"
        RequestModel(
            name=f"Request {name}", url=f"https://example.test/{name}", path=path
        ).save_to_disk(path)
    return tmp_path


@pytest.fixture
def transport(monkeypatch):
    held = HeldTransport()
    monkeypatch.setattr(httpx.AsyncClient, "send", held.send)
    return held


async def open_request(pilot, index: int) -> None:
    # The request editor mounts lazily; opening a request needs it in place.
    while not pilot.app.screen.query(ParamsTable):
        await pilot.pause(0.05)
    tree = pilot.app.screen.query_one(CollectionTree)
    tree.move_cursor(tree.root.children[index])
    tree.focus()
    await pilot.press("enter")
    await pilot.pause()


async def press_send_button(pilot) -> None:
    await pilot.click(SendRequestButton)
    # Textual ignores clicks while the button's 0.2s press effect is active.
    await pilot.pause(0.25)


async def settle(pilot) -> None:
    """Wait until no request is in flight and the UI has caught up."""
    for _ in range(100):
        if not pilot.app.screen._requests_in_flight:
            break
        await pilot.pause(0.05)
    await pilot.pause()


def button_label(pilot) -> str:
    return str(pilot.app.screen.query_one(SendRequestButton).label)


@use_config("general.yaml")
def test_running_request_is_not_sent_again(collection, transport):
    asyncio.run(_running_request_is_not_sent_again(collection, transport))


async def _running_request_is_not_sent_again(collection, transport):
    app = make_posting(collection=collection)
    async with app.run_test(size=SIZE) as pilot:
        await open_request(pilot, 0)

        await press_send_button(pilot)
        assert button_label(pilot) == "Cancel"

        # The keybinding and Enter in the URL bar do not resend it.
        await app.screen.run_action("send_request")
        url_input = app.screen.url_input
        url_input.post_message(url_input.Submitted(url_input, ""))
        await pilot.pause()
        assert transport.sent == ["https://example.test/a"]

        transport.release("https://example.test/a")
        await settle(pilot)
        assert button_label(pilot) == "Send"
        assert app.screen.query_one(UrlBar).response_status_code == 201


@use_config("general.yaml")
def test_cancel_stops_waiting_for_the_response(collection, transport):
    asyncio.run(_cancel_stops_waiting(collection, transport))


async def _cancel_stops_waiting(collection, transport):
    app = make_posting(collection=collection)
    async with app.run_test(size=SIZE) as pilot:
        await open_request(pilot, 0)
        await press_send_button(pilot)

        await press_send_button(pilot)
        await settle(pilot)
        assert button_label(pilot) == "Send"
        assert app.screen.query_one(UrlBar).response_status_code is None

        # A cancelled request can be sent again.
        await press_send_button(pilot)
        assert button_label(pilot) == "Cancel"
        assert transport.sent == ["https://example.test/a"] * 2
        transport.release("https://example.test/a")
        await settle(pilot)


@use_config("general.yaml")
def test_other_requests_stay_sendable_and_keep_their_responses(
    collection, transport
):
    asyncio.run(_other_requests_stay_sendable(collection, transport))


async def _other_requests_stay_sendable(collection, transport):
    app = make_posting(collection=collection)
    async with app.run_test(size=SIZE) as pilot:
        await open_request(pilot, 0)
        await press_send_button(pilot)

        await open_request(pilot, 1)
        assert button_label(pilot) == "Send"
        await press_send_button(pilot)
        assert transport.sent == ["https://example.test/a", "https://example.test/b"]

        # The response for the request not on screen is held back.
        transport.release("https://example.test/a")
        await pilot.pause(0.1)
        url_bar = app.screen.query_one(UrlBar)
        assert url_bar.response_status_code != 201
        assert button_label(pilot) == "Cancel"

        transport.release("https://example.test/b")
        await settle(pilot)
        assert url_bar.response_status_code == 202
        assert button_label(pilot) == "Send"

        await open_request(pilot, 0)
        assert url_bar.response_status_code == 201
        assert button_label(pilot) == "Send"


def shown_body(pilot) -> str:
    return pilot.app.screen.response_area.text_editor.text_area.text


@use_config("general.yaml")
def test_sending_clears_the_previous_response(collection, transport):
    asyncio.run(_sending_clears_the_previous_response(collection, transport))


async def _sending_clears_the_previous_response(collection, transport):
    app = make_posting(collection=collection)
    async with app.run_test(size=SIZE) as pilot:
        await open_request(pilot, 0)
        await press_send_button(pilot)
        transport.release("https://example.test/a")
        await settle(pilot)
        url_bar = app.screen.query_one(UrlBar)
        assert url_bar.response_status_code == 201
        assert "example.test/a" in shown_body(pilot)

        transport.gates.clear()
        await press_send_button(pilot)
        assert button_label(pilot) == "Cancel"
        assert url_bar.response_status_code is None
        assert shown_body(pilot) == ""

        transport.release("https://example.test/a")
        await settle(pilot)


@use_config("general.yaml")
def test_each_request_shows_its_own_response(collection, transport):
    asyncio.run(_each_request_shows_its_own_response(collection, transport))


async def _each_request_shows_its_own_response(collection, transport):
    app = make_posting(collection=collection)
    async with app.run_test(size=SIZE) as pilot:
        await open_request(pilot, 0)
        await press_send_button(pilot)
        transport.release("https://example.test/a")
        await settle(pilot)

        await open_request(pilot, 1)
        url_bar = app.screen.query_one(UrlBar)
        assert url_bar.response_status_code is None
        assert shown_body(pilot) == ""

        await open_request(pilot, 0)
        assert url_bar.response_status_code == 201
        assert "example.test/a" in shown_body(pilot)


@use_config("general.yaml")
def test_shortcut_clears_the_response(collection, transport):
    asyncio.run(_shortcut_clears_the_response(collection, transport))


async def _shortcut_clears_the_response(collection, transport):
    app = make_posting(collection=collection)
    async with app.run_test(size=SIZE) as pilot:
        await open_request(pilot, 0)
        await press_send_button(pilot)
        transport.release("https://example.test/a")
        await settle(pilot)

        await pilot.press("ctrl+shift+k")
        await pilot.pause()
        url_bar = app.screen.query_one(UrlBar)
        assert url_bar.response_status_code is None
        assert shown_body(pilot) == ""

        # The cleared response stays cleared when the request is reopened.
        await open_request(pilot, 1)
        await open_request(pilot, 0)
        assert url_bar.response_status_code is None
