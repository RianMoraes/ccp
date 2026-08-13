from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlmodel import Session, select
from app.database import get_session
from app.models import Usuario, PerfilUsuarioEnum
from app.routes.auth import obter_usuario_atual, gerar_hash_senha, exigir_administrador
from datetime import datetime

router = APIRouter(prefix="/api/usuarios", tags=["Usuários"])

@router.get("", response_model=List[Usuario], dependencies=[Depends(exigir_administrador)])
def listar_usuarios(
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Retorna todos os usuários cadastrados e ativos no sistema."""
    return session.exec(select(Usuario).where(Usuario.ativo == True)).all()

@router.post("", response_model=Usuario, status_code=status.HTTP_201_CREATED, dependencies=[Depends(exigir_administrador)])
def cadastrar_usuario(
    dados: Usuario,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Cadastra um novo usuário criptografando a senha informada."""
    # Verificar se o e-mail já existe
    existente = session.exec(select(Usuario).where(Usuario.email == dados.email)).first()
    if existente:
        raise HTTPException(status_code=400, detail="E-mail já está sendo utilizado por outro usuário")
    
    # Criar hash da senha
    dados.senha_hash = gerar_hash_senha(dados.senha_hash)
    dados.criado_em = datetime.utcnow()
    dados.atualizado_em = datetime.utcnow()
    
    session.add(dados)
    session.commit()
    session.refresh(dados)
    return dados

@router.put("/{usuario_id}", response_model=Usuario, dependencies=[Depends(exigir_administrador)])
def atualizar_usuario(
    usuario_id: str,
    dados: Usuario,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Atualiza dados do usuário (se informar senha, recria o hash)."""
    user = session.get(Usuario, usuario_id)
    if not user or not user.ativo:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    # Verificar duplicidade de e-mail se alterou
    if user.email != dados.email:
        existente = session.exec(select(Usuario).where(Usuario.email == dados.email, Usuario.id != user.id)).first()
        if existente:
            raise HTTPException(status_code=400, detail="E-mail já está sendo utilizado por outro usuário")
            
    user.nome = dados.nome
    user.email = dados.email
    user.cargo = dados.cargo
    user.perfil = dados.perfil
    
    # Se uma nova senha plana foi fornecida, atualiza o hash
    if dados.senha_hash and not dados.senha_hash.startswith("$2b$"):
        user.senha_hash = gerar_hash_senha(dados.senha_hash)
        
    user.atualizado_em = datetime.utcnow()
    
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@router.delete("/{usuario_id}", dependencies=[Depends(exigir_administrador)])
def deletar_usuario(
    usuario_id: str,
    session: Session = Depends(get_session),
    usuario_atual: Usuario = Depends(obter_usuario_atual)
):
    """Realiza a exclusão lógica do usuário no sistema."""
    user = session.get(Usuario, usuario_id)
    if not user or not user.ativo:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
        
    # Evitar autoexclusão
    if user.id == usuario_atual.id:
        raise HTTPException(status_code=400, detail="Não é permitido desativar o próprio usuário logado")
        
    user.ativo = False
    user.atualizado_em = datetime.utcnow()
    session.add(user)
    session.commit()
    return {"message": "Usuário desativado com sucesso"}
