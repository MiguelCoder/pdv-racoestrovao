from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
import sqlite3
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = FastAPI()
templates = Jinja2Templates(directory="templates")
DB = "caixa.db"
from fastapi.middleware.cors import CORSMiddleware

@app.middleware("http")
async def ngrok_skip_browser_warning(request: Request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response


# ---------- BANCO ----------
def get_db():
    return sqlite3.connect(DB)


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto TEXT,
            valor REAL,
            pagamento TEXT,
            nota_dada REAL,
            troco REAL,
            data TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT,
            valor REAL,
            data TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------- HOME ----------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    hoje = datetime.now().strftime("%d/%m/%Y")

    conn = get_db()
    c = conn.cursor()

    vendas = c.execute("""
        SELECT * FROM vendas
        WHERE data LIKE ?
        ORDER BY id DESC
    """, (f"{hoje}%",)).fetchall()

    gastos = c.execute("""
        SELECT * FROM gastos
        WHERE data LIKE ?
        ORDER BY id DESC
    """, (f"{hoje}%",)).fetchall()

    conn.close()

    total = sum(v[2] for v in vendas)
    pix = sum(v[2] for v in vendas if v[3] == "pix")
    maquina = sum(v[2] for v in vendas if v[3] == "maquina")
    dinheiro = sum(v[2] for v in vendas if v[3] == "dinheiro")
    total_gastos = sum(g[2] for g in gastos)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "vendas": vendas,
        "gastos": gastos,
        "total": total,
        "pix": pix,
        "maquina": maquina,
        "dinheiro": dinheiro,
        "total_gastos": total_gastos,
        "data": hoje
    })


# ---------- NOVA VENDA ----------
@app.post("/venda")
def nova_venda(
    produto: str = Form(...),
    valor: float = Form(...),
    pagamento: str = Form(...),
    nota_dada: float = Form(0)
):
    troco = 0
    if pagamento == "dinheiro":
        troco = round(nota_dada - valor, 2)

    data = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO vendas (produto, valor, pagamento, nota_dada, troco, data)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (produto, valor, pagamento, nota_dada, troco, data))

    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)


# ---------- NOVO GASTO ----------
@app.post("/gasto")
def novo_gasto(
    descricao: str = Form(...),
    valor: float = Form(...)
):
    data = datetime.now().strftime("%d/%m/%Y %H:%M")

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO gastos (descricao, valor, data)
        VALUES (?, ?, ?)
    """, (descricao, valor, data))

    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)


# ---------- DELETAR ----------
@app.get("/deletar/venda/{id}")
def deletar_venda(id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM vendas WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=303)


@app.get("/deletar/gasto/{id}")
def deletar_gasto(id: int):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM gastos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=303)


# ---------- EDITAR ----------
@app.get("/editar/venda/{id}", response_class=HTMLResponse)
def editar_venda(request: Request, id: int):
    conn = get_db()
    c = conn.cursor()
    venda = c.execute(
        "SELECT * FROM vendas WHERE id = ?",
        (id,)
    ).fetchone()
    conn.close()

    return templates.TemplateResponse("editar.html", {
        "request": request,
        "venda": venda
    })


@app.post("/editar/venda/{id}")
def salvar_edicao(
    id: int,
    produto: str = Form(...),
    valor: float = Form(...),
    pagamento: str = Form(...),
    nota_dada: float = Form(0)
):
    troco = 0
    if pagamento == "dinheiro":
        troco = round(nota_dada - valor, 2)

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE vendas
        SET produto=?, valor=?, pagamento=?, nota_dada=?, troco=?
        WHERE id=?
    """, (produto, valor, pagamento, nota_dada, troco, id))

    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)


# ---------- PDF ----------
@app.get("/pdf")
def gerar_pdf():
    hoje = datetime.now().strftime("%d/%m/%Y")
    arquivo = f"fechamento_{hoje.replace('/', '-')}.pdf"

    conn = get_db()
    c = conn.cursor()

    vendas = c.execute("""
        SELECT produto, valor, pagamento, troco
        FROM vendas
        WHERE data LIKE ?
    """, (f"{hoje}%",)).fetchall()

    gastos = c.execute("""
        SELECT descricao, valor
        FROM gastos
        WHERE data LIKE ?
    """, (f"{hoje}%",)).fetchall()

    conn.close()

    total = sum(v[1] for v in vendas)
    pix = sum(v[1] for v in vendas if v[2] == "pix")
    maquina = sum(v[1] for v in vendas if v[2] == "maquina")
    dinheiro = sum(v[1] for v in vendas if v[2] == "dinheiro")
    total_gastos = sum(g[1] for g in gastos)

    pdf = canvas.Canvas(arquivo, pagesize=A4)
    y = 800

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "FECHAMENTO DE CAIXA - Rações Trovão")
    y -= 25

    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, y, f"Data: {hoje}")
    y -= 30

    for v in vendas:
        pdf.drawString(
            50, y,
            f"{v[0]} | R$ {v[1]:.2f} | {v[2]} | Troco: R$ {v[3]:.2f}"
        )
        y -= 15

    y -= 20

    y -= 15

    pdf.setFont("Helvetica", 11)
    for g in gastos:
        pdf.drawString(50, y, f"{g[0]} - R$ {g[1]:.2f}")
        y -= 14

    y -= 20
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, f"TOTAL: R$ {total:.2f}")
    y -= 14
    pdf.drawString(50, y, f"PIX: R$ {pix:.2f}")
    y -= 14
    pdf.drawString(50, y, f"MÁQUINA: R$ {maquina:.2f}")
    y -= 14
    pdf.drawString(50, y, f"DINHEIRO: R$ {dinheiro:.2f}")
    y -= 14
    pdf.drawString(50, y, f"GASTOS: R$ {total_gastos:.2f}")

    pdf.save()

    return FileResponse(arquivo, filename=arquivo)
