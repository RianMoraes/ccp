import re
import os
import shutil
import unicodedata
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path

import pymupdf as fitz
import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


class FolhaIDInvalida(ValueError):
    pass


def _limpar(valor):
    if valor is None:
        return ""
    return " ".join(str(valor).replace("\n", " ").split()).strip()


def _normalizar(valor):
    texto = unicodedata.normalize("NFKD", _limpar(valor))
    return "".join(c for c in texto if not unicodedata.combining(c)).upper()


def _valor_campo(tabelas, rotulo):
    alvo = _normalizar(rotulo)
    for tabela in tabelas:
        for linha in tabela:
            for indice, celula in enumerate(linha):
                bruto = str(celula or "").strip()
                normalizado = _normalizar(bruto)
                if not normalizado.startswith(alvo):
                    continue
                partes = [parte.strip() for parte in bruto.replace(":", "\n", 1).splitlines() if parte.strip()]
                if len(partes) > 1:
                    return _limpar(" ".join(partes[1:]))
                for seguinte in linha[indice + 1:]:
                    if _limpar(seguinte):
                        return _limpar(seguinte)
    return None


def _inteiro(valor, padrao=1):
    encontrado = re.search(r"\d+", _limpar(valor))
    return int(encontrado.group()) if encontrado else padrao


def _codigo_revisao(valor):
    codigo = _limpar(valor)
    encontrado = re.match(r"^(.*?)[\s-]+(R\d+)$", codigo, re.IGNORECASE)
    if encontrado:
        return encontrado.group(1).strip(), encontrado.group(2).upper()
    return codigo, None


def _quantidade(valor):
    original = _limpar(valor)
    numero = _inteiro(original)
    unidade = re.sub(r"^[\s0]*\d+[\s]*", "", original).strip() or None
    return numero, unidade, original


def _configurar_tesseract():
    configurado = os.getenv("TESSERACT_CMD")
    candidatos = [
        configurado,
        shutil.which("tesseract"),
        str(Path.home() / "AppData/Local/Programs/Tesseract-OCR/tesseract.exe"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    ]
    executavel = next((c for c in candidatos if c and Path(c).is_file()), None)
    if not executavel:
        raise FolhaIDInvalida(
            "Este PDF parece digitalizado, mas o mecanismo OCR Tesseract não está instalado no servidor."
        )
    pytesseract.pytesseract.tesseract_cmd = executavel


def _preparar_imagem_ocr(pagina):
    # Aproximadamente 216 DPI. Nos formulários testados, preserva melhor os
    # caracteres finos das tabelas que ampliações excessivas.
    pixmap = pagina.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
    imagem = Image.open(BytesIO(pixmap.tobytes("png"))).convert("L")
    return ImageOps.autocontrast(imagem)


def _campo_texto_ocr(texto, campo, padrao_linha=True):
    if padrao_linha:
        encontrado = re.search(rf"(?im)^\s*{campo}\s*:?\s*(.+?)\s*$", texto)
    else:
        encontrado = re.search(rf"(?i)\b{campo}\s*:?\s*([^\n|]+)", texto)
    return _limpar(encontrado.group(1)) if encontrado else None


def _extrair_campos_por_posicao(imagem):
    """Lê os valores abaixo dos rótulos do cabeçalho preservando as colunas."""
    dados = pytesseract.image_to_data(
        imagem, lang="por+eng", config="--psm 6", output_type=pytesseract.Output.DICT
    )
    palavras = []
    for indice, texto in enumerate(dados["text"]):
        texto = _limpar(texto)
        if not texto:
            continue
        palavras.append({
            "texto": texto,
            "normalizado": re.sub(r"[^A-Z0-9]", "", _normalizar(texto)),
            "x": dados["left"][indice],
            "y": dados["top"][indice],
            "w": dados["width"][indice],
            "h": dados["height"][indice],
        })

    def ancora(rotulo, y_referencia=None):
        alvo = _normalizar(rotulo)
        candidatos = [p for p in palavras if p["normalizado"] == alvo]
        if y_referencia is None:
            return min(candidatos, key=lambda p: p["y"], default=None)
        return min(candidatos, key=lambda p: abs(p["y"] - y_referencia), default=None)

    def valor_abaixo(rotulo, proximo_rotulo, margem_vertical=95, referencia=None):
        referencia_y = ancora(referencia)["y"] if referencia and ancora(referencia) else None
        inicio = ancora(rotulo, referencia_y)
        fim = ancora(proximo_rotulo, inicio["y"]) if proximo_rotulo and inicio else None
        if not inicio:
            return None
        x_inicio = inicio["x"] - 8
        x_fim = (fim["x"] - 8) if fim and abs(fim["y"] - inicio["y"]) < 45 else imagem.width + 1
        y_inicio = inicio["y"] + max(inicio["h"] - 5, 15)
        candidatos = [
            p for p in palavras
            if y_inicio <= p["y"] <= inicio["y"] + margem_vertical
            and x_inicio <= p["x"] + (p["w"] / 2) < x_fim
            and re.search(r"[A-Z0-9]", p["normalizado"])
        ]
        if not candidatos:
            return None
        primeira_linha = min(p["y"] for p in candidatos)
        candidatos = [p for p in candidatos if abs(p["y"] - primeira_linha) <= 18]
        return _limpar(" ".join(p["texto"] for p in sorted(candidatos, key=lambda p: p["x"]))) or None

    return {
        "cliente": valor_abaixo("CLIENTE", "OP"),
        "local": valor_abaixo("LOCAL", "RV"),
        "equipamento": valor_abaixo("EQUIPAMENTO", "COMPONENTE"),
        "componente": valor_abaixo("COMPONENTE", "LIBERADO"),
        "liberado_por": valor_abaixo("LIBERADO", "DATA"),
        "data_liberacao_bruta": valor_abaixo("DATA", None, referencia="EQUIPAMENTO"),
    }


def _extrair_desenhos_ocr(textos_por_pagina):
    desenhos = []
    vistos = set()
    codigo_rx = re.compile(r"(?<![A-Z0-9])([A-Z1|]{1,5}[I0-9]?-?[A-Z0-9]*[-.]\s*\d{2,5}[.]\d{2,5})(?:\s*(R[I1\d]+))?\b", re.I)
    for pagina, texto in textos_por_pagina:
        em_tabela = False
        item_sequencial = 0
        for linha_bruta in texto.splitlines():
            linha = _limpar(linha_bruta).replace("|", " ")
            normalizada = _normalizar(linha)
            if "RELACAO DE DESENHOS" in normalizada:
                em_tabela = True
                continue
            if "DESENHO" in normalizada and ("DESCRICAO" in normalizada or "QTD" in normalizada):
                em_tabela = True
                continue
            if any(marcador in normalizada for marcador in ("CONFERIDO", "APROVADO", "LISTADO", "CORTE CNC")):
                em_tabela = False
                continue
            codigo_match = codigo_rx.search(linha)
            if not codigo_match:
                continue

            # O próprio padrão de um código técnico é uma âncora confiável. Isso
            # cobre digitalizações em que o cabeçalho da tabela ficou ilegível.
            em_tabela = True

            codigo = re.sub(r"\s+", "", codigo_match.group(1)).upper()
            codigo = codigo.replace("|", "I")
            prefixo_match = re.match(r"^([A-Z1]+)([-.])(.+)$", codigo)
            if prefixo_match:
                prefixo, separador, restante = prefixo_match.groups()
                prefixos_ti_confundidos = {"T", "T1", "1", "I", "TL"}
                if prefixo in prefixos_ti_confundidos:
                    prefixo = "TI"
                codigo = f"{prefixo}-{restante}" if separador == "." else f"{prefixo}{separador}{restante}"
            revisao = codigo_match.group(2).upper().replace("I", "1") if codigo_match.group(2) else None
            antes = linha[:codigo_match.start()].strip()
            depois = linha[codigo_match.end():].strip()
            item_match = re.search(r"\d+", antes)
            item = int(item_match.group()) if item_match else None

            tokens = depois.split()
            copias = 1
            if tokens and re.fullmatch(r"\d+", tokens[0]):
                copias = int(tokens.pop(0))

            quantidade = 1
            unidade = None
            quantidade_original = "1"
            if tokens:
                ultimo = tokens[-1].upper().replace("O", "0")
                penultimo = tokens[-2].upper() if len(tokens) > 1 else ""
                if ultimo == "CJ" and re.fullmatch(r"\d+", penultimo.replace("O", "0")):
                    quantidade_original = f"{penultimo} CJ"
                    quantidade = int(penultimo.replace("O", "0"))
                    unidade = "CJ"
                    tokens = tokens[:-2]
                else:
                    qtd_match = re.fullmatch(r"0*(\d+)(CJ)?", ultimo)
                    if qtd_match:
                        quantidade = int(qtd_match.group(1))
                        unidade = "CJ" if qtd_match.group(2) else None
                        quantidade_original = tokens[-1]
                        tokens = tokens[:-1]

            descricao = _limpar(" ".join(tokens))
            if not descricao:
                continue
            item_sequencial += 1
            chave = (codigo, revisao or "", descricao.upper(), quantidade)
            if chave in vistos:
                continue
            vistos.add(chave)
            desenhos.append({
                "codigo": codigo,
                "revisao": revisao,
                "descricao": descricao,
                "copias": copias,
                "quantidade": max(quantidade, 1),
                "unidade": unidade,
                "quantidade_original": quantidade_original,
                "item": item or item_sequencial,
                "pagina_origem": pagina,
            })
    return desenhos


def _analisar_com_ocr(documento=None, imagens_originais=None):
    _configurar_tesseract()
    idiomas = "por+eng"
    textos_psm3 = []
    textos_psm4 = []
    textos_psm6 = []
    campos_posicionais = {}
    fontes = imagens_originais if imagens_originais is not None else documento
    for numero, fonte in enumerate(fontes, 1):
        if imagens_originais is not None:
            imagem = ImageOps.exif_transpose(Image.open(BytesIO(fonte))).convert("L")
            imagem = ImageOps.autocontrast(imagem)
        else:
            imagem = _preparar_imagem_ocr(fonte)
        if numero == 1:
            campos_posicionais = _extrair_campos_por_posicao(imagem)
        textos_psm3.append((numero, pytesseract.image_to_string(imagem, lang=idiomas, config="--psm 3")))
        textos_psm4.append((numero, pytesseract.image_to_string(imagem, lang=idiomas, config="--psm 4")))
        textos_psm6.append((numero, pytesseract.image_to_string(imagem, lang=idiomas, config="--psm 6")))

    desenhos_psm3 = _extrair_desenhos_ocr(textos_psm3)
    desenhos_psm4 = _extrair_desenhos_ocr(textos_psm4)
    desenhos_psm6 = _extrair_desenhos_ocr(textos_psm6)
    candidatos_ocr = [
        (desenhos_psm3, textos_psm3),
        (desenhos_psm4, textos_psm4),
        (desenhos_psm6, textos_psm6),
    ]
    desenhos, textos_por_pagina = max(candidatos_ocr, key=lambda candidato: len(candidato[0]))
    texto_completo = "\n".join(texto for _, texto in textos_psm3 + textos_psm4 + textos_psm6)
    if not desenhos:
        raise FolhaIDInvalida(
            "O OCR leu o documento, mas não conseguiu identificar a tabela de desenhos. Confira a qualidade da digitalização."
        )

    def numero(campo):
        encontrado = re.search(rf"(?i)\b{campo}\s*:?\s*([0-9O]+/[0-9O]+)", texto_completo)
        return encontrado.group(1).replace("O", "0") if encontrado else None

    numero_id = numero("[I1]D")
    if not numero_id:
        raise FolhaIDInvalida("O OCR não conseguiu identificar o número da ID.")

    op = numero("OP")
    rv = numero("RV")
    if not op or not rv:
        # Alguns layouts antigos separam visualmente o rótulo e seu valor em
        # blocos distintos. A ordem OP -> RV permanece estável no formulário.
        candidatos = re.findall(r"\b\d{2,6}/\d{2,4}\b", texto_completo)
        candidatos = [valor for valor in candidatos if valor != numero_id]
        candidatos = [
            valor for valor in candidatos
            if not (int(valor.split("/")[0]) <= 31 and int(valor.split("/")[1]) <= 12)
        ]
        if not op and candidatos:
            op = candidatos[0]
        if not rv and len(candidatos) > 1:
            rv = candidatos[1]

    cliente = campos_posicionais.get("cliente") or _campo_texto_ocr(texto_completo, "CLIENTE")
    local = campos_posicionais.get("local") or _campo_texto_ocr(texto_completo, "LOCAL")
    equipamento = campos_posicionais.get("equipamento") or _campo_texto_ocr(texto_completo, "EQUIPAMENTO")
    componente = campos_posicionais.get("componente") or _campo_texto_ocr(texto_completo, "COMPONENTE")
    liberado_por = campos_posicionais.get("liberado_por") or _campo_texto_ocr(texto_completo, "LIBERADO POR")
    data_liberacao = None
    texto_data = campos_posicionais.get("data_liberacao_bruta") or texto_completo
    data_match = re.search(r"(?i)(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}))?", texto_data)
    if data_match:
        bruto = data_match.group(1) + ((" " + data_match.group(2)) if data_match.group(2) else "")
        formato = "%d/%m/%Y %H:%M" if data_match.group(2) else "%d/%m/%Y"
        try:
            data_liberacao = datetime.strptime(bruto, formato).isoformat()
        except ValueError:
            pass

    return {
        "modelo_documento": "ocr_digitalizado",
        "modo_leitura": "ocr",
        "paginas": len(fontes),
        "numero_id": numero_id,
        "op": op,
        "rv": rv,
        "cliente": cliente,
        "local": local,
        "equipamento": equipamento,
        "componente": componente,
        "liberado_por": liberado_por,
        "data_liberacao": data_liberacao,
        "desenhos": desenhos,
    }


def _extrair_desenhos(tabelas_por_pagina):
    desenhos = []
    vistos = set()
    for pagina, tabelas in tabelas_por_pagina:
        for tabela in tabelas:
            cabecalho_indice = None
            indices = {}
            for idx, linha in enumerate(tabela):
                normalizados = [_normalizar(c) for c in linha]
                if "DESENHO" in normalizados and any("DESCRICAO" in c for c in normalizados):
                    cabecalho_indice = idx
                    for col, nome in enumerate(normalizados):
                        if nome == "ITEM": indices["item"] = col
                        elif nome == "DESENHO": indices["desenho"] = col
                        elif nome.startswith("COP"): indices["copias"] = col
                        elif "DESCRICAO" in nome: indices["descricao"] = col
                        elif nome.startswith("QTD"): indices["quantidade"] = col
                    break
            if cabecalho_indice is None or "desenho" not in indices:
                continue

            for linha in tabela[cabecalho_indice + 1:]:
                codigo_bruto = linha[indices["desenho"]] if indices["desenho"] < len(linha) else None
                codigo, revisao = _codigo_revisao(codigo_bruto)
                if not codigo or not re.search(r"[A-Z]", codigo, re.IGNORECASE):
                    continue
                descricao = _limpar(linha[indices["descricao"]]) if indices.get("descricao", -1) < len(linha) else ""
                qtd_bruta = linha[indices["quantidade"]] if indices.get("quantidade", -1) < len(linha) else "1"
                quantidade, unidade, quantidade_original = _quantidade(qtd_bruta)
                copias = _inteiro(linha[indices["copias"]]) if indices.get("copias", -1) < len(linha) else 1
                item = _inteiro(linha[indices["item"]], None) if "item" in indices and indices["item"] < len(linha) else None
                chave = (codigo.upper(), revisao or "", descricao.upper(), quantidade)
                if chave in vistos:
                    continue
                vistos.add(chave)
                desenhos.append({
                    "codigo": codigo,
                    "revisao": revisao,
                    "descricao": descricao,
                    "copias": copias,
                    "quantidade": quantidade,
                    "unidade": unidade,
                    "quantidade_original": quantidade_original,
                    "item": item,
                    "pagina_origem": pagina,
                })
    return desenhos


def analisar_folha_id(conteudo: bytes):
    try:
        documento = fitz.open(stream=conteudo, filetype="pdf")
    except Exception as exc:
        raise FolhaIDInvalida("Não foi possível abrir o PDF enviado.") from exc

    if documento.is_encrypted:
        raise FolhaIDInvalida("O PDF está protegido por senha.")

    textos = []
    tabelas_por_pagina = []
    todas_tabelas = []
    for numero, pagina in enumerate(documento, 1):
        textos.append(pagina.get_text("text"))
        try:
            # PyMuPDF imprime uma recomendação opcional sobre pymupdf_layout
            # diretamente no terminal. A extração nativa já atende aos modelos
            # suportados, então mantemos o log do servidor limpo.
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                tabelas = [tabela.extract() for tabela in pagina.find_tables().tables]
        except Exception:
            tabelas = []
        tabelas_por_pagina.append((numero, tabelas))
        todas_tabelas.extend(tabelas)

    texto = "\n".join(textos)
    desenhos = _extrair_desenhos(tabelas_por_pagina)
    if not desenhos:
        return _analisar_com_ocr(documento)

    def regex(campo):
        encontrado = re.search(rf"\b{campo}\s*:?\s*([0-9]+/[0-9]+)", texto, re.IGNORECASE)
        return encontrado.group(1) if encontrado else None

    numero_id = regex("ID")
    if not numero_id:
        raise FolhaIDInvalida("O número da ID não foi encontrado no documento.")

    data_liberacao = None
    liberado_por = _valor_campo(todas_tabelas, "LIBERADO POR")
    for tabela in todas_tabelas:
        for linha in tabela:
            if any(_normalizar(c).startswith("LIBERADO POR") for c in linha):
                for indice, celula in enumerate(linha):
                    rotulo_data = _normalizar(celula).rstrip(":")
                    if rotulo_data == "DATA" or rotulo_data.startswith("DATA "):
                        candidato = _limpar(celula).replace("DATA", "", 1).replace(":", "").strip()
                        if not candidato:
                            candidato = next((_limpar(c) for c in linha[indice + 1:] if _limpar(c)), "")
                        encontrado = re.search(r"\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?", candidato)
                        if encontrado:
                            formato = "%d/%m/%Y %H:%M" if " " in encontrado.group() else "%d/%m/%Y"
                            data_liberacao = datetime.strptime(encontrado.group(), formato).isoformat()
                        break

    modelo = "modelo_2" if any("ITEM" in [_normalizar(c) for c in linha] for tabela in todas_tabelas for linha in tabela) else "modelo_1"
    return {
        "modelo_documento": modelo,
        "modo_leitura": "texto",
        "paginas": len(documento),
        "numero_id": numero_id,
        "op": regex("OP") or _valor_campo(todas_tabelas, "OP"),
        "rv": regex("RV") or _valor_campo(todas_tabelas, "RV"),
        "cliente": _valor_campo(todas_tabelas, "CLIENTE"),
        "local": _valor_campo(todas_tabelas, "LOCAL"),
        "equipamento": _valor_campo(todas_tabelas, "EQUIPAMENTO"),
        "componente": _valor_campo(todas_tabelas, "COMPONENTE"),
        "liberado_por": liberado_por,
        "data_liberacao": data_liberacao,
        "desenhos": desenhos,
    }


def analisar_folha_id_imagens(conteudos):
    if not conteudos:
        raise FolhaIDInvalida("Nenhuma imagem foi enviada.")
    try:
        for conteudo in conteudos:
            imagem = Image.open(BytesIO(conteudo))
            if imagem.format not in {"JPEG", "MPO"}:
                raise FolhaIDInvalida("Envie somente imagens JPG ou JPEG.")
            imagem.verify()
    except FolhaIDInvalida:
        raise
    except Exception as exc:
        raise FolhaIDInvalida("Uma das imagens JPG/JPEG está inválida ou corrompida.") from exc
    return _analisar_jpegs_por_regioes(conteudos)


def _agrupar_indices(indices, distancia=3):
    grupos = []
    for indice in indices:
        indice = int(indice)
        if not grupos or indice - grupos[-1][-1] > distancia:
            grupos.append([indice])
        else:
            grupos[-1].append(indice)
    return [round((grupo[0] + grupo[-1]) / 2) for grupo in grupos]


def _corrigir_inclinacao_jpeg(imagem):
    pixels = np.asarray(imagem)
    binaria = cv2.adaptiveThreshold(
        pixels, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 41, 13,
    )
    linhas = cv2.HoughLinesP(
        binaria, 1, np.pi / 1800, threshold=300,
        minLineLength=max(round(imagem.width * 0.35), 300), maxLineGap=50,
    )
    angulos = []
    if linhas is not None:
        for x1, y1, x2, y2 in linhas.reshape(-1, 4):
            angulo = np.degrees(np.arctan2(int(y2) - int(y1), int(x2) - int(x1)))
            if abs(angulo) < 5:
                angulos.append(angulo)
    if not angulos:
        raise FolhaIDInvalida(
            "Não foi possível determinar a inclinação da tabela nesta imagem JPEG."
        )
    angulo = float(np.median(angulos))
    return imagem.rotate(angulo, Image.Resampling.BICUBIC, expand=False, fillcolor=255)


def _estrutura_formulario_jpeg(imagem):
    pixels = np.asarray(imagem)
    altura, largura = pixels.shape
    binaria = cv2.adaptiveThreshold(
        pixels, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 41, 13,
    )
    horizontais = cv2.morphologyEx(
        binaria,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(largura // 35, 50), 1)),
    )
    verticais = cv2.morphologyEx(
        binaria,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(altura // 35, 40))),
    )
    linhas_y = _agrupar_indices(
        np.where((horizontais > 0).sum(axis=1) > largura * 0.35)[0], distancia=6
    )
    linhas_x = _agrupar_indices(
        np.where((verticais > 0).sum(axis=0) > altura * 0.18)[0], distancia=6
    )
    linhas_x = [x for x in linhas_x if largura * 0.02 < x < largura * 0.98]
    if len(linhas_y) < 6 or len(linhas_x) < 9:
        raise FolhaIDInvalida(
            "Não foi possível localizar com segurança as linhas e colunas da Folha de ID nesta imagem JPEG."
        )
    return linhas_y, linhas_x


def _preparar_recorte_ocr(imagem, caixa):
    x1, y1, x2, y2 = [round(valor) for valor in caixa]
    if x2 <= x1 or y2 <= y1:
        return None
    recorte = ImageOps.autocontrast(imagem.crop((x1, y1, x2, y2)))
    return recorte.resize((recorte.width * 2, recorte.height * 2), Image.Resampling.LANCZOS)


def _ocr_recorte(imagem, caixa, psm=7, caracteres=None, idioma="por+eng"):
    recorte = _preparar_recorte_ocr(imagem, caixa)
    if recorte is None:
        return ""
    config = f"--psm {psm}"
    if caracteres:
        config += f" -c tessedit_char_whitelist={caracteres}"
    return _limpar(pytesseract.image_to_string(recorte, lang=idioma, config=config))


def _ocr_numero_celula(imagem, caixa):
    recorte = _preparar_recorte_ocr(imagem, caixa)
    if recorte is None:
        return None
    texto = _limpar(pytesseract.image_to_string(
        recorte, lang="eng", config="--psm 8 -c tessedit_char_whitelist=0123456789/O"
    ))
    encontrado = re.search(r"([0-9O]{2,6}/[0-9O]{2,4})", texto)
    return encontrado.group(1).replace("O", "0") if encontrado else None


def _ocr_descricao_celula(imagem, caixa):
    recorte = _preparar_recorte_ocr(imagem, caixa)
    if recorte is None:
        return ""
    dados = pytesseract.image_to_data(
        recorte, lang="por+eng", config="--psm 7", output_type=pytesseract.Output.DICT
    )
    tokens = []
    for indice, texto in enumerate(dados["text"]):
        texto = _limpar(texto)
        if not texto:
            continue
        try:
            confianca = float(dados["conf"][indice])
        except (TypeError, ValueError):
            confianca = -1
        tokens.append([
            texto, confianca, int(dados["left"][indice]), int(dados["width"][indice])
        ])

    while tokens:
        texto, confianca, esquerda, _ = tokens[-1]
        alfanumerico = re.sub(r"[^A-Za-zÀ-ÿ0-9]", "", texto)
        distancia_anterior = 0
        if len(tokens) > 1:
            anterior = tokens[-2]
            distancia_anterior = esquerda - (anterior[2] + anterior[3])
        isolado = distancia_anterior > max(60, recorte.width * 0.06)
        if (
            not alfanumerico
            or (len(alfanumerico) <= 2 and confianca < 65)
            or (len(alfanumerico) <= 3 and isolado)
        ):
            tokens.pop()
        else:
            break

    descricao = _limpar(" ".join(token[0] for token in tokens)).strip(" |,")
    if "FLANGE" in _normalizar(descricao):
        descricao = re.sub(r"\b9(?=\d{3}(?:\D|$))", "Ø", descricao)
    return descricao


def _interpretar_codigo_jpeg(texto):
    texto = re.sub(r"\s+", "", texto).upper().replace("|", "I")
    encontrado = re.search(
        r"((?:[A-Z][A-Z0-9]{0,4}-\d{3,5}\.\d{3}|[A-Z]\d{4,6}\.\d{4}))(R\d{1,2})?",
        texto,
    )
    if not encontrado:
        return None
    codigo = encontrado.group(1)
    prefixo = codigo.split("-", 1)[0] if "-" in codigo else ""
    if prefixo in {"T", "T1", "TL", "1"}:
        codigo = "TI-" + codigo.split("-", 1)[1]
    return codigo, encontrado.group(2)


def _analisar_jpegs_por_regioes(conteudos):
    _configurar_tesseract()
    desenhos = []
    cabecalho = {}
    for pagina_numero, conteudo in enumerate(conteudos, 1):
        original = ImageOps.exif_transpose(Image.open(BytesIO(conteudo))).convert("L")
        imagem = _corrigir_inclinacao_jpeg(ImageOps.autocontrast(original))
        ys, xs = _estrutura_formulario_jpeg(imagem)

        # Estrutura esperada: quatro linhas de cabeçalho, cabeçalho da tabela
        # e uma sequência regular de linhas de desenhos.
        y_topo, y_cliente, y_local, y_campos, y_tabela = ys[:5]
        linhas_dados = ys[4:]
        x_esquerda, x_desenho, x_copias, x_descricao, x_qtd = xs[:5]
        x_cliente = x_qtd
        x_op = xs[-3]
        x_codigo = xs[-2]
        x_direita = xs[-1]

        margem = max(round((y_tabela - y_campos) * 0.08), 4)
        if pagina_numero == 1:
            texto_id = _ocr_recorte(imagem, (imagem.width * 0.72, y_topo * 0.30, x_direita, y_topo + 35), 6)
            id_match = re.search(r"[I1]D\s*:\s*([0-9O]{2,6}/[0-9O]{2,4})", texto_id, re.I)

            def caixa_valor(x1, y1, x2, y2):
                altura_celula = y2 - y1
                return (x1 + margem, y1 + altura_celula * 0.42, x2 - margem, y2 - margem)

            def valor(x1, y1, x2, y2):
                return _ocr_recorte(imagem, caixa_valor(x1, y1, x2, y2)) or None

            cabecalho = {
                "numero_id": id_match.group(1).replace("O", "0") if id_match else None,
                "cliente": valor(x_cliente, y_topo, x_op, y_cliente),
                "op": _ocr_numero_celula(imagem, caixa_valor(x_op, y_topo, x_codigo, y_cliente)),
                "local": valor(x_cliente, y_cliente, x_op, y_local),
                "rv": _ocr_numero_celula(imagem, caixa_valor(x_op, y_cliente, x_codigo, y_local)),
                "equipamento": valor(x_esquerda, y_local, x_cliente, y_campos),
                "componente": valor(x_cliente, y_local, x_op, y_campos),
                "liberado_por": valor(x_op, y_local, x_codigo, y_campos),
                "data_bruta": valor(x_codigo, y_local, x_direita, y_campos),
            }

        for y1, y2 in zip(linhas_dados, linhas_dados[1:]):
            codigo_lido = None
            for psm_codigo, fator_margem in ((7, 0.09), (8, 0.12)):
                margem_codigo_y = max(round((y2 - y1) * fator_margem), 5)
                codigo_bruto = _ocr_recorte(
                    imagem,
                    (x_esquerda + 5, y1 + margem_codigo_y, x_desenho - 5, y2 - margem_codigo_y),
                    psm_codigo,
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-",
                    "eng",
                )
                codigo_lido = _interpretar_codigo_jpeg(codigo_bruto)
                if codigo_lido:
                    break
            if not codigo_lido:
                continue
            codigo, revisao = codigo_lido
            margem_linha = max(round((y2 - y1) * 0.09), 4)
            copias_bruto = _ocr_recorte(
                imagem, (x_desenho + margem, y1 + margem_linha, x_copias - margem, y2 - margem_linha),
                10, "0123456789"
            )
            descricao = _ocr_descricao_celula(
                imagem, (x_copias + margem, y1 + margem_linha, x_descricao - margem, y2 - margem_linha)
            )
            qtd_bruta = _ocr_recorte(
                imagem, (x_descricao + margem, y1 + margem_linha, x_qtd - margem, y2 - margem_linha),
                7, "0123456789CJ"
            ).replace("O", "0").replace(" ", "").upper()
            digitos = "".join(re.findall(r"\d", qtd_bruta))
            if len(digitos) == 3 and digitos.startswith("0"):
                digitos = digitos[:2]
            quantidade = int(digitos) if digitos else 1
            unidade = "CJ" if "CJ" in qtd_bruta else None
            desenhos.append({
                "codigo": codigo,
                "revisao": revisao,
                "descricao": descricao,
                "copias": _inteiro(copias_bruto),
                "quantidade": max(quantidade, 1),
                "unidade": unidade,
                "quantidade_original": f"{quantidade:02d}{unidade or ''}",
                "item": len(desenhos) + 1,
                "pagina_origem": pagina_numero,
            })

    if not cabecalho.get("numero_id"):
        raise FolhaIDInvalida("Não foi possível identificar o número da ID no cabeçalho da imagem JPEG.")
    if not desenhos:
        raise FolhaIDInvalida("A tabela foi localizada, mas nenhum desenho foi reconhecido nas imagens JPEG.")
    data_liberacao = None
    data_match = re.search(r"\d{2}/\d{2}/\d{4}", cabecalho.get("data_bruta") or "")
    if data_match:
        try:
            data_liberacao = datetime.strptime(data_match.group(), "%d/%m/%Y").isoformat()
        except ValueError:
            pass
    return {
        "modelo_documento": "jpeg_por_regioes",
        "modo_leitura": "ocr_regioes",
        "paginas": len(conteudos),
        "numero_id": cabecalho["numero_id"],
        "op": cabecalho.get("op"),
        "rv": cabecalho.get("rv"),
        "cliente": cabecalho.get("cliente"),
        "local": cabecalho.get("local"),
        "equipamento": cabecalho.get("equipamento"),
        "componente": cabecalho.get("componente"),
        "liberado_por": cabecalho.get("liberado_por"),
        "data_liberacao": data_liberacao,
        "desenhos": desenhos,
    }
