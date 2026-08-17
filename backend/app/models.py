from typing import List, Optional
from datetime import datetime, date
from enum import Enum
from sqlmodel import Field, Relationship, SQLModel
import uuid

# --- ENUMS ---

class PrioridadeEnum(str, Enum):
    NORMAL = "normal"
    MEDIA = "media"
    ALTA = "alta"
    URGENTE = "urgente"
    CRITICA = "critica"

class StatusComponenteEnum(str, Enum):
    NAO_INICIADO = "nao_iniciado"
    AGUARDANDO = "aguardando"
    EM_ANDAMENTO = "em_andamento"
    PAUSADO = "pausado"
    CONCLUIDO = "concluido"
    BLOQUEADO = "bloqueado"

class StatusEtapaEnum(str, Enum):
    PENDENTE = "pendente"
    EM_ANDAMENTO = "em_andamento"
    CONCLUIDA = "concluida"
    PULADA = "pulada"

class StatusEquipamentoEnum(str, Enum):
    EM_PRODUCAO = "em_producao"
    CONCLUIDO = "concluido"
    CANCELADO = "cancelado"
    CARREGADO = "carregado"
    CARREGADO_COM_PENDENCIA = "carregado_com_pendencia"

class PerfilUsuarioEnum(str, Enum):
    ADMIN = "admin"
    PCP = "pcp"
    GERENTE = "gerente"
    VISUALIZADOR = "visualizador"

class StatusPendenciaEnum(str, Enum):
    ABERTA = "aberta"
    RESOLVIDA = "resolvida"

class StatusIDTecnicaEnum(str, Enum):
    LIBERADA = "liberada"
    EM_REVISAO = "em_revisao"
    REVISADA = "revisada"
    SUBSTITUIDA = "substituida"
    CANCELADA = "cancelada"

class StatusRevisaoDesenhoEnum(str, Enum):
    EM_REVISAO = "em_revisao"
    RESOLVIDA = "resolvida"
    CANCELADA = "cancelada"

# --- MODELOS ---

class Cliente(SQLModel, table=True):
    __tablename__ = "clientes"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    nome: str = Field(index=True)
    sigla: str = Field(unique=True, index=True)
    observacoes: Optional[str] = Field(default=None)
    ativo: bool = Field(default=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    
    equipamentos: List["Equipamento"] = Relationship(back_populates="cliente")


class Equipamento(SQLModel, table=True):
    __tablename__ = "equipamentos"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    cliente_id: str = Field(foreign_key="clientes.id", index=True)
    nome: str = Field(index=True)
    codigo: Optional[str] = Field(default=None)
    descricao: Optional[str] = Field(default=None)
    op: Optional[str] = Field(default=None, index=True)
    rv: Optional[str] = Field(default=None)
    data_inicio: Optional[date] = Field(default=None)
    data_entrega: Optional[date] = Field(default=None)
    status: StatusEquipamentoEnum = Field(default=StatusEquipamentoEnum.EM_PRODUCAO)
    ativo: bool = Field(default=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    
    cliente: Cliente = Relationship(back_populates="equipamentos")
    componentes: List["Componente"] = Relationship(back_populates="equipamento")


class Componente(SQLModel, table=True):
    __tablename__ = "componentes"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    equipamento_id: str = Field(foreign_key="equipamentos.id", index=True)
    nome: str = Field(index=True)
    descricao: Optional[str] = Field(default=None)
    prioridade: PrioridadeEnum = Field(default=PrioridadeEnum.NORMAL)
    status: StatusComponenteEnum = Field(default=StatusComponenteEnum.NAO_INICIADO)
    etapa_atual_id: Optional[str] = Field(default=None, foreign_key="etapas.id")
    percentual: float = Field(default=0.0)
    responsavel: Optional[str] = Field(default=None)
    data_prevista: Optional[date] = Field(default=None)
    data_conclusao: Optional[date] = Field(default=None)
    observacoes: Optional[str] = Field(default=None)  # Campo de observações simples conforme d-11
    ativo: bool = Field(default=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    
    equipamento: Equipamento = Relationship(back_populates="componentes")
    fluxo: Optional["Fluxo"] = Relationship(back_populates="componente", sa_relationship_kwargs={"uselist": False})
    ids_tecnicas: List["IDTecnica"] = Relationship(back_populates="componente")
    pendencias: List["Pendencia"] = Relationship(back_populates="componente")
    historicos: List["Historico"] = Relationship(back_populates="componente")
    anexos: List["Anexo"] = Relationship(back_populates="componente")


class ModeloFluxo(SQLModel, table=True):
    __tablename__ = "modelos_fluxo"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    nome: str = Field(unique=True, index=True)
    descricao: Optional[str] = Field(default=None)
    ativo: bool = Field(default=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
    
    etapas_modelo: List["EtapaModelo"] = Relationship(back_populates="modelo_fluxo")
    fluxos: List["Fluxo"] = Relationship(back_populates="modelo_origem")


class EtapaModelo(SQLModel, table=True):
    __tablename__ = "etapas_modelo"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    modelo_fluxo_id: str = Field(foreign_key="modelos_fluxo.id", index=True)
    nome: str = Field()
    ordem: int = Field()
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    
    modelo_fluxo: ModeloFluxo = Relationship(back_populates="etapas_modelo")


class Fluxo(SQLModel, table=True):
    __tablename__ = "fluxos"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    componente_id: str = Field(foreign_key="componentes.id", unique=True, index=True)
    modelo_origem_id: Optional[str] = Field(default=None, foreign_key="modelos_fluxo.id")
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    
    componente: Componente = Relationship(back_populates="fluxo")
    modelo_origem: Optional[ModeloFluxo] = Relationship(back_populates="fluxos")
    etapas: List["Etapa"] = Relationship(back_populates="fluxo")


class Etapa(SQLModel, table=True):
    __tablename__ = "etapas"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    fluxo_id: str = Field(foreign_key="fluxos.id", index=True)
    nome: str = Field()
    ordem: int = Field()
    status: StatusEtapaEnum = Field(default=StatusEtapaEnum.PENDENTE)
    data_inicio: Optional[datetime] = Field(default=None)
    data_fim: Optional[datetime] = Field(default=None)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    
    fluxo: Fluxo = Relationship(back_populates="etapas")


class IDTecnica(SQLModel, table=True):
    __tablename__ = "ids_tecnicas"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    componente_id: str = Field(foreign_key="componentes.id", index=True)
    numero: str = Field(index=True)
    op: Optional[str] = Field(default=None)
    rv: Optional[str] = Field(default=None)
    cliente_documento: Optional[str] = Field(default=None)
    equipamento_documento: Optional[str] = Field(default=None)
    componente_documento: Optional[str] = Field(default=None)
    local: Optional[str] = Field(default=None)
    status: StatusIDTecnicaEnum = Field(default=StatusIDTecnicaEnum.LIBERADA)
    versao: int = Field(default=1)
    id_origem_id: Optional[str] = Field(default=None, index=True)
    substitui_id: Optional[str] = Field(default=None, index=True)
    liberado_por: Optional[str] = Field(default=None)
    data_liberacao: Optional[datetime] = Field(default=None)
    arquivo_nome: Optional[str] = Field(default=None)
    arquivo_caminho: Optional[str] = Field(default=None)
    modelo_documento: Optional[str] = Field(default=None)
    hash_arquivo: Optional[str] = Field(default=None, index=True)
    tamanho_original: Optional[int] = Field(default=None)
    tamanho_armazenado: Optional[int] = Field(default=None)
    arquivo_compactado: bool = Field(default=False)
    motivo_revisao: Optional[str] = Field(default=None)
    retornada_por: Optional[str] = Field(default=None)
    retornada_em: Optional[datetime] = Field(default=None)
    pendencia_revisao_id: Optional[str] = Field(default=None)
    importado_por: Optional[str] = Field(default=None)
    importado_em: Optional[datetime] = Field(default=None)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    
    componente: Componente = Relationship(back_populates="ids_tecnicas")
    desenhos: List["Desenho"] = Relationship(back_populates="id_tecnica")


class Desenho(SQLModel, table=True):
    __tablename__ = "desenhos"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    id_tecnica_id: str = Field(foreign_key="ids_tecnicas.id", index=True)
    codigo: str = Field(index=True)
    descricao: Optional[str] = Field(default=None)
    quantidade: int = Field(default=1)
    revisao: Optional[str] = Field(default=None)
    copias: int = Field(default=1)
    unidade: Optional[str] = Field(default=None)
    item: Optional[int] = Field(default=None)
    pagina_origem: Optional[int] = Field(default=None)
    quantidade_original: Optional[str] = Field(default=None)
    recebido: bool = Field(default=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    
    id_tecnica: IDTecnica = Relationship(back_populates="desenhos")


class RevisaoDesenho(SQLModel, table=True):
    __tablename__ = "revisoes_desenhos"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    componente_id: str = Field(foreign_key="componentes.id", index=True)
    desenho_origem_id: str = Field(foreign_key="desenhos.id", index=True)
    desenho_substituto_id: Optional[str] = Field(default=None, foreign_key="desenhos.id", index=True)
    status: StatusRevisaoDesenhoEnum = Field(default=StatusRevisaoDesenhoEnum.EM_REVISAO, index=True)
    motivo: str = Field()
    retornada_por: str = Field()
    retornada_em: datetime = Field(default_factory=datetime.utcnow)
    resolvida_por: Optional[str] = Field(default=None)
    resolvida_em: Optional[datetime] = Field(default=None)
    cancelada_por: Optional[str] = Field(default=None)
    cancelada_em: Optional[datetime] = Field(default=None)


class Pendencia(SQLModel, table=True):
    __tablename__ = "pendencias"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    componente_id: str = Field(foreign_key="componentes.id", index=True)
    titulo: str = Field()
    descricao: Optional[str] = Field(default=None)
    bloqueante: bool = Field(default=False)
    status: StatusPendenciaEnum = Field(default=StatusPendenciaEnum.ABERTA)
    aberta_por: str = Field()
    aberta_em: datetime = Field(default_factory=datetime.utcnow)
    encerrada_por: Optional[str] = Field(default=None)
    encerrada_em: Optional[datetime] = Field(default=None)
    
    componente: Componente = Relationship(back_populates="pendencias")


class Historico(SQLModel, table=True):
    __tablename__ = "historicos"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    componente_id: str = Field(foreign_key="componentes.id", index=True)
    usuario: str = Field()
    evento: str = Field()
    descricao: str = Field()
    data_hora: datetime = Field(default_factory=datetime.utcnow)
    
    componente: Componente = Relationship(back_populates="historicos")


class Anexo(SQLModel, table=True):
    __tablename__ = "anexos"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    componente_id: str = Field(foreign_key="componentes.id", index=True)
    nome: str = Field()
    caminho: str = Field()
    tipo: Optional[str] = Field(default=None)
    enviado_por: str = Field()
    enviado_em: datetime = Field(default_factory=datetime.utcnow)
    
    componente: Componente = Relationship(back_populates="anexos")


class Usuario(SQLModel, table=True):
    __tablename__ = "usuarios"
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    nome: str = Field()
    email: str = Field(unique=True, index=True)
    senha_hash: str = Field()
    cargo: Optional[str] = Field(default=None)
    perfil: PerfilUsuarioEnum = Field(default=PerfilUsuarioEnum.VISUALIZADOR)
    ativo: bool = Field(default=True)
    criado_em: datetime = Field(default_factory=datetime.utcnow)
    atualizado_em: datetime = Field(default_factory=datetime.utcnow)
