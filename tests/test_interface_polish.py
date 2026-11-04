"""Local-only regressions for layout, presentation and quota-independent navigation."""
import pytest
from PySide6.QtWidgets import QApplication, QScrollArea

from jarvis.bootstrap import build_application
from jarvis.core.browser_navigation import same_tab_url
from jarvis.core.config import JarvisSettings
from jarvis.core.fast_command_router import FastCommandRouter
from jarvis.core.interaction import action_event, build_reply
from jarvis.models.connection_errors import ProviderConnectionError
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from jarvis.ui.pages.chat_page import ChatPage


@pytest.fixture
def qt():
    return QApplication.instance() or QApplication([])


def test_controls_do_not_squeeze_conversation_and_each_tab_scrolls(qt,tmp_path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path));page = ChatPage(app,"Help")
    page.resize(900,600);page.show();qt.processEvents()
    try:
        original = page.activity_scroll.size()
        original_input = page.input_box.size()
        page.controls_button.click();qt.processEvents()
        assert page.controls_dialog.isVisible()
        assert page.activity_scroll.height() >= original.height()-2
        assert abs(page.input_box.width()-original_input.width()) <= 2
        dialog = page.controls_dialog;dialog.resize(400,340)
        for index in range(dialog.tabs.count()):
            dialog.tabs.setCurrentIndex(index);qt.processEvents()
            scroll = dialog.tabs.widget(index)
            assert isinstance(scroll,QScrollArea)
            assert scroll.viewport().width() > 250 and scroll.viewport().height() > 100
    finally:
        page.close();app.shutdown()


def test_companion_captions_and_motion_sync_and_survive_restart(qt,tmp_path):
    app = build_application(JarvisSettings(workspace_dir=tmp_path));page = ChatPage(app,"Help")
    try:
        page.desktop_button.setChecked(True)
        companion = page.companion
        assert companion is not None
        page.presence.update_state(phase="speaking",caption="Here is what I found.")
        assert "found" in companion.compact_caption.text()
        companion.set_expanded(True);companion.captions_toggle.setChecked(False)
        assert not page.captions_toggle.isChecked() and companion.caption.isHidden()
        companion.set_expanded(False)
        assert companion.compact_caption.isHidden()
        page.reduce_motion.setChecked(True)
        assert not companion.bubble.timer.isActive() and not page.activity_card.timer.isActive()
        page.particles_toggle.setChecked(False)
        page.close()
        reopened = ChatPage(app,"Help")
        try:
            assert not reopened.presence.captions and not reopened.presence.motion and not reopened.presence.particles
        finally:reopened.close()
    finally:
        app.shutdown()


@pytest.mark.parametrize("prompt",[
    "Can you open Facebook in it?", "Open github in the current tab.",
    "Visit https://www.python.org/about/ in this browser", "Open reddit without opening a new tab",
])
def test_same_tab_parser_retains_literal_website(prompt):
    assert same_tab_url(prompt,FastCommandRouter()).startswith("https://")


@pytest.mark.parametrize("prompt",[
    "Open the first link in it", "Open facebook and read my messages in it",
    "Open javascript:alert(1) in it", "Tell me about facebook in it",
])
def test_same_tab_parser_does_not_guess_other_actions(prompt):
    assert not same_tab_url(prompt,FastCommandRouter())


def _fake_browser(app,monkeypatch):
    import win32gui

    import jarvis.core.browser_navigation as navigation
    screen = app.tool_service.registry.get("observe_screen")
    monkeypatch.setattr(screen.context,"current_window",lambda:123)
    monkeypatch.setattr(navigation,"is_browser_window",lambda handle:handle == 123)
    monkeypatch.setattr(win32gui,"IsWindow",lambda handle:True)
    monkeypatch.setattr(win32gui,"GetWindowText",lambda handle:"Current browser")


def test_same_tab_uses_local_commands_even_when_provider_is_unavailable(tmp_path,monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path));calls = []
    _fake_browser(app,monkeypatch)
    monkeypatch.setattr(app,"permission_decision",lambda cap:PermissionDecision.ALLOW)
    monkeypatch.setattr(app,"_execute_tool_with_confirmation",lambda request,_handler:calls.append(request) or {"ok":True})
    monkeypatch.setattr(app,"ask_with_tools",lambda *_a,**_k:pytest.fail("Simple navigation must not call AI"))
    try:
        reply = app.interact("Can you open Facebook in it?")
        assert reply.kind == "action" and "current tab" in reply.message
        assert [call.tool_name for call in calls] == ["keyboard_action","type_text","keyboard_action"]
        assert calls[0].arguments["action"] == "focus_address_bar"
        assert calls[1].arguments["text"] == "https://www.facebook.com/"
        assert calls[2].arguments["action"] == "enter"
        assert app.interaction.focus_url == "https://www.facebook.com/"
    finally:app.shutdown()


def test_same_tab_stops_before_input_when_browser_permission_denied(tmp_path,monkeypatch):
    app = build_application(JarvisSettings(workspace_dir=tmp_path));calls = []
    _fake_browser(app,monkeypatch)
    monkeypatch.setattr(app,"permission_decision",lambda cap:PermissionDecision.DENY if cap == Capability.USE_BROWSER else PermissionDecision.ALLOW)
    monkeypatch.setattr(app,"_execute_tool_with_confirmation",lambda request,_handler:calls.append(request))
    try:
        reply = app.interact("Open facebook in this tab")
        assert reply.kind == "failed" and not calls
    finally:app.shutdown()


def test_chrome_tab_navigation_does_not_type_after_user_switches_tabs(monkeypatch):
    from jarvis.tools.chrome_tab import ChromeTab, ChromeTabNavigation

    navigation = ChromeTabNavigation(None, None, None)
    original = ChromeTab(123, (1, 2))
    monkeypatch.setattr(navigation, "selected", lambda: ChromeTab(123, (1, 3)))
    with navigation.keep_tab(original), pytest.raises(ValueError, match="tab changed"):
        navigation.navigate("https://example.com/")


def test_quota_after_action_reports_receipt_first_and_keeps_error_details():
    events = [action_event("list_ui_elements",{},{}),action_event("open_url",{"url":"https://www.facebook.com/"},{"ok":True})]
    error = ProviderConnectionError("groq HTTP 429 quota reached",status_code=429,retry_after=42)
    reply = build_reply(str(error),events,error=error)
    assert reply.kind == "partial" and reply.message.startswith("Opened facebook.com.")
    assert "42 seconds" in reply.message and "Local commands are still available" in reply.message
    assert "available app controls" not in reply.message and "429" in reply.details
