"""Render the real native UI locally. Opens no microphone, screen capture or API."""
import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.bootstrap import build_application
from jarvis.core.config import JarvisSettings
from jarvis.ui.appearance import stylesheet_for
from jarvis.ui.companion import DesktopCompanion
from jarvis.ui.orb import AssistantOrb
from jarvis.ui.pages.chat_page import ChatPage
from jarvis.ui.presence import AssistantPresence


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True)
    output=parser.parse_args().output;output.mkdir(parents=True,exist_ok=True)
    qt=QApplication.instance() or QApplication([])
    assert isinstance(qt,QApplication)
    for filename in ("segoeui.ttf","seguisb.ttf","segoeuil.ttf"):
        font=Path("C:/Windows/Fonts")/filename
        if font.is_file():QFontDatabase.addApplicationFont(str(font))
    qt.setFont(QFont("Segoe UI",10))
    app=build_application(JarvisSettings(workspace_dir=Path(__file__).resolve().parents[1]/"workspace/ui-preview"))
    root=QWidget();root.setObjectName("previewRoot")
    root.setStyleSheet(stylesheet_for()+"QWidget#previewRoot {background:#0e1118;}");root.resize(1180,850)
    body=QHBoxLayout(root);body.setContentsMargins(16,16,16,16);body.setSpacing(16)
    side=QWidget();side.setObjectName("sidebar");side.setFixedWidth(196);nav=QVBoxLayout(side)
    nav.setContentsMargins(18,24,18,20);brand=QLabel("JARVIS");brand.setObjectName("brandTitle");nav.addWidget(brand)
    tag=QLabel("Personal assistant");tag.setObjectName("mutedText");nav.addWidget(tag);nav.addSpacing(20)
    nav.addWidget(QPushButton("+ New conversation"));nav.addSpacing(12)
    for label in ("Assistant","Tasks","API assistant","Updates","Permissions","Settings","Memory","Logs"):
        button=QPushButton(label);button.setObjectName("navButton");button.setCheckable(True);button.setChecked(label=="Assistant");nav.addWidget(button)
    nav.addStretch();note=QLabel("DESIGN PREVIEW");note.setObjectName("mutedText");nav.addWidget(note)
    body.addWidget(side)
    page=ChatPage(app,"Local design preview")
    page.connection_label.setText("Design preview · no microphone, screen capture or AI requests")
    page._connection_timer.stop();body.addWidget(page,1)
    root.show();qt.processEvents();page._fit_activity();qt.processEvents()
    assert root.grab().save(str(output/"Jarvis-orb-interface.png"))
    page.controls_button.click();qt.processEvents()
    for index in range(page.controls_dialog.tabs.count()):
        page.controls_dialog.tabs.setCurrentIndex(index);qt.processEvents()
        assert page.controls_dialog.grab().save(str(output/f"Jarvis-controls-{index}.png"))
    page.controls_dialog.hide()
    companion=DesktopCompanion(page.presence);companion.set_expanded(True);companion.show();qt.processEvents()
    assert companion.grab().save(str(output/"Jarvis-floating-companion.png"))
    companion.set_expanded(False)
    page.presence.update_state(phase="speaking",caption="Here is what I found. You can interrupt me anytime.")
    qt.processEvents()
    assert companion.grab().save(str(output/"Jarvis-compact-companion.png"))
    from PySide6.QtTest import QTest
    frame_folder = output/"companion-frames";frame_folder.mkdir(exist_ok=True)
    for index in range(24):
        QTest.qWait(70)
        assert companion.grab().save(str(frame_folder/f"frame-{index:02d}.png"))
    page.presence.update_state(phase="idle",caption="What would you like to do?")
    companion.hide()
    states=QWidget();states.setObjectName("previewStates");states.setStyleSheet(stylesheet_for()+"QWidget#previewStates {background:#0e1118;}");states.resize(1000,320)
    grid=QGridLayout(states)
    heading=QLabel("Listening, thinking, speaking · visual state preview");heading.setObjectName("sectionHeading");grid.addWidget(heading,0,0,1,5)
    for col,(phase,label) in enumerate((("idle","Ready"),("listening","Listening"),("thinking","Thinking"),("speaking","Speaking"),("error","Needs attention"))):
        presence=AssistantPresence(states);presence.update_state(phase=phase,motion=False)
        orb=AssistantOrb(presence,size=174);grid.addWidget(orb,1,col)
        title=QLabel(label);title.setAlignment(Qt.AlignmentFlag.AlignCenter);grid.addWidget(title,2,col)
    states.show();qt.processEvents();assert states.grab().save(str(output/"Jarvis-orb-states.png"))
    print("Rendered native UI, companion and state previews without API/device access.")
    companion.close();states.close();root.close();page.shutdown_ui();app.shutdown();qt.processEvents()


if __name__=="__main__":main()
