export function renderSidebar(activeMenu = "dashboard") {
    const userStr = localStorage.getItem("ccp_user");
    const user = userStr ? JSON.parse(userStr) : null;
    const podeAdministrar = user?.perfil === "admin";
    const podeOperar = user?.perfil === "admin" || user?.perfil === "pcp";
    window.CCP_ACESSO = { perfil: user?.perfil || null, podeOperar, podeAdministrar };
    const sidebarHtml = `
    <aside class="fixed left-0 top-0 h-full z-40 flex flex-col bg-white border-r border-slate-200 w-64 transition-colors duration-150 ease-in-out">
        <div class="p-6 flex flex-col gap-1">
            <h1 class="font-headline-sm text-headline-sm font-bold text-slate-800">CCP</h1>
            <p class="font-body-sm text-body-sm text-slate-400">Controle de Produção</p>
        </div>
        <nav class="flex-1 px-3 space-y-1">
            <a id="menu-dashboard" class="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors duration-150 ease-in-out ${activeMenu === 'dashboard' ? 'bg-blue-50 text-blue-900 font-bold' : 'text-slate-500 hover:bg-slate-100'}" href="index.html">
                <span class="material-symbols-outlined">home</span>
                <span class="font-body-md text-body-md">Painel de Controle</span>
            </a>
            <a id="menu-equipamentos" class="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors duration-150 ease-in-out ${activeMenu === 'equipamentos' ? 'bg-blue-50 text-blue-900 font-bold' : 'text-slate-500 hover:bg-slate-100'}" href="equipamentos.html">
                <span class="material-symbols-outlined">factory</span>
                <span class="font-body-md text-body-md">Equipamentos</span>
            </a>
            <a id="menu-kanban" class="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors duration-150 ease-in-out ${activeMenu === 'kanban' ? 'bg-blue-50 text-blue-900 font-bold' : 'text-slate-500 hover:bg-slate-100'}" href="kanban.html">
                <span class="material-symbols-outlined">view_kanban</span>
                <span class="font-body-md text-body-md">Kanban</span>
            </a>
            <a id="menu-entregas" class="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors duration-150 ease-in-out ${activeMenu === 'entregas' ? 'bg-blue-50 text-blue-900 font-bold' : 'text-slate-500 hover:bg-slate-100'}" href="entregas.html">
                <span class="material-symbols-outlined">local_shipping</span>
                <span class="font-body-md text-body-md">Entregas</span>
            </a>
        </nav>
        <div class="p-3 border-t border-slate-200 space-y-1">
            ${podeAdministrar ? `<a id="menu-settings" class="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors duration-150 ease-in-out ${activeMenu === 'settings' ? 'bg-blue-50 text-blue-900 font-bold' : 'text-slate-500 hover:bg-slate-100'}" href="configuracoes.html">
                <span class="material-symbols-outlined">settings</span>
                <span class="font-body-md text-body-md">Configurações</span>
            </a>` : ''}
            <button id="btn-logout" class="flex items-center gap-3 w-full px-3 py-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors duration-150 ease-in-out text-left">
                <span class="material-symbols-outlined">logout</span>
                <span class="font-body-md text-body-md">Sair</span>
            </button>
        </div>
    </aside>
    `;
    
    // Insere no elemento com id="sidebar-container" ou no início do body
    const container = document.getElementById("sidebar-container");
    if (container) {
        container.innerHTML = sidebarHtml;
    } else {
        document.body.insertAdjacentHTML("afterbegin", sidebarHtml);
    }

    aplicarModoConsulta(podeOperar);
    
    // Adiciona listener do botão Sair
    const logoutBtn = document.getElementById("btn-logout");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            localStorage.removeItem("ccp_token");
            localStorage.removeItem("ccp_user");
            window.location.href = "login.html";
        });
    }
}

function aplicarModoConsulta(podeOperar) {
    if (podeOperar) return;

    document.documentElement.classList.add("ccp-somente-consulta");
    const seletoresOperacao = [
        "#btn-novo-equipamento", "#btn-novo-componente",
        "#btn-retornar", "#btn-avancar", "#btn-abrir-pendencia-modal",
        "#btn-customizar-fluxo-componente", "#btn-excluir-componente",
        "#modal-btn-salvar", "#btn-analisar-folha-id", "#btn-confirmar-folha-id",
        "#btn-comp-add-etapa", "#btn-novo-cliente", "#btn-novo-usuario",
        "#btn-novo-modelo", "#btn-add-etapa-input",
        "[onclick*='abrirModalComponente']", "[onclick*='excluirEquipamento']",
        "[onclick*='excluirComponente']", "[onclick*='cancelarPendencia']",
        "[onclick*='retornarIDRevisao']", "[onclick*='abrirImportacaoFolhaID']",
        "[onclick*='excluirFolhaID']", "[onclick*='deletarCliente']",
        "[onclick*='deletarUsuario']", "[onclick*='deletarModelo']",
        "[onclick*='removerEtapaInput']", "[onchange*='alterarPrazo']"
    ].join(",");

    const ocultarAcoes = raiz => {
        if (raiz.nodeType !== Node.ELEMENT_NODE && raiz !== document) return;
        const elementos = [];
        if (raiz !== document && raiz.matches?.(seletoresOperacao)) elementos.push(raiz);
        elementos.push(...raiz.querySelectorAll(seletoresOperacao));
        elementos.forEach(elemento => elemento.classList.add("hidden"));

        const arrastaveis = [];
        if (raiz !== document && raiz.matches?.("[draggable='true']")) arrastaveis.push(raiz);
        arrastaveis.push(...raiz.querySelectorAll("[draggable='true']"));
        arrastaveis.forEach(elemento => {
            elemento.draggable = false;
            elemento.classList.remove("cursor-grab", "active:cursor-grabbing");
        });
    };

    ocultarAcoes(document);
    new MutationObserver(mudancas => {
        mudancas.forEach(mudanca => mudanca.addedNodes.forEach(ocultarAcoes));
    }).observe(document.body, { childList: true, subtree: true });
}
