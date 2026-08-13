from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlmodel import Session, select
from app.database import get_session
from app.models import (
    Pendencia, Componente, IDTecnica, Usuario, StatusComponenteEnum,
    StatusIDTecnicaEnum, StatusPendenciaEnum
)
from app.routes.auth import obter_usuario_atual, exigir_operacao
from app.routes.componentes import registrar_historico
from datetime import datetime

router = APIRouter(prefix="/api/pendencias", tags=["Pendências"])

@router.post("", response_model=Pendencia, status_code=status.HTTP_201_CREATED, dependencies=[Depends(exigir_operacao)])
def abrir_pendencia(
    pendencia: Pendencia,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    c = session.get(Componente, pendencia.componente_id)
    if not c or not c.ativo:
        raise HTTPException(status_code=404, detail="Componente não encontrado")
        
    pendencia.aberta_por = usuario_atual.nome
    pendencia.aberta_em = datetime.utcnow()
    pendencia.status = StatusPendenciaEnum.ABERTA
    
    # Se for uma pendência bloqueante, altera o status do componente
    if pendencia.bloqueante:
        c.status = StatusComponenteEnum.BLOQUEADO
        c.atualizado_em = datetime.utcnow()
        session.add(c)
        
    session.add(pendencia)
    
    registrar_historico(
        session, c.id, usuario_atual.nome, "Abertura de Pendência",
        f"Pendência aberta: '{pendencia.titulo}'. Bloqueante: {'Sim' if pendencia.bloqueante else 'Não'}."
    )
    
    session.commit()
    session.refresh(pendencia)
    return pendencia

@router.patch("/{pendencia_id}/encerrar", response_model=Pendencia, dependencies=[Depends(exigir_operacao)])
def encerrar_pendencia(
    pendencia_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    p = session.get(Pendencia, pendencia_id)
    if not p:
        raise HTTPException(status_code=404, detail="Pendência não encontrada")
        
    if p.status == StatusPendenciaEnum.RESOLVIDA:
        raise HTTPException(status_code=400, detail="Pendência já está resolvida")

    id_em_revisao = session.exec(
        select(IDTecnica).where(
            IDTecnica.pendencia_revisao_id == p.id,
            IDTecnica.status == StatusIDTecnicaEnum.EM_REVISAO,
        )
    ).first()
    if id_em_revisao:
        raise HTTPException(
            status_code=400,
            detail=f"A pendência será encerrada automaticamente quando uma nova versão da ID {id_em_revisao.numero} for importada."
        )
        
    p.status = StatusPendenciaEnum.RESOLVIDA
    p.encerrada_por = usuario_atual.nome
    p.encerrada_em = datetime.utcnow()
    session.add(p)
    
    c = session.get(Componente, p.componente_id)
    
    # Se o componente estava bloqueado por esta pendência, verificar se existem outras bloqueantes ativas
    if p.bloqueante and c.status == StatusComponenteEnum.BLOQUEADO:
        restantes = session.exec(
            select(Pendencia).where(
                Pendencia.componente_id == c.id,
                Pendencia.bloqueante == True,
                Pendencia.status == StatusPendenciaEnum.ABERTA,
                Pendencia.id != p.id
            )
        ).all()
        
        # Se não há mais nenhuma pendência bloqueante ativa, desbloqueia o componente
        if not restantes:
            c.status = StatusComponenteEnum.EM_ANDAMENTO
            c.atualizado_em = datetime.utcnow()
            session.add(c)
            
    registrar_historico(
        session, c.id, usuario_atual.nome, "Encerramento de Pendência",
        f"Pendência encerrada/resolvida: '{p.titulo}'."
    )
    
    session.commit()
    session.refresh(p)
    return p
