from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer
from datetime import datetime, date
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import psycopg2
import os

# ---------------- APP ----------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- SEGURANÇA ----------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
serializer = URLSafeSerializer(os.getenv("SECRET_KEY", "chave-super-secreta"))

def hash_senha(senha):
    return pwd_context.hash(senha)

def verificar_senha(senha, senha_hash):
    return pwd_context.verify(senha, senha_hash)

def usuario_logado(request: Request):
    cookie = request.cookies.get("session")
    if not cookie:
        return None
    try:
        return serializer.loads(cookie)
    except:
        return None

# ---------------- BANCO ----------------
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

# ---------------- LOGIN ----------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT password FROM usuarios WHERE username=%s", (username,))
    user = c.fetchone()
    conn.close()

    if not user or not verificar_senha(password, user[0]):
        return RedirectResponse("/login", status_code=303)

    response = RedirectResponse("/", status_code=303)
    response.set_cookie("session", serializer.dumps(username), httponly=True)
    return response

@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response

# ---------------- HOME ----------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request, data: str | None = None):
    if not usuario_logado(request):
        return RedirectResponse("/login")

    data_filtro = data or date.today().isoformat()

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT * FROM vendas
        WHERE data::date = %s
        ORDER BY id DESC
    """, (data_filtro,))
    vendas = c.fetchall()

    c.execute("""
        SELECT * FROM gastos
        WHERE data::date = %s
        ORDER BY id DESC
    """, (data_filtro,))
    gastos = c.fetchall()

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
        "data": data_filtro
    })

# ---------------- VENDAS ----------------
@app.post("/venda")
def nova_venda(
    produto: str = Form(...),
    valor: float = Form(...),
    pagamento: str = Form(...),
    nota_dada: float = Form(0)
):
    data = datetime.now()

    troco = round(nota_dada - valor, 2) if pagamento == "dinheiro" else 0

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO vendas (produto, valor, pagamento, nota_dada, troco, data)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (produto, valor, pagamento, nota_dada, troco, data))
    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)

# ---------------- GASTOS ----------------
@app.post("/gasto")
def novo_gasto(descricao: str = Form(...), valor: float = Form(...)):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO gastos (descricao, valor, data)
        VALUES (%s, %s, %s)
    """, (descricao, valor, datetime.now()))
    conn.commit()
    conn.close()

    return RedirectResponse("/", status_code=303)

# ---------------- PDF ----------------
@app.get("/pdf")
def gerar_pdf(data: str | None = None):
    data_filtro = data or date.today().isoformat()
    arquivo = f"fechamento_{data_filtro}.pdf"

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT produto, valor, pagamento, troco
        FROM vendas
        WHERE data::date = %s
    """, (data_filtro,))
    vendas = c.fetchall()

    c.execute("""
        SELECT descricao, valor
        FROM gastos
        WHERE data::date = %s
    """, (data_filtro,))
    gastos = c.fetchall()

    conn.close()

    pdf = canvas.Canvas(arquivo, pagesize=A4)
    y = 800

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "FECHAMENTO DE CAIXA - Rações Trovão")
    y -= 30

    for v in vendas:
        pdf.drawString(50, y, f"{v[0]} | R$ {v[1]:.2f} | {v[2]}")
        y -= 15

    y -= 20
    for g in gastos:
        pdf.drawString(50, y, f"{g[0]} - R$ {g[1]:.2f}")
        y -= 14

    pdf.save()
    return FileResponse(arquivo, filename=arquivo)
