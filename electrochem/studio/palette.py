"""Command palette (Ctrl+K): every action by name, filtered as you type, with its shortcut."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from . import theme


class Palette(QDialog):
    def __init__(self, parent, actions):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("Palette")
        t = theme.tokens()
        self.setStyleSheet(f"QDialog#Palette {{ background: {t.raised}; border: 1px solid {t.line_strong}; border-radius: 10px; }}")
        self.actions = [a for a in actions if a.isEnabled() and a.text()]
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 10, 10, 10); lay.setSpacing(6)
        self.edit = QLineEdit(); self.edit.setPlaceholderText("Type an action: open, export, cycles, theme…")
        self.edit.setAccessibleName("Search actions")
        self.edit.setFont(theme.font(11))
        self.edit.textChanged.connect(self._filter)
        lay.addWidget(self.edit)
        self.list = QListWidget(); self.list.setMinimumHeight(320)
        self.list.itemActivated.connect(self._run)
        lay.addWidget(self.list)
        hint = QLabel("Enter runs the action, Esc closes"); hint.setProperty("role", "muted")
        lay.addWidget(hint)
        self.resize(560, 420)
        self._filter("")

    def _filter(self, text):
        words = text.lower().split()
        self.list.clear()
        for a in self.actions:
            name = a.text().replace("&", "")
            hay = (name + " " + (a.toolTip() or "")).lower()
            if all(w in hay for w in words):
                sc = a.shortcut().toString()
                it = QListWidgetItem(f"{name}" + (f"    {sc}" if sc else ""))
                it.setData(Qt.UserRole, a)
                self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Down, Qt.Key_Up):
            r = self.list.currentRow() + (1 if e.key() == Qt.Key_Down else -1)
            self.list.setCurrentRow(max(0, min(self.list.count() - 1, r)))
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            it = self.list.currentItem()
            if it:
                self._run(it)
            return
        super().keyPressEvent(e)

    def _run(self, it):
        a = it.data(Qt.UserRole)
        self.accept()
        a.trigger()

    def showEvent(self, e):
        super().showEvent(e)
        p = self.parent()
        if p:
            g = p.geometry()
            self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 90)
        self.edit.setFocus()
