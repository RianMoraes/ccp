from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from pathlib import Path
from app.database import init_db
from app.routes import auth, clientes, equipamentos, componentes, pendencias, export, busca, usuarios, modelos_fluxo, folhas_id, pendencias_desenhos
from sqlmodel import Session, select
from app.database import get_session
from app.models import (
    Componente, Equipamento, Etapa, StatusComponenteEnum,
    StatusEquipamentoEnum, StatusPendenciaEnum, Pendencia, StatusEtapaEnum
)
from datetime import date, datetime, timedelta
from typing import List

app = FastAPI(
    title="CCP Industrial API",
    description="API de Gestão e Acompanhamento do Centro de Controle de Produção",
    version="1.0.0"
)

# Configuração de CORS para permitir acesso local do Frontend estático
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, restringir para os domínios do front
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicialização das tabelas no SQLite
@app.on_event("startup")
def startup_event():
    init_db()

# Registro de Rotas da API
app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(equipamentos.router)
app.include_router(componentes.router)
app.include_router(pendencias.router)
app.include_router(export.router)
app.include_router(busca.router)
app.include_router(usuarios.router)
app.include_router(modelos_fluxo.router)
app.include_router(folhas_id.router)
app.include_router(pendencias_desenhos.router)

# Servir o Frontend estático (pasta frontend/ ao lado da pasta backend/)
# Acessível em http://localhost:8000/app/...
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

# Rotas do Dashboard e KPIs Gerais
@app.get("/api/dashboard/resumo", tags=["Dashboard"])
def obter_resumo_dashboard(session: Session = Depends(get_session)):
    """Retorna KPIs gerais (RF-02) do dashboard."""
    # 1. Equipamentos em atraso (prazo expirado e não concluído)
    atrasados_query = select(Equipamento).where(
        Equipamento.ativo == True,
        Equipamento.status.in_([
            StatusEquipamentoEnum.EM_PRODUCAO,
            StatusEquipamentoEnum.CARREGADO_COM_PENDENCIA,
        ]),
        Equipamento.data_entrega < date.today()
    )
    atrasados = len(session.exec(atrasados_query).all())
    
    # 2. Bloqueios ativos (pendências abertas bloqueantes)
    bloqueios_query = select(Pendencia).where(
        Pendencia.status == StatusPendenciaEnum.ABERTA,
        Pendencia.bloqueante == True
    )
    bloqueios = len(session.exec(bloqueios_query).all())
    
    # 3. Entregas da semana (equipamentos com data de entrega nos próximos 7 dias)
    hoje = date.today()
    fim_semana = hoje + timedelta(days=7)
    entregas_semana = len(session.exec(
        select(Equipamento).where(
            Equipamento.ativo == True,
            Equipamento.data_entrega >= hoje,
            Equipamento.data_entrega <= fim_semana
        )
    ).all())
    
    return {
        "equipamentos_atraso": atrasados,
        "bloqueios_ativos": bloqueios,
        "entregas_semana": entregas_semana
    }

@app.get("/api/dashboard/prioridade-dia", tags=["Dashboard"])
def obter_prioridade_dia(session: Session = Depends(get_session)):
    hoje = date.today()
    limite_prioridade = hoje + timedelta(days=7)

    """Retorna as prioridades do dia (RF-01) - equipamentos com prazo mais próximo."""
    prioritarios = session.exec(
        select(Equipamento).where(
            Equipamento.ativo == True,
            Equipamento.status.in_([
                StatusEquipamentoEnum.EM_PRODUCAO,
                StatusEquipamentoEnum.CARREGADO_COM_PENDENCIA,
            ]),
            Equipamento.data_entrega != None,
            Equipamento.data_entrega <= limite_prioridade,
        ).order_by(Equipamento.data_entrega).limit(5)
    ).all()

    if not prioritarios:
        return []

    resultado = []
    for prioritario in prioritarios:
        componentes = session.exec(
            select(Componente).where(Componente.equipamento_id == prioritario.id, Componente.ativo == True)
        ).all()

        bloqueio_critico = "Nenhuma pendência ativa"
        possui_bloqueio = False
        for c in componentes:
            if c.status == StatusComponenteEnum.BLOQUEADO:
                possui_bloqueio = True
                bloqueio_critico = c.observacoes or "Componente paralisado por pendência"
                break

        dias_restantes = 0
        if prioritario.data_entrega:
            dias_restantes = max((prioritario.data_entrega - hoje).days, 0)

        resultado.append({
            "id": prioritario.id,
            "nome": prioritario.nome,
            "op": prioritario.op,
            "rv": prioritario.rv,
            "dias_prazo": dias_restantes,
            "bloqueio": bloqueio_critico,
            "bloqueado": possui_bloqueio
        })

    return resultado
@app.get("/api/dashboard/producao-por-etapa", tags=["Dashboard"])
def obter_producao_por_etapa(session: Session = Depends(get_session)):
    """Retorna totais de componentes em cada etapa de produção (RF-03), dinâmico conforme as etapas reais em uso."""
    componentes = session.exec(
        select(Componente)
        .join(Equipamento, Componente.equipamento_id == Equipamento.id)
        .where(
            Componente.ativo == True,
            Equipamento.ativo == True,
            Componente.etapa_atual_id != None
        )
    ).all()

    resumo_map = {}
    for c in componentes:
        etapa_real = session.get(Etapa, c.etapa_atual_id)
        if not etapa_real:
            continue

        nome = etapa_real.nome
        if nome not in resumo_map:
            resumo_map[nome] = {"etapa": nome, "total": 0, "criticos": 0, "_ordem": etapa_real.ordem}

        resumo_map[nome]["total"] += 1
        if c.prioridade in ["alta", "urgente", "critica"] or c.status == StatusComponenteEnum.BLOQUEADO:
            resumo_map[nome]["criticos"] += 1

    resumo = sorted(resumo_map.values(), key=lambda x: x["_ordem"])
    for item in resumo:
        item.pop("_ordem")
    return resumo
@app.get("/", tags=["Geral"], include_in_schema=False)
def index():
    """Redireciona para a tela de login do frontend."""
    return RedirectResponse(url="/app/login.html")
