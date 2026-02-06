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

# ======================================================
# CONFIGURAÇÕES DE AMBIENTE
# ======================================================
ENV = os.getenv("ENV", "development")
IS_PROD = ENV == "production"

DATABASE_URL = os.getenv("postgresql://postgres:IFhlMrHSEravHSmCkgBVEaIDmKozdZIU@Postgres.railway.internal:5432/railway")
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL não definida")

SECRET_KEY = os.getenv("R4c0esTrov4o_2026_SUPER_SECRET_!@")
if not SECRET_KEY:
    raise RuntimeError("❌ SECRET_KEY não definida")

# ======================================================
# APP
# ======================================================
app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================================
# SEGURANÇA
# ======================================================
pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto"
)

serializer = URLSafeSerializer(SECRET_KEY)


def verificar_senha(senha: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha, senha_hash)


def usuario_logado(request: Request):
    cookie = request.cookies.get("session")
    if not cookie:
        return None
    try:
        return serializer.loads(cookie)
    except Exception:
        return None


# ======================================================
# BANCO DE DADOS
# ======================================================
def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require"
    )


# ======================================================
# LOGIN
# ======================================================
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT password FROM usuarios WHERE username = %s",
        (username,)
    )
    user = cur.fetchone()

    cur.close()
    conn.close()

    if not user or not verificar_senha(password, user[0]):
        return RedirectResponse("/login", status_code=303)

    response = RedirectResponse("/", status_code=303)

    response.set_cookie(
        key="session",
        value=serializer.dumps(username),
        httponly=True,
        secure=IS_PROD,        # 🔐 true em produção
        samesite="lax",
        path="/",
        max_age=60 * 60 * 8    # 8 horas
    )

    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session", path="/")
    return response


# ======================================================
# HOME
# ======================================================
@app.get("/", response_class=HTMLResponse)
def index(request: Request, data: str | None = None):
    if not usuario_logado(request):
        return RedirectResponse("/login", status_code=303)

    data_filtro = data or date.today().isoformat()

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM vendas
        WHERE data::date = %s
        ORDER BY id DESC
    """, (data_filtro,))
    vendas = cur.fetchall()

    cur.execute("""
        SELECT * FROM gastos
        WHERE data::date = %s
        ORDER BY id DESC
    """, (data_filtro,))
    gastos = cur.fetchall()

    cur.close()
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


# ======================================================
# VENDAS
# ======================================================
@app.post("/venda")
def nova_venda(
    produto: str = Form(...),
    valor: float = Form(...),
    pagamento: str = Form(...),
    nota_dada: float = Form(0)
):
    troco = round(nota_dada - valor, 2) if pagamento == "dinheiro" else 0

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO vendas (produto, valor, pagamento, nota_dada, troco, data)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (produto, valor, pagamento, nota_dada, troco, datetime.now()))

    conn.commit()
    cur.close()
    conn.close()

    return RedirectResponse("/", status_code=303)


# ======================================================
# GASTOS
# ======================================================
@app.post("/gasto")
def novo_gasto(descricao: str = Form(...), valor: float = Form(...)):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO gastos (descricao, valor, data)
        VALUES (%s, %s, %s)
    """, (descricao, valor, datetime.now()))

    conn.commit()
    cur.close()
    conn.close()

    return RedirectResponse("/", status_code=303)


# ======================================================
# PDF
# ======================================================
@app.get("/pdf")
def gerar_pdf(data: str | None = None):
    data_filtro = data or date.today().isoformat()
    arquivo = f"fechamento_{data_filtro}.pdf"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT produto, valor, pagamento, troco
        FROM vendas
        WHERE data::date = %s
    """, (data_filtro,))
    vendas = cur.fetchall()

    cur.execute("""
        SELECT descricao, valor
        FROM gastos
        WHERE data::date = %s
    """, (data_filtro,))
    gastos = cur.fetchall()

    cur.close()
    conn.close()

    pdf = canvas.Canvas(arquivo, pagesize=A4)
    y = 800

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "FECHAMENTO DE CAIXA - Rações Trovão")
    y -= 30

    pdf.setFont("Helvetica", 11)
    for v in vendas:
        pdf.drawString(50, y, f"{v[0]} | R$ {v[1]:.2f} | {v[2]}")
        y -= 15

    y -= 20
    for g in gastos:
        pdf.drawString(50, y, f"{g[0]} - R$ {g[1]:.2f}")
        y -= 14

    pdf.save()
    return FileResponse(arquivo, filename=arquivo)
