from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from app.database import get_session
from app.models import Cliente, Equipamento, Componente, Usuario
from app.routes.auth import obter_usuario_atual
from typing import List

router = APIRouter(prefix="/api/busca", tags=["Busca Global"])

@router.get("")
def realizar_busca(
    q: str = Query(..., min_length=2, description="Termo de pesquisa"),
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Realiza busca global (RF-07) por termo em Clientes, Equipamentos, Componentes e OPs."""
    termo = f"%{q}%"
    
    # 1. Clientes
    clientes = session.exec(
        select(Cliente).where(Cliente.ativo == True, Cliente.nome.like(termo) | Cliente.sigla.like(termo))
    ).all()
    
    # 2. Equipamentos (busca no nome, código ou OP)
    equipamentos = session.exec(
        select(Equipamento).where(
            Equipamento.ativo == True,
            Equipamento.nome.like(termo) | Equipamento.codigo.like(termo) | Equipamento.op.like(termo)
        )
    ).all()
    
    # 3. Componentes
    componentes = session.exec(
        select(Componente).where(Componente.ativo == True, Componente.nome.like(termo))
    ).all()
    
    return {
        "termo": q,
        "resultados": {
            "clientes": [
                {"id": c.id, "nome": c.nome, "sigla": c.sigla} for c in clientes
            ],
            "equipamentos": [
                {"id": eq.id, "nome": eq.nome, "op": eq.op, "codigo": eq.codigo} for eq in equipamentos
            ],
            "componentes": [
                {
                    "id": comp.id,
                    "nome": comp.nome,
                    "equipamento_id": comp.equipamento_id,
                    "equipamento_nome": comp.equipamento.nome if comp.equipamento else ""
                } for comp in componentes
            ]
        }
    }
