from sqlmodel import create_engine, Session, SQLModel
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

def get_session():
    """Dependency para injeção de sessão do banco de dados nas rotas do FastAPI."""
    with Session(engine) as session:
        yield session
