"""Build the Cyclara user handout (PDF), version 0.6.

Every image in it comes from shareable data: the synthetic demonstration file
data/demo/cyclara_demo_synthetic.mpt (made by scripts/make_demo_data.py; it says
so in its header) and the public data/public/mpt/020-formation_CB5.mpt (CC BY 4.0).
So the handout can live in the repository. Usage:

    python scripts/studio_images.py docs/images/app
    python docs/make_handout.py docs/images/app docs/Cyclara_handout.pdf
"""
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "images" / "app"
OUT = sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "docs" / "Cyclara_handout.pdf")
MARK = ROOT / "electrochem" / "studio" / "assets" / "cyclara_mark_1024.png"
VERSION = "0.9.1"

INK = colors.HexColor("#16202B")
NIGHT = colors.HexColor("#0A101A")
SECONDARY = colors.HexColor("#475263")
MUTED = colors.HexColor("#636E7C")
PANEL = colors.HexColor("#F2F4F7")
LINE = colors.HexColor("#D8DEE5")
VIOLET = colors.HexColor("#3B3B9E")
TEAL = colors.HexColor("#169C8C")
OCHRE = colors.HexColor("#946200")
TINT = colors.HexColor("#EEF0FA")
WARN_TINT = colors.HexColor("#FFF6E0")

ss = getSampleStyleSheet()
body = ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14.2, spaceAfter=4,
                      textColor=INK)
small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=11.5, textColor=MUTED)
h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=17, leading=21, spaceBefore=4, spaceAfter=8)
h2 = ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=VIOLET,
                    spaceBefore=10, spaceAfter=4)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=12, bulletIndent=2)
cell = ParagraphStyle("cell", parent=body, fontSize=9, leading=12.2, spaceAfter=0)
letter = ParagraphStyle("letter", parent=body, fontSize=10.5, leading=15.5, spaceAfter=7)


def P(t, s=body):
    return Paragraph(t, s)


def img(name, width_mm, folder=None):
    p = (folder or ASSETS) / name
    from PIL import Image as PI
    w, h = PI.open(p).size
    return Image(str(p), width=width_mm * mm, height=width_mm * mm * h / w)


def steps(items, colour=VIOLET):
    rows = []
    for k, (head, text) in enumerate(items, 1):
        rows.append([P(f"<font color='white'><b>{k}</b></font>", cell), P(f"<b>{head}</b><br/>{text}", cell)])
    t = Table(rows, colWidths=[9 * mm, 160 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colour), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.6, colors.white), ("BACKGROUND", (1, 0), (1, -1), PANEL)]))
    return t


def table(rows, widths):
    data = [[P(f"<font color='white'><b>{c}</b></font>", cell) for c in rows[0]]]
    data += [[P(c, cell) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), INK), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PANEL])]))
    return t


def note(text, tint=TINT, edge=VIOLET):
    t = Table([[P(text, cell)]], colWidths=[169 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), tint), ("LINEBEFORE", (0, 0), (0, -1), 3, edge),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 7),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return t


def page(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(20 * mm, h - 13 * mm, w - 20 * mm, h - 13 * mm)
    canvas.drawImage(str(MARK), 20 * mm, h - 11.6 * mm, 4.2 * mm, 4.2 * mm, mask="auto")
    canvas.setFillColor(SECONDARY)
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.drawString(25.6 * mm, h - 10.5 * mm, "Cyclara")
    canvas.setFont("Helvetica", 8.5)
    canvas.drawRightString(w - 20 * mm, h - 10.5 * mm, f"user handout, version {VERSION}")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(w / 2, 10 * mm, f"{doc.page}")
    canvas.restoreState()


def cover(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFillColor(NIGHT)
    canvas.rect(0, h - 118 * mm, w, 118 * mm, stroke=0, fill=1)
    canvas.drawImage(str(MARK), w - 20 * mm - 64 * mm, h - 108 * mm, 64 * mm, 64 * mm, mask="auto")
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 38)
    canvas.drawString(20 * mm, h - 44 * mm, "Cyclara")
    canvas.setFont("Helvetica", 15)
    canvas.setFillColor(colors.HexColor("#3CCBB2"))
    canvas.drawString(20 * mm, h - 56 * mm, "Every cycle, clearly.")
    canvas.setFont("Helvetica", 11)
    canvas.setFillColor(colors.HexColor("#C9D1DC"))
    canvas.drawString(20 * mm, h - 72 * mm, "Battery cycling data, from any cycler, to checked numbers")
    canvas.drawString(20 * mm, h - 78 * mm, "and journal-ready figures")
    canvas.setFont("Helvetica", 9.5)
    canvas.setFillColor(colors.HexColor("#8798AE"))
    canvas.drawString(20 * mm, h - 104 * mm, f"User handout, version {VERSION}, October 2026")
    # no author line on the cover (the author asked for it to go); the credits are on the last page
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(w / 2, 10 * mm, "Free software, GPL-3.0-or-later. github.com/asajeevan/electrochem-toolkit")
    canvas.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm,
                        bottomMargin=18 * mm, title="Cyclara user handout", author="Aswadh Shyma Sajeevan",
                        subject=f"Cyclara {VERSION}, electrochem-toolkit")
S = []

# ---------------------------------------------------------------- cover page
S.append(Spacer(1, 114 * mm))
S.append(P("What it does", h1))
S.append(P("Open a BioLogic EC-Lab galvanostatic cycling file (.mpr or .mpt), a LANHE .cex, another cycler's export, or a "
           "whole experiment folder. Answer the few "
           "things only you can tell. Look through every cycle. Export:"))
for line in ("<b>Journal figures that check themselves</b>: drawn at the exact column width of Nature or Elsevier, type "
             "within the journal's limits (sub- and superscripts too), nothing cut off or overlapping, legends and labels "
             "clear of the data, every point inside its axes. PDF and SVG with editable text, PNG at 600 dpi.",
             "<b>Every calculated quantity as tables</b>: one row per cycle, per charge or discharge branch and per rest.",
             "<b>An Origin folder</b> that builds an editable Origin project on a PC with Origin 2021 or later.",
             "<b>A record of what was done</b> (settings.json): the file's fingerprint, your answers, the equations, the "
             "figure checks and the cycles shown, so the analysis can be repeated."):
    S.append(P(f"&bull; {line}", bullet))
S.append(Spacer(1, 6))
S.append(note("<b>Nothing is guessed.</b> What a file cannot say is asked: the current direction (unless the file's step "
              "types name it, as a LANHE .cex does), what the potential column measures, the active mass, and the cycle "
              "order when a file starts with a discharge. A value that needs an answer you have not given is shown as "
              "<i>withheld</i>, with the reason. Capacity agrees with EC-Lab's own counters to better than 10<super>-6</super>."))
S.append(PageBreak())

# ---------------------------------------------------------------- a note to friends
S.append(P("Before you start: a note from me", h1))
for para in (
    "I built this tool for my own cycling data. During my PhD I kept rewriting the same scripts for every new cell and "
    "fixing figures by hand before every paper, and I wanted one place where the numbers are checked once and the "
    "figures come out right the first time. It is free, and it will stay free.",
    "If you run cycling experiments, on an EC-Lab or any other cycler, please try it on one or two of your own files, and pass it on to anyone in "
    "your lab who might use it.",
    "What helps me most is hearing where it went wrong for you:",
):
    S.append(P(para, letter))
for line in ("a file it refused or read wrongly (the exact message, and the file if you can share it);",
             "a number that disagrees with EC-Lab or with your own calculation;",
             "anything in the window that made you stop and wonder, even for a second;",
             "a figure you still had to change before you could use it."):
    S.append(P(f"&bull; {line}", ParagraphStyle("lb", parent=letter, leftIndent=14, bulletIndent=4, spaceAfter=3)))
S.append(Spacer(1, 4))
S.append(P("Tell me in person, send me a message, or open an issue at github.com/asajeevan/electrochem-toolkit/issues "
           "(Help &gt; Report a problem in the app opens it). Every report makes the next version better for all of us.",
           letter))
S.append(P("Thank you,<br/>Aswadh", letter))
S.append(Spacer(1, 10))
S.append(note("Nothing leaves your computer. Cyclara reads your files, never changes them, and needs no internet "
              "connection after installation.", WARN_TINT, OCHRE))
S.append(PageBreak())

# ---------------------------------------------------------------- install
S.append(P("1. Install it once (one click)", h1))
S.append(P("Windows 10 (version 1903 or later) or Windows 11, 64-bit", h2))
S.append(steps([
    ("Run Cyclara-" + VERSION + "-Setup.exe", "Double-click it and click <b>Next</b>, <b>Install</b>, <b>Finish</b>. Cyclara, its own "
                        "Python and every package go into your user folder (about 450 MB); no administrator password is "
                        "asked for and nothing else on the PC is changed. A <b>Cyclara</b> icon appears on the desktop and "
                        "in the Start menu."),
    ("If Windows asks", "The first time, SmartScreen may say <b>Windows protected your PC</b>, because the installer is not "
                        "signed with a paid certificate. Click <b>More info</b>, then <b>Run anyway</b>. Once."),
    ("To remove it", "Settings &gt; Apps &gt; Cyclara &gt; Uninstall. Your files and settings are left alone."),
]))
S.append(P("macOS 14 Sonoma or later", h2))
S.append(steps([
    ("Download the zip for your Mac", "<b>Cyclara-" + VERSION + "-macOS-AppleSilicon.zip</b> for an M1 to M4 Mac, "
                                      "<b>Cyclara-" + VERSION + "-macOS-Intel.zip</b> for an Intel Mac (Apple menu &gt; About This "
                                      "Mac says which). Safari unzips it by itself."),
    ("Drag Cyclara.app to Applications", "Or keep it anywhere you like."),
    ("First launch", "Double-click it. macOS says it cannot verify the app (no paid Apple certificate): click <b>Done</b>, "
                     "open <b>System Settings &gt; Privacy &amp; Security</b>, scroll to Security and click <b>Open Anyway</b>, "
                     "then open Cyclara.app again. Once. On an older macOS, right-click the app and choose <b>Open</b>."),
], TEAL))
S.append(Spacer(1, 6))
S.append(note("Nothing needs installing first: no Python, no Git. The source folder still works the old way too "
              "(<b>Setup.bat</b> or <b>Setup (Mac).command</b> with Python 3.12 installed), for anyone who wants to read or "
              "change the code. <b>Help &gt; Check this installation</b> runs the self-tests on your computer and says "
              "whether everything passed.", WARN_TINT, OCHRE))
S.append(PageBreak())

# ---------------------------------------------------------------- every time
S.append(P("2. Analyse a cell", h1))
S.append(steps([
    ("Open Cyclara", "From the shortcut or the app. A short launch sequence plays; any click or key skips it, and "
                     "View &gt; Motion turns it off."),
    ("Open the file", "Drop the .mpr or .mpt anywhere on the window, or click <b>Open a file</b>; a whole experiment folder "
                      "works too, and <b>Try the demonstration</b> opens a synthetic cell. The reading screen lists only "
                      "what has really happened: rows read, which potential and current columns are used, branches "
                      "segmented. A text or Excel export from another cycler opens straight through when its header is "
                      "recognised; otherwise the review page on the next page opens."),
    ("Answer the questions", "On the right. <b>Which current direction charges the cell</b>; <b>whether each cycle starts with a "
                             "charge or a discharge</b> (asked when the file starts with a discharge, or with a step that ended at "
                             "once); <b>what the potential "
                             "column measures</b>, a half-cell against a reference you name or the cell voltage; and the "
                             "<b>active-material mass</b>, or <b>No mass</b> for capacities in mAh."),
    ("Check the pill", "Top right. It counts the answers still needed and turns green, <b>Ready to export</b>, with a short "
                       "sweep, when every value is available."),
    ("Look and pick cycles", "Switch between Overview, Profiles, Capacity, dQ/dE, Voltage, Timeline and Data. Choose the cycles "
                             "to show on the strip under the plots (page 5)."),
    ("Export", "Open <b>Figures</b>, check the preview and its checks, click <b>Export figures and tables</b> and choose where. "
               "A new folder <b>&lt;file name&gt;_analysis</b> is made there; nothing is overwritten. With Origin on the PC, "
               "<b>Build Origin project</b> in the message that follows makes the .opju (the first time: one click on "
               "<b>Set up Origin link</b>, once); the origin folder holds the tables in Origin's import layout in any case, "
               "for every cycler's file."),
]))
S.append(Spacer(1, 4))
S.append(img("reading.png", 150))
S.append(P("The reading screen. The pictures in this handout use a synthetic demonstration file (it says so in its header) "
           "so they can show fifty cycles.", small))
S.append(PageBreak())

S.append(P("A file from another cycler", h1))
S.append(P("An EC-Lab file is recognised by its signature, and so is a LANHE (LAND) .cex, which is read directly: its "
           "current and voltage are checked against the tester's own capacity and energy counters wherever the file "
           "holds enough records (a note says when it does not), and the tester's steps, with its pauses and "
           "restarts, are listed in instrument_steps.csv. Any other text or Excel export is matched against the "
           "import profiles Cyclara knows (Arbin, Neware, Maccor and the ones you have saved). When none fits, this page "
           "opens instead of the plots:", body))
S.append(Spacer(1, 4))
S.append(img("light_mapping.png", 169))
S.append(Spacer(1, 4))
S.append(steps([
    ("Which column is which", "Cyclara proposes the time, current, potential, step and cycle columns from their names and "
                              "reads the unit from each header; a column without a unit asks for one. Change anything that "
                              "is wrong."),
    ("What the file cannot say", "Which sign of the current means charging (or that the current is unsigned and the step "
                                 "type says), what each step type means, what the capacity columns accumulate, and where "
                                 "cycles start counting. A line of evidence records where you checked."),
    ("Check, then open", "<b>Check</b> reads the whole file with those settings and compares the instrument's own capacity "
                         "counter with the integral of the current, charge and discharge separately. Only a passing check "
                         "unlocks <b>Use these settings</b>. Tick <b>Remember this instrument</b> and every later file with "
                         "the same header opens straight through."),
], TEAL))
S.append(Spacer(1, 4))
S.append(note("Binary files from other makers (.res, .nda, .ndax) are not read: export them as text or Excel from the "
              "instrument's own software first. The compatibility matrix in the docs folder says which instruments were "
              "checked on real files.", WARN_TINT, OCHRE))
S.append(PageBreak())

S.append(P("The window", h1))
S.append(img("light_overview.png", 169))
S.append(Spacer(1, 4))
S.append(table([
    ["Area", "What it is for"],
    ["Files (left)", "Every open file with its state in words: answers needed, analysing, ready to export, could not be read. "
                     "It appears once two files are open, or with one file on a wide window."],
    ["Views (centre)", "Overview (four linked panels), Profiles, Capacity, dQ/dE, Evolution (every cycle's dQ/dE as a colour map "
                       "or a waterfall), Voltage, Timeline, Data and Figures. Hover any "
                       "curve: the measured point under the cursor is read out below the plot, never over the data."],
    ["Cycle strip", "One bar per cycle (next page): the selector, the legend and a picture of the fade."],
    ["Inspector (right)", "The questions, then this record's headline values (each naming its cycle), the focused cycle's "
                          "values, and how the file was read."],
    ["Results (bottom)", "Cycles, Branches and Rests as tables; Diagnostics; Activity, the log of everything you did. "
                         "Ctrl+C copies rows with headers and units, ready for Excel or Origin. The chevron (or Ctrl+J) "
                         "folds them to their tab row to give the plots the room; on a low window they start folded."],
    ["Top bar", "The menus (on macOS in the system menu bar), Open, undo and redo, <b>Search actions</b> (Ctrl+K, or Cmd+K on a "
                "Mac, finds any action by name), the readiness pill, light or dark theme (the new one spreads from the "
                "switch), Export."],
    ["Small screens", "From 1024 x 600 points up (a 14-inch laptop at 150 % scaling) nothing is cut off: the Overview "
                      "arranges its panels for the room, axis titles shorten instead of being cut, the window opens at a "
                      "size that fits the screen and reopens where you left it."],
], [36 * mm, 133 * mm]))
S.append(PageBreak())

# ---------------------------------------------------------------- strip
S.append(P("3. The cycle strip", h1))
S.append(img("strip.png", 169))
S.append(Spacer(1, 4))
S.append(P("Each bar is one cycle; its height is the discharge capacity, so the strip shows the fade at a glance. The selected "
           "cycles take the colours their curves have in every plot, from deep violet for the earliest to teal for the latest: "
           "the strip is the legend. Grey bars are not shown. An outlined stub marks a cycle without a partner branch."))
S.append(table([
    ["To do this", "Do this"],
    ["Add or remove one cycle", "Click its bar."],
    ["Select a range", "Drag across the bars. Hold Ctrl to add the range to the selection."],
    ["Focus one cycle", "Double-click it. It is drawn thicker everywhere, underlined in orange, and its values fill the "
                        "inspector."],
    ["Browse without changing the selection", "Left and Right on the strip, or Up and Down in the Cycles table, move the focus. "
                                              "A focused cycle outside the selection is previewed dashed and is not exported."],
    ["Type a selection", "In the box: <b>1, 2, 5:10, -1</b>. A colon gives a range, a third number a step (<b>0:100:10</b> is "
                         "every tenth cycle), and negative numbers count from the end (<b>-1</b> is the last cycle). Numbers "
                         "that are not in the file are named in the status bar."],
], [52 * mm, 117 * mm]))
S.append(Spacer(1, 6))
S.append(note("The cycles you select here are the cycles in the exported figures, and settings.json records them."))
S.append(PageBreak())

# ---------------------------------------------------------------- figures
S.append(P("4. Figures and their checks", h1))
S.append(img("light_figures.png", 169))
S.append(Spacer(1, 4))
S.append(P("The Figures view draws each figure with exactly the code that writes the file, so the preview is the export. "
           "<b>True size</b> shows it at its printed size (hold a ruler to the screen once to confirm), <b>Fit</b> fills the view. "
           "Untick a figure to leave it out of the export; your ticks are kept."))
S.append(table([
    ["Check", "What it verifies"],
    ["Width, height", "Exactly one of the journal's column widths (Nature 89, 120, 136 or 183 mm; Elsevier 90, 140 or 190 mm) "
                      "and no taller than allowed."],
    ["Type size", "Every label between the journal's minimum and maximum (Nature 5 to 7 pt), sub- and superscripts included "
                  "(at least 5 pt for Nature, 6 pt for Elsevier); panel letters 8 pt bold lowercase."],
    ["Text inside, no overlap", "No label is cut at the edge or touches another."],
    ["Legends and text clear of data", "No point, line, band or bar lies under a legend or an annotation. Legends are placed "
                                       "where they cover nothing."],
    ["Data inside the axes", "Every plotted point lies within its axes, so nothing is silently missing."],
    ["Line weights, colour contrast", "Every stroke and tick at least 0.25 pt; every data colour at least 3:1 against white."],
    ["Typeface, editable text", "Arial or a metric twin, embedded as TrueType so the text stays editable."],
], [50 * mm, 119 * mm]))
S.append(PageBreak())

S.append(P("A summary figure", h1))
S.append(img("fig_summary.png", 169))
S.append(P("Drawn by Cyclara from the synthetic demonstration file (fifty cycles of an imaginary positive electrode against "
           "lithium; not a measurement). a: potential against specific capacity. b: charge (open) and discharge (filled) "
           "capacity with coulombic efficiency. c: dQ/dE with potential on the vertical axis, discharge left and charge right. "
           "d: average charge and discharge potential and their difference. All twelve checks pass.", small))
S.append(Spacer(1, 6))
S.append(img("light_measured_cb5.png", 169))
S.append(P("Measured data: the public formation file 020-formation_CB5.mpt (CC BY 4.0), a full cell analysed without a mass, "
           "so capacities are in mAh.", small))
S.append(PageBreak())

# ---------------------------------------------------------------- numbers
S.append(P("5. What the numbers mean", h1))
S.append(table([
    ["Quantity", "Definition used by Cyclara"],
    ["Capacity", "Charge passed in one charge or discharge branch: the instrument's own charge increments when the file has "
                 "them (EC-Lab's dq, integrated at the full acquisition rate), otherwise the trapezoid of the recorded "
                 "current; the trapezoid is always reported beside it as a check."],
    ["Specific or areal capacity", "Per gram of active material when you give the mass; per cm<super>2</super> when you give "
                                   "only the electrode area; otherwise mAh. Every label and value use the same basis."],
    ["Cycle", "One charge and the discharge after it, or with <i>Discharge, then charge</i> one discharge and the charge after "
              "it. Numbered from 1; EC-Lab's own counter can differ by one (the Branches table lists both)."],
    ["Coulombic efficiency", "100 x Q<sub>discharge</sub> / Q<sub>charge</sub> of the same cycle, complete pairs only, never "
                             "clipped at 100 %."],
    ["Capacity retention", "100 x Q<sub>discharge</sub>(n) / Q<sub>discharge</sub>(reference cycle, 1 unless you change it). "
                           "A reference that is not a complete cycle is refused, with the reason."],
    ["Average voltage", "Energy divided by charge of the branch: the charge-weighted mean potential. With several plateaus "
                        "it is the capacity-weighted mean of the plateau potentials (next page)."],
    ["Voltage hysteresis", "Average charge voltage minus average discharge voltage of the same cycle."],
    ["dQ/dE", "Capacity interpolated onto a 10 mV grid inside the measured range and differentiated; constant-voltage stages "
              "excluded; none for a branch interrupted or paused inside its curve, not in a constant-voltage hold "
              "at its start or end (the cycle note says why). Peak positions "
              "describe the measured curve at that rate; they are not equilibrium potentials."],
    ["dQ/dE peaks", "Each peak is one plateau: its potential, the capacity under it (valley to valley), its partner in the "
                    "opposite branch of the same cycle (paired within 200 mV) or <i>unpaired</i>, and the cycles in which it "
                    "is seen. Help &gt; How the numbers are calculated has the full rules."],
    ["Capacity fade", "Negative slope of a straight line fitted to retention against cycle number, in % per cycle."],
    ["Withheld", "A value that needs an answer you have not given, or that is not defined for that cycle. The reason is "
                 "shown beside it, and in a tooltip in the tables."],
], [40 * mm, 129 * mm]))
S.append(Spacer(1, 6))
S.append(P("Diagnostics", h2))
S.append(P("The Diagnostics tab lists what the analysis noticed: edges not integrated (a time reset, a gap, an error flag), "
           "cycles without a partner, any branch that passed more than three times the median charge of its direction, and "
           "specific capacities above any electrode material's theoretical capacity (usually a wrong mass, such as EC-Lab's "
           "0.001 mg default). It reports; it does not name a cause, because the data alone cannot tell a short from a side "
           "reaction."))
S.append(PageBreak())

# ---------------------------------------------------------------- plateaus
S.append(P("Several plateaus, and how they change", h1))
S.append(P("A material with three or four plateaus that return on discharge and one or two that do not gives one dQ/dE peak "
           "per plateau. The inspector lists the focused cycle's peaks; the Evolution view shows every cycle's dQ/dE as a "
           "colour map (or a waterfall), so a plateau that stays is a vertical band, one that fades or drifts bends or "
           "thins, and one present in the first charge only is a mark on the first row.", body))
S.append(Spacer(1, 4))
S.append(img("light_plateaus.png", 150))
S.append(P("The synthetic test cell of tests/plateau_cell.py, run for 30 cycles (not a measurement): plateaus at 3.0, 3.4 and "
           "3.8 V with 60 mV between charge and discharge, one at 4.10 V in the first charge only, a small one from cycle 3.",
           small))
S.append(Spacer(1, 4))
S.append(steps([
    ("Mean potential", "The average potential of a branch is energy divided by charge, so plateaus of 40, 80 and 30 mAh g"
                       "<super>-1</super> at 3.0, 3.4 and 3.8 V give (40 x 3.0 + 80 x 3.4 + 30 x 3.8) / 150 = 3.373 V. Each "
                       "plateau's own potential is its peak in dqde_peaks.csv, with the capacity under it."),
    ("Peaks that do not return", "A charge peak with no discharge peak within 200 mV in the same cycle is <i>unpaired</i>; "
                                 "one seen only in the first cycle is <i>first cycle only</i>. Cyclara does not call a peak "
                                 "irreversible: a counterpart can also be shifted, merged or below the threshold."),
    ("3D", "Export writes fig6_dqde_map (colour map) and fig7_dqde_surface (below). Read numbers from the tables or the "
           "map: a 3D view hides what lies behind a ridge."),
], VIOLET))
S.append(Spacer(1, 4))
S.append(img("fig_plateau_surface.png", 169))
S.append(PageBreak())

# ---------------------------------------------------------------- results
S.append(P("6. The results folder", h1))
S.append(table([
    ["File", "Contents"],
    ["summary.json", "Headline numbers: first complete cycle's capacities and efficiency, maximum capacity, retention at the "
                     "last cycle, cycle reaching 80 % retention, fade per cycle, mean efficiency, mean hysteresis, theoretical "
                     "capacity, utilisation."],
    ["cycles.csv", "One row per cycle with all the quantities above, plus energies, energy efficiency, C-rates, open-circuit "
                   "potentials."],
    ["branches.csv", "One row per charge or discharge, including the constant-current and constant-voltage parts and the "
                     "cross-check against the instrument counter."],
    ["rests.csv", "Every rest: duration, potential at start and end, relaxation."],
    ["curves_potential_capacity.csv", "The plotted curves at full resolution."],
    ["dqde_curves.csv, dqde_peaks.csv, dqde_pairs.csv, dqde_map.csv",
     "Differential capacity curves; every cycle's peaks with the capacity under each, the partner peak in the opposite "
     "branch (paired within 200 mV) or 'unpaired', and the cycles in which it is seen; the pairs; the evolution grid."],
    ["metadata.json", "What the file declares: an EC-Lab header with its step table, or another reader's record. A "
                      "LANHE .cex adds instrument_steps.csv, the tester's step table."],
    ["settings.json", "Your answers, the methods, the figure checks and the cycles shown. Keep it with the data."],
    ["activity.txt", "Everything you did in the app, in time order."],
    ["fig1 to fig7, fig_summary", "The figures, each as .pdf, .svg and .png; fig6 and fig7 are the dQ/dE evolution map and surfaces."],
    ["origin", "The tables in Origin's import layout and the script that builds the Origin project."],
], [50 * mm, 119 * mm]))
S.append(Spacer(1, 8))
S.append(P("7. If something goes wrong", h1))
S.append(table([
    ["Message or symptom", "What it means and what to do"],
    ["The file is named as impedance, CV or chronoamperometry", "Not a cycling file. This version analyses GCPL, CC and CCCV."],
    ["The .mpr reader is not installed", "Git was missing during setup. Install Git and run the setup again, or export .mpt."],
    ["An .mps file holds a protocol's settings", "Open the run's .mpr or .mpt; the .mps has no measurements."],
    ["A red note about the theoretical capacity", "Check the mass: active material only, in mg."],
    ["Efficiencies far above 100 %, curves swapped", "The current direction is the wrong way round. Choose the other answer; "
                                                     "Ctrl+Z undoes it."],
    ["Windows refused to write there", "A file from an earlier export is open in Excel, Origin or a PDF viewer. Close it."],
    ["macOS: the app cannot be verified", "Click Done, then System Settings &gt; Privacy &amp; Security &gt; Open Anyway, and "
                                          "open Cyclara again (once). On macOS 14, right-click the app and choose Open."],
], [62 * mm, 107 * mm]))
S.append(Spacer(1, 6))
S.append(P("Still stuck? Help &gt; Show the error log opens the log; send it with the message you saw, activity.txt from the "
           "export if there was one, and if possible the data file.", body))
S.append(PageBreak())

S.append(P("Where the numbers come from, and how to cite", h1))
S.append(P("Help &gt; <b>How the numbers are calculated</b> explains every quantity Cyclara reports, first in plain words, "
           "then in full (equation, units, sign convention, what the file must contain, the settings that change it, when "
           "it is not produced), with the settings of the open file filled in under each topic. Several plateaus, "
           "irreversible peaks, the C-rate's reference capacity, the two charge paths: each has its page.", body))
S.append(Spacer(1, 4))
S.append(img("light_methods.png", 150))
S.append(Spacer(1, 4))
S.append(steps([
    ("Copy a methods paragraph", "A paragraph for the experimental section, written from the answers you gave (mass, "
                                 "reference cycle, potential role, dQ/dE grid), ending with the reference."),
    ("Cite Cyclara", "Help &gt; <b>Cite Cyclara</b> copies the citation as a reference-list entry, BibTeX, CITATION.cff or "
                     "a one-line methods sentence. Cite the version: the way a number is calculated can change between "
                     "versions, and the version makes a result reproducible."),
], TEAL))
S.append(PageBreak())

S.append(P("8. Good practice", h1))
for line in ("Keep the .mpt export next to the .mpr so the header (mass, step programme) is read; Cyclara recognises the export "
             "by the file name in its header.",
             "Never edit cycles.csv by hand; change the answer in the app and export again, so settings.json stays true.",
             "Keep settings.json with the figures you publish: it documents the mass, the conventions and the equations behind "
             "every number.",
             "Use the same retention reference cycle for every cell you compare, and say which in the caption.",
             "Repeated cycles of one cell are not independent replicates. Compare cells, not cycles, when you report a mean and "
             "a spread."):
    S.append(P(f"&bull; {line}", bullet))
S.append(Spacer(1, 10))
S.append(P("Credits and licence", h1))
S.append(P("Cyclara and electrochem-toolkit were created by <b>Aswadh Shyma Sajeevan</b> and are free software under "
           "GPL-3.0-or-later: use, share and modify them, keeping the author notice. If the tool contributes to a publication, "
           "please cite it (Help &gt; Cite Cyclara, or CITATION.cff in the toolkit). The .mpr reader Galvani is an external GPL project by echemdata; the "
           "app uses Qt for Python (PySide6, LGPL) and pyqtgraph (MIT); the Inter typeface is used under the SIL Open Font "
           "License. Not affiliated with BioLogic."))

doc.build(S, onFirstPage=cover, onLaterPages=page)
print("written", OUT)
