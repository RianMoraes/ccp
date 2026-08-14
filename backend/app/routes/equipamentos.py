from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from sqlmodel import Session, select, SQLModel
from app.database import get_session
from app.models import (
    Equipamento, Componente, Usuario, StatusEquipamentoEnum, StatusComponenteEnum,
    Etapa, RevisaoDesenho, StatusRevisaoDesenhoEnum,
)
from app.routes.auth import obter_usuario_atual, exigir_operacao
from datetime import datetime, date

router = APIRouter(prefix="/api/equipamentos", tags=["Equipamentos"])

def _resolver_etapa_atual(session: Session, etapa_atual_id: Optional[str]) -> Optional[dict]:
    """Resolve o id da etapa atual do componente para {id, nome, ordem}."""
    if not etapa_atual_id:
        return None
    etapa = session.get(Etapa, etapa_atual_id)
    if not etapa:
        return None
    return {"id": etapa.id, "nome": etapa.nome, "ordem": etapa.ordem}

def _contar_desenhos_em_revisao(session: Session, componente_id: str) -> int:
    return len(session.exec(select(RevisaoDesenho).where(
        RevisaoDesenho.componente_id == componente_id,
        RevisaoDesenho.status == StatusRevisaoDesenhoEnum.EM_REVISAO,
    )).all())

# Schemas de input desacoplados do modelo de tabela
class EquipamentoCreate(SQLModel):
    cliente_id: str
    nome: str
    codigo: Optional[str] = None
    descricao: Optional[str] = None
    op: Optional[str] = None
    rv: Optional[str] = None
    data_inicio: Optional[date] = None
    data_entrega: Optional[date] = None

class EquipamentoUpdate(SQLModel):
    nome: str
    codigo: Optional[str] = None
    descricao: Optional[str] = None
    op: Optional[str] = None
    rv: Optional[str] = None
    data_inicio: Optional[date] = None
    data_entrega: Optional[date] = None
    status: Optional[str] = None

@router.get("")
def listar_equipamentos(
    cliente_id: Optional[str] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    query = select(Equipamento).where(Equipamento.ativo == True)
    if cliente_id:
        query = query.where(Equipamento.cliente_id == cliente_id)
    if status:
        query = query.where(Equipamento.status == status)
        
    equipamentos = session.exec(query).all()
    
    # Calcular percentual geral agregado e criticidade por equipamento para retorno enriquecido
    result = []
    for eq in equipamentos:
        componentes = session.exec(select(Componente).where(Componente.equipamento_id == eq.id, Componente.ativo == True)).all()
        
        # Calcular percentual agregado (d-04)
        pct_agregado = 0.0
        possui_bloqueio = any(c.status == StatusComponenteEnum.BLOQUEADO for c in componentes)
        if componentes:
            pct_agregado = sum(c.percentual for c in componentes) / len(componentes)
            

        # Determinar a criticidade baseada no prazo (d-06)
        criticidade = "normal"
        if eq.status == StatusEquipamentoEnum.CARREGADO:
            criticidade = "carregado"
        elif eq.status == StatusEquipamentoEnum.CARREGADO_COM_PENDENCIA:
            criticidade = "pendencia_pos_carregamento"
        elif eq.data_entrega:
            dias_restantes = (eq.data_entrega - date.today()).days
            if dias_restantes <= 5:
                criticidade = "critico"
            elif dias_restantes <= 15:
                criticidade = "alerta"

        # Equipamento 100% concluído: status e criticidade exibidos como "carregado"
        status_exibicao = eq.status
        if (
            componentes
            and pct_agregado >= 100
            and eq.status != StatusEquipamentoEnum.CARREGADO_COM_PENDENCIA
        ):
            status_exibicao = "carregado"
            criticidade = "carregado"

        result.append({
            "possui_bloqueio": possui_bloqueio,
            "id": eq.id,
            "cliente_id": eq.cliente_id,
            "cliente_nome": eq.cliente.nome if eq.cliente else "",
            "nome": eq.nome,
            "codigo": eq.codigo,
            "op": eq.op,
            "rv": eq.rv,
            "descricao": eq.descricao,
            "data_inicio": eq.data_inicio,
            "data_entrega": eq.data_entrega,
            "status": status_exibicao,
            "percentual_geral": round(pct_agregado, 1),
            "criticidade": criticidade,
            "total_componentes": len(componentes)
        })
    return result

@router.get("/{equipamento_id}")
def obter_equipamento(
    equipamento_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    eq = session.get(Equipamento, equipamento_id)
    if not eq or not eq.ativo:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
        
    componentes = session.exec(select(Componente).where(Componente.equipamento_id == eq.id, Componente.ativo == True)).all()
    
    pct_agregado = 0.0
    if componentes:
        pct_agregado = sum(c.percentual for c in componentes) / len(componentes)
        
    # Indentação corrigida no bloco abaixo:
    criticidade = "normal"
    if eq.status == StatusEquipamentoEnum.CARREGADO:
        criticidade = "carregado"
    elif eq.status == StatusEquipamentoEnum.CARREGADO_COM_PENDENCIA:
        criticidade = "pendencia_pos_carregamento"
    elif eq.data_entrega:
        dias_restantes = (eq.data_entrega - date.today()).days
        if dias_restantes <= 5:
            criticidade = "critico"
        elif dias_restantes <= 15:
            criticidade = "alerta"

    return {
        "id": eq.id,
        "cliente_id": eq.cliente_id,
        "cliente_nome": eq.cliente.nome if eq.cliente else "",
        "nome": eq.nome,
        "codigo": eq.codigo,
        "op": eq.op,
        "rv": eq.rv,
        "descricao": eq.descricao,
        "data_inicio": eq.data_inicio,
        "data_entrega": eq.data_entrega,
        "status": eq.status,
        "percentual_geral": round(pct_agregado, 1),
        "criticidade": criticidade,
        "componentes": [
            {
                "id": c.id,
                "nome": c.nome,
                "prioridade": c.prioridade,
                "status": c.status,
                "percentual": c.percentual,
                "responsavel": c.responsavel,
                "data_prevista": c.data_prevista,
                "observacoes": c.observacoes,
                "desenhos_em_revisao": _contar_desenhos_em_revisao(session, c.id),
                "etapa_atual": _resolver_etapa_atual(session, c.etapa_atual_id)
            }
            for c in componentes
        ]
    }

@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(exigir_operacao)])
def criar_equipamento(
    dados: EquipamentoCreate,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    from app.models import Cliente
    cliente = session.get(Cliente, dados.cliente_id)
    if not cliente or not cliente.ativo:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    eq = Equipamento(
        cliente_id=dados.cliente_id,
        nome=dados.nome,
        codigo=dados.codigo,
        descricao=dados.descricao,
        op=dados.op,
        rv=dados.rv,
        data_inicio=dados.data_inicio,
        data_entrega=dados.data_entrega,
    )
    session.add(eq)
    session.commit()
    session.refresh(eq)
    return {"id": eq.id, "nome": eq.nome, "op": eq.op, "rv": eq.rv, "status": eq.status, "cliente_id": eq.cliente_id}

@router.put("/{equipamento_id}", dependencies=[Depends(exigir_operacao)])
def atualizar_equipamento(
    equipamento_id: str,
    dados: EquipamentoUpdate,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    eq = session.get(Equipamento, equipamento_id)
    if not eq or not eq.ativo:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    
    eq.nome = dados.nome
    eq.codigo = dados.codigo
    eq.descricao = dados.descricao
    eq.op = dados.op
    eq.rv = dados.rv
    eq.data_inicio = dados.data_inicio
    eq.data_entrega = dados.data_entrega
    if dados.status:
        eq.status = dados.status
    eq.atualizado_em = datetime.utcnow()
    
    session.add(eq)
    session.commit()
    session.refresh(eq)
    return {"id": eq.id, "nome": eq.nome, "op": eq.op, "rv": eq.rv, "status": eq.status, "cliente_id": eq.cliente_id}

@router.delete("/{equipamento_id}", dependencies=[Depends(exigir_operacao)])
def deletar_equipamento(
    equipamento_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    eq = session.get(Equipamento, equipamento_id)
    if not eq or not eq.ativo:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    eq.ativo = False
    eq.atualizado_em = datetime.utcnow()
    session.add(eq)

    # Cascata: desativa também os componentes vinculados (evita órfãos ativos)
    componentes = session.exec(
        select(Componente).where(Componente.equipamento_id == eq.id, Componente.ativo == True)
    ).all()
    for c in componentes:
        c.ativo = False
        c.atualizado_em = datetime.utcnow()
        session.add(c)

    session.commit()
    return {"message": f"Equipamento e {len(componentes)} componente(s) vinculado(s) deletados com sucesso (soft delete)"}

@router.patch("/{equipamento_id}/prazo", dependencies=[Depends(exigir_operacao)])
def atualizar_prazo_equipamento(
    equipamento_id: str,
    nova_data: date,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Atualiza apenas a data de entrega (prazo) do equipamento."""
    eq = session.get(Equipamento, equipamento_id)
    if not eq or not eq.ativo:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")
    
    eq.data_entrega = nova_data
    eq.atualizado_em = datetime.utcnow()
    
    session.add(eq)
    session.commit()
    session.refresh(eq)
    return {"id": eq.id, "data_entrega": eq.data_entrega, "message": "Prazo atualizado com sucesso"}

@router.patch("/{equipamento_id}/inicio", dependencies=[Depends(exigir_operacao)])
def atualizar_inicio_equipamento(
    equipamento_id: str,
    nova_data: date,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Atualiza o mês planejado de início, armazenado no primeiro dia do mês."""
    eq = session.get(Equipamento, equipamento_id)
    if not eq or not eq.ativo:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    eq.data_inicio = nova_data.replace(day=1)
    eq.atualizado_em = datetime.utcnow()
    session.add(eq)
    session.commit()
    session.refresh(eq)
    return {"id": eq.id, "data_inicio": eq.data_inicio, "message": "Mês de início atualizado com sucesso"}
