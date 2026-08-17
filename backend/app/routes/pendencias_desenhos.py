from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    Componente, Desenho, Equipamento, IDTecnica, RevisaoDesenho,
    StatusIDTecnicaEnum, StatusRevisaoDesenhoEnum, Usuario,
)
from app.routes.auth import obter_usuario_atual


router = APIRouter(prefix="/api/pendencias-desenhos", tags=["Pendencias de desenhos"])


def _montar_item(session: Session, desenho: Desenho, revisao: RevisaoDesenho | None = None):
    id_tecnica = session.get(IDTecnica, desenho.id_tecnica_id)
    componente = session.get(Componente, id_tecnica.componente_id) if id_tecnica else None
    equipamento = session.get(Equipamento, componente.equipamento_id) if componente else None
    if not id_tecnica or not componente or not equipamento or not componente.ativo or not equipamento.ativo:
        return None
    return {
        "desenho_id": desenho.id,
        "codigo": desenho.codigo,
        "descricao": desenho.descricao,
        "quantidade": desenho.quantidade,
        "unidade": desenho.unidade,
        "recebido": desenho.recebido,
        "conferencia_atualizada_em": desenho.conferencia_atualizada_em or desenho.criado_em,
        "conferencia_atualizada_por": desenho.conferencia_atualizada_por,
        "em_revisao": revisao is not None,
        "revisao_id": revisao.id if revisao else None,
        "motivo_revisao": revisao.motivo if revisao else None,
        "retornada_em": revisao.retornada_em if revisao else None,
        "retornada_por": revisao.retornada_por if revisao else None,
        "id_tecnica_id": id_tecnica.id,
        "id_numero": id_tecnica.numero,
        "id_versao": id_tecnica.versao,
        "id_status": id_tecnica.status,
        "componente_id": componente.id,
        "componente_nome": componente.nome,
        "equipamento_id": equipamento.id,
        "equipamento_nome": equipamento.nome,
        "op": equipamento.op,
        "rv": equipamento.rv,
        "cliente_nome": equipamento.cliente.nome if equipamento.cliente else "",
    }


@router.get("")
def listar_pendencias_desenhos(
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual),
):
    itens = {}

    revisoes = session.exec(select(RevisaoDesenho).where(
        RevisaoDesenho.status == StatusRevisaoDesenhoEnum.EM_REVISAO
    )).all()
    for revisao in revisoes:
        desenho = session.get(Desenho, revisao.desenho_origem_id)
        if not desenho:
            continue
        item = _montar_item(session, desenho, revisao)
        if item:
            itens[desenho.id] = item

    ids_atuais = session.exec(select(IDTecnica).where(
        IDTecnica.status.in_([StatusIDTecnicaEnum.LIBERADA, StatusIDTecnicaEnum.EM_REVISAO])
    )).all()
    ids_atuais_por_id = {item.id: item for item in ids_atuais}
    faltantes = session.exec(select(Desenho).where(
        Desenho.id_tecnica_id.in_(list(ids_atuais_por_id)),
        Desenho.recebido == False,
    )).all() if ids_atuais_por_id else []
    for desenho in faltantes:
        if desenho.id in itens:
            itens[desenho.id]["recebido"] = False
            continue
        item = _montar_item(session, desenho)
        if item:
            itens[desenho.id] = item

    resultado = list(itens.values())
    resultado.sort(key=lambda item: (
        item["retornada_em"] or item["conferencia_atualizada_em"],
        item["codigo"],
    ))
    return {
        "total": len(resultado),
        "em_revisao": sum(1 for item in resultado if item["em_revisao"]),
        "nao_recebidos": sum(1 for item in resultado if item["recebido"] is False),
        "itens": resultado,
    }
