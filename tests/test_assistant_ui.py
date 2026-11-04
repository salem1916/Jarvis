import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.ui.pages.memory_page import MemoryPage
from jarvis.ui.pages.settings_page import SettingsPage
from jarvis.ui.pages.tasks_page import TasksPage


def test_saving_an_agent_selects_it_and_submits_to_the_correct_worker(tmp_path: Path) -> None:
    qt = QApplication.instance() or QApplication([])
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.agent_team._run_worker = lambda worker, prompt: f"{worker.name}: {prompt}"
    page = TasksPage(app)
    try:
        page.agent_name.setText("coder")
        page.backend.setCurrentText("chatgpt")
        page.instructions.setText("Explain Java")
        page._save_agent()
        assert page.agent.currentText() == "coder"
        assert page.agent_name.text() == "coder"
        assert page.backend.currentText() == "chatgpt"
        page.prompt.setPlainText("Explain classes")
        page._submit()
        job = app.agent_team.jobs()[0]
        app.agent_team._futures[job.job_id].result(timeout=3)
        page.refresh_view()
        assert app.agent_team.job(job.job_id).result == "coder: Explain classes"
        assert "coder: Explain classes" in page.result.toPlainText()
        assert len(app.conversation) == 0
    finally:
        page.timer.stop()
        page.close()
        app.shutdown()
        qt.processEvents()


def test_settings_preserve_explicit_source_and_store_keys_outside_memory(tmp_path: Path, monkeypatch) -> None:
    qt = QApplication.instance() or QApplication([])
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = SettingsPage(app)
    try:
        page.key_source.setCurrentIndex(page.key_source.findData("groq"))
        page.key_input.setText("test-secret-not-a-real-api-key")
        monkeypatch.setattr(page.hub, "list_models", lambda _: [{"id": "openai/gpt-oss-20b", "name": "Test model"}])
        monkeypatch.setattr(page, "_operate", lambda operation, success, text: success(operation()))
        page._save_key()
        assert "key accepted" in page.status.text()
        assert not page.key_input.text()
        page.source.setCurrentIndex(page.source.findData("groq"))
        page.model.setEditText("openai/gpt-oss-20b")
        page.theme.setCurrentIndex(page.theme.findData("light"))
        page._apply()
        assert app.intelligence is not None
        prefs = app.intelligence.preferences()
        assert prefs["source"] == "groq" and prefs["model"] == "openai/gpt-oss-20b"
        assert prefs["theme"] == "light"
        assert "test-secret" not in str(app.personal_memory.records("intelligence"))
        assert not app.personal_memory.facts()
        assert not app.intelligence.account.session()["connected"]
    finally:
        page.close()
        app.shutdown()
        qt.processEvents()


def test_memory_page_edits_and_removes_facts(tmp_path: Path) -> None:
    qt = QApplication.instance() or QApplication([])
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = MemoryPage(app)
    try:
        page.name.setText("learning_goal")
        page.value.setText("Spring Boot")
        page._save()
        assert app.personal_memory.facts() == {"learning_goal": "Spring Boot"}
        page.table.selectRow(0)
        page._forget()
        assert not app.personal_memory.facts()
        assert page.table.rowCount() == 0
    finally:
        page.timer.stop()
        page.close()
        app.shutdown()
        qt.processEvents()


def test_api_assistant_preserves_loaded_models_and_edited_id(tmp_path: Path) -> None:
    from jarvis.ui.pages.provider_assistant_page import ProviderAssistantPage

    qt = QApplication.instance() or QApplication([])
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = ProviderAssistantPage(app)
    try:
        page._account_models["groq"] = [{"id": "account-model", "name": "Account model"}]
        page.refresh_view()
        assert page.model.currentData() == "account-model"
        page.model.setEditText("custom-model-id")
        page.refresh_view()
        assert page.model.currentText() == "custom-model-id"
        page.commercial.setChecked(True)
        page._save_policy()
        assert app.intelligence is not None
        assert app.intelligence.steward.policy()["enabled"]
        assert not app.intelligence.steward.memory.records("provider_approval")
        settings = SettingsPage(app)
        settings.refresh_view()
        assert not settings.connect_button.isEnabled()
        settings.close()
    finally:
        page.timer.stop()
        page.close()
        app.shutdown()
        qt.processEvents()


def test_saving_gemini_key_loads_available_model_without_silently_activating(tmp_path: Path, monkeypatch) -> None:
    qt = QApplication.instance() or QApplication([])
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    page = SettingsPage(app)
    try:
        monkeypatch.setattr(page.hub, "list_models", lambda _: [{"id": "gemini-flash-latest", "name": "Flash"}])
        monkeypatch.setattr(page, "_operate", lambda operation, success, text: success(operation()))
        page.key_source.setCurrentIndex(page.key_source.findData("gemini"))
        page.key_input.setText("AQ.fake-key")
        page._save_key()
        assert not page.key_input.text()
        assert page.source.currentData() == "gemini"
        assert page.model.currentData() == "gemini-flash-latest"
        assert "Apply preferences" in page.status.text()
        assert page.hub.preferences()["source"] == "auto"
        page._apply()
        assert page.hub.preferences()["model"] == "gemini-flash-latest"
    finally:
        page.close()
        app.shutdown()
        qt.processEvents()


def test_updates_collect_once_preserve_selection_and_preview_is_read_only(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QPlainTextEdit

    from jarvis.agents.team import Job
    from jarvis.ui.pages.updates_page import UpdatesPage

    qt = QApplication.instance() or QApplication([])
    app = build_application(JarvisSettings(workspace_dir=tmp_path))
    app.agent_team._save(Job("older", "designer", "local", "draft", "completed", "Draft one", created_at=1))
    page = UpdatesPage(app)
    notifications = []
    page.attention.connect(notifications.append)
    try:
        page.table.selectRow(0)
        app.agent_team._save(Job("newer", "designer", "local", "draft", "completed", "Draft two", created_at=2))
        page.refresh_view()
        assert page._selected() == "older"
        assert "Draft one" in page.details.toPlainText()
        assert len(notifications) == 1
        page.refresh_view()
        assert len(notifications) == 1
        page._preview()
        assert len(page._previews) == 1
        editor = page._previews[0].findChild(QPlainTextEdit)
        assert editor is not None and editor.isReadOnly() and editor.toPlainText() == "Draft one"
        page._previews[0].close()
        page._transition("reviewed")
        assert app.assistant_inbox.unread_count() == 1
        page.quiet.setChecked(True)
        app.agent_team._save(Job("quiet", "designer", "local", "draft", "failed", "Not available", created_at=3))
        page.refresh_view()
        assert len(notifications) == 1
    finally:
        page.timer.stop()
        page.close()
        app.shutdown()
        qt.processEvents()


def test_browser_permission_can_be_saved_as_always_allow(tmp_path: Path, monkeypatch) -> None:
    from PySide6.QtWidgets import QMessageBox

    from jarvis.security.capabilities import Capability
    from jarvis.security.permission_mode import PermissionMode
    from jarvis.ui.pages.permissions_page import PermissionsPage
    qt = QApplication.instance() or QApplication([])
    settings = JarvisSettings(workspace_dir=tmp_path, state_dir=tmp_path / "state", persist_permission_modes=True)
    app = build_application(settings)
    page = PermissionsPage(app)
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    page.browser_mode_combo.setCurrentIndex(page.browser_mode_combo.findData("always_allow"))
    assert app.permission_mode(Capability.USE_BROWSER) == PermissionMode.ALWAYS_ALLOW
    page.close()
    app.shutdown()
    restored = build_application(settings)
    assert restored.permission_mode(Capability.USE_BROWSER) == PermissionMode.ALWAYS_ALLOW
    restored.shutdown()
    qt.processEvents()


def test_browser_outage_reaches_chat_as_partial_result_with_retry_progress(tmp_path: Path, monkeypatch) -> None:
    import httpx

    from jarvis.models.gemini import GeminiProvider
    from jarvis.security.capabilities import Capability
    from jarvis.security.policy import PermissionDecision
    from jarvis.ui.pages.chat_page import AskWorker

    qt = QApplication.instance() or QApplication([])
    app = build_application(JarvisSettings(workspace_dir=tmp_path, gemini_api_key="fake-key"))
    assert app.intelligence is not None
    app.intelligence.save_preferences("gemini", "gemini-3.1-flash-lite", True, "dark")
    app.tool_service.executor.policy.set_decision(Capability.USE_BROWSER, PermissionDecision.ALLOW)
    provider = GeminiProvider(provider_name="gemini", model="gemini-3.1-flash-lite", api_key="fake-key",
                              base_url="https://example.test", transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    monkeypatch.setattr(app.intelligence, "provider", lambda *args: provider)
    actions = []
    def execute(arguments):
        actions.append(arguments)
        return {"ok":True, "url":"https://example.com/", "snapshot":"Observed page", "links":[]}
    monkeypatch.setattr(app.tool_service.registry.get("browser_mcp"), "execute", execute)
    monkeypatch.setattr("jarvis.models.retry.wait_before_retry", lambda _: None)
    worker = AskWorker(app, "browser: Open https://example.com and find information", "Be helpful")
    replies, errors, progress, structured = [], [], [], []
    worker.finished.connect(replies.append)
    worker.failed.connect(errors.append)
    worker.progress.connect(progress.append)
    worker.reply_ready.connect(structured.append)
    try:
        worker.run()
        assert len(replies) == 1 and not errors and len(actions) == 1
        assert "page is open" in replies[0] and "couldn't finish" in replies[0]
        assert "503" not in replies[0] and "503" in structured[0].details
        assert structured[0].kind == "partial"
        assert "Task partly completed" in structured[0].details and "https://example.com/" in structured[0].details
        assert "Still needed" in app.conversation.snapshot()[-1].content
        assert any("Retrying" in text for text in progress)
    finally:
        app.shutdown()
        qt.processEvents()
