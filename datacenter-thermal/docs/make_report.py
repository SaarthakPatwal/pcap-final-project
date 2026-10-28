"""Generate the eight-page beginner viva guide from the inspected source."""
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

HERE = Path(__file__).resolve().parent
OUT = HERE / "Project_Explanation.pdf"
W, H = A4
LEFT, RIGHT, TOP, BOTTOM = 45, 45, 49, 43
WIDTH = W - LEFT - RIGHT
INK = colors.HexColor("#1e3034")
MUTED = colors.HexColor("#587078")
TEAL = colors.HexColor("#087f73")
PALE = colors.HexColor("#eaf4ef")
LINE = colors.HexColor("#d7e2dd")
ORANGE = colors.HexColor("#d66547")

FONT_DIR = Path(r"C:\Windows\Fonts")
pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "arialbd.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold")
pdfmetrics.registerFont(TTFont("Consolas", str(FONT_DIR / "consola.ttf")))

BODY = ParagraphStyle("body", fontName="Arial", fontSize=11, leading=15.3,
                      textColor=INK, alignment=TA_LEFT)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=10.5, leading=13.7)
TABLE = ParagraphStyle("table", parent=BODY, fontSize=10.2, leading=13.5)
TABLE_HEAD = ParagraphStyle("head", parent=TABLE, fontName="Arial-Bold", textColor=TEAL)
QA = ParagraphStyle("qa", parent=BODY, fontSize=10.6, leading=13.6)

c = canvas.Canvas(str(OUT), pagesize=A4, pageCompression=1)
c.setTitle("Parallel Data Center Thermal Simulation - Project Explanation")
c.setAuthor("Soham Bhattacherjee, Saarthak Patwal, Akshansh Goel")
page = 0
y = H - TOP


def check(height=0):
    if y - height < BOTTOM:
        raise ValueError(f"Page {page} overflows by {BOTTOM - (y-height):.1f} pt")


def new_page(title, label):
    global page, y
    if page:
        c.showPage()
    page += 1
    c.setFillColor(TEAL)
    c.setFont("Arial-Bold", 9)
    c.drawString(LEFT, H - 28, "P-CAP  /  PROJECT EXPLANATION")
    c.setFillColor(MUTED)
    c.setFont("Arial", 9)
    c.drawRightString(W - RIGHT, H - 28, label.upper())
    c.setStrokeColor(LINE)
    c.line(LEFT, H - 34, W - RIGHT, H - 34)
    y = H - TOP - 9
    if title:
        heading(title, 20, 27)


def finish_page():
    check()
    c.setStrokeColor(LINE)
    c.line(LEFT, 31, W - RIGHT, 31)
    c.setFillColor(MUTED)
    c.setFont("Arial", 8.5)
    c.drawString(LEFT, 20, "Based on the project's C++, Python and browser source")
    c.drawRightString(W - RIGHT, 20, f"{page} / 8")


def heading(text, size=15, after=19):
    global y
    check(size + 6)
    c.setFillColor(INK)
    c.setFont("Arial-Bold", size)
    c.drawString(LEFT, y - size, text)
    y -= size + after


def sub(text):
    global y
    check(22)
    c.setFillColor(TEAL)
    c.setFont("Arial-Bold", 11.5)
    c.drawString(LEFT, y - 11.5, text)
    y -= 22


def para(text, style=BODY, gap=8, x=LEFT, width=WIDTH):
    global y
    p = Paragraph(text, style)
    _, h = p.wrap(width, 1000)
    check(h + gap)
    p.drawOn(c, x, y - h)
    y -= h + gap


def summary(text):
    global y
    p = Paragraph("<b>In short:</b> " + text, BODY)
    _, h = p.wrap(WIDTH - 25, 1000)
    height = h + 22
    check(height + 13)
    c.setFillColor(PALE)
    c.roundRect(LEFT, y - height, WIDTH, height, 7, stroke=0, fill=1)
    p.drawOn(c, LEFT + 13, y - 11 - h)
    y -= height + 13


def gap(points=6):
    global y
    check(points)
    y -= points


def formula(lines, note=None):
    global y
    line_h = 15
    height = len(lines) * line_h + (21 if note else 0) + 17
    check(height + 8)
    c.setFillColor(colors.HexColor("#f3f6f5"))
    c.roundRect(LEFT, y - height, WIDTH, height, 5, stroke=0, fill=1)
    c.setFillColor(INK)
    c.setFont("Consolas", 9.7)
    for i, line in enumerate(lines):
        c.drawString(LEFT + 12, y - 17 - i * line_h, line)
    if note:
        c.setFont("Arial", 10)
        c.setFillColor(MUTED)
        c.drawString(LEFT + 12, y - height + 11, note)
    y -= height + 8


def table(headers, rows, widths, row_gap=8, style=TABLE):
    global y
    assert abs(sum(widths) - WIDTH) < 1
    all_rows = [headers] + rows
    for row_i, row in enumerate(all_rows):
        ps = [Paragraph(cell, TABLE_HEAD if row_i == 0 else style) for cell in row]
        hs = [p.wrap(widths[i] - 14, 1000)[1] for i, p in enumerate(ps)]
        rh = max(hs) + row_gap * 2
        check(rh)
        c.setFillColor(PALE if row_i == 0 else (colors.white if row_i % 2 else colors.HexColor("#f8faf9")))
        c.rect(LEFT, y - rh, WIDTH, rh, stroke=0, fill=1)
        for i, p in enumerate(ps):
            x = LEFT + sum(widths[:i]) + 7
            p.drawOn(c, x, y - row_gap - hs[i])
        c.setStrokeColor(LINE)
        c.line(LEFT, y - rh, W - RIGHT, y - rh)
        y -= rh
    gap(10)


def qa(number, question, answer):
    para(f"<b>{number}. {escape(question)}</b> {escape(answer)}", QA, gap=5)


# 1 - Title and overview
new_page("", "title")
gap(70)
c.setFillColor(TEAL)
c.setFont("Arial-Bold", 12)
c.drawString(LEFT, y, "UNIVERSITY VIVA GUIDE  /  P-CAP")
gap(30)
heading("Parallel Data Center", 26, 10)
heading("Thermal Simulation", 26, 10)
heading("and Hotspot Analysis", 26, 13)
c.setFillColor(ORANGE)
c.roundRect(LEFT, y - 6, 85, 5, 2, stroke=0, fill=1)
gap(38)
summary("A small digital twin: one computer model of a data center, shown as a grid of racks.")
para("We can change one rack or select many racks and change their temperature, workload, and cooling together. The model updates the heat in each rack and shows how heat moves to nearby racks. We can watch this happen on a live heatmap. The same calculation runs on one CPU core, on multiple CPU cores with OpenMP, or on an NVIDIA GPU with CUDA. A second page compares their speed.")
gap(18)
sub("Team members")
para("<b>Soham Bhattacherjee</b><br/><b>Saarthak Patwal</b><br/><b>Akshansh Goel</b>")
gap(24)
para("<b>What to say first:</b> The project studies how heat, workload, and cooling interact across nearby racks. It also shows when parallel computing makes the same simulation faster.")
para("This is a simple teaching model. One step is one update, not one real-world second.", SMALL)
finish_page()

# 2 - Tech stack
new_page("Tools and architecture", "02 / stack")
summary("The browser displays results; Flask passes requests to one compiled C++ library; that library chooses CPU, OpenMP, or CUDA.")
table(["Component", "Technology", "Why we used it", "Its job here"], [
    ["Simulator", "C++", "Fast loops over many racks", "Updates temperatures and statistics"],
    ["CPU parallel mode", "OpenMP", "Simple way to split loops", "Runs rack updates on CPU workers"],
    ["GPU mode", "CUDA", "Many GPU threads", "Runs one GPU thread per rack"],
    ["Build", "CMake", "Builds the same library for Windows", "Finds OpenMP and optional CUDA"],
    ["Server", "Python + Flask", "Small web server", "Receives requests and returns JSON data"],
    ["Bridge", "ctypes", "Calls a compiled C library from Python", "Loads thermal.dll and passes arrays"],
    ["Interface", "HTML, CSS, JavaScript", "Simple two-page interface", "Controls, layout, requests, selection"],
    ["Heatmap", "Canvas", "Draws many colored cells", "Shows temperatures and outlines"],
    ["Charts", "Chart.js", "Draws line and bar graphs", "History and benchmark plots"],
], [89, 91, 155, 170], row_gap=6)
sub("Request path")
formula(["Browser  ->  Flask  ->  ctypes  ->  thermal.dll", "                                |", "                         CPU / OpenMP / CUDA"],
        "JSON is the text format used between browser and server.")
para("<b>Library:</b> thermal.dll is the compiled C++ program on Windows. A plain C interface in api.cpp lets ctypes call it. CUDA is included only when CMake finds its compiler.", SMALL)
finish_page()

# 3 - Grid and double buffering
new_page("One grid, many racks", "03 / simulation")
summary("Each square is a server rack. Each step changes its workload, then computes a new temperature using its old temperature and nearby racks.")
para("An N x N grid has N rows and N columns. Each rack stores <b>temperature</b> (degrees C), <b>workload</b> (0-100%), and <b>cooling</b> (0-100%). The arrays are flat: <font name='Consolas'>index = row * N + column</font>. The live page offers N = 64, 128, 256, or 512.")
sub("Which neighbors affect a rack?")
grid_x, grid_y, cell = LEFT + 165, y - 10, 37
for r in range(3):
    for col in range(3):
        lab = {(0, 1): "N", (1, 0): "W", (1, 1): "C", (1, 2): "E", (2, 1): "S"}.get((r, col), "-")
        c.setFillColor(PALE if lab == "C" else colors.HexColor("#f7faf8"))
        c.setStrokeColor(LINE)
        c.rect(grid_x + col * cell, grid_y - (r + 1) * cell, cell, cell, stroke=1, fill=1)
        c.setFillColor(TEAL if lab == "C" else INK)
        c.setFont("Arial-Bold", 11)
        c.drawCentredString(grid_x + col * cell + cell/2, grid_y - (r + 1) * cell + 13, lab)
y -= 139
para("For center rack C, the code averages North, South, West, and East. At an edge it uses only existing neighbors. A corner therefore has two neighbors; no heat wraps around the grid.")
sub("Why two temperature arrays?")
formula(["OLD temperatures  ->  calculate every NEW temperature", "      read only                 write once per rack", "After all racks finish: swap OLD and NEW arrays."], None)
para("This is <b>double buffering</b>: an old grid and a new grid. In the 3 x 3 example, C reads the old values of N, S, W, and E. If C changed the old grid immediately, its later neighbors might read a mixture of old and new values. Separate arrays keep every rack on the same step.")
sub("Order within one step")
table(["1", "2", "3", "4"], [["Change workload by -2 to +2", "Update temperature", "Apply throughput throttling", "Compute max, average, hotspots, throughput"]], [114, 126, 127, 138], row_gap=7)
para("The grid starts at 25 C. Cooling starts at 50%. Workload starts at a reproducible value from 45% to 55% for each rack. A <b>hotspot</b> is a rack above the chosen threshold, initially 85 C.", SMALL)
finish_page()

# 4 - Formulas, first half
new_page("Formulas: the update", "04 / formulas")
summary("A repeatable small workload change feeds the heat equation. Nearby temperatures, workload, cooling, and ambient temperature determine the new value.")
sub("1. Dynamic workload")
formula(["delta = cell_hash(index, step) % 5 - 2", "w_new = clamp(w_old + delta, 0, 100)"], None)
para("<b>Symbols:</b> index is the rack's flat position; step counts updates; w is workload in percent. The hash makes a repeatable integer delta from -2 to +2. <b>Meaning:</b> each rack's work changes a little each step. <b>Example:</b> if w_old = 60 and hash % 5 = 4, delta = 2 and w_new = 62%.", SMALL)
sub("2. Neighbor average and ambient cooling")
formula(["avg = sum(existing N, S, W, E temperatures) / count", "effective_cooling = cooling + (25.0 - ambient)"], None)
para("<b>Symbols:</b> count is 2, 3, or 4 for corner, edge, or interior racks; ambient defaults to 25 C and its slider allows 10-45 C. Cooling initially is 50%. <b>Meaning:</b> a warmer ambient makes cooling less effective. <b>Example:</b> neighbors 70, 70, 70, 70 give avg = 70 C. Cooling 20 and ambient 30 give effective_cooling = 20 + (25 - 30) = 15.", SMALL)
sub("3. Temperature after one step")
formula(["T_new = T + alpha * (avg - T) + beta * w_new", "          - gamma * effective_cooling", "alpha = 0.2; beta = 0.01; gamma = 0.01"], None)
para("<b>Symbols:</b> T is the rack's old temperature, avg is the neighbor average, and w_new is the updated workload. alpha controls heat exchange with neighbors; beta adds workload heat; gamma removes heat through cooling. These constants are fixed in common.h. <b>Meaning:</b> heat moves toward the neighbor average, workload adds heat, and cooling removes heat.", SMALL)
formula(["T=80, avg=70, w_new=60, cooling=20, ambient=25", "effective_cooling = 20 + (25 - 25) = 20", "T_new = 80 + 0.2*(70-80) + 0.01*60 - 0.01*20", "      = 80 - 2 + 0.6 - 0.2 = 78.4 C"], "Worked example: a cooling rack with four neighbors at 70 C.")
para("At ambient 30 C, effective_cooling becomes 15, so the same example ends at 78.45 C. The code does not clamp temperature after this calculation.", SMALL)
finish_page()

# 5 - Formulas, second half
new_page("Formulas: what we measure", "05 / formulas")
summary("The updated temperature decides whether a rack throttles and whether it is counted as a hotspot. Statistics combine all racks.")
sub("4. Throttling and throughput")
formula(["effective_workload = (T_new > 85.0) ? w_new * 0.7 : w_new", "throughput = sum(effective_workload of all racks)"], None)
para("<b>Symbols:</b> w_new is the stored workload after drift. The throttle cutoff is fixed at 85 C. <b>Meaning:</b> a hot rack contributes only 70% of its workload to throughput; its stored workload and heat input are unchanged. <b>Example:</b> at 86 C and workload 60%, effective workload is 42; at 85 C it is 60. Together they contribute 102 units.", SMALL)
sub("5. Hotspots and temperature statistics")
formula(["hotspot = (T_new > threshold)", "hotspot_count = sum(hotspot over all racks)", "maximum = max(T_new over all racks)", "average = sum(T_new over all racks) / (N * N)"], None)
para("<b>Symbols:</b> threshold starts at 85 C and the UI allows 30-120 C. N is the grid width. <b>Meaning:</b> threshold changes only the hotspot display, not the fixed 85 C throttle rule. <b>Example:</b> temperatures 78.4 and 86 give maximum 86, average 82.2, and one hotspot when threshold = 85; at threshold = 90 there are none.", SMALL)
sub("6. Comparing speed")
formula(["time_per_step_ms = measured_wall_time_ms / steps", "speedup = CPU_time_per_step_ms / backend_time_per_step_ms", "verified if abs(final_max - CPU_final_max) <= 0.001 C"], None)
para("<b>Meaning:</b> smaller time is faster; speedup above 1 means faster than sequential CPU. <b>Example:</b> CPU 10 ms and CUDA 2 ms give 5x speedup. The check compares final maximum temperature only, within 0.001 C. The benchmark uses five warm-up steps outside its timing.", SMALL)
sub("How temperature becomes dynamic")
para("Three inputs can change it: the per-rack workload drift each step; the cooling and ambient values; and user edits to one or many racks. The next grid then spreads a changed rack's heat to its neighbors over later steps.")
finish_page()

# 6 - Backends + concepts
new_page("Three ways to compute", "06 / parallelism")
summary("All three modes use the same rack equation. They differ in how work is assigned and where arrays live.")
sub("Sequential CPU")
para("cpu_sim.cpp visits each row and column in ordinary nested loops. It writes one new rack value at a time. After swapping temperature arrays, one loop collects the statistics. This is the reference mode.", SMALL)
sub("OpenMP: several CPU workers")
para("omp_sim.cpp adds <font name='Consolas'>#pragma omp parallel for collapse(2) schedule(static)</font>. <b>collapse(2)</b> combines the row and column loops into one list of rack jobs. A <b>thread</b> is one worker. Each thread writes different rack positions. The loop's end is a <b>barrier</b>: everyone finishes before the arrays swap.", SMALL)
para("The statistics loop uses <font name='Consolas'>reduction(+:sum,throughput,hotspots)</font> and <font name='Consolas'>reduction(max:maximum)</font>. A <b>reduction</b> combines each worker's partial answer into one result without several workers editing one counter at once.", SMALL)
sub("CUDA: many GPU threads")
para("cuda_sim.cu maps a 16 x 16 <b>block</b> (a group of 256 GPU threads) onto a 16 x 16 rack region. One thread updates one rack. The two temperature arrays, workload, and cooling stay in GPU <b>global memory</b> between steps. A selectable tiled kernel first caches an 18 x 18 region in faster <b>shared memory</b>, including a one-rack border called a halo.", SMALL)
para("A first reduction kernel combines up to 256 racks per block; a second combines the block results for max temperature, temperature sum, hotspot count, and throughput. <font name='Consolas'>cudaDeviceSynchronize()</font> waits between steps. CUDA events time the GPU work. Full arrays return to the CPU only when the browser asks for a frame.", SMALL)
table(["Mode", "Runs on", "Workers / memory", "Useful when"], [
    ["CPU", "CPU", "One loop; host RAM", "A simple reference or small grid"],
    ["OpenMP", "CPU cores only", "Several CPU threads; shared host RAM", "Enough racks to share across cores"],
    ["CUDA", "RTX 4060 GPU", "16 x 16 thread blocks; GPU memory", "Large grids with many independent racks"],
], [73, 105, 190, 137], row_gap=5)
para("<b>Key ideas:</b> Data parallelism means using the same equation on different racks. Double buffering avoids a <b>race</b>, where results depend on execution order. Moving data between host RAM and GPU memory costs time, so CUDA keeps arrays on the GPU. Small grids may lose time to thread setup or kernel launches.", SMALL)
finish_page()

# 7 - Interface and settings
new_page("What the user can do", "07 / interface")
summary("The live page changes racks and shows the result. The benchmark page compares speed and checks the final maximum temperature.")
sub("Page 1: Live Simulation")
para("Choose <b>CPU, OpenMP, or CUDA</b> and a <b>grid size</b>; either choice resets the grid. <b>Start</b> runs repeatedly, <b>Pause</b> stops, <b>Step +1</b> runs once, and <b>Reset</b> restores initial data. The speed slider chooses steps per requested frame, not guaranteed frames per second.", SMALL)
para("Click to select one cell; drag to select a rectangle; Shift-click to add or remove one cell. Select all and Clear selection work on the whole grid. Apply sets temperature, workload, and cooling for every selected rack. Quick buttons add 10 C, subtract 10 C, set max workload, or set workload to zero. The last action is temporary: workload drift resumes next step.", SMALL)
para("Presets are Normal load, Hot aisle failure, Cooling failure, Cooling boost, and Random spikes. The heatmap shows rack color, white selection outlines, and yellow hotspot outlines. Hover shows a rack's three values. Six cards show max/average temperature, hotspots, throughput, step, and ms per step. A line chart tracks max temperature and throughput.", SMALL)
sub("Page 2: Performance Comparison")
para("Run Benchmark tests 128, 256, 512, 1024, and 2048-wide grids. The <b>bar chart</b> uses grid size on X and wall milliseconds per step on Y; shorter bars are faster. The <b>line chart</b> uses grid size on X and speedup over CPU on Y; higher is faster. The table lists times and speedups. Its check compares final maximum temperature with CPU within 0.001 C. The page also shows OpenMP threads, GPU name, CUDA block size, and a CSV download.", SMALL)
sub("Settings: adjustable versus fixed")
table(["Setting", "Default", "Allowed / where"], [
    ["Live grid size", "64", "64, 128, 256, 512 (UI)"] ,
    ["Steps per frame", "5", "1-30 (UI); /step accepts 0-100"],
    ["Benchmark size / steps", "128-2048 / 100", "Five fixed sizes / 1-1000 steps"],
    ["Ambient / hotspot threshold", "25 C / 85 C", "10-45 C / 30-120 C"],
    ["Selected temp / work / cool", "65 C / 100% / 25%", "UI: 0-120 C / 0-100% / 0-100%"],
    ["alpha / beta / gamma", "0.2 / 0.01 / 0.01", "Fixed in code; no UI control"],
    ["CUDA block / tiling", "16 x 16 / off", "Block fixed; tiling checkbox on/off"],
    ["OpenMP workers", "8 for run-cuda.ps1", "OMP_NUM_THREADS environment variable"],
], [195, 105, 205], row_gap=4, style=TABLE)
finish_page()

# 8 - Run and questions
new_page("Run it and explain it", "08 / viva")
summary("Start the saved CUDA build from the project folder, open the local page, then use these short answers to explain the design.")
formula(["cd C:\\Users\\Saarthak\\Desktop\\datacenter_final\\datacenter-thermal", "powershell -NoProfile -ExecutionPolicy Bypass -File .\\run-cuda.ps1", "Open http://127.0.0.1:5000  ->  choose CUDA in the UI"], None)
para("The script sets <font name='Consolas'>THERMAL_LIBRARY</font> to build-cuda-vs/Release/thermal.dll and <font name='Consolas'>OMP_NUM_THREADS=8</font>, adds the OpenMP runtime path, then runs <font name='Consolas'>server/app.py</font>. Keep the terminal open; Ctrl+C stops the server. Rebuild with <font name='Consolas'>.\\build-cuda.cmd</font> after changing C++ or CUDA source.", SMALL)
sub("Ten likely viva questions")
qa(1, "Why double buffering?", "Every rack reads the old grid. A separate new grid stops update order from changing the answer.")
qa(2, "Why one GPU thread per rack?", "Each rack runs the same small equation and writes its own output, so the jobs are independent.")
qa(3, "Why is OpenMP CPU-only here?", "Its parallel loops use CPU workers sharing host memory. CUDA launches work on the NVIDIA GPU.")
qa(4, "What is a reduction?", "It combines many partial values, such as local maxima or counts, into one final statistic.")
qa(5, "What makes parallel mode faster?", "Many rack updates happen at once. Setup and memory costs can outweigh that gain for small grids.")
qa(6, "What happens above 85 C?", "Effective workload becomes 70% of stored workload, reducing reported throughput.")
qa(7, "How do several racks change at once?", "The UI sends indices or a rectangle. CPU loops or a GPU edit kernel update those racks.")
qa(8, "Why can the backends agree?", "They use the same equation, old/new arrays, and a hash based on rack index and step.")
qa(9, "What is shared-memory tiling?", "A CUDA block caches a 16 x 16 region plus a one-cell halo before updating its racks.")
qa(10, "What does the benchmark verify?", "It checks final maximum temperature against CPU within 0.001 C. Speedup is CPU time divided by backend time.")
finish_page()

assert page == 8, page
c.save()
print(OUT)
