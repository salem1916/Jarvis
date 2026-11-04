import os
import time
from pathlib import Path
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.core.request_control import check_cancelled, current_control
from jarvis.models.base import ModelProvider
from jarvis.security.capabilities import Capability
from jarvis.security.policy import PermissionDecision
from jarvis.ui.pages.chat_page import ChatPage


def spin(qt, predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qt.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("Desktop worker did not reach the expected state")


@pytest.fixture
def desktop(tmp_path: Path, monkeypatch):
    qt = QApplication.instance() or QApplication([])
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    entered, unwound = Event(), Event()
    class WaitingModel(ModelProvider):
        name = "test"
        def generate(self, request):
            entered.set()
            control = current_control()
            assert control is not None
            try:
                while not control.cancelled.wait(0.01):
                    pass
                check_cancelled()
                raise AssertionError("Cancellation must stop inference")
            finally:
                unwound.set()
    app.cloud_provider = WaitingModel()
    opened = []
    def open_url(url):
        if entered.is_set():
            assert unwound.is_set(), "Replacement action overlapped the previous request"
        opened.append(url)
        return True
    monkeypatch.setattr(app.tool_service.registry.get("open_url"), "_opener", open_url)
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
    page = ChatPage(app, "Be helpful")
    try:
        yield qt, app, page, entered, unwound, opened
    finally:
        page._stop_request()
        spin(qt, lambda: page.worker_thread is None)
        page.close()
        app.shutdown()
        qt.processEvents()


def begin_waiting(qt, page, entered):
    page.input_box.setText("Explain SQL")
    page._send_message()
    spin(qt, entered.is_set)
    assert page.input_box.isEnabled() and page.send_button.isEnabled()


def test_replacement_waits_for_old_worker_and_runs_once(desktop):
    qt, _, page, entered, unwound, opened = desktop
    begin_waiting(qt, page, entered)
    page.input_box.setText("open google")
    page._send_message()
    spin(qt, lambda: len(opened) == 1 and page.worker_thread is None)
    assert unwound.is_set() and opened == ["https://www.google.com/"]
    assert page.activity_message.text() == "Opened Google."
    assert page.chat_view.toPlainText().count("Opened Google.") == 1
    assert page.details_button.isVisibleTo(page)


def test_latest_replacement_wins_and_draft_is_preserved(desktop):
    qt, _, page, entered, _, opened = desktop
    begin_waiting(qt, page, entered)
    page.input_box.setText("open github")
    page._send_message()
    page.input_box.setText("open google")
    page._send_message()
    page.input_box.setText("An unsent draft")
    spin(qt, lambda: len(opened) == 1 and page.worker_thread is None)
    assert opened == ["https://www.google.com/"]
    assert page.input_box.text() == "An unsent draft"


def test_explicit_stop_removes_queued_replacement(desktop):
    qt, _, page, entered, _, opened = desktop
    begin_waiting(qt, page, entered)
    page.input_box.setText("open google")
    page._send_message()
    page._stop_request()
    spin(qt, lambda: page.worker_thread is None)
    assert not opened and not page._pending_prompt
    assert "Stopped" in page.activity_state.text()


def test_approval_is_inline_and_bound_to_the_waiting_task(desktop):
    qt, app, page, _, _, opened = desktop
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.REQUIRE_CONFIRMATION)
    page.input_box.setText("open google")
    page._send_message()
    spin(qt, lambda: page._approval_token is not None)
    assert page.input_box.isEnabled() and not opened
    assert not page.approval_panel.isHidden()
    page.approve_button.click()
    spin(qt, lambda: page.worker_thread is None)
    assert opened == ["https://www.google.com/"] and page.approval_panel.isHidden()


def test_stale_approval_cannot_authorize_the_next_task(desktop):
    qt, app, page, _, _, opened = desktop
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.REQUIRE_CONFIRMATION)
    page.input_box.setText("open google")
    page._send_message()
    spin(qt, lambda: page._approval_token is not None)
    old_token = page._approval_token
    page.input_box.setText("open github")
    page._send_message()
    spin(qt, lambda: page._approval_token is not None and page._approval_token is not old_token)
    page._resolve_approval(True, old_token)
    assert not opened and page._approval_token is not None
    page.deny_button.click()
    spin(qt, lambda: page.worker_thread is None)
    assert not opened


def test_plain_text_activity_does_not_render_page_markup(desktop):
    from PySide6.QtCore import Qt

    from jarvis.core.interaction import AssistantEvent
    _, _, page, _, _, _ = desktop
    page._handle_activity(AssistantEvent("working", '<img src="file:///private.png">'))
    assert page.activity_message.textFormat() == Qt.TextFormat.PlainText


def test_stream_chunks_are_batched_without_duplicating_the_final_answer(desktop):
    _, _, page, _, _, _ = desktop
    chunks = ["Hello ", "there", ". How ", "can I help?"]
    for chunk in chunks:
        page._handle_delta(chunk)
    assert not page.chat_view.toPlainText()
    page._handle_response("".join(chunks))
    assert page.chat_view.toPlainText().count("Hello there. How can I help?") == 1
    assert not page._pending_text


def test_action_stream_details_stay_out_of_the_short_chat_reply(desktop):
    from jarvis.core.interaction import AssistantEvent, AssistantReply

    _, _, page, _, _, _ = desktop
    page._handle_activity(AssistantEvent("working", "Reading the page…", "browser_mcp"))
    page._handle_delta("Long response with technical details and many sources")
    reply = AssistantReply("action", "Found the contact details.", "Found the contact details.", "Full source information")
    page._handle_reply(reply)
    page._handle_response(reply.message)
    assert "Long response" not in page.chat_view.toPlainText()
    assert "Found the contact details." in page.chat_view.toPlainText()
    page.details_button.setChecked(True)
    assert page.details_view.toPlainText() == "Full source information"


def test_typed_no_denies_the_current_approval_without_starting_a_new_task(desktop):
    qt, app, page, _, _, opened = desktop
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.REQUIRE_CONFIRMATION)
    page.input_box.setText("open google")
    page._send_message()
    spin(qt, lambda: page._approval_token is not None)
    page.input_box.setText("no")
    page._send_message()
    spin(qt, lambda: page.worker_thread is None)
    assert not opened and not page._pending_prompt


def test_status_question_does_not_cancel_the_running_task(desktop):
    qt, _, page, entered, unwound, _ = desktop
    begin_waiting(qt, page, entered)
    worker = page.worker
    page.input_box.setText("What are you doing?")
    page._send_message()
    assert page.worker is worker and not unwound.is_set() and not page._pending_prompt
    assert worker is not None and not worker.control.cancelled.is_set()
    assert "What are you doing?" in page.chat_view.toPlainText()


def test_small_layout_keeps_details_and_input_accessible(desktop):
    from jarvis.core.interaction import AssistantReply

    qt, _, page, _, _, _ = desktop
    page.history_button.setChecked(True)
    page.resize(630, 568)
    page.show()
    message = "A detailed observed result with useful information. " * 8
    page._handle_reply(AssistantReply("action", message, message, "Full details\n" * 25))
    page.details_button.setChecked(True)
    for _ in range(12):
        qt.processEvents()
        time.sleep(0.005)
    assert page.activity_card.width() >= page.activity_scroll.viewport().width() - 2
    assert page.activity_scroll.geometry().bottom() < page.details_button.geometry().top()
    assert page.details_button.geometry().bottom() < page.chat_view.geometry().top()
    container = page.input_box.parentWidget()
    assert container is not None
    assert page.chat_view.geometry().bottom() < container.geometry().top()
    assert container.geometry().bottom() <= page.height()
