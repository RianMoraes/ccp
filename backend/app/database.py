from sqlmodel import create_engine, Session, SQLModel
from sqlalchemy import inspect, text
import os

# Em produção (Railway/Render/Docker), aponte DATABASE_PATH para um volume
# persistente (ex: /data/database.db). Sem isso, o banco some a cada deploy.
DATABASE_FILE = os.getenv("DATABASE_PATH", "database.db")
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"

# Configuração do engine do SQLite
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # Necessário para FastAPI e múltiplas threads
)

def init_db():
    """Inicializa o banco de dados criando todas as tabelas mapeadas no SQLModel."""
    SQLModel.metadata.create_all(engine)
    _aplicar_migracoes_sqlite()
    _garantir_administrador_inicial()


def _garantir_administrador_inicial():
    """Promove somente a conta inicial quando ainda nao houver administrador cadastrado."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conexao:
        possui_admin = conexao.execute(
            text("SELECT 1 FROM usuarios WHERE perfil = 'ADMIN' AND ativo = 1 LIMIT 1")
        ).first()
        if not possui_admin:
            conexao.execute(
                text("UPDATE usuarios SET perfil = 'ADMIN' WHERE email = 'admin@ccp.com.br' AND ativo = 1")
            )

def _aplicar_migracoes_sqlite():
    """Adiciona campos novos sem apagar ou recriar o banco SQLite existente."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    colunas = {
        "ids_tecnicas": {
            "status": "VARCHAR(20) NOT NULL DEFAULT 'LIBERADA'",
            "cliente_documento": "VARCHAR",
            "equipamento_documento": "VARCHAR",
            "componente_documento": "VARCHAR",
            "versao": "INTEGER NOT NULL DEFAULT 1",
            "id_origem_id": "VARCHAR",
            "substitui_id": "VARCHAR",
            "liberado_por": "VARCHAR",
            "data_liberacao": "DATETIME",
            "arquivo_nome": "VARCHAR",
            "arquivo_caminho": "VARCHAR",
            "modelo_documento": "VARCHAR",
            "hash_arquivo": "VARCHAR",
            "tamanho_original": "INTEGER",
            "tamanho_armazenado": "INTEGER",
            "arquivo_compactado": "BOOLEAN NOT NULL DEFAULT 0",
            "motivo_revisao": "VARCHAR",
            "retornada_por": "VARCHAR",
            "retornada_em": "DATETIME",
            "pendencia_revisao_id": "VARCHAR",
            "importado_por": "VARCHAR",
            "importado_em": "DATETIME",
        },
        "desenhos": {
            "copias": "INTEGER NOT NULL DEFAULT 1",
            "unidade": "VARCHAR",
            "item": "INTEGER",
            "pagina_origem": "INTEGER",
            "quantidade_original": "VARCHAR",
            "recebido": "BOOLEAN NOT NULL DEFAULT 1",
            "conferencia_atualizada_em": "DATETIME",
            "conferencia_atualizada_por": "VARCHAR",
        },
    }

    with engine.begin() as conexao:
        inspetor = inspect(conexao)
        for tabela, definicoes in colunas.items():
            existentes = {coluna["name"] for coluna in inspetor.get_columns(tabela)}
            for nome, definicao in definicoes.items():
                if nome not in existentes:
                    conexao.execute(text(f'ALTER TABLE "{tabela}" ADD COLUMN "{nome}" {definicao}'))
        conexao.execute(text("""
            UPDATE desenhos
            SET recebido = 1,
                conferencia_atualizada_em = COALESCE(conferencia_atualizada_em, CURRENT_TIMESTAMP),
                conferencia_atualizada_por = COALESCE(conferencia_atualizada_por, 'Correcao automatica')
            WHERE recebido = 0 AND id IN (
                SELECT desenho_origem_id FROM revisoes_desenhos
                WHERE status IN ('EM_REVISAO', 'em_revisao')
            )
        """))

def get_session():
    """Dependency para injeção de sessão do banco de dados nas rotas do FastAPI."""
    with Session(engine) as session:
        yield session
