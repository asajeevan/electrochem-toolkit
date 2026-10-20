"""Help > Cite Cyclara and Help > How the numbers are calculated.

Two windows that put text on the clipboard: the citation in the form a reference
list, BibTeX or a methods section wants, and the explanation of every quantity
Cyclara reports, in plain words and in full, with the settings of the open file
filled in and a methods paragraph ready to paste. The texts come from
`electrochem.citation` and `electrochem.methods_text`; nothing here decides a
number.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QTextDocument
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QPushButton, QSplitter, QTabWidget, QTextBrowser, QVBoxLayout,
                               QWidget)

from .. import __version__, citation, methods_text
from . import theme

M01 = Path(__file__).resolve().parents[2] / "docs" / "M01_Cycling_Method_Specification.md"


def _flash(button: QPushButton, text: str, back: str, ms: int = 1600):
    """The button says what it did, then returns to its label: the only confirmation a copy needs."""
    button.setText(text)
    QTimer.singleShot(ms, lambda: button.setText(back))


class CiteDialog(QDialog):
    """Help > Cite Cyclara: the citation in four forms, each one click from the clipboard."""

    FORMS = ("Reference", "BibTeX", "CITATION.cff", "Methods sentence")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cite Cyclara")
        self.setModal(False)
        self.resize(720, 440)
        lay = QVBoxLayout(self); lay.setContentsMargins(28, 22, 28, 20); lay.setSpacing(10)
        head = QLabel("Cite Cyclara"); head.setProperty("role", "title")
        lay.addWidget(head)
        text = QLabel(f"If Cyclara contributed to a publication, cite it with its version, {__version__}: the way a "
                      "number is calculated can change between versions, and the version makes a result "
                      "reproducible. Pick the form your reference list or manuscript wants and copy it.")
        text.setProperty("role", "secondary"); text.setWordWrap(True)
        lay.addWidget(text)
        self.tabs = QTabWidget()
        self.boxes: dict[str, QPlainTextEdit] = {}
        forms = citation.all_forms()
        for name in self.FORMS:
            box = QPlainTextEdit(forms[name]); box.setReadOnly(True)
            box.setLineWrapMode(QPlainTextEdit.WidgetWidth if name in ("Reference", "Methods sentence")
                                else QPlainTextEdit.NoWrap)
            if name in ("BibTeX", "CITATION.cff"):
                box.setStyleSheet(theme.css("font-family: 'Consolas', 'Menlo', monospace; font-size: 9pt;"))
            self.boxes[name] = box
            self.tabs.addTab(box, name)
        lay.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        site = QPushButton("Open the project page"); site.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(citation.__url__)))
        row.addWidget(site); row.addStretch(1)
        self.copy = QPushButton("Copy"); self.copy.setProperty("kind", "primary"); self.copy.setDefault(True)
        self.copy.clicked.connect(self.copy_current)
        close = QPushButton("Close"); close.clicked.connect(self.close)
        row.addWidget(self.copy); row.addWidget(close)
        lay.addLayout(row)
        self.tabs.currentChanged.connect(self._relabel)
        self._relabel()

    def current_form(self) -> str:
        return self.FORMS[self.tabs.currentIndex()]

    def current_text(self) -> str:
        return self.boxes[self.current_form()].toPlainText()

    def _relabel(self, *_):
        self.copy.setText({"Reference": "Copy the reference", "BibTeX": "Copy BibTeX", "CITATION.cff": "Copy CITATION.cff",
                           "Methods sentence": "Copy the methods sentence"}[self.current_form()])

    def copy_current(self):
        QApplication.clipboard().setText(self.current_text())
        _flash(self.copy, "Copied", self.copy.text())


class MethodsDialog(QDialog):
    """Help > How the numbers are calculated: one topic per quantity, in plain words and in full, with the
    settings that apply to the open file, and a methods paragraph for a manuscript."""

    def __init__(self, parent=None, context: methods_text.Context | None = None):
        super().__init__(parent)
        self.setWindowTitle("How the numbers are calculated")
        self.setModal(False)
        self.resize(1040, 680)
        self.ctx = context or methods_text.Context()
        lay = QVBoxLayout(self); lay.setContentsMargins(28, 22, 28, 20); lay.setSpacing(10)
        head = QLabel("How the numbers are calculated"); head.setProperty("role", "title")
        lay.addWidget(head)
        self.intro = QLabel(); self.intro.setProperty("role", "secondary"); self.intro.setWordWrap(True)
        lay.addWidget(self.intro)
        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget(); self.list.setMinimumWidth(290); self.list.setMaximumWidth(340)
        self.list.setWordWrap(True); self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for t in methods_text.TOPICS:
            it = QListWidgetItem(t.title); it.setData(Qt.UserRole, t.key)
            self.list.addItem(it)
        self.browser = QTextBrowser(); self.browser.setOpenExternalLinks(True)
        self.browser.setFrameShape(QTextBrowser.NoFrame)
        split.addWidget(self.list); split.addWidget(self.browser)
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        spec = QPushButton("Open the method specification"); spec.clicked.connect(self.open_spec)
        spec.setEnabled(M01.exists())
        row.addWidget(spec); row.addStretch(1)
        self.copy_topic = QPushButton("Copy this explanation"); self.copy_topic.clicked.connect(self.copy_explanation)
        self.copy_para = QPushButton("Copy a methods paragraph"); self.copy_para.setProperty("kind", "primary")
        self.copy_para.clicked.connect(self.copy_paragraph)
        close = QPushButton("Close"); close.clicked.connect(self.close)
        for b in (self.copy_topic, self.copy_para, close):
            row.addWidget(b)
        lay.addLayout(row)
        self.list.currentRowChanged.connect(lambda _r: self.show_topic())
        self.set_context(self.ctx)
        self.list.setCurrentRow(0)

    # ------------------------------------------------------------------ content
    def set_context(self, ctx: methods_text.Context):
        self.ctx = ctx
        if ctx.settings is None:
            self.intro.setText("Every quantity Cyclara reports: what it means in plain words, then the equation, the "
                               "units, the conventions and the settings that change it. Open a file and the settings "
                               "of that file appear under each topic.")
        else:
            self.intro.setText(f"Every quantity Cyclara reports, in plain words and in full. 'For this file' shows "
                               f"the settings that apply to {ctx.file_name or 'the open file'}; the methods "
                               "paragraph is written from the same settings.")
        self.show_topic()

    def current_topic(self) -> methods_text.Topic:
        it = self.list.currentItem()
        key = it.data(Qt.UserRole) if it is not None else methods_text.TOPICS[0].key
        return methods_text.BY_KEY[key]

    def _html(self, t: methods_text.Topic) -> str:
        k = theme.tokens()
        lines = methods_text.for_file(t.key, self.ctx)
        for_file = ""
        if lines:
            for_file = ("<h3>For this file</h3><ul>" + "".join(f"<li>{line}</li>" for line in lines) + "</ul>")
        return (
            "<html><head><style>"
            f"body {{ color: {k.ink}; font-family: '{theme.FAMILY}'; font-size: {theme.css('10pt')}; }}"
            f"h2 {{ font-family: '{theme.DISPLAY}'; font-size: {theme.css('16pt')}; font-weight: 600; margin: 0 0 6px 0; }}"
            f"h3 {{ font-size: {theme.css('11pt')}; font-weight: 600; color: {k.ink}; margin: 18px 0 4px 0; }}"
            f"h4 {{ font-size: {theme.css('10pt')}; font-weight: 600; color: {k.secondary}; margin: 12px 0 2px 0; }}"
            "p { margin: 0 0 8px 0; line-height: 135%; }"
            f"p.eq {{ margin: 6px 0 10px 18px; font-size: {theme.css('11pt')}; }}"
            f"li {{ margin: 0 0 4px 0; }}"
            f"span.where {{ color: {k.muted}; }}"
            "</style></head><body>"
            f"<h2>{t.title}</h2>"
            f"<h3>In short</h3>{t.short}"
            f"<h3>In full</h3>{t.detail}"
            f"{for_file}"
            f"<h3>Where it appears</h3><p>{t.outputs}.</p>"
            f"<p><span class='where'>Specified in {t.spec}.</span></p>"
            "</body></html>")

    def show_topic(self):
        t = self.current_topic()
        self.browser.setHtml(self._html(t))
        self.browser.verticalScrollBar().setValue(0)

    def explanation_text(self) -> str:
        """The topic as plain text, for the clipboard."""
        doc = QTextDocument(); doc.setHtml(self._html(self.current_topic()))
        return doc.toPlainText().strip() + f"\n\n{citation.sentence()}"

    def paragraph_text(self) -> str:
        return methods_text.paragraph(self.ctx)

    # ------------------------------------------------------------------ actions
    def copy_explanation(self):
        QApplication.clipboard().setText(self.explanation_text())
        _flash(self.copy_topic, "Copied", "Copy this explanation")

    def copy_paragraph(self):
        QApplication.clipboard().setText(self.paragraph_text())
        _flash(self.copy_para, "Copied", "Copy a methods paragraph")

    def open_spec(self):
        if M01.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(M01)))

    def select(self, key: str):
        for r in range(self.list.count()):
            if self.list.item(r).data(Qt.UserRole) == key:
                self.list.setCurrentRow(r)
                return
