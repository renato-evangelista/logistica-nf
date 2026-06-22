# 📦 Controle Logístico de Notas Fiscais

Sistema que recebe webhooks do Omie, armazena NFs no PostgreSQL e expõe endpoints para relatórios.

---

## Estrutura do projeto

```
logistica-nf/
├── main.py           # Servidor FastAPI (webhook + rotas de consulta)
├── database.py       # Conexão com o banco e todas as funções de dados
├── requirements.txt  # Dependências Python
├── .env              # Credenciais locais (nunca sobe pro GitHub)
└── .gitignore
```

---

## 1. Pré-requisitos (Windows 11)

- [Python 3.11+](https://python.org) — marcar ✅ "Add Python to PATH" na instalação
- [PostgreSQL](https://www.postgresql.org/download/windows/) — instala junto o pgAdmin
- [ngrok](https://ngrok.com) — para expor o servidor ao Omie durante o desenvolvimento

---

## 2. Instalação

Abra o PowerShell na pasta do projeto e rode:

```bash
pip install -r requirements.txt
```

---

## 3. Configurar o banco de dados

Abra o pgAdmin, crie um banco chamado `logistica_db` e edite o arquivo `.env`:

```env
DATABASE_URL=postgresql://postgres:SUA_SENHA@localhost/logistica_db
```

As tabelas são criadas automaticamente quando o servidor sobe pela primeira vez.

---

## 4. Rodar localmente

Abra **dois terminais** no PowerShell:

**Terminal 1 — servidor:**
```bash
uvicorn main:app --reload --port 8000
```

**Terminal 2 — ngrok:**
```bash
ngrok http 8000
```

O ngrok vai exibir uma URL pública tipo:
```
Forwarding   https://abc123.ngrok.io → http://localhost:8000
```

---

## 5. Configurar o Omie

No painel do Omie:
**Configurações → Integrações → Webhooks → Adicionar**

- **URL:** `https://abc123.ngrok.io/webhook/omie`
- **Eventos:** NF emitida, NF cancelada

---

## 6. Endpoints disponíveis

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/webhook/omie` | Recebe eventos do Omie |
| GET | `/notas` | Lista todas as notas |
| GET | `/notas?status=cancelada` | Filtra por status |
| GET | `/notas?data_inicio=2024-01-01&data_fim=2024-12-31` | Filtra por período |
| GET | `/relatorio/periodo?data_inicio=...&data_fim=...` | Resumo por cliente |
| GET | `/relatorio/cancelamentos?data_inicio=...&data_fim=...` | Resumo de cancelamentos |
| GET | `/health` | Verifica se o servidor está no ar |
| GET | `/docs` | Documentação interativa automática (Swagger) |

---

## 7. Status possíveis de uma NF

| Status | Significado |
|--------|-------------|
| `emitida` | NF recebida do Omie, aguardando envio |
| `em_transito` | Mercadoria a caminho do cliente |
| `entregue` | Entrega confirmada |
| `cancelada` | NF cancelada (mantida no banco para histórico fiscal) |

Para atualizar o status logístico manualmente, use o pgAdmin ou adicione um endpoint de PATCH conforme necessário.

---

## 8. Deploy em produção (Railway)

1. Suba o projeto para o GitHub (`git push`)
2. Acesse [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Adicione um banco PostgreSQL: **+ New → Database → PostgreSQL**
4. Em **Variables**, adicione: `DATABASE_URL` = (Railway preenche automaticamente)
5. O Omie passa a apontar para a URL permanente do Railway (sem ngrok)

---

## Dúvidas?

Acesse `http://localhost:8000/docs` com o servidor rodando para ver e testar todos os endpoints interativamente.
