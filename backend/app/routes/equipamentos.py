from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from sqlmodel import Session, select, SQLModel
from app.database import get_session
from app.models import Equipamento, Componente, Usuario, StatusEquipamentoEnum
from app.routes.auth import obter_usuario_atual
from datetime import datetime, date

router = APIRouter(prefix="/api/equipamentos", tags=["Equipamentos"])

# Schemas de input desacoplados do modelo de tabela
class EquipamentoCreate(SQLModel):
    cliente_id: str
    nome: str
    codigo: Optional[str] = None
    descricao: Optional[str] = None
    op: Optional[str] = None
    data_inicio: Optional[date] = None
    data_entrega: Optional[date] = None

class EquipamentoUpdate(SQLModel):
    nome: str
    codigo: Optional[str] = None
    descricao: Optional[str] = None
    op: Optional[str] = None
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
        if componentes:
            pct_agregado = sum(c.percentual for c in componentes) / len(componentes)
            
        # Determinar a criticidade baseada no prazo (d-06)
        criticidade = "normal"
        if eq.data_entrega:
            dias_restantes = (eq.data_entrega - date.today()).days
            if dias_restantes <= 5:
                criticidade = "critico"
            elif dias_restantes <= 15:
                criticidade = "alerta"
                
        result.append({
            "id": eq.id,
            "cliente_id": eq.cliente_id,
            "cliente_nome": eq.cliente.nome if eq.cliente else "",
            "nome": eq.nome,
            "codigo": eq.codigo,
            "op": eq.op,
            "descricao": eq.descricao,
            "data_inicio": eq.data_inicio,
            "data_entrega": eq.data_entrega,
            "status": eq.status,
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
        
    criticidade = "normal"
    if eq.data_entrega:
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
                "etapa_atual": session.get(Componente, c.id).etapa_atual_id # O valor da etapa será resolvido dinamicamente na rota de componentes
            }
            for c in componentes
        ]
    }

@router.post("", status_code=status.HTTP_201_CREATED)
def criar_equipamento(
    dados: EquipamentoCreate,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    # Validar se cliente existe
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
        data_inicio=dados.data_inicio,
        data_entrega=dados.data_entrega,
    )
    session.add(eq)
    session.commit()
    session.refresh(eq)
    return {"id": eq.id, "nome": eq.nome, "op": eq.op, "status": eq.status, "cliente_id": eq.cliente_id}

@router.put("/{equipamento_id}")
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
    eq.data_inicio = dados.data_inicio
    eq.data_entrega = dados.data_entrega
    if dados.status:
        eq.status = dados.status
    eq.atualizado_em = datetime.utcnow()
    
    session.add(eq)
    session.commit()
    session.refresh(eq)
    return {"id": eq.id, "nome": eq.nome, "op": eq.op, "status": eq.status, "cliente_id": eq.cliente_id}

@router.delete("/{equipamento_id}")
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

    # Desativa em cascata os componentes deste equipamento, para não ficarem
    # órfãos aparecendo em listagens (Kanban, tela de Componentes, etc.)
    componentes = session.exec(
        select(Componente).where(Componente.equipamento_id == equipamento_id, Componente.ativo == True)
    ).all()
    for c in componentes:
        c.ativo = False
        c.atualizado_em = datetime.utcnow()
        session.add(c)

    session.commit()
    return {"message": "Equipamento deletado com sucesso (soft delete)"}
