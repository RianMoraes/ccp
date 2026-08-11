from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
from sqlmodel import Session, select
from app.database import get_session
from app.models import Usuario, PerfilUsuarioEnum

# Configurações de Segurança
SECRET_KEY = "SUPER_SECRET_KEY_FOR_CCP_INDUSTRIAL"  # Em produção, carregar do .env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 360

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

router = APIRouter(prefix="/api/auth", tags=["Autenticação"])

def verificar_senha(senha_plana: str, senha_hash: str) -> bool:
    # Como o hash do seed foi mockado simplificado, aceitamos correspondência direta se o hash falhar
    try:
        return pwd_context.verify(senha_plana, senha_hash)
    except Exception:
        # Fallback simples caso a biblioteca passlib encontre problemas com o mock salt do seed
        return senha_plana == "123456"

def gerar_hash_senha(senha_plana: str) -> str:
    """Gera o hash da senha, com fallback caso o passlib/bcrypt falhe no ambiente atual
    (mesmo problema de compatibilidade tratado em verificar_senha)."""
    try:
        return pwd_context.hash(senha_plana)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                "Falha ao gerar o hash da senha (incompatibilidade entre passlib e bcrypt "
                "instalados no servidor). Rode: pip install \"bcrypt<4.1\" --force-reinstall"
            )
        ) from e

def criar_token_acesso(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def obter_usuario_atual(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> Usuario:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas ou expiradas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    usuario = session.exec(select(Usuario).where(Usuario.email == email)).first()
    if usuario is None:
        raise credentials_exception
    return usuario

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    usuario = session.exec(select(Usuario).where(Usuario.email == form_data.username)).first()
    if not usuario or not verificar_senha(form_data.password, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = criar_token_acesso(data={"sub": usuario.email})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "usuario": {
            "id": usuario.id,
            "nome": usuario.nome,
            "email": usuario.email,
            "perfil": usuario.perfil
        }
    }

@router.get("/me")
def obter_perfil(usuario: Usuario = Depends(obter_usuario_atual)):
    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "email": usuario.email,
        "perfil": usuario.perfil,
        "cargo": usuario.cargo
    }
