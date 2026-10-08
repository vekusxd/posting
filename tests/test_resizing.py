import asyncio

from test_snapshots import SAMPLE_COLLECTIONS, patch_env
from textual.geometry import Region

from posting.__main__ import make_posting
from posting.resizing import (
    SIDEBAR_MIN_WIDTH,
    SPLIT_MAX,
    SPLIT_MIN,
    clamp_sidebar_width,
    clamp_split,
    on_sidebar_edge,
    on_split_edge,
    sidebar_width_at,
    split_at,
)

SIZE = (140, 40)


def test_sidebar_width_is_clamped() -> None:
    assert clamp_sidebar_width(4, body_width=136) == SIDEBAR_MIN_WIDTH
    assert clamp_sidebar_width(50, body_width=136) == 50
    assert clamp_sidebar_width(200, body_width=136) == 106


def test_split_is_clamped() -> None:
    assert clamp_split(0) == SPLIT_MIN
    assert clamp_split(60) == 60
    assert clamp_split(100) == SPLIT_MAX


def test_sidebar_width_follows_the_pointer() -> None:
    sidebar = Region(2, 5, 32, 30)
    assert sidebar_width_at(43, sidebar, "left") == 42
    assert sidebar_width_at(10, Region(100, 5, 32, 30), "right") == 122


def test_split_follows_the_pointer() -> None:
    request, response = Region(34, 5, 50, 30), Region(84, 5, 50, 30)
    assert split_at(83, request, response, horizontal=True) == 50
    request, response = Region(34, 5, 100, 15), Region(34, 20, 100, 15)
    assert split_at(25, request, response, horizontal=False) == 70


def test_edges_are_detected() -> None:
    sidebar = Region(2, 5, 32, 30)
    assert on_sidebar_edge(33, 10, sidebar, "left")
    assert not on_sidebar_edge(32, 10, sidebar, "left")
    assert not on_sidebar_edge(33, 40, sidebar, "left")
    assert on_sidebar_edge(2, 10, sidebar, "right")

    request, response = Region(34, 5, 50, 30), Region(84, 5, 50, 30)
    assert on_split_edge(83, 10, request, response, horizontal=True)
    assert on_split_edge(84, 10, request, response, horizontal=True)
    assert not on_split_edge(60, 10, request, response, horizontal=True)

    request, response = Region(34, 5, 100, 15), Region(34, 20, 100, 15)
    assert on_split_edge(50, 19, request, response, horizontal=False)
    assert on_split_edge(50, 20, request, response, horizontal=False)
    assert not on_split_edge(50, 10, request, response, horizontal=False)


def run(check) -> None:
    async def wrapper():
        app = make_posting(collection=SAMPLE_COLLECTIONS)
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            await check(app.screen, pilot)

    asyncio.run(wrapper())


def test_resize_mode_moves_the_sidebar_edge() -> None:
    async def check(screen, pilot):
        browser = screen.collection_browser
        before = browser.outer_size.width
        await pilot.press("ctrl+r", "l", "l", "L")
        await pilot.pause()
        assert screen.resize_mode
        assert browser.has_class("-resize-target")
        assert browser.outer_size.width == before + 14
        await pilot.press("h")
        await pilot.pause()
        assert browser.outer_size.width == before + 12
        await pilot.press("equals_sign")
        await pilot.pause()
        assert browser.outer_size.width == before

    run(check)


def test_resize_mode_moves_the_request_response_split() -> None:
    async def check(screen, pilot):
        request, response = screen.request_editor, screen.response_area
        await pilot.press("ctrl+r", "tab")
        await pilot.pause()
        assert screen.resize_target == "split"
        assert request.has_class("-resize-target")
        assert not screen.collection_browser.has_class("-resize-target")
        await pilot.press("j", "j", "j", "j", "j")
        await pilot.pause()
        assert screen.split_percent == 60
        assert request.outer_size.height > response.outer_size.height

    run(check)


def test_leaving_resize_mode_gives_keys_back() -> None:
    async def check(screen, pilot):
        screen.url_input.focus()
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert screen.focused is None
        await pilot.press("escape")
        await pilot.pause()
        assert not screen.resize_mode
        assert not screen.collection_browser.has_class("-resize-target")
        assert screen.focused is screen.url_input
        await pilot.press("l")
        await pilot.pause()
        assert screen.url_input.value == "l"
        assert screen.split_percent == 50

    run(check)


def test_dragging_the_sidebar_edge() -> None:
    async def check(screen, pilot):
        browser = screen.collection_browser
        edge = browser.region.right - 1
        y = browser.region.y + 5
        await pilot.mouse_down(offset=(edge, y))
        assert browser.has_class("-resize-target")
        await pilot.hover(offset=(edge + 10, y))
        await pilot.mouse_up(offset=(edge + 10, y))
        await pilot.pause()
        assert browser.region.right - 1 == edge + 10
        assert not browser.has_class("-resize-target")

    run(check)


def test_dragging_the_split() -> None:
    async def check(screen, pilot):
        request, response = screen.request_editor, screen.response_area
        x = request.region.x + 5
        edge = request.region.bottom - 1
        await pilot.mouse_down(offset=(x, edge))
        await pilot.hover(offset=(x, edge - 4))
        await pilot.mouse_up(offset=(x, edge - 4))
        await pilot.pause()
        assert request.outer_size.height < response.outer_size.height

    run(check)


@patch_env("POSTING_COLLECTION_BROWSER__WIDTH", "50")
def test_configured_sidebar_width() -> None:
    async def check(screen, pilot):
        assert screen.collection_browser.outer_size.width == 50

    run(check)


def test_focusing_a_widget_ends_resize_mode() -> None:
    async def check(screen, pilot):
        await pilot.press("ctrl+r")
        await pilot.pause()
        screen.url_input.focus()
        await pilot.pause()
        assert not screen.resize_mode
        assert screen.focused is screen.url_input

    run(check)
