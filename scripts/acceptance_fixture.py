"""A generated, separate-process Windows app used by check_jarvis_acceptance.py."""

import argparse
import json
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    qt = QApplication([])
    window = QWidget()
    window.setWindowTitle("Acceptance Test Window")
    window.resize(650, 370)
    window.setStyleSheet("QWidget { background: #f5f5f7; color: #1d1d1f; font-family: Segoe UI; font-size: 20px; } QPushButton { padding: 15px; background: #dcecff; }")
    layout = QVBoxLayout(window)
    layout.addWidget(QLabel("GENERATED TEST APP — not business data"))
    detail = QLabel("Details are closed.")
    detail.setAccessibleName("Reference status")
    layout.addWidget(detail)
    button = QPushButton("Show details")
    button.clicked.connect(lambda: detail.setText("Details loaded. Reference: LIME-27"))
    layout.addWidget(button)
    summary = QLabel("Summary is closed.")
    layout.addWidget(summary)
    summary_button = QPushButton("Show summary")
    summary_button.clicked.connect(lambda: summary.setText("Summary loaded. Status: READY"))
    layout.addWidget(summary_button)
    window.show()
    QTimer.singleShot(200, lambda: args.ready_file.write_text(json.dumps({"handle": int(window.winId())}), encoding="utf-8"))
    raise SystemExit(qt.exec())


if __name__ == "__main__":
    main()
