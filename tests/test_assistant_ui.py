import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.ui.pages.memory_page import MemoryPage
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
