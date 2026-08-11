"""
Corrige o hash de senha do usuário admin já existente no banco de dados.

Motivo: o seed antigo gravou um hash bcrypt "fake" (inventado, não gerado de
verdade pelo bcrypt) para a senha padrão '123456'. Isso só não dava erro por
causa de um bug de compatibilidade entre passlib e bcrypt que fazia o login
cair num fallback. Com o bcrypt corrigido (bcrypt<4.1), o hash fake passou a
ser corretamente rejeitado, causando 401 no login.

Rode este script UMA VEZ, com o venv do backend ativado:
    python corrigir_senha_admin.py

Ele redefine a senha do usuário admin@ccp.com.br para '123456' (gerando um
hash bcrypt real desta vez). Depois de logar, recomendamos trocar a senha.
"""
from passlib.context import CryptContext
from sqlmodel import Session, select
from app.database import engine
from app.models import Usuario

EMAIL_ADMIN = "admin@ccp.com.br"
NOVA_SENHA = "123456"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def main():
    novo_hash = pwd_context.hash(NOVA_SENHA)

    with Session(engine) as session:
        usuarios = session.exec(select(Usuario)).all()

        if not usuarios:
            print("Nenhum usuário encontrado no banco.")
            return

        corrigidos = []
        for u in usuarios:
            # Corrige o admin do seed (pelo e-mail) e qualquer outro usuário
            # que ainda esteja com aquele hash fake antigo gerado pelo seed.
            if u.email == EMAIL_ADMIN or u.senha_hash.startswith("$2b$12$R.S/mZ73sZ73"):
                u.senha_hash = novo_hash
                session.add(u)
                corrigidos.append(u.email)

        if not corrigidos:
            print("Nenhum usuário com hash inválido encontrado (talvez já esteja corrigido).")
            return

        session.commit()
        print(f"Senha redefinida para '{NOVA_SENHA}' nos usuários: {', '.join(corrigidos)}")
        print("Login novamente com essa senha e, se quiser, troque-a em Configurações.")

if __name__ == "__main__":
    main()
