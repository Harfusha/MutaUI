from types import SimpleNamespace

from mutaui.ui import preferences_controller
from mutaui.ui.page_shell import PAGE_ROUTES
from mutaui.ui.preferences import ADVANCED_ROUTE_IDS
from mutaui.ui.preferences_controller import PreferencesController


class _Visibility:
    def __init__(self) -> None:
        self.visible = True

    def setVisible(self, visible: bool) -> None:
        self.visible = visible


class _Text:
    def __init__(self) -> None:
        self.text = ""
        self.tooltip = ""

    def setText(self, text: str) -> None:
        self.text = text

    def setToolTip(self, text: str) -> None:
        self.tooltip = text

    def property(self, _name: str) -> None:
        return None


def test_basic_mode_hides_advanced_routes_and_leaves_hidden_page() -> None:
    window = SimpleNamespace(
        ui_mode="advanced",
        nav=[_Visibility() for _ in PAGE_ROUTES],
        nav_section_labels={
            route.route_id: _Visibility() for route in PAGE_ROUTES if route.section
        },
        pages=SimpleNamespace(
            currentIndex=lambda: next(
                index
                for index, route in enumerate(PAGE_ROUTES)
                if route.route_id in ADVANCED_ROUTE_IDS
            )
        ),
        page_changes=[],
    )
    window.set_page = window.page_changes.append

    PreferencesController(window).set_ui_mode("basic")

    assert window.ui_mode == "basic"
    assert [button.visible for button in window.nav] == [
        route.route_id not in ADVANCED_ROUTE_IDS for route in PAGE_ROUTES
    ]
    assert window.page_changes == [0]


def test_apply_theme_uses_system_scheme_and_main_window_stylesheet(monkeypatch) -> None:
    applied: list[str] = []
    monkeypatch.setattr(
        preferences_controller.QGuiApplication,
        "styleHints",
        lambda: SimpleNamespace(colorScheme=lambda: preferences_controller.Qt.ColorScheme.Light),
    )
    monkeypatch.setattr(
        preferences_controller,
        "resolve_theme",
        lambda theme, *, system_is_light: f"{theme}:{system_is_light}",
    )
    monkeypatch.setattr(
        preferences_controller,
        "theme_stylesheet",
        lambda stylesheet, theme: f"{stylesheet}|{theme}",
    )
    window = SimpleNamespace(setStyleSheet=applied.append)

    PreferencesController(window, stylesheet="base-css").apply_theme("system")

    assert applied == ["base-css|system:True"]


def test_apply_ui_language_updates_main_navigation_and_endpoints(monkeypatch) -> None:
    updates: list[object] = []
    nav = [_Text() for _ in PAGE_ROUTES]
    sections = {route.route_id: _Text() for route in PAGE_ROUTES if route.section is not None}
    window = SimpleNamespace(
        findChildren=lambda _kind: [],
        property=lambda _name: None,
        nav=nav,
        nav_section_labels=sections,
        pages=SimpleNamespace(currentIndex=lambda: 0),
        page_name=_Text(),
        page_caption=_Text(),
        snapshot=object(),
        update_endpoint_sessions=updates.append,
    )
    monkeypatch.setattr(preferences_controller, "set_active_language", lambda language: language)

    PreferencesController(window).apply_ui_language("cs")

    assert window.ui_language == "cs"
    assert nav[0].text and nav[0].tooltip
    assert window.page_name.text == nav[0].text.split("    ", maxsplit=1)[1]
    assert updates == [window.snapshot]
