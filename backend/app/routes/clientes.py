from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlmodel import Session, select
from app.database import get_session
from app.models import Cliente, Usuario
from app.routes.auth import obter_usuario_atual, exigir_operacao
from datetime import datetime

router = APIRouter(prefix="/api/clientes", tags=["Clientes"])

@router.get("", response_model=List[Cliente])
def listar_clientes(
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Retorna todos os clientes ativos cadastrados no sistema."""
    return session.exec(select(Cliente).where(Cliente.ativo == True)).all()

@router.get("/{cliente_id}", response_model=Cliente)
def obter_cliente(
    cliente_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    cliente = session.get(Cliente, cliente_id)
    if not cliente or not cliente.ativo:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente

@router.post("", response_model=Cliente, status_code=status.HTTP_201_CREATED, dependencies=[Depends(exigir_operacao)])
def criar_cliente(
    cliente: Cliente,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    # Validar sigla única
    existente = session.exec(select(Cliente).where(Cliente.sigla == cliente.sigla)).first()
    if existente:
        raise HTTPException(status_code=400, detail="Já existe um cliente cadastrado com essa sigla")
    
    session.add(cliente)
    session.commit()
    session.refresh(cliente)
    return cliente

@router.put("/{cliente_id}", response_model=Cliente, dependencies=[Depends(exigir_operacao)])
def atualizar_cliente(
    cliente_id: str,
    dados_atualizacao: Cliente,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    cliente = session.get(Cliente, cliente_id)
    if not cliente or not cliente.ativo:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    cliente.nome = dados_atualizacao.nome
    cliente.sigla = dados_atualizacao.sigla
    cliente.observacoes = dados_atualizacao.observacoes
    cliente.atualizado_em = datetime.utcnow()
    
    session.add(cliente)
    session.commit()
    session.refresh(cliente)
    return cliente

@router.delete("/{cliente_id}", dependencies=[Depends(exigir_operacao)])
def deletar_cliente(
    cliente_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    cliente = session.get(Cliente, cliente_id)
    if not cliente or not cliente.ativo:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Soft Delete (RN-027)
    cliente.ativo = False
    cliente.atualizado_em = datetime.utcnow()
    session.add(cliente)
    session.commit()
    return {"message": "Cliente desativado com sucesso"}
