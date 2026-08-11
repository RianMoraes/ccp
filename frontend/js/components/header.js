import { API } from "../api.js";

export function renderHeader(title = "Centro de Controle da Produção") {
    // Carregar informações do usuário logado
    const userStr = localStorage.getItem("ccp_user");
    const user = userStr ? JSON.parse(userStr) : { nome: "Analista PCP", cargo: "Planejamento" };

    const headerHtml = `
    <header class="fixed top-0 right-0 left-64 h-20 z-30 flex flex-col justify-center px-6 bg-white border-b border-slate-200 transition-all duration-200">
        <div class="flex items-center justify-between w-full">
            <div class="flex flex-col gap-0.5 flex-1">
                <div id="header-title" class="font-headline-md text-headline-md font-black text-slate-800 leading-tight">${title}</div>
            </div>
            <div class="flex items-center gap-6">
                <!-- Busca Global -->
                <div class="relative w-96 group">
                    <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-[20px] group-focus-within:text-slate-800 transition-colors">search</span>
                    <input id="input-busca-global" class="w-full bg-slate-50 hover:bg-slate-100 focus:bg-white border border-slate-200 rounded-xl py-2 pl-10 pr-12 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-blue-900 focus:ring-1 focus:ring-blue-900 transition-all shadow-sm" placeholder="Buscar por equipamento, componente, cliente ou ordem..." type="text">
                    <div id="busca-resultados-modal" class="hidden absolute left-0 right-0 top-12 bg-white border border-slate-200 rounded-xl shadow-lg p-4 z-50 max-h-96 overflow-y-auto">
                        <!-- Inserção dos resultados via JS -->
                    </div>
                </div>
                <!-- Perfil Usuário -->
                <div class="flex items-center gap-3 pl-6 border-l border-slate-200">
                    <div class="text-right">
                        <p class="font-label-bold text-label-bold text-slate-800">${user.nome}</p>
                        <p class="text-[10px] text-slate-500">${user.cargo || "Analista PCP"}</p>
                    </div>
                </div>
            </div>
        </div>
    </header>
    `;

    const container = document.getElementById("header-container");
    if (container) {
        container.innerHTML = headerHtml;
    } else {
        const main = document.querySelector("main");
        if (main) {
            main.insertAdjacentHTML("beforebegin", headerHtml);
        }
    }

    // Configuração de eventos da busca global
    const inputBusca = document.getElementById("input-busca-global");
    const modalResultados = document.getElementById("busca-resultados-modal");

    if (inputBusca && modalResultados) {
        inputBusca.addEventListener("input", async (e) => {
            const termo = e.target.value.trim();
            if (termo.length < 2) {
                modalResultados.classList.add("hidden");
                return;
            }

            try {
                const res = await API.buscarGlobal(termo);
                const { clientes, equipamentos, componentes } = res.resultados;

                let html = "";
                
                if (!clientes.length && !equipamentos.length && !componentes.length) {
                    html = `<p class="text-xs text-slate-500 italic">Nenhum resultado encontrado.</p>`;
                } else {
                    if (clientes.length) {
                        html += `<div class="mb-3">
                            <h4 class="text-[10px] font-bold text-slate-800 uppercase tracking-wider mb-1">Clientes</h4>
                            ${clientes.map(c => `<div class="py-1 border-b border-slate-200 text-xs"><a href="equipamentos.html?cliente_id=${c.id}" class="hover:text-slate-800 font-medium">${c.nome} (${c.sigla})</a></div>`).join("")}
                        </div>`;
                    }
                    if (equipamentos.length) {
                        html += `<div class="mb-3">
                            <h4 class="text-[10px] font-bold text-slate-800 uppercase tracking-wider mb-1">Equipamentos</h4>
                            ${equipamentos.map(eq => `<div class="py-1 border-b border-slate-200 text-xs"><a href="equipamento-detalhe.html?id=${eq.id}" class="hover:text-slate-800 font-medium">${eq.nome}</a> <span class="text-[10px] text-slate-500 font-mono">OP: ${eq.op || 'N/A'}</span></div>`).join("")}
                        </div>`;
                    }
                    if (componentes.length) {
                        html += `<div>
                            <h4 class="text-[10px] font-bold text-slate-800 uppercase tracking-wider mb-1">Componentes</h4>
                            ${componentes.map(comp => `<div class="py-1 border-b border-slate-200 text-xs"><a href="equipamento-detalhe.html?id=${comp.equipamento_id}&componente_id=${comp.id}" class="hover:text-slate-800 font-medium">${comp.nome}</a> <span class="text-[10px] text-slate-500">em ${comp.equipamento_nome}</span></div>`).join("")}
                        </div>`;
                    }
                }

                modalResultados.innerHTML = html;
                modalResultados.classList.remove("hidden");
            } catch (err) {
                console.error("Erro na busca global:", err);
            }
        });

        // Fechar resultados ao clicar fora
        document.addEventListener("click", (e) => {
            if (!inputBusca.contains(e.target) && !modalResultados.contains(e.target)) {
                modalResultados.classList.add("hidden");
            }
        });
    }
}
