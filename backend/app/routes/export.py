from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from app.database import get_session
from app.models import Componente, Equipamento, Etapa
from app.routes.auth import obter_usuario_atual
import pandas as pd
import io

router = APIRouter(prefix="/api/export", tags=["Exportação"])

@router.get("/excel")
def exportar_excel(
    session: Session = Depends(get_session),
    usuario_atual = Depends(obter_usuario_atual)
):
    """Exporta o relatório geral de componentes e andamento de fabricação para o Excel (d-13)."""
    componentes = session.exec(select(Componente).where(Componente.ativo == True)).all()
    
    dados = []
    for c in componentes:
        etapa_atual = session.get(Etapa, c.etapa_atual_id) if c.etapa_atual_id else None
        
        dados.append({
            "Cliente": c.equipamento.cliente.nome if c.equipamento and c.equipamento.cliente else "N/A",
            "Equipamento": c.equipamento.nome if c.equipamento else "N/A",
            "OP": c.equipamento.op if c.equipamento else "N/A",
            "Componente": c.nome,
            "Prioridade": c.prioridade.value.upper(),
            "Etapa Atual": etapa_atual.nome if etapa_atual else "N/A",
            "Status na Etapa": c.status.value.replace("_", " ").upper(),
            "Progresso (%)": f"{c.percentual}%",
            "Responsável PCP": c.responsavel or "Não Atribuído",
            "Prazo Previsto": c.data_prevista.strftime("%d/%m/%Y") if c.data_prevista else "N/A",
            "Observações / Bloqueios": c.observacoes or ""
        })
        
    df = pd.DataFrame(dados)
    
    # Criar buffer em memória para o Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Acompanhamento CCP")
        
        # Obter planilha para formatações simples
        workbook = writer.book
        worksheet = writer.sheets["Acompanhamento CCP"]
        
        # Ajustar tamanho das colunas automaticamente
        for col in worksheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = col[0].column_letter
            worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)
            
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=CCP_Acompanhamento_Producao.xlsx"}
    )
