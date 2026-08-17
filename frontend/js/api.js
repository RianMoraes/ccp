const API_BASE_URL = window.location.origin + "/api";

// Recupera o token do armazenamento local
function getAuthToken() {
    return localStorage.getItem("ccp_token");
}

// Configura os cabeçalhos das requisições padrão
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
        // Token expirado ou inválido
        localStorage.removeItem("ccp_token");
        localStorage.removeItem("ccp_user");
        if (!window.location.pathname.includes("login.html")) {
            window.location.href = "login.html";
        }
        throw new Error("Sessão expirada. Faça login novamente.");
    }
    
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Erro na comunicação com a API");
    }
    
    // Se for um arquivo de exportação (Excel), retorna o blob
    const contentDisposition = response.headers.get("content-disposition");
    if (contentDisposition && contentDisposition.includes("attachment")) {
        return response.blob();
    }
    
    return response.json();
}

export const API = {
    // Autenticação
    async login(username, password) {
        const params = new URLSearchParams();
        params.append("username", username);
        params.append("password", password);
        
        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: params
        });
        
        const data = await handleResponse(response);
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
    
    // AJUSTE DE EDICAO DE DATA: Atualiza a data de entrega do equipamento
    async atualizarPrazoEquipamento(id, novaData) {
        const response = await fetch(`${API_BASE_URL}/equipamentos/${id}/prazo?nova_data=${novaData}`, {
            method: "PATCH",
            headers: getHeaders()
        });
        return handleResponse(response);
    },

    async atualizarInicioEquipamento(id, novoMes) {
        const novaData = `${novoMes}-01`;
        const response = await fetch(`${API_BASE_URL}/equipamentos/${id}/inicio?nova_data=${novaData}`, {
            method: "PATCH",
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
    
    // AJUSTE DE EDICAO DE DATA: Atualiza a data prevista do componente
    async atualizarPrazoComponente(id, novaData) {
        const response = await fetch(`${API_BASE_URL}/componentes/${id}/prazo?nova_data=${novaData}`, {
            method: "PATCH",
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
    
    async alterarPrioridade(id, prioridade) {
        const response = await fetch(`${API_BASE_URL}/componentes/${id}/prioridade?nova_prioridade=${prioridade}`, {
            method: "PATCH",
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    async criarComponente(dados) {
        const response = await fetch(`${API_BASE_URL}/componentes`, {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify(dados)
        });
        return handleResponse(response);
    },

    async atualizarFluxo(id, etapasNomes) {
        const response = await fetch(`${API_BASE_URL}/componentes/${id}/fluxo`, {
            method: "PUT",
            headers: getHeaders(),
            body: JSON.stringify(etapasNomes)
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
    
    // Pendências
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

    // Folhas de ID em PDF
    async analisarFolhaID(componenteId, arquivos) {
        const formData = new FormData();
        arquivos.forEach(arquivo => formData.append("arquivos", arquivo));
        const response = await fetch(`${API_BASE_URL}/componentes/${componenteId}/folhas-id/analisar`, {
            method: "POST",
            headers: getHeaders(null),
            body: formData
        });
        return handleResponse(response);
    },

    async confirmarFolhaID(componenteId, arquivos, dados) {
        const formData = new FormData();
        arquivos.forEach(arquivo => formData.append("arquivos", arquivo));
        formData.append("dados_json", JSON.stringify(dados));
        const response = await fetch(`${API_BASE_URL}/componentes/${componenteId}/folhas-id/confirmar`, {
            method: "POST",
            headers: getHeaders(null),
            body: formData
        });
        return handleResponse(response);
    },

    async retornarFolhaIDRevisao(componenteId, idTecnicaId, motivo) {
        const response = await fetch(`${API_BASE_URL}/componentes/${componenteId}/folhas-id/${idTecnicaId}/retornar-revisao`, {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify({ motivo })
        });
        return handleResponse(response);
    },

    async retornarDesenhoRevisao(componenteId, idTecnicaId, desenhoId, motivo) {
        const response = await fetch(`${API_BASE_URL}/componentes/${componenteId}/folhas-id/${idTecnicaId}/desenhos/${desenhoId}/retornar-revisao`, {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify({ motivo })
        });
        return handleResponse(response);
    },

    async cancelarRevisaoDesenho(componenteId, idTecnicaId, desenhoId) {
        const response = await fetch(`${API_BASE_URL}/componentes/${componenteId}/folhas-id/${idTecnicaId}/desenhos/${desenhoId}/cancelar-revisao`, {
            method: "POST",
            headers: getHeaders()
        });
        return handleResponse(response);
    },

    async alterarRecebimentoDesenho(componenteId, idTecnicaId, desenhoId, recebido) {
        const response = await fetch(`${API_BASE_URL}/componentes/${componenteId}/folhas-id/${idTecnicaId}/desenhos/${desenhoId}/recebimento`, {
            method: "PATCH",
            headers: getHeaders(),
            body: JSON.stringify({ recebido })
        });
        return handleResponse(response);
    },

    async excluirFolhaID(componenteId, idTecnicaId) {
        const response = await fetch(`${API_BASE_URL}/componentes/${componenteId}/folhas-id/${idTecnicaId}`, {
            method: "DELETE",
            headers: getHeaders()
        });
        return handleResponse(response);
    },

    async baixarFolhaID(componenteId, idTecnicaId) {
        const response = await fetch(`${API_BASE_URL}/componentes/${componenteId}/folhas-id/${idTecnicaId}/arquivo`, {
            headers: getHeaders(null)
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

    async getPendenciasDesenhos() {
        const response = await fetch(`${API_BASE_URL}/pendencias-desenhos`, {
            headers: getHeaders()
        });
        return handleResponse(response);
    },
    
    // Exportação Excel
    async exportarExcel() {
        const response = await fetch(`${API_BASE_URL}/export/excel`, {
            headers: getHeaders(null) // Cabeçalho Content-Type vazio
        });
        return handleResponse(response);
    }
};
