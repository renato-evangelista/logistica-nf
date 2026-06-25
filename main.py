from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional
from database import init_db, salvar_nota, cancelar_nota, listar_notas, relatorio_por_periodo, relatorio_cancelamentos
from contextlib import asynccontextmanager


# ─────────────────────────────────────────────
# MODELO DO WEBHOOK
# Diz ao FastAPI o formato esperado do payload
# Isso faz o campo "Request body" aparecer no /docs
# ─────────────────────────────────────────────

class WebhookOmie(BaseModel):
    topic: Optional[str] = None
    nfe: Optional[Dict[str, Any]] = None
    chave_nfe: Optional[str] = None
    chave: Optional[str] = None
    motivo_cancelamento: Optional[str] = None
    motivo: Optional[str] = None

    class Config:
        extra = "allow"  # permite campos extras que o Omie possa enviar


@asynccontextmanager
async def lifespan(app):
    """Inicializa o banco quando o servidor sobe."""
    init_db()
    yield


app = FastAPI(
    title="Controle Logístico de NFs",
    description="Recebe webhooks do Omie e armazena notas fiscais para controle logístico.",
    version="1.0.0",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────
# WEBHOOK — recebe eventos do Omie
# ─────────────────────────────────────────────

@app.post("/webhook/omie")
async def receber_webhook(payload: WebhookOmie):
    """
    Endpoint que o Omie chama automaticamente ao emitir ou cancelar uma NF.
    Configure no Omie: Configurações → Integrações → Webhooks
    """
    # Ping de teste do Omie — só confirma que o servidor está no ar
    if payload.topic is None or payload.topic == "":
        return {"status": "ok", "acao": "ping_recebido"}

    evento = payload.topic

    import json
    print("=" * 60)
    print(json.dumps(payload.model_dump(), indent=2, ensure_ascii=False))
    print("=" * 60)

    # ── NFe.NotaAutorizada ───────────────────────
    # Disparado quando a NF é emitida e autorizada pela SEFAZ
    if evento == "NFe.NotaAutorizada":
        nf = payload.nfe or payload.model_dump()
        salvar_nota(nf)
        return {"status": "ok", "acao": "nota_salva"}

    # ── NFe.NotaCancelada ────────────────────────
    # Disparado quando a NF é cancelada no Omie
    elif evento == "NFe.NotaCancelada":
        chave  = payload.chave_nfe or payload.chave
        motivo = payload.motivo_cancelamento or payload.motivo or "Não informado"
        cancelar_nota(chave, motivo)
        return {"status": "ok", "acao": "nota_cancelada"}

    # ── Evento não tratado ──────────────────────
    # Omie pode disparar outros eventos — apenas loga e ignora
    else:
        print(f"⚠️  Evento não tratado: '{evento}' | payload: {payload}")
        return {"status": "ignorado", "evento": evento}


# ─────────────────────────────────────────────
# ROTAS DE CONSULTA
# ─────────────────────────────────────────────

@app.get("/notas")
def get_notas(
    status: str = None,
    data_inicio: str = None,
    data_fim: str = None,
):
    """
    Lista notas fiscais com filtros opcionais.
    Exemplos:
      GET /notas
      GET /notas?status=emitida
      GET /notas?status=cancelada&data_inicio=2024-01-01&data_fim=2024-12-31
    """
    notas = listar_notas(status=status, data_inicio=data_inicio, data_fim=data_fim)
    return {"total": len(notas), "notas": notas}


@app.get("/relatorio/periodo")
def get_relatorio(data_inicio: str, data_fim: str):
    """
    Resumo de faturamento por cliente no período (exclui canceladas).
    Exemplo: GET /relatorio/periodo?data_inicio=2024-01-01&data_fim=2024-12-31
    """
    dados = relatorio_por_periodo(data_inicio, data_fim)
    return {"periodo": {"inicio": data_inicio, "fim": data_fim}, "clientes": dados}


@app.get("/relatorio/cancelamentos")
def get_cancelamentos(data_inicio: str, data_fim: str):
    """
    Resumo de cancelamentos no período.
    Exemplo: GET /relatorio/cancelamentos?data_inicio=2024-01-01&data_fim=2024-12-31
    """
    dados = relatorio_cancelamentos(data_inicio, data_fim)
    return {"periodo": {"inicio": data_inicio, "fim": data_fim}, "cancelamentos": dados}


@app.get("/health")
def health():
    """Verificação rápida se o servidor está no ar."""
    return {"status": "ok"}
