from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlmodel import Session, select
from app.database import get_session
from app.models import ModeloFluxo, EtapaModelo, Usuario
from app.routes.auth import obter_usuario_atual
from datetime import datetime

router = APIRouter(prefix="/api/modelos-fluxo", tags=["Modelos de Fluxo"])

@router.get("")
def listar_modelos(
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Retorna todos os templates de fluxo com suas respectivas etapas padrão."""
    modelos = session.exec(select(ModeloFluxo).where(ModeloFluxo.ativo == True)).all()
    
    result = []
    for mod in modelos:
        etapas = session.exec(
            select(EtapaModelo).where(EtapaModelo.modelo_fluxo_id == mod.id).order_by(EtapaModelo.ordem)
        ).all()
        result.append({
            "id": mod.id,
            "nome": mod.nome,
            "descricao": mod.descricao,
            "etapas": [et.nome for et in etapas]
        })
    return result

@router.post("", status_code=status.HTTP_201_CREATED)
def criar_modelo(
    dados: dict,  # Recebe { nome, descricao, etapas: ["Etapa 1", "Etapa 2"] }
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    nome = dados.get("nome")
    descricao = dados.get("descricao")
    etapas = dados.get("etapas", [])
    
    if not nome:
        raise HTTPException(status_code=400, detail="O nome do modelo de fluxo é obrigatório")
        
    existente = session.exec(select(ModeloFluxo).where(ModeloFluxo.nome == nome)).first()
    if existente:
        raise HTTPException(status_code=400, detail="Já existe um modelo de fluxo com este nome")
        
    mod = ModeloFluxo(nome=nome, descricao=descricao)
    session.add(mod)
    session.commit()
    session.refresh(mod)
    
    # Criar etapas padrão vinculadas
    for i, nome_etapa in enumerate(etapas):
        et_mod = EtapaModelo(modelo_fluxo_id=mod.id, nome=nome_etapa, ordem=i + 1)
        session.add(et_mod)
        
    session.commit()
    
    return {
        "id": mod.id,
        "nome": mod.nome,
        "descricao": mod.descricao,
        "etapas": etapas
    }

@router.delete("/{modelo_id}")
def deletar_modelo(
    modelo_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    mod = session.get(ModeloFluxo, modelo_id)
    if not mod or not mod.ativo:
        raise HTTPException(status_code=404, detail="Modelo de fluxo não encontrado")
        
    mod.ativo = False
    mod.atualizado_em = datetime.utcnow()
    session.add(mod)
    session.commit()
    return {"message": "Modelo de fluxo desativado com sucesso"}
