from app.models import (
    Componente, Fluxo, Etapa, Historico, Usuario, Pendencia,
    PrioridadeEnum, StatusComponenteEnum, StatusEtapaEnum, IDTecnica, Desenho
)
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from sqlmodel import Session, select
from app.database import get_session
from app.models import (
    Componente, Fluxo, Etapa, Historico, Usuario,
    PrioridadeEnum, StatusComponenteEnum, StatusEtapaEnum, IDTecnica, Desenho
)
from app.routes.auth import obter_usuario_atual
from app.models import Equipamento, StatusEquipamentoEnum
from datetime import datetime

router = APIRouter(prefix="/api/componentes", tags=["Componentes"])

def sincronizar_status_equipamento(session: Session, equipamento_id: str):
    """Mantém o status do equipamento sincronizado com o progresso real dos componentes.
    Quando todos os componentes ativos chegam a 100%, o equipamento vira 'carregado'.
    Se algum componente voltar (retrabalho) ou for excluído, reavalia e reverte se preciso."""
    equipamento = session.get(Equipamento, equipamento_id)
    if not equipamento or not equipamento.ativo:
        return
    if equipamento.status == StatusEquipamentoEnum.CANCELADO:
        return  # não mexe em equipamento cancelado

    componentes_ativos = session.exec(
        select(Componente).where(Componente.equipamento_id == equipamento_id, Componente.ativo == True)
    ).all()

    todos_completos = bool(componentes_ativos) and all(c.percentual >= 100 for c in componentes_ativos)

    if todos_completos and equipamento.status != StatusEquipamentoEnum.CARREGADO:
        equipamento.status = StatusEquipamentoEnum.CARREGADO
        session.add(equipamento)
    elif not todos_completos and equipamento.status == StatusEquipamentoEnum.CARREGADO:
        equipamento.status = StatusEquipamentoEnum.EM_PRODUCAO
        session.add(equipamento)

def registrar_historico(session: Session, componente_id: str, usuario: str, evento: str, descricao: str):
    """Auxiliar para geração de histórico imutável (RN-019, RN-020)."""
    hist = Historico(
        componente_id=componente_id,
        usuario=usuario,
        evento=evento,
        descricao=descricao,
        data_hora=datetime.utcnow()
    )
    session.add(hist)

@router.get("")
def listar_todos_componentes(
    equipamento_id: Optional[str] = None,
    prioridade: Optional[str] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    query = select(Componente).where(Componente.ativo == True)
    if equipamento_id:
        query = query.where(Componente.equipamento_id == equipamento_id)
    if prioridade:
        query = query.where(Componente.prioridade == prioridade)
    if status:
        query = query.where(Componente.status == status)
        
    componentes = session.exec(query).all()
    
    result = []
    for c in componentes:
        etapa_atual = session.get(Etapa, c.etapa_atual_id) if c.etapa_atual_id else None

        # Etapas reais do fluxo deste componente (pode ser padrão, personalizado, etc. - RN-005)
        etapas_fluxo = []
        if c.fluxo:
            etapas_fluxo = session.exec(
                select(Etapa).where(Etapa.fluxo_id == c.fluxo.id).order_by(Etapa.ordem)
            ).all()

        result.append({
            "id": c.id,
            "equipamento_id": c.equipamento_id,
            "equipamento_nome": c.equipamento.nome if c.equipamento else "",
            "cliente_nome": c.equipamento.cliente.nome if c.equipamento and c.equipamento.cliente else "",
            "nome": c.nome,
            "descricao": c.descricao,
            "prioridade": c.prioridade,
            "status": c.status,
            "percentual": c.percentual,
            "responsavel": c.responsavel,
            "data_prevista": c.data_prevista,
            "data_conclusao": c.data_conclusao,
            "observacoes": c.observacoes,
            "etapa_atual_id": c.etapa_atual_id,
            "etapa_atual_nome": etapa_atual.nome if etapa_atual else "N/A",
            "etapa_atual_ordem": etapa_atual.ordem if etapa_atual else 0,
            # Fluxo completo do componente: usado pelo Kanban para montar colunas dinâmicas
            # e validar avanço/retorno com base no fluxo REAL, não em nomes fixos.
            "etapas": [{"id": et.id, "nome": et.nome, "ordem": et.ordem, "status": et.status} for et in etapas_fluxo]
        })
    return result

@router.get("/{componente_id}")
def obter_componente_detalhe(
    componente_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    c = session.get(Componente, componente_id)
    if not c or not c.ativo:
        raise HTTPException(status_code=404, detail="Componente não encontrado")
        
    etapas = []
    if c.fluxo:
        # Carregar etapas ordenadas do fluxo
        etapas = session.exec(
            select(Etapa).where(Etapa.fluxo_id == c.fluxo.id).order_by(Etapa.ordem)
        ).all()
        
    ids_tecnicas = session.exec(
        select(IDTecnica).where(IDTecnica.componente_id == c.id)
    ).all()
    
    ids_detalhado = []
    for id_tec in ids_tecnicas:
        desenhos = session.exec(
            select(Desenho).where(Desenho.id_tecnica_id == id_tec.id)
        ).all()
        ids_detalhado.append({
            "id": id_tec.id,
            "numero": id_tec.numero,
            "op": id_tec.op,
            "rv": id_tec.rv,
            "local": id_tec.local,
            "desenhos": desenhos
        })
        
    historico = session.exec(
        select(Historico).where(Historico.componente_id == c.id).order_by(Historico.data_hora.desc())
    ).all()

    return {
        "id": c.id,
        "equipamento_id": c.equipamento_id,
        "equipamento_nome": c.equipamento.nome if c.equipamento else "",
        "cliente_nome": c.equipamento.cliente.nome if c.equipamento and c.equipamento.cliente else "",
        "nome": c.nome,
        "descricao": c.descricao,
        "prioridade": c.prioridade,
        "status": c.status,
        "percentual": c.percentual,
        "responsavel": c.responsavel,
        "data_prevista": c.data_prevista,
        "data_conclusao": c.data_conclusao,
        "observacoes": c.observacoes,
        "etapas": etapas,
        "ids_tecnicas": ids_detalhado,
        "historico": historico
    }

@router.patch("/{componente_id}/prioridade")
def alterar_prioridade(
    componente_id: str,
    nova_prioridade: PrioridadeEnum,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    c = session.get(Componente, componente_id)
    if not c or not c.ativo:
        raise HTTPException(status_code=404, detail="Componente não encontrado")
        
    prioridade_antiga = c.prioridade
    c.prioridade = nova_prioridade
    c.atualizado_em = datetime.utcnow()
    
    registrar_historico(
        session, c.id, usuario_atual.nome, "Alteração de Prioridade",
        f"Prioridade alterada de '{prioridade_antiga.value}' para '{nova_prioridade.value}'."
    )
    
    session.add(c)
    session.commit()
    session.refresh(c)
    return c

@router.patch("/{componente_id}/avancar-etapa")
def avancar_etapa(
    componente_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    c = session.get(Componente, componente_id)
    if not c or not c.ativo:
        raise HTTPException(status_code=404, detail="Componente não encontrado")
        
    if not c.fluxo:
        raise HTTPException(status_code=400, detail="Componente não possui fluxo definido")

    if c.status == StatusComponenteEnum.BLOQUEADO:
        raise HTTPException(
            status_code=400,
            detail="Componente bloqueado por pendência(s) ativa(s). Resolva as pendências antes de avançar."
        )
        
    etapas = session.exec(
        select(Etapa).where(Etapa.fluxo_id == c.fluxo.id).order_by(Etapa.ordem)
    ).all()
    
    if not etapas:
        raise HTTPException(status_code=400, detail="Fluxo não possui etapas cadastradas")
        
    etapa_atual = session.get(Etapa, c.etapa_atual_id) if c.etapa_atual_id else None
    
    nova_etapa = None
    if not etapa_atual:
        # Se não começou, a primeira etapa vira a atual
        nova_etapa = etapas[0]
    else:
        # Achar o índice da atual e pegar a próxima
        for idx, et in enumerate(etapas):
            if et.id == etapa_atual.id:
                if idx + 1 < len(etapas):
                    nova_etapa = etapas[idx + 1]
                break
                
    if not nova_etapa:
        raise HTTPException(status_code=400, detail="Componente já está na última etapa do fluxo")
        
    # Concluir a atual
    if etapa_atual:
        etapa_atual.status = StatusEtapaEnum.CONCLUIDA
        etapa_atual.data_fim = datetime.utcnow()
        session.add(etapa_atual)
        
    # Iniciar a nova
    nova_etapa.status = StatusEtapaEnum.EM_ANDAMENTO
    nova_etapa.data_inicio = datetime.utcnow()
    session.add(nova_etapa)
    
    c.etapa_atual_id = nova_etapa.id
    c.status = StatusComponenteEnum.EM_ANDAMENTO
    
    # Calcular percentual (d-03)
    # Achar o índice da nova etapa para o cálculo
    idx_nova = next(i for i, e in enumerate(etapas) if e.id == nova_etapa.id)
    c.percentual = round(((idx_nova) / len(etapas)) * 100, 1)
    
    # Se avançou para a última etapa (ex: Finalizado ou Expedição concluída), marca data de conclusão
    if idx_nova == len(etapas) - 1:
        c.percentual = 100.0
        c.status = StatusComponenteEnum.CONCLUIDO
        c.data_conclusao = datetime.utcnow().date()
        
    registrar_historico(
        session, c.id, usuario_atual.nome, "Avanço de Etapa",
        f"Avançou da etapa '{etapa_atual.nome if etapa_atual else 'N/A'}' para '{nova_etapa.nome}'."
    )
    
    sincronizar_status_equipamento(session, c.equipamento_id)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c

@router.patch("/{componente_id}/retornar-etapa")
def retornar_etapa(
    componente_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    c = session.get(Componente, componente_id)
    if not c or not c.ativo:
        raise HTTPException(status_code=404, detail="Componente não encontrado")
        
    if not c.fluxo or not c.etapa_atual_id:
        raise HTTPException(status_code=400, detail="Componente não está em nenhuma etapa ativa")
        
    etapas = session.exec(
        select(Etapa).where(Etapa.fluxo_id == c.fluxo.id).order_by(Etapa.ordem)
    ).all()
    
    etapa_atual = session.get(Etapa, c.etapa_atual_id)
    
    nova_etapa = None
    for idx, et in enumerate(etapas):
        if et.id == etapa_atual.id:
            if idx - 1 >= 0:
                nova_etapa = etapas[idx - 1]
            break
            
    if not nova_etapa:
        raise HTTPException(status_code=400, detail="Componente já está na primeira etapa")
        
    # Resetar a etapa atual
    etapa_atual.status = StatusEtapaEnum.PENDENTE
    etapa_atual.data_inicio = None
    etapa_atual.data_fim = None
    session.add(etapa_atual)
    
    # Reabrir a etapa anterior
    nova_etapa.status = StatusEtapaEnum.EM_ANDAMENTO
    nova_etapa.data_fim = None
    session.add(nova_etapa)
    
    c.etapa_atual_id = nova_etapa.id
    c.status = StatusComponenteEnum.EM_ANDAMENTO
    
    # Recalcular percentual
    idx_nova = next(i for i, e in enumerate(etapas) if e.id == nova_etapa.id)
    c.percentual = round(((idx_nova) / len(etapas)) * 100, 1)
    
    registrar_historico(
        session, c.id, usuario_atual.nome, "Retorno de Etapa (Retrabalho)",
        f"Retornou da etapa '{etapa_atual.nome}' para '{nova_etapa.nome}' por motivos de retrabalho."
    )
    
    sincronizar_status_equipamento(session, c.equipamento_id)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c

@router.post("", status_code=status.HTTP_201_CREATED)
def criar_componente(
    dados: dict,  # Recebe { equipamento_id, nome, descricao, prioridade, responsavel, data_prevista, observacoes, etapas: ["Etapa 1", "Etapa 2"] }
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    equipamento_id = dados.get("equipamento_id")
    nome = dados.get("nome")
    descricao = dados.get("descricao")
    prioridade = dados.get("prioridade", PrioridadeEnum.NORMAL)
    responsavel = dados.get("responsavel")
    data_prevista_str = dados.get("data_prevista")
    observacoes = dados.get("observacoes")
    etapas_nomes = dados.get("etapas", [])

    if not equipamento_id or not nome:
        raise HTTPException(status_code=400, detail="Equipamento e Nome do Componente são obrigatórios")
        
    data_prevista = None
    if data_prevista_str:
        try:
            data_prevista = datetime.strptime(data_prevista_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    # Criar componente
    c = Componente(
        equipamento_id=equipamento_id,
        nome=nome,
        descricao=descricao,
        prioridade=prioridade,
        status=StatusComponenteEnum.NAO_INICIADO,
        responsavel=responsavel,
        data_prevista=data_prevista,
        observacoes=observacoes
    )
    session.add(c)
    session.commit()
    session.refresh(c)

    # Criar fluxo do componente
    fluxo = Fluxo(componente_id=c.id)
    session.add(fluxo)
    session.commit()
    session.refresh(fluxo)

    # Adicionar etapas ao fluxo
    etapas_criadas = []
    for i, nome_etapa in enumerate(etapas_nomes):
        status_et = StatusEtapaEnum.EM_ANDAMENTO if i == 0 else StatusEtapaEnum.PENDENTE
        et = Etapa(
            fluxo_id=fluxo.id,
            nome=nome_etapa,
            ordem=i + 1,
            status=status_et,
            data_inicio=datetime.utcnow() if i == 0 else None
        )
        session.add(et)
        etapas_criadas.append(et)
    
    session.commit()

    # Vincular primeira etapa criada como a atual do componente
    if etapas_criadas:
        c.etapa_atual_id = etapas_criadas[0].id
        c.status = StatusComponenteEnum.EM_ANDAMENTO
        session.add(c)
        session.commit()
        session.refresh(c)

    registrar_historico(
        session, c.id, usuario_atual.nome, "Criação de Componente",
        f"Componente cadastrado com fluxo personalizado de {len(etapas_nomes)} etapas."
    )
    session.commit()
    return c

@router.put("/{componente_id}/fluxo")
def atualizar_fluxo_etapas(
    componente_id: str,
    etapas_nomes: List[str],
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Permite alterar as etapas de fabricação (RN-006) do componente se ele estiver na primeira etapa ou não iniciado."""
    c = session.get(Componente, componente_id)
    if not c or not c.ativo:
        raise HTTPException(status_code=404, detail="Componente não encontrado")
        
    if not c.fluxo:
        raise HTTPException(status_code=400, detail="Componente não possui fluxo")
        
    etapas_existentes = session.exec(
        select(Etapa).where(Etapa.fluxo_id == c.fluxo.id).order_by(Etapa.ordem)
    ).all()
    
    concluidas = [e for e in etapas_existentes if e.status == StatusEtapaEnum.CONCLUIDA]
    if len(concluidas) > 0:
        raise HTTPException(
            status_code=400,
            detail="Não é permitido reestruturar o fluxo de componentes que já possuem etapas concluídas"
        )
        
    # Excluir etapas antigas
    for et in etapas_existentes:
        session.delete(et)
    session.commit()
    
    # Inserir novas etapas
    etapas_criadas = []
    for i, nome_etapa in enumerate(etapas_nomes):
        status_et = StatusEtapaEnum.EM_ANDAMENTO if i == 0 else StatusEtapaEnum.PENDENTE
        et = Etapa(
            fluxo_id=c.fluxo.id,
            nome=nome_etapa,
            ordem=i + 1,
            status=status_et,
            data_inicio=datetime.utcnow() if i == 0 else None
        )
        session.add(et)
        etapas_criadas.append(et)
    session.commit()
    
    if etapas_criadas:
        c.etapa_atual_id = etapas_criadas[0].id
        c.percentual = 0.0
        c.status = StatusComponenteEnum.EM_ANDAMENTO
        session.add(c)
        
    registrar_historico(
        session, c.id, usuario_atual.nome, "Alteração de Fluxo",
        f"Estrutura do fluxo alterada estruturalmente pelo PCP para {len(etapas_nomes)} etapas."
    )
    session.commit()
    return {"message": "Fluxo de fabricação atualizado com sucesso"}

@router.get("/{componente_id}/pendencias")
def listar_pendencias_componente(
    componente_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    c = session.get(Componente, componente_id)
    if not c or not c.ativo:
        raise HTTPException(status_code=404, detail="Componente não encontrado")

    return session.exec(
        select(Pendencia)
        .where(Pendencia.componente_id == componente_id)
        .order_by(Pendencia.aberta_em.desc())
    ).all()

@router.delete("/{componente_id}")
def deletar_componente(
    componente_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    c = session.get(Componente, componente_id)
    if not c or not c.ativo:
        raise HTTPException(status_code=404, detail="Componente não encontrado")

    equipamento_id = c.equipamento_id

    c.ativo = False
    c.atualizado_em = datetime.utcnow()
    session.add(c)

    # Reavalia o status do equipamento pai, já que remover um componente
    # pode mudar se todos os componentes ativos restantes estão 100% ou não.
    sincronizar_status_equipamento(session, equipamento_id)

    session.commit()
    return {"message": "Componente deletado com sucesso (soft delete)"}