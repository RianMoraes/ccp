import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.database import get_session
from app.models import (
    Anexo, Componente, Desenho, Historico, IDTecnica, Pendencia, RevisaoDesenho,
    StatusComponenteEnum, StatusIDTecnicaEnum, StatusPendenciaEnum,
    StatusRevisaoDesenhoEnum, Usuario,
)
from app.routes.auth import obter_usuario_atual, exigir_operacao
from app.routes.componentes import registrar_historico, sincronizar_status_equipamento
from app.services.folha_id_parser import FolhaIDInvalida, analisar_folha_id, analisar_folha_id_imagens
from app.services.pdf_compressor import compactar_pdf, imagens_jpeg_para_pdf


router = APIRouter(prefix="/api/componentes/{componente_id}/folhas-id", tags=["Folhas de ID"])
UPLOAD_ROOT = Path(os.getenv("UPLOAD_DIR", Path(__file__).resolve().parents[2] / "uploads"))


def _obter_componente(session, componente_id):
    componente = session.get(Componente, componente_id)
    if not componente or not componente.ativo:
        raise HTTPException(status_code=404, detail="Componente não encontrado")
    return componente


async def _ler_documentos(arquivos):
    if not arquivos:
        raise HTTPException(status_code=400, detail="Selecione um PDF ou uma ou mais imagens JPG/JPEG.")
    itens = [(arquivo, await arquivo.read()) for arquivo in arquivos]
    pdfs = [(arquivo, conteudo) for arquivo, conteudo in itens if conteudo.startswith(b"%PDF")]
    imagens = [(arquivo, conteudo) for arquivo, conteudo in itens if conteudo[:3] == b"\xff\xd8\xff"]
    if len(pdfs) == 1 and len(itens) == 1:
        return "pdf", [pdfs[0][1]], Path(pdfs[0][0].filename or "folha-id.pdf").name
    if len(imagens) == len(itens):
        nomes = [Path(arquivo.filename or "pagina.jpg").name for arquivo, _ in imagens]
        return "imagens", [conteudo for _, conteudo in imagens], nomes
    raise HTTPException(status_code=400, detail="Envie um único PDF ou somente imagens JPG/JPEG. Não misture os formatos.")


def _hash_documentos(conteudos):
    if len(conteudos) == 1:
        return hashlib.sha256(conteudos[0]).hexdigest()
    resumo = hashlib.sha256()
    for conteudo in conteudos:
        resumo.update(len(conteudo).to_bytes(8, "big"))
        resumo.update(conteudo)
    return resumo.hexdigest()


def _avisos_componente(componente, dados):
    avisos = []
    equipamento = componente.equipamento
    if dados.get("op") and equipamento and equipamento.op and dados["op"] != equipamento.op:
        avisos.append(f"A OP do PDF ({dados['op']}) difere da OP do equipamento ({equipamento.op}).")
    if dados.get("rv") and equipamento and equipamento.rv and dados["rv"] != equipamento.rv:
        avisos.append(f"A RV do PDF ({dados['rv']}) difere da RV do equipamento ({equipamento.rv}).")
    if dados.get("componente") and dados["componente"].casefold() != componente.nome.casefold():
        avisos.append(f"O componente informado no PDF é '{dados['componente']}', mas a importação será atribuída a '{componente.nome}'.")
    return avisos


@router.post("/analisar", dependencies=[Depends(exigir_operacao)])
async def analisar_pdf(
    componente_id: str,
    arquivos: List[UploadFile] = File(...),
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual),
):
    componente = _obter_componente(session, componente_id)
    tipo, conteudos, nomes = await _ler_documentos(arquivos)
    try:
        dados = analisar_folha_id(conteudos[0]) if tipo == "pdf" else analisar_folha_id_imagens(conteudos)
    except FolhaIDInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    dados["arquivo_nome"] = nomes if tipo == "pdf" else "Folha de ID - imagens.pdf"
    dados["arquivos_origem"] = nomes if tipo == "imagens" else [nomes]
    dados["hash_arquivo"] = _hash_documentos(conteudos)
    dados["avisos"] = _avisos_componente(componente, dados)
    return dados


@router.post("/confirmar", status_code=status.HTTP_201_CREATED, dependencies=[Depends(exigir_operacao)])
async def confirmar_importacao(
    componente_id: str,
    dados_json: str = Form(...),
    arquivos: List[UploadFile] = File(...),
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual),
):
    componente = _obter_componente(session, componente_id)
    tipo, conteudos, nomes = await _ler_documentos(arquivos)
    conteudo = conteudos[0] if tipo == "pdf" else imagens_jpeg_para_pdf(conteudos)
    try:
        dados = json.loads(dados_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Os dados de confirmação são inválidos.") from exc

    numero = str(dados.get("numero_id") or "").strip()
    desenhos = dados.get("desenhos") or []
    if not numero or not desenhos:
        raise HTTPException(status_code=400, detail="A ID e ao menos um desenho são obrigatórios.")

    hash_arquivo = _hash_documentos(conteudos)
    duplicado = session.exec(
        select(IDTecnica).where(
            IDTecnica.componente_id == componente_id,
            IDTecnica.hash_arquivo == hash_arquivo,
        )
    ).first()
    if duplicado:
        raise HTTPException(status_code=409, detail="Este mesmo PDF já foi importado para o componente.")

    revisao_de_id = str(dados.get("revisao_de_id") or "").strip() or None
    revisao_desenho_id = str(dados.get("revisao_desenho_id") or "").strip() or None
    confirma_substituicao = dados.get("confirma_substituicao") is True
    revisao_desenho = None
    desenho_origem = None
    indice_substituto = None
    if revisao_desenho_id:
        revisao_desenho = session.get(RevisaoDesenho, revisao_desenho_id)
        if (
            not revisao_desenho
            or revisao_desenho.componente_id != componente_id
            or revisao_desenho.status != StatusRevisaoDesenhoEnum.EM_REVISAO
        ):
            raise HTTPException(status_code=409, detail="A revisão individual deste desenho não está mais aberta.")
        desenho_origem = session.get(Desenho, revisao_desenho.desenho_origem_id)
        if not desenho_origem:
            raise HTTPException(status_code=404, detail="O desenho original da revisão não foi encontrado.")
        try:
            indice_substituto = int(dados.get("desenho_substituto_indice"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Selecione qual desenho recebido resolve a revisão.")
        if indice_substituto < 0 or indice_substituto >= len(desenhos):
            raise HTTPException(status_code=400, detail="O desenho selecionado para a revisão é inválido.")
        codigo_substituto = str(desenhos[indice_substituto].get("codigo") or "").strip()
        if codigo_substituto.casefold() != desenho_origem.codigo.casefold() and dados.get("confirma_substituicao_desenho") is not True:
            raise HTTPException(
                status_code=409,
                detail=f"Confirme que o desenho {codigo_substituto} substitui o desenho {desenho_origem.codigo}.",
            )
    alvo_revisao = None
    if revisao_desenho and not revisao_de_id:
        raise HTTPException(status_code=400, detail="Informe a ID de origem do desenho em revisão.")
    if revisao_de_id:
        alvo_revisao = session.get(IDTecnica, revisao_de_id)
        if not alvo_revisao or alvo_revisao.componente_id != componente_id:
            raise HTTPException(status_code=404, detail="A ID indicada para revisão não foi encontrada neste componente.")
        if revisao_desenho and alvo_revisao.status != StatusIDTecnicaEnum.LIBERADA:
            id_atual = session.exec(
                select(IDTecnica)
                .where(
                    IDTecnica.componente_id == componente_id,
                    IDTecnica.numero == alvo_revisao.numero,
                    IDTecnica.status == StatusIDTecnicaEnum.LIBERADA,
                )
                .order_by(IDTecnica.versao.desc())
            ).first()
            if id_atual:
                alvo_revisao = id_atual
        if alvo_revisao.status != StatusIDTecnicaEnum.EM_REVISAO and not revisao_desenho:
            raise HTTPException(status_code=409, detail="A ID indicada não está mais em revisão.")
        if numero != alvo_revisao.numero and not confirma_substituicao:
            raise HTTPException(
                status_code=409,
                detail=f"Confirme que a ID {numero} substitui a ID {alvo_revisao.numero} antes de continuar.",
            )

    existentes = session.exec(
        select(IDTecnica)
        .where(IDTecnica.componente_id == componente_id, IDTecnica.numero == numero)
        .order_by(IDTecnica.versao.desc())
    ).all()
    anterior = existentes[0] if existentes else None
    substituicao = bool(alvo_revisao and numero != alvo_revisao.numero)
    if substituicao and anterior:
        raise HTTPException(status_code=409, detail=f"A ID substituta {numero} já está cadastrada neste componente.")
    if anterior and anterior.status != StatusIDTecnicaEnum.EM_REVISAO and not revisao_desenho:
        raise HTTPException(status_code=409, detail="Esta ID já existe. Retorne-a para revisão antes de importar uma nova versão.")
    if anterior and not alvo_revisao:
        raise HTTPException(status_code=409, detail="Use o botão 'Importar revisão' da ID que está em revisão.")
    if alvo_revisao and not substituicao and anterior.id != alvo_revisao.id:
        raise HTTPException(status_code=409, detail="A revisão selecionada não corresponde à versão atual desta ID.")

    anterior_fluxo = alvo_revisao if alvo_revisao else anterior
    versao = 1 if substituicao else ((anterior.versao + 1) if anterior else 1)
    raiz_id = None if substituicao else ((anterior.id_origem_id or anterior.id) if anterior else None)
    pasta = UPLOAD_ROOT / "folhas_id" / componente_id
    pasta.mkdir(parents=True, exist_ok=True)
    nome_seguro = f"{uuid.uuid4()}-v{versao}.pdf"
    caminho = pasta / nome_seguro
    compactacao = compactar_pdf(conteudo)
    caminho.write_bytes(compactacao["conteudo"])

    try:
        data_liberacao = datetime.fromisoformat(dados["data_liberacao"]) if dados.get("data_liberacao") else None
        id_tecnica = IDTecnica(
            componente_id=componente_id,
            numero=numero,
            op=dados.get("op"),
            rv=dados.get("rv"),
            cliente_documento=dados.get("cliente"),
            equipamento_documento=dados.get("equipamento"),
            componente_documento=dados.get("componente"),
            local=dados.get("local"),
            status=StatusIDTecnicaEnum.LIBERADA,
            versao=versao,
            id_origem_id=raiz_id,
            substitui_id=alvo_revisao.id if substituicao else None,
            liberado_por=dados.get("liberado_por"),
            data_liberacao=data_liberacao,
            arquivo_nome=nomes if tipo == "pdf" else "Folha de ID - imagens.pdf",
            arquivo_caminho=str(caminho.resolve()),
            modelo_documento=dados.get("modelo_documento"),
            hash_arquivo=hash_arquivo,
            tamanho_original=compactacao["tamanho_original"],
            tamanho_armazenado=compactacao["tamanho_armazenado"],
            arquivo_compactado=compactacao["compactado"],
            importado_por=usuario_atual.nome,
            importado_em=datetime.utcnow(),
        )
        session.add(id_tecnica)
        session.flush()

        novos_desenhos = []
        for posicao, desenho in enumerate(desenhos, 1):
            codigo = str(desenho.get("codigo") or "").strip()
            if not codigo:
                raise HTTPException(status_code=400, detail=f"O desenho da linha {posicao} não possui código.")
            novo_desenho = Desenho(
                id_tecnica_id=id_tecnica.id,
                codigo=codigo,
                descricao=desenho.get("descricao"),
                quantidade=max(int(desenho.get("quantidade") or 1), 1),
                revisao=desenho.get("revisao"),
                copias=max(int(desenho.get("copias") or 1), 1),
                unidade=desenho.get("unidade"),
                item=desenho.get("item"),
                pagina_origem=desenho.get("pagina_origem"),
                quantidade_original=desenho.get("quantidade_original"),
                recebido=desenho.get("recebido") is not False,
                conferencia_atualizada_em=datetime.utcnow(),
                conferencia_atualizada_por=usuario_atual.nome,
            )
            session.add(novo_desenho)
            session.flush()
            novos_desenhos.append(novo_desenho)

        if revisao_desenho:
            desenho_substituto = novos_desenhos[indice_substituto]
            revisao_desenho.desenho_substituto_id = desenho_substituto.id
            revisao_desenho.status = StatusRevisaoDesenhoEnum.RESOLVIDA
            revisao_desenho.resolvida_por = usuario_atual.nome
            revisao_desenho.resolvida_em = datetime.utcnow()
            session.add(revisao_desenho)

            desenhos_anteriores = session.exec(
                select(Desenho).where(Desenho.id_tecnica_id == alvo_revisao.id)
            ).all()
            novos_por_codigo = {item.codigo.casefold(): item for item in novos_desenhos}
            anteriores_por_id = {item.id: item for item in desenhos_anteriores}
            outras_revisoes = session.exec(
                select(RevisaoDesenho).where(
                    RevisaoDesenho.componente_id == componente_id,
                    RevisaoDesenho.status == StatusRevisaoDesenhoEnum.EM_REVISAO,
                    RevisaoDesenho.id != revisao_desenho.id,
                )
            ).all()
            for outra in outras_revisoes:
                origem_anterior = anteriores_por_id.get(outra.desenho_origem_id)
                if origem_anterior and origem_anterior.codigo.casefold() in novos_por_codigo:
                    outra.desenho_origem_id = novos_por_codigo[origem_anterior.codigo.casefold()].id
                    session.add(outra)

        session.add(Anexo(
            componente_id=componente_id,
            nome=id_tecnica.arquivo_nome,
            caminho=id_tecnica.arquivo_caminho,
            tipo="application/pdf",
            enviado_por=usuario_atual.nome,
        ))

        if anterior_fluxo:
            anterior_fluxo.status = StatusIDTecnicaEnum.SUBSTITUIDA if substituicao else StatusIDTecnicaEnum.REVISADA
            session.add(anterior_fluxo)
            if anterior_fluxo.pendencia_revisao_id:
                pendencia = session.get(Pendencia, anterior_fluxo.pendencia_revisao_id)
                if pendencia and pendencia.status == StatusPendenciaEnum.ABERTA:
                    pendencia.status = StatusPendenciaEnum.RESOLVIDA
                    pendencia.encerrada_por = usuario_atual.nome
                    pendencia.encerrada_em = datetime.utcnow()
                    session.add(pendencia)
                    outras = session.exec(select(Pendencia).where(
                        Pendencia.componente_id == componente_id,
                        Pendencia.bloqueante == True,
                        Pendencia.status == StatusPendenciaEnum.ABERTA,
                        Pendencia.id != pendencia.id,
                    )).all()
                    if not outras:
                        componente.status = StatusComponenteEnum.EM_ANDAMENTO
                        session.add(componente)

        acao = "Substituição de Folha de ID" if substituicao else "Importação de Folha de ID"
        detalhe = (
            f"ID '{alvo_revisao.numero}' substituída pela ID '{numero}' versão 1, com {len(desenhos)} desenho(s)."
            if substituicao else f"ID '{numero}' versão {versao} importada com {len(desenhos)} desenho(s)."
        )
        if revisao_desenho and desenho_origem:
            detalhe += f" Revisão individual do desenho '{desenho_origem.codigo}' resolvida."
        if compactacao["compactado"]:
            detalhe += f" PDF compactado com redução de {compactacao['percentual_reducao']}%."
        registrar_historico(
            session, componente_id, usuario_atual.nome, acao, detalhe
        )
        session.commit()
        session.refresh(id_tecnica)
        return {
            "id": id_tecnica.id,
            "numero": numero,
            "versao": versao,
            "desenhos_importados": len(desenhos),
            "arquivo_compactado": compactacao["compactado"],
            "tamanho_original": compactacao["tamanho_original"],
            "tamanho_armazenado": compactacao["tamanho_armazenado"],
            "percentual_reducao": compactacao["percentual_reducao"],
        }
    except Exception:
        session.rollback()
        caminho.unlink(missing_ok=True)
        raise


@router.post("/{id_tecnica_id}/retornar-revisao", dependencies=[Depends(exigir_operacao)])
def retornar_para_revisao(
    componente_id: str,
    id_tecnica_id: str,
    dados: dict,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual),
):
    componente = _obter_componente(session, componente_id)
    id_tecnica = session.get(IDTecnica, id_tecnica_id)
    if not id_tecnica or id_tecnica.componente_id != componente_id:
        raise HTTPException(status_code=404, detail="ID técnica não encontrada")
    if id_tecnica.status == StatusIDTecnicaEnum.EM_REVISAO:
        raise HTTPException(status_code=400, detail="Esta ID já está em revisão.")
    desenhos_id = session.exec(select(Desenho).where(Desenho.id_tecnica_id == id_tecnica_id)).all()
    ids_desenhos = [desenho.id for desenho in desenhos_id]
    revisoes_individuais = session.exec(select(RevisaoDesenho).where(
        RevisaoDesenho.desenho_origem_id.in_(ids_desenhos),
        RevisaoDesenho.status == StatusRevisaoDesenhoEnum.EM_REVISAO,
    )).all() if ids_desenhos else []
    if revisoes_individuais:
        raise HTTPException(
            status_code=409,
            detail="Esta ID possui desenho(s) em revisão individual. Resolva ou cancele esses retornos antes de retornar a ID completa.",
        )
    motivo = str(dados.get("motivo") or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Informe o motivo do retorno para revisão.")

    pendencia = Pendencia(
        componente_id=componente_id,
        titulo=f"ID {id_tecnica.numero} retornada para revisão",
        descricao=motivo,
        bloqueante=True,
        status=StatusPendenciaEnum.ABERTA,
        aberta_por=usuario_atual.nome,
    )
    session.add(pendencia)
    session.flush()
    id_tecnica.status = StatusIDTecnicaEnum.EM_REVISAO
    id_tecnica.motivo_revisao = motivo
    id_tecnica.retornada_por = usuario_atual.nome
    id_tecnica.retornada_em = datetime.utcnow()
    id_tecnica.pendencia_revisao_id = pendencia.id
    componente.status = StatusComponenteEnum.BLOQUEADO
    session.add(id_tecnica)
    session.add(componente)
    registrar_historico(
        session, componente_id, usuario_atual.nome, "ID retornada para revisão",
        f"ID '{id_tecnica.numero}' versão {id_tecnica.versao}: {motivo}"
    )
    session.commit()
    return {"message": "ID retornada para revisão e componente bloqueado."}


@router.post("/{id_tecnica_id}/desenhos/{desenho_id}/retornar-revisao", dependencies=[Depends(exigir_operacao)])
def retornar_desenho_para_revisao(
    componente_id: str, id_tecnica_id: str, desenho_id: str, dados: dict,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual),
):
    _obter_componente(session, componente_id)
    id_tecnica = session.get(IDTecnica, id_tecnica_id)
    desenho = session.get(Desenho, desenho_id)
    if not id_tecnica or id_tecnica.componente_id != componente_id:
        raise HTTPException(status_code=404, detail="ID técnica não encontrada.")
    if not desenho or desenho.id_tecnica_id != id_tecnica_id:
        raise HTTPException(status_code=404, detail="Desenho não encontrado nesta ID.")
    if id_tecnica.status != StatusIDTecnicaEnum.LIBERADA:
        raise HTTPException(status_code=409, detail="Somente desenhos da ID liberada atual podem retornar para revisão.")
    existente = session.exec(select(RevisaoDesenho).where(
        RevisaoDesenho.desenho_origem_id == desenho_id,
        RevisaoDesenho.status == StatusRevisaoDesenhoEnum.EM_REVISAO,
    )).first()
    if existente:
        raise HTTPException(status_code=409, detail="Este desenho já está em revisão.")
    motivo = str(dados.get("motivo") or "").strip()
    if not motivo:
        raise HTTPException(status_code=400, detail="Informe o motivo do retorno para revisão.")
    revisao = RevisaoDesenho(
        componente_id=componente_id, desenho_origem_id=desenho_id,
        motivo=motivo, retornada_por=usuario_atual.nome,
    )
    session.add(revisao)
    registrar_historico(
        session, componente_id, usuario_atual.nome, "Desenho retornado para revisão",
        f"Desenho '{desenho.codigo}' da ID '{id_tecnica.numero}': {motivo}. O componente permaneceu em andamento.",
    )
    session.commit()
    session.refresh(revisao)
    return {"message": "Desenho retornado para revisão sem bloquear o componente.", "id": revisao.id}


@router.post("/{id_tecnica_id}/desenhos/{desenho_id}/cancelar-revisao", dependencies=[Depends(exigir_operacao)])
def cancelar_revisao_desenho(
    componente_id: str, id_tecnica_id: str, desenho_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual),
):
    _obter_componente(session, componente_id)
    id_tecnica = session.get(IDTecnica, id_tecnica_id)
    desenho = session.get(Desenho, desenho_id)
    if not id_tecnica or id_tecnica.componente_id != componente_id or not desenho or desenho.id_tecnica_id != id_tecnica_id:
        raise HTTPException(status_code=404, detail="Desenho não encontrado nesta ID.")
    revisao = session.exec(select(RevisaoDesenho).where(
        RevisaoDesenho.desenho_origem_id == desenho_id,
        RevisaoDesenho.status == StatusRevisaoDesenhoEnum.EM_REVISAO,
    )).first()
    if not revisao:
        raise HTTPException(status_code=409, detail="Este desenho não possui revisão aberta.")
    revisao.status = StatusRevisaoDesenhoEnum.CANCELADA
    revisao.cancelada_por = usuario_atual.nome
    revisao.cancelada_em = datetime.utcnow()
    session.add(revisao)
    registrar_historico(
        session, componente_id, usuario_atual.nome, "Revisão de desenho cancelada",
        f"Retorno do desenho '{desenho.codigo}' da ID '{id_tecnica.numero}' cancelado.",
    )
    session.commit()
    return {"message": "Revisão do desenho cancelada."}


@router.patch("/{id_tecnica_id}/desenhos/{desenho_id}/recebimento", dependencies=[Depends(exigir_operacao)])
def alterar_recebimento_desenho(
    componente_id: str, id_tecnica_id: str, desenho_id: str, dados: dict,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual),
):
    _obter_componente(session, componente_id)
    id_tecnica = session.get(IDTecnica, id_tecnica_id)
    desenho = session.get(Desenho, desenho_id)
    if not id_tecnica or id_tecnica.componente_id != componente_id:
        raise HTTPException(status_code=404, detail="ID tecnica nao encontrada.")
    if not desenho or desenho.id_tecnica_id != id_tecnica_id:
        raise HTTPException(status_code=404, detail="Desenho nao encontrado nesta ID.")
    if not isinstance(dados.get("recebido"), bool):
        raise HTTPException(status_code=400, detail="Informe se o desenho veio ou nao veio.")

    desenho.recebido = dados["recebido"]
    desenho.conferencia_atualizada_em = datetime.utcnow()
    desenho.conferencia_atualizada_por = usuario_atual.nome
    session.add(desenho)
    situacao = "Veio" if desenho.recebido else "Nao veio"
    registrar_historico(
        session, componente_id, usuario_atual.nome, "Conferencia de desenho",
        f"Desenho '{desenho.codigo}' da ID '{id_tecnica.numero}' marcado como '{situacao}'. O andamento do componente nao foi alterado.",
    )
    session.commit()
    return {"message": f"Desenho marcado como '{situacao}'.", "recebido": desenho.recebido}


@router.delete("/{id_tecnica_id}", dependencies=[Depends(exigir_operacao)])
def excluir_folha_id(
    componente_id: str,
    id_tecnica_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual),
):
    """Remove uma importacao feita no componente incorreto, incluindo desenhos e arquivo."""
    componente = _obter_componente(session, componente_id)
    id_tecnica = session.get(IDTecnica, id_tecnica_id)
    if not id_tecnica or id_tecnica.componente_id != componente_id:
        raise HTTPException(status_code=404, detail="ID tecnica nao encontrada")

    dependentes = session.exec(
        select(IDTecnica).where(
            (IDTecnica.id_origem_id == id_tecnica.id) |
            (IDTecnica.substitui_id == id_tecnica.id)
        )
    ).all()
    if dependentes:
        raise HTTPException(
            status_code=409,
            detail="Esta ID possui revisoes ou substituicoes vinculadas. Exclua primeiro a ID mais recente.",
        )

    caminho_arquivo = Path(id_tecnica.arquivo_caminho) if id_tecnica.arquivo_caminho else None
    desenhos = session.exec(select(Desenho).where(Desenho.id_tecnica_id == id_tecnica.id)).all()
    ids_desenhos = [desenho.id for desenho in desenhos]
    revisoes_abertas = session.exec(select(RevisaoDesenho).where(
        RevisaoDesenho.desenho_origem_id.in_(ids_desenhos),
        RevisaoDesenho.status == StatusRevisaoDesenhoEnum.EM_REVISAO,
    )).all() if ids_desenhos else []
    if revisoes_abertas:
        raise HTTPException(
            status_code=409,
            detail="Esta ID possui desenho(s) em revisão. Cancele as revisões individuais antes de excluir a ID.",
        )
    anexos = session.exec(
        select(Anexo).where(
            Anexo.componente_id == componente_id,
            Anexo.caminho == id_tecnica.arquivo_caminho,
        )
    ).all()

    if id_tecnica.pendencia_revisao_id:
        pendencia = session.get(Pendencia, id_tecnica.pendencia_revisao_id)
        if pendencia:
            session.delete(pendencia)
        outras_pendencias = session.exec(
            select(Pendencia).where(
                Pendencia.componente_id == componente_id,
                Pendencia.bloqueante == True,
                Pendencia.status == StatusPendenciaEnum.ABERTA,
                Pendencia.id != id_tecnica.pendencia_revisao_id,
            )
        ).all()
        if not outras_pendencias and componente.status == StatusComponenteEnum.BLOQUEADO:
            componente.status = StatusComponenteEnum.EM_ANDAMENTO
            session.add(componente)
    for desenho in desenhos:
        session.delete(desenho)
    for anexo in anexos:
        session.delete(anexo)

    numero = id_tecnica.numero
    versao = id_tecnica.versao
    session.delete(id_tecnica)
    registrar_historico(
        session, componente_id, usuario_atual.nome, "Exclusao de Folha de ID",
        f"ID '{numero}' versao {versao} excluida do componente, com {len(desenhos)} desenho(s).",
    )
    session.commit()
    sincronizar_status_equipamento(session, componente.equipamento_id)
    session.commit()

    if caminho_arquivo and caminho_arquivo.is_file():
        caminho_arquivo.unlink()
    return {"message": "ID excluida com sucesso."}


@router.get("/{id_tecnica_id}/arquivo")
def baixar_pdf(
    componente_id: str,
    id_tecnica_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual),
):
    id_tecnica = session.get(IDTecnica, id_tecnica_id)
    if not id_tecnica or id_tecnica.componente_id != componente_id or not id_tecnica.arquivo_caminho:
        raise HTTPException(status_code=404, detail="Arquivo da ID não encontrado")
    caminho = Path(id_tecnica.arquivo_caminho)
    if not caminho.is_file():
        raise HTTPException(status_code=404, detail="O PDF não está disponível no armazenamento.")
    return FileResponse(caminho, media_type="application/pdf", filename=id_tecnica.arquivo_nome or "folha-id.pdf")
