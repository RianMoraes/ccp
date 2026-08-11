const API_BASE_URL = window.location.origin + "/api";

// Recupera o token do armazenamento local
function getAuthToken() {
    return localStorage.getItem("ccp_token");
}

// Configura os cabeÃ§alhos das requisiÃ§Ãµes padrÃ£o
function getHeaders(contentType = "application/json") {
    const token = getAuthToken();
    const headers = {};
    if (contentType) {
        headers["Content-Type"] = contentType;
    }
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
}

// Verifica e trata respostas HTTP
async function handleResponse(response) {
    if (response.status === 401) {
        // Token expirado ou invÃ¡lido
        localStorage.removeItem("ccp_token");
        localStorage.removeItem("ccp_user");
        if (!window.location.pathname.includes("login.html")) {
            window.location.href = "login.html";
        }
        throw new Error("SessÃ£o expirada. FaÃ§a login novamente.");
    }
    
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Erro na comunicaÃ§Ã£o com a API");
    }
    
    // Se for um arquivo de exportaÃ§Ã£o (Excel), retorna o blob
    const contentDisposition = response.headers.get("content-disposition");
    if (contentDisposition && contentDisposition.includes("attachment")) {
        return response.blob();
    }
    
    return response.json();
}

export const API = {
    // AutenticaÃ§Ã£o
    async login(username, password) {
        const params = new URLSearchParams();
        params.append("username", username);
        params.append("password", password);
        
        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: params
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || "Erro ao fazer login. Verifique suas credenciais.");
        }

        const data = await response.json();
        localStorage.setItem("ccp_token", data.access_token);
        localStorage.setItem("ccp_user", JSON.stringify(data.usuario));
        return data;
    },
    
    logout() {
        localStorage.removeItem("ccp_token");
        localStorage.removeItem("ccp_user");
        window.location.href = "login.html";
    },
    
    async getMe() {
        const response = await fetch(`${API_BASE_URL}/auth/me`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    // Dashboard e KPIs
    async getDashboardResumo() {
        const response = await fetch(`${API_BASE_URL}/dashboard/resumo`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    async getPrioridadeDia() {
        const response = await fetch(`${API_BASE_URL}/dashboard/prioridade-dia`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    async getProducaoPorEtapa() {
        const response = await fetch(`${API_BASE_URL}/dashboard/producao-por-etapa`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    // Equipamentos
    async getEquipamentos() {
        const response = await fetch(`${API_BASE_URL}/equipamentos`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    async getEquipamentoDetalhes(id) {
        const response = await fetch(`${API_BASE_URL}/equipamentos/${id}`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    async criarEquipamento(dados) {
        const response = await fetch(`${API_BASE_URL}/equipamentos`, {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify(dados)
        });
        return handleResponse(response);
    },

    async deletarEquipamento(id) {
        const response = await fetch(`${API_BASE_URL}/equipamentos/${id}`, {
            method: "DELETE",
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    // Componentes
    async getComponentes(params = {}) {
        const urlParams = new URLSearchParams(params).toString();
        const response = await fetch(`${API_BASE_URL}/componentes?${urlParams}`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    async getComponenteDetalhes(id) {
        const response = await fetch(`${API_BASE_URL}/componentes/${id}`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    async avancarEtapa(id) {
        const response = await fetch(`${API_BASE_URL}/componentes/${id}/avancar-etapa`, {
            method: "PATCH",
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    async retornarEtapa(id) {
        const response = await fetch(`${API_BASE_URL}/componentes/${id}/retornar-etapa`, {
            method: "PATCH",
            headers: getHeaders()
        });
        return handleResponse(response);
    },

    async deletarComponente(id) {
        const response = await fetch(`${API_BASE_URL}/componentes/${id}`, {
            method: "DELETE",
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    async alterarPrioridade(id, prioridade) {
        const response = await fetch(`${API_BASE_URL}/componentes/${id}/prioridade?nova_prioridade=${prioridade}`, {
            method: "PATCH",
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    // Pendencias
    async criarPendencia(dados) {
        const response = await fetch(`${API_BASE_URL}/pendencias`, {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify(dados)
        });
        return handleResponse(response);
    },

    async getPendenciasComponente(componenteId) {
        const response = await fetch(`${API_BASE_URL}/componentes/${componenteId}/pendencias`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    async encerrarPendencia(id) {
        const response = await fetch(`${API_BASE_URL}/pendencias/${id}/encerrar`, {
            method: "PATCH",
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    // Busca Global
    async buscarGlobal(q) {
        const response = await fetch(`${API_BASE_URL}/busca?q=${q}`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    // ExportaÃ§Ã£o Excel
    async exportarExcel() {
        const response = await fetch(`${API_BASE_URL}/export/excel`, {
            headers: getHeaders(null) // CabeÃ§alho Content-Type vazio
        });
        return handleResponse(response);
    }
};
