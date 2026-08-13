from io import BytesIO

import pymupdf as fitz
from PIL import Image
from PIL import ImageOps


LIMITE_COMPACTACAO = 100 * 1024
ECONOMIA_MINIMA = 0.10
DPI_DIGITALIZADO = 300
QUALIDADE_JPEG = 75


def _parece_digitalizado(documento):
    if not len(documento):
        return False
    paginas_com_imagem = 0
    paginas_com_texto = 0
    for pagina in documento:
        if len(pagina.get_text("text").strip()) >= 100:
            paginas_com_texto += 1
        if pagina.get_images(full=True):
            paginas_com_imagem += 1
    return paginas_com_imagem == len(documento) and paginas_com_texto == 0


def _compactar_digitalizado(documento):
    destino = fitz.open()
    try:
        for pagina in documento:
            pixmap = pagina.get_pixmap(dpi=DPI_DIGITALIZADO, alpha=False)
            imagem = Image.open(BytesIO(pixmap.tobytes("png"))).convert("L")
            jpeg = BytesIO()
            imagem.save(
                jpeg,
                "JPEG",
                quality=QUALIDADE_JPEG,
                optimize=True,
                progressive=True,
            )
            nova_pagina = destino.new_page(width=pagina.rect.width, height=pagina.rect.height)
            nova_pagina.insert_image(nova_pagina.rect, stream=jpeg.getvalue())
        return destino.tobytes(garbage=4, deflate=True)
    finally:
        destino.close()


def _compactar_digital(documento):
    return documento.tobytes(
        garbage=4,
        clean=True,
        deflate=True,
        deflate_images=True,
        deflate_fonts=True,
    )


def compactar_pdf(conteudo):
    """Retorna o PDF mais econômico sem tornar a importação dependente da compactação."""
    tamanho_original = len(conteudo)
    resultado = {
        "conteudo": conteudo,
        "tamanho_original": tamanho_original,
        "tamanho_armazenado": tamanho_original,
        "compactado": False,
        "percentual_reducao": 0.0,
    }
    if tamanho_original <= LIMITE_COMPACTACAO:
        return resultado

    documento = None
    validacao = None
    try:
        documento = fitz.open(stream=conteudo, filetype="pdf")
        paginas = len(documento)
        candidato = _compactar_digitalizado(documento) if _parece_digitalizado(documento) else _compactar_digital(documento)
        economia = 1 - (len(candidato) / tamanho_original)
        if economia < ECONOMIA_MINIMA:
            return resultado

        validacao = fitz.open(stream=candidato, filetype="pdf")
        if validacao.is_encrypted or len(validacao) != paginas:
            return resultado
        # Força a leitura de todas as páginas para detectar arquivo truncado.
        for pagina in validacao:
            pagina.get_pixmap(matrix=fitz.Matrix(0.2, 0.2), alpha=False)

        resultado.update({
            "conteudo": candidato,
            "tamanho_armazenado": len(candidato),
            "compactado": True,
            "percentual_reducao": round(economia * 100, 1),
        })
        return resultado
    except Exception:
        return resultado
    finally:
        if validacao:
            validacao.close()
        if documento:
            documento.close()


def imagens_jpeg_para_pdf(conteudos):
    """Reúne JPEGs originais em um PDF, preservando 300 DPI e a ordem recebida."""
    documento = fitz.open()
    try:
        for conteudo in conteudos:
            imagem = ImageOps.exif_transpose(Image.open(BytesIO(conteudo))).convert("L")
            jpeg = BytesIO()
            imagem.save(jpeg, "JPEG", quality=85, optimize=True, progressive=True, dpi=(300, 300))
            largura_pontos = imagem.width * 72 / 300
            altura_pontos = imagem.height * 72 / 300
            pagina = documento.new_page(width=largura_pontos, height=altura_pontos)
            pagina.insert_image(pagina.rect, stream=jpeg.getvalue())
        return documento.tobytes(garbage=4, deflate=True)
    finally:
        documento.close()
