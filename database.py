import os
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL", "postgresql://postgres:senha@localhost/logistica_db"))


def init_db():
    """Cria as tabelas se não existirem."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS notas_fiscais (
                id                   SERIAL PRIMARY KEY,
                numero_nf            TEXT UNIQUE,
                chave_nfe            TEXT UNIQUE,
                data_emissao         DATE,
                cliente              TEXT,
                cnpj_cliente         TEXT,
                valor_total          NUMERIC(12,2),
                status               TEXT DEFAULT 'emitida',
                data_cancelamento    TIMESTAMP,
                motivo_cancelamento  TEXT,
                criado_em            TIMESTAMP DEFAULT NOW(),
                atualizado_em        TIMESTAMP DEFAULT NOW()
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS itens_nf (
                id              SERIAL PRIMARY KEY,
                nf_id           INT REFERENCES notas_fiscais(id) ON DELETE CASCADE,
                codigo_produto  TEXT,
                descricao       TEXT,
                quantidade      NUMERIC(10,3),
                valor_unitario  NUMERIC(12,2),
                valor_total     NUMERIC(12,2)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fila_cancelamentos (
                id           SERIAL PRIMARY KEY,
                chave_nfe    TEXT UNIQUE,
                motivo       TEXT,
                recebido_em  TIMESTAMP DEFAULT NOW()
            )
        """))

        # Índices para relatórios rápidos
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_nf_data     ON notas_fiscais(data_emissao)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_nf_cliente  ON notas_fiscais(cnpj_cliente)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_nf_status   ON notas_fiscais(status)"))

        conn.commit()
        print("✅ Banco de dados inicializado com sucesso.")


def salvar_nota(nf: dict):
    """Insere ou atualiza uma nota fiscal no banco."""
    with engine.connect() as conn:
        resultado = conn.execute(text("""
            INSERT INTO notas_fiscais
                (numero_nf, chave_nfe, data_emissao, cliente, cnpj_cliente, valor_total, status)
            VALUES
                (:numero, :chave, :data, :cliente, :cnpj, :valor, 'emitida')
            ON CONFLICT (numero_nf) DO UPDATE SET
                status        = EXCLUDED.status,
                atualizado_em = NOW()
            RETURNING id
        """), {
            "numero": nf.get("numero_nf") or nf.get("numero"),
            "chave":  nf.get("chave_nfe"),
            "data":   nf.get("data_emissao"),
            "cliente": nf.get("nome_cliente") or nf.get("cliente"),
            "cnpj":   nf.get("cnpj_cpf_cliente") or nf.get("cnpj"),
            "valor":  nf.get("valor_total_nf") or nf.get("valor_total"),
        })

        nf_id = resultado.fetchone()[0]

        # Salva os itens da nota, se vierem no payload
        itens = nf.get("itens") or nf.get("produtos") or []
        for item in itens:
            conn.execute(text("""
                INSERT INTO itens_nf (nf_id, codigo_produto, descricao, quantidade, valor_unitario, valor_total)
                VALUES (:nf_id, :codigo, :descricao, :qtd, :v_unit, :v_total)
            """), {
                "nf_id":     nf_id,
                "codigo":    item.get("codigo_produto"),
                "descricao": item.get("descricao") or item.get("nome"),
                "qtd":       item.get("quantidade"),
                "v_unit":    item.get("valor_unitario"),
                "v_total":   item.get("valor_total"),
            })

        conn.commit()
        print(f"✅ Nota {nf.get('numero_nf')} salva (id={nf_id})")
        return nf_id


def cancelar_nota(chave: str, motivo: str):
    """Marca a NF como cancelada. Nunca deleta — mantém histórico fiscal."""
    with engine.connect() as conn:
        resultado = conn.execute(text("""
            UPDATE notas_fiscais
            SET
                status              = 'cancelada',
                motivo_cancelamento = :motivo,
                data_cancelamento   = :data_cancelamento,
                atualizado_em       = NOW()
            WHERE chave_nfe = :chave
            RETURNING id, numero_nf
        """), {
            "chave":             chave,
            "motivo":            motivo,
            "data_cancelamento": datetime.now(),
        })

        nota = resultado.fetchone()

        if not nota:
            # Webhook de cancelamento chegou antes do de emissão (raro mas possível)
            conn.execute(text("""
                INSERT INTO fila_cancelamentos (chave_nfe, motivo, recebido_em)
                VALUES (:chave, :motivo, NOW())
                ON CONFLICT (chave_nfe) DO NOTHING
            """), {"chave": chave, "motivo": motivo})
            print(f"⚠️  Cancelamento enfileirado (NF ainda não recebida): chave={chave}")
        else:
            print(f"🚫 Nota {nota[1]} cancelada (id={nota[0]})")

        conn.commit()
        return nota


def listar_notas(status: str = None, data_inicio: str = None, data_fim: str = None):
    """Lista notas com filtros opcionais."""
    filtros = []
    params = {}

    if status:
        filtros.append("status = :status")
        params["status"] = status
    if data_inicio:
        filtros.append("data_emissao >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim:
        filtros.append("data_emissao <= :data_fim")
        params["data_fim"] = data_fim

    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""

    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id, numero_nf, data_emissao, cliente, cnpj_cliente,
                   valor_total, status, data_cancelamento, motivo_cancelamento
            FROM notas_fiscais
            {where}
            ORDER BY data_emissao DESC
        """), params).fetchall()

    return [dict(r._mapping) for r in rows]


def relatorio_por_periodo(data_inicio: str, data_fim: str):
    """Resumo por cliente no período, excluindo canceladas."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                cliente,
                cnpj_cliente,
                COUNT(*)                                            AS total_nfs,
                SUM(valor_total)                                    AS valor_total,
                COUNT(*) FILTER (WHERE status = 'entregue')        AS entregues,
                COUNT(*) FILTER (WHERE status = 'em_transito')     AS em_transito,
                COUNT(*) FILTER (WHERE status = 'emitida')         AS emitidas
            FROM notas_fiscais
            WHERE
                status != 'cancelada'
                AND data_emissao BETWEEN :inicio AND :fim
            GROUP BY cliente, cnpj_cliente
            ORDER BY valor_total DESC
        """), {"inicio": data_inicio, "fim": data_fim}).fetchall()

    return [dict(r._mapping) for r in rows]


def relatorio_cancelamentos(data_inicio: str, data_fim: str):
    """Resumo de cancelamentos no período."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                cliente,
                COUNT(*)                AS total_canceladas,
                SUM(valor_total)        AS valor_cancelado,
                motivo_cancelamento
            FROM notas_fiscais
            WHERE
                status = 'cancelada'
                AND data_cancelamento BETWEEN :inicio AND :fim
            GROUP BY cliente, motivo_cancelamento
            ORDER BY valor_cancelado DESC
        """), {"inicio": data_inicio, "fim": data_fim}).fetchall()

    return [dict(r._mapping) for r in rows]
