# CCP Industrial — Centro de Controle de Produção

Sistema web de gestão e acompanhamento operacional da fábrica, centralizando o andamento dos componentes desde a engenharia até a expedição.

---

## 🚀 Como Iniciar o Sistema Localmente

O projeto está dividido em duas partes simples: `backend` (FastAPI em Python) e `frontend` (Páginas estáticas em HTML5/JS/Tailwind).

### 1. Iniciar o Backend (API)

Abra o terminal na pasta raiz do projeto e execute os seguintes comandos:

```powershell
# Entrar no diretório do backend
cd backend

# Ativar o ambiente virtual (Windows)
.\venv\Scripts\activate

# Iniciar o servidor de desenvolvimento
uvicorn app.main:app --reload
```

* O servidor iniciará em [http://localhost:8000](http://localhost:8000).
* A documentação interativa das APIs (Swagger) estará disponível automaticamente em [http://localhost:8000/docs](http://localhost:8000/docs).
* O banco de dados SQLite (`database.db`) e os dados de teste já foram inicializados automaticamente na pasta do backend.

---

### 2. Iniciar o Frontend (Interface)

Como o frontend utiliza JavaScript moderno (ES6 Modules) que faz requisições Ajax, o navegador exige que a pasta seja servida sob um servidor local (para evitar erros de política CORS local file://).

Você pode servir a pasta do frontend de três formas simples sem instalar nada novo:

#### Opção A: Servidor HTTP do Python (Recomendada e mais simples)
Abra outro terminal na pasta raiz do projeto e digite:

```powershell
# Servir a pasta frontend na porta 3000
python -m http.server 3000 --directory frontend
```
* Abra o seu navegador em [http://localhost:3000](http://localhost:3000).

#### Opção B: Extensão do VS Code (Live Server)
* Se você estiver usando o VS Code, basta abrir a pasta `frontend` e clicar no botão **"Go Live"** no canto inferior direito.

---

## 👤 Credenciais de Acesso de Teste

Para realizar o login na tela inicial (`login.html`):

* **E-mail:** `admin@ccp.com.br`
* **Senha:** `123456`

---

## 🛠️ Principais Recursos Implementados

1. **Dashboard Industrial:** KPIs de atraso, banner inteligente do equipamento prioritário do dia, medidores de peças por etapa e feed ordenado por criticidade.
2. **Equipamentos & Componentes:** Listagem expansível de equipamentos exibindo seus componentes filhos, percentuais agregados, prazos e prioridades.
3. **Gaveta de Controle (Drawer):** Timeline de histórico imutável (auditoria), listagem de desenhos/IDs técnicas associadas e botões rápidos para avançar ou retornar etapas.
4. **Pendências & Bloqueios:** Interface para sinalizar impedimentos. Abertura de pendências bloqueantes altera o status do componente para "BLOQUEADO" e restabelece a produção automaticamente após a resolução da mesma.
5. **Quadro Kanban:** Visualização do fluxo integrado por colunas, permitindo a movimentação das etapas via arrastar e soltar (drag & drop) nativo do navegador.
6. **Exportação Excel:** Geração em tempo real do relatório consolidado de andamento industrial de todos os componentes da fábrica para o Excel (.xlsx).
