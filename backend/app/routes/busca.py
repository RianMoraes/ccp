from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from app.database import get_session
from app.models import Cliente, Equipamento, Componente, IDTecnica, Usuario
from app.routes.auth import obter_usuario_atual
from typing import List

router = APIRouter(prefix="/api/busca", tags=["Busca Global"])

@router.get("")
def realizar_busca(
    q: str = Query(..., min_length=2, description="Termo de pesquisa"),
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Busca clientes, equipamentos, componentes, OPs e folhas de ID."""
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

    # 4. Folhas de ID. Mantém apenas a versão mais recente de cada número
    # dentro do componente para não repetir o mesmo resultado no cabeçalho.
    linhas_ids = session.exec(
        select(IDTecnica, Componente, Equipamento)
        .join(Componente, IDTecnica.componente_id == Componente.id)
        .join(Equipamento, Componente.equipamento_id == Equipamento.id)
        .where(
            Componente.ativo == True,
            Equipamento.ativo == True,
            IDTecnica.numero.like(termo),
        )
        .order_by(IDTecnica.versao.desc(), IDTecnica.criado_em.desc())
    ).all()
    ids = []
    ids_vistas = set()
    for id_tecnica, componente, equipamento in linhas_ids:
        chave = (componente.id, id_tecnica.numero)
        if chave in ids_vistas:
            continue
        ids_vistas.add(chave)
        ids.append({
            "id": id_tecnica.id,
            "numero": id_tecnica.numero,
            "versao": id_tecnica.versao,
            "status": id_tecnica.status,
            "componente_id": componente.id,
            "componente_nome": componente.nome,
            "equipamento_id": equipamento.id,
            "equipamento_nome": equipamento.nome,
        })
    
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
            ],
            "ids_tecnicas": ids,
        }
    }
