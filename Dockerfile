FROM python:3.12-slim

WORKDIR /srv

# Instala dependências primeiro (aproveita cache do Docker)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copia o restante do projeto (backend + frontend)
COPY backend ./backend
COPY frontend ./frontend

WORKDIR /srv/backend

# Pasta para o volume persistente do banco SQLite
RUN mkdir -p /data
ENV DATABASE_PATH=/data/database.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
