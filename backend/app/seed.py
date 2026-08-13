from sqlmodel import Session
from app.database import engine
from app.models import (
    Cliente, Equipamento, Componente, ModeloFluxo, EtapaModelo,
    Fluxo, Etapa, IDTecnica, Desenho, Usuario,
    PrioridadeEnum, StatusComponenteEnum, StatusEtapaEnum,
    StatusEquipamentoEnum, PerfilUsuarioEnum, StatusPendenciaEnum
)
from datetime import date, datetime, timedelta
from passlib.context import CryptContext
import uuid

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash real gerado em tempo de execução para a senha padrão '123456'.
# (Antes havia um hash fixo "mockado" aqui que não era um bcrypt válido de verdade,
# o que só não dava erro por causa de um bug de compatibilidade bcrypt/passlib.)
SENHA_PADRAO_HASH = _pwd_context.hash("123456")

def run_seed():
    """Popula o banco SQLite com dados iniciais condizentes com os protótipos de wireframe."""
    with Session(engine) as session:
        # 1. Verificar se já existem dados
        if session.query(Usuario).first():
            print("Banco de dados já possui dados. Pulando Seed.")
            return

        print("Iniciando injeção de dados de Seed...")

        # 2. Criar Usuários
        admin_pcp = Usuario(
            nome="Admin CCP",
            email="admin@ccp.com.br",
            senha_hash=SENHA_PADRAO_HASH,
            cargo="Gerente Industrial",
            perfil=PerfilUsuarioEnum.ADMIN,
            ativo=True
        )
        session.add(admin_pcp)

        # 3. Criar Clientes
        comigo = Cliente(nome="COMIGO", sigla="COMIGO", observacoes="Filial Acreúna GO")
        barry = Cliente(nome="BARRY CALLEBAUT", sigla="BARRY", observacoes="Fábrica de Chocolate")
        potencial = Cliente(nome="POTENCIAL BIOCOMBUSTIVEIS", sigla="POTENCIAL", observacoes="Biodiesel")
        session.add_all([comigo, barry, potencial])
        session.commit()

        # 4. Criar Modelos de Fluxo Padrão
        modelo_padrao = ModeloFluxo(nome="Padrão Completo", descricao="Fluxo completo de fabricação da fábrica")
        session.add(modelo_padrao)
        session.commit()

        etapas_modelo = [
            "Engenharia", "Listagem", "Aguardando Material", "Material Completo",
            "Programação CNC", "Corte", "Caldeiraria", "Pintura", "Montagem",
            "Qualidade", "Expedição", "Finalizado"
        ]
        for i, nome_etapa in enumerate(etapas_modelo):
            et_mod = EtapaModelo(modelo_fluxo_id=modelo_padrao.id, nome=nome_etapa, ordem=i + 1)
            session.add(et_mod)
        session.commit()

        # 5. Criar Equipamentos
        # Equipamento 1 (Comigo) - Critico
        elevador = Equipamento(
            cliente_id=comigo.id,
            nome="Elevador EC30 - Comigo Santa Helena",
            codigo="EC30",
            op="132/45",
            data_inicio=date.today() - timedelta(days=20),
            data_entrega=date.today() + timedelta(days=5),
            status=StatusEquipamentoEnum.EM_PRODUCAO
        )
        # Equipamento 2 (Barry Callebaut) - Alerta
        prensa = Equipamento(
            cliente_id=barry.id,
            nome="Prensa PH-500T - Barry Callebaut",
            codigo="PH500",
            op="456/22",
            data_inicio=date.today() - timedelta(days=10),
            data_entrega=date.today() + timedelta(days=26),
            status=StatusEquipamentoEnum.EM_PRODUCAO
        )
        # Equipamento 3 (Potencial) - Normal
        tc42 = Equipamento(
            cliente_id=potencial.id,
            nome="TC-42\" - Potencial Biocombustíveis",
            codigo="TC42",
            op="789/23",
            data_inicio=date.today() - timedelta(days=5),
            data_entrega=date.today() + timedelta(days=53),
            status=StatusEquipamentoEnum.EM_PRODUCAO
        )
        session.add_all([elevador, prensa, tc42])
        session.commit()

        # 6. Criar Componentes e seus fluxos
        # --- Componentes do Elevador EC30 ---
        # Componente 1: Estrutura Superior (Atrasado no Corte CNC, 15% progresso)
        comp_superior = Componente(
            equipamento_id=elevador.id,
            nome="Estrutura Superior",
            prioridade=PrioridadeEnum.CRITICA,
            status=StatusComponenteEnum.BLOQUEADO,
            responsavel="Gustavo",
            data_prevista=date.today() - timedelta(days=2),
            observacoes="Material SAE1020 em falta no estoque"
        )
        session.add(comp_superior)
        session.commit()

        # Criar fluxo do componente superior baseado no padrão
        fluxo_sup = Fluxo(componente_id=comp_superior.id, modelo_origem_id=modelo_padrao.id)
        session.add(fluxo_sup)
        session.commit()

        # Criar etapas do fluxo
        etapas_sup = []
        for i, nome_etapa in enumerate(etapas_modelo):
            status_et = StatusEtapaEnum.PENDENTE
            if i < 5:  # Concluídas as anteriores ao Corte
                status_et = StatusEtapaEnum.CONCLUIDA
            elif i == 5:  # Corte CNC está em andamento (com bloqueio)
                status_et = StatusEtapaEnum.EM_ANDAMENTO
                
            et = Etapa(
                fluxo_id=fluxo_sup.id,
                nome=nome_etapa,
                ordem=i + 1,
                status=status_et,
                data_inicio=datetime.utcnow() - timedelta(days=12-i) if i <= 5 else None,
                data_fim=datetime.utcnow() - timedelta(days=11-i) if i < 5 else None
            )
            session.add(et)
            etapas_sup.append(et)
        session.commit()

        # Vincular etapa atual e calcular percentual
        comp_superior.etapa_atual_id = etapas_sup[5].id
        comp_superior.percentual = 15.0
        session.add(comp_superior)

        # Adicionar ID técnica e desenhos
        id_sup = IDTecnica(componente_id=comp_superior.id, numero="0154", op="132/45", rv="342/25", local="Acreúna GO")
        session.add(id_sup)
        session.commit()

        des1 = Desenho(id_tecnica_id=id_sup.id, codigo="TM-1238.456 R1", descricao="CONJ BICA DE ALIM CONICA C TAMPA E REVEST", quantidade=1, revisao="1")
        des2 = Desenho(id_tecnica_id=id_sup.id, codigo="TM-1238.749", descricao="PC001 FRONTAL BICA ALIM CONICA EC17", quantidade=1)
        session.add_all([des1, des2])

        # Componente 2: Eixo Principal (Bloqueado na Usinagem, 45% progresso)
        comp_eixo = Componente(
            equipamento_id=elevador.id,
            nome="Eixo Principal",
            prioridade=PrioridadeEnum.URGENTE,
            status=StatusComponenteEnum.BLOQUEADO,
            responsavel="Gustavo",
            data_prevista=date.today(),
            observacoes="Aguardando revisão do desenho (B)"
        )
        session.add(comp_eixo)
        session.commit()

        fluxo_eixo = Fluxo(componente_id=comp_eixo.id, modelo_origem_id=modelo_padrao.id)
        session.add(fluxo_eixo)
        session.commit()

        etapas_eixo = []
        for i, nome_etapa in enumerate(etapas_modelo):
            status_et = StatusEtapaEnum.PENDENTE
            if i < 6:
                status_et = StatusEtapaEnum.CONCLUIDA
            elif i == 6:  # Usinagem/Caldeiraria
                status_et = StatusEtapaEnum.EM_ANDAMENTO
            et = Etapa(
                fluxo_id=fluxo_eixo.id,
                nome=nome_etapa,
                ordem=i + 1,
                status=status_et,
                data_inicio=datetime.utcnow() - timedelta(days=10-i) if i <= 6 else None,
                data_fim=datetime.utcnow() - timedelta(days=9-i) if i < 6 else None
            )
            session.add(et)
            etapas_eixo.append(et)
        session.commit()

        comp_eixo.etapa_atual_id = etapas_eixo[6].id
        comp_eixo.percentual = 45.0
        session.add(comp_eixo)

        # --- Componentes da Prensa PH-500T ---
        # Componente 3: Cilindro Hidráulico Mod. A (No prazo na Montagem Final, 85%)
        comp_cilindro = Componente(
            equipamento_id=prensa.id,
            nome="Cilindro Hidráulico Mod. A",
            prioridade=PrioridadeEnum.MEDIA,
            status=StatusComponenteEnum.EM_ANDAMENTO,
            responsavel="Richard",
            data_prevista=date.today() + timedelta(days=1),
            observacoes="Sem pendências ativas"
        )
        session.add(comp_cilindro)
        session.commit()

        fluxo_cil = Fluxo(componente_id=comp_cilindro.id, modelo_origem_id=modelo_padrao.id)
        session.add(fluxo_cil)
        session.commit()

        etapas_cil = []
        for i, nome_etapa in enumerate(etapas_modelo):
            status_et = StatusEtapaEnum.PENDENTE
            if i < 8:
                status_et = StatusEtapaEnum.CONCLUIDA
            elif i == 8:  # Montagem
                status_et = StatusEtapaEnum.EM_ANDAMENTO
            et = Etapa(
                fluxo_id=fluxo_cil.id,
                nome=nome_etapa,
                ordem=i + 1,
                status=status_et,
                data_inicio=datetime.utcnow() - timedelta(days=8-i) if i <= 8 else None,
                data_fim=datetime.utcnow() - timedelta(days=7-i) if i < 8 else None
            )
            session.add(et)
            etapas_cil.append(et)
        session.commit()

        comp_cilindro.etapa_atual_id = etapas_cil[8].id
        comp_cilindro.percentual = 85.0
        session.add(comp_cilindro)

        # Componente 4: Base Estrutural Soldada (Atrasado na Caldeiraria, 40%)
        comp_base = Componente(
            equipamento_id=prensa.id,
            nome="Base Estrutural Soldada",
            prioridade=PrioridadeEnum.ALTA,
            status=StatusComponenteEnum.EM_ANDAMENTO,
            responsavel="Richard",
            data_prevista=date.today() + timedelta(days=3),
            observacoes="Falta de soldadores qualificados no turno B"
        )
        session.add(comp_base)
        session.commit()

        fluxo_base = Fluxo(componente_id=comp_base.id, modelo_origem_id=modelo_padrao.id)
        session.add(fluxo_base)
        session.commit()

        etapas_base = []
        for i, nome_etapa in enumerate(etapas_modelo):
            status_et = StatusEtapaEnum.PENDENTE
            if i < 6:
                status_et = StatusEtapaEnum.CONCLUIDA
            elif i == 6:  # Caldeiraria
                status_et = StatusEtapaEnum.EM_ANDAMENTO
            et = Etapa(
                fluxo_id=fluxo_base.id,
                nome=nome_etapa,
                ordem=i + 1,
                status=status_et,
                data_inicio=datetime.utcnow() - timedelta(days=6-i) if i <= 6 else None,
                data_fim=datetime.utcnow() - timedelta(days=5-i) if i < 6 else None
            )
            session.add(et)
            etapas_base.append(et)
        session.commit()

        comp_base.etapa_atual_id = etapas_base[6].id
        comp_base.percentual = 40.0
        session.add(comp_base)

        session.commit()
        print("Seed finalizado com sucesso!")

if __name__ == "__main__":
    from app.database import init_db
    init_db()
    run_seed()
