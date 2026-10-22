"use strict";

/*
 * RiscoIA - analise.js
 * -------------------------------------------------------------------------
 * Páginas de dados dentro do próprio site (sem mandar para o portal do
 * InfoSiga): Explorar dados, Ficha de via/zona, Comparar cidades e Dados
 * (transparência). Consome `GET /analise/...` (ver src/app/api/routes/
 * analise.py), `GET /sinistros/geojson` e, na ficha, `GET /risco/...`.
 * Cada página é identificada por <body data-page="...">.
 */
(function () {
    const pagina = document.body.dataset.page;
    if (!["explorar", "ficha", "comparar", "dados"].includes(pagina)) return;

    const esc = RiscoIA.escapeHtml;
    const fmt = (v, casas = 0) => Number(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
    const pct = (parte, total) => (total ? fmt((parte / total) * 100, 1) + "%" : "-");
    const dataBr = (iso) => (iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : "-");
    const COR = { fatal: "#d03b3b", grave: "#ec835a", leve: "#fab219", ileso: "#22c55e", nao_disponivel: "#64748b", azul: "#38bdf8", laranja: "#f59e0b", destaque: "#ef4444", neutro: "#3b82f6" };
    const DIAS = RiscoIA.DIA_OPTIONS;

    async function api(path) {
        const response = await fetch(RiscoIA.apiUrl(path));
        if (!response.ok) {
            const erro = await response.json().catch(() => null);
            throw new Error(erro?.detail || "Falha ao consultar " + path);
        }
        return response.json();
    }

    function qs(obj) {
        const p = new URLSearchParams();
        Object.entries(obj).forEach(([k, v]) => {
            if (v === undefined || v === null || v === "") return;
            (Array.isArray(v) ? v : [v]).forEach((x) => p.append(k, x));
        });
        const s = p.toString();
        return s ? "?" + s : "";
    }

    // A base oficial vem em maiúsculas e sem acento.
    const ROTULOS = {
        MADRUGADA: "Madrugada", MANHA: "Manhã", TARDE: "Tarde", NOITE: "Noite",
        "NAO DISPONIVEL": "Não informado", "NAO INFORMADO": "Não informado",
        COLISAO: "Colisão", ATROPELAMENTO: "Atropelamento", CHOQUE: "Choque", OUTROS: "Outros",
        "VIAS URBANAS": "Vias urbanas", "ESTRADAS E RODOVIAS": "Estradas e rodovias",
        NOTIFICACAO: "Notificação", "SINISTRO FATAL": "Sinistro fatal", "SINISTRO NAO FATAL": "Sinistro não fatal",
        AUTOMOVEL: "Automóvel", MOTOCICLETA: "Motocicleta", CAMINHAO: "Caminhão", ONIBUS: "Ônibus",
        BICICLETA: "Bicicleta", PEDESTRE: "Pedestre", CONDUTOR: "Condutor", PASSAGEIRO: "Passageiro",
        MASCULINO: "Masculino", FEMININO: "Feminino"
    };
    const rotulo = (chave) => ROTULOS[chave] || RiscoIA.formatVia(chave);

    // ---------------------------------------------------------------------
    // Gráficos (Chart.js)
    // ---------------------------------------------------------------------
    const graficos = {};
    if (typeof Chart !== "undefined") {
        Chart.defaults.color = "#9db3c9";
        Chart.defaults.borderColor = "rgba(91,145,190,.15)";
        Chart.defaults.maintainAspectRatio = false;
    }

    function grafico(id, config) {
        const canvas = document.getElementById(id);
        if (!canvas || typeof Chart === "undefined") return;
        graficos[id]?.destroy();
        graficos[id] = new Chart(canvas, config);
    }

    function barras(id, itens, { horizontal = false, cor = COR.neutro, rotuloFn = rotulo, label = "Sinistros", campo = "sinistros" } = {}) {
        grafico(id, {
            type: "bar",
            data: { labels: itens.map((i) => rotuloFn(i.chave)), datasets: [{ label, data: itens.map((i) => i[campo]), backgroundColor: cor }] },
            options: { indexAxis: horizontal ? "y" : "x", plugins: { legend: { display: false } }, scales: { [horizontal ? "x" : "y"]: { beginAtZero: true } } }
        });
    }

    function serieSinistrosObitos(id, pontos, rotuloFn = (p) => p) {
        grafico(id, {
            type: "bar",
            data: {
                labels: pontos.map((p) => rotuloFn(p.periodo)),
                datasets: [
                    { type: "bar", label: "Sinistros", data: pontos.map((p) => p.sinistros), backgroundColor: "rgba(59,130,246,.55)", yAxisID: "y" },
                    { type: "line", label: "Óbitos", data: pontos.map((p) => p.obitos), borderColor: COR.fatal, backgroundColor: COR.fatal, tension: 0.25, yAxisID: "y2" }
                ]
            },
            options: {
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { position: "bottom" } },
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: "Sinistros" } },
                    y2: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Óbitos" } }
                }
            }
        });
    }

    // Vítimas por grupo, empilhadas por gravidade.
    function vitimasEmpilhadas(id, grupos, { horizontal = true, rotuloFn = rotulo } = {}) {
        const camadas = [["fatal", "Óbito"], ["grave", "Grave"], ["leve", "Leve"], ["ileso", "Ileso"], ["nao_disponivel", "Não informado"]];
        grafico(id, {
            type: "bar",
            data: {
                labels: grupos.map((g) => rotuloFn(g.chave)),
                datasets: camadas.map(([k, nome]) => ({ label: nome, data: grupos.map((g) => g[k]), backgroundColor: COR[k] }))
            },
            options: {
                indexAxis: horizontal ? "y" : "x",
                plugins: { legend: { position: "bottom" } },
                scales: { x: { stacked: true, beginAtZero: true }, y: { stacked: true, beginAtZero: true } }
            }
        });
    }

    function kpis(el, itens) {
        if (!el) return;
        el.innerHTML = itens.map(([valor, nome, extra]) =>
            `<article class="kpi-card"><strong>${valor}</strong><span>${esc(nome)}</span>${extra ? `<small>${esc(extra)}</small>` : ""}</article>`
        ).join("");
    }

    function kpisResumo(r) {
        kpis(document.getElementById("kpis"), [
            [fmt(r.sinistros), "sinistros", `${dataBr(r.data_inicio)} a ${dataBr(r.data_fim)}`],
            [fmt(r.obitos), "óbitos", `${fmt(r.sinistros_fatais)} sinistros fatais`],
            [fmt(r.feridos_graves), "feridos graves", ""],
            [fmt(r.feridos_leves), "feridos leves", ""],
            [pct(r.com_coordenada, r.sinistros), "com coordenada", r.coordenada_generica
                ? `${fmt(r.coordenada_generica)} em ponto genérico, fora do mapa` : "aparecem no mapa"]
        ]);
    }

    function heatmapDiaHora(el, nota, dados) {
        if (!el) return;
        const max = Math.max(1, ...dados.matriz.flat());
        let html = '<div class="heat-cel heat-cab"></div>' + Array.from({ length: 24 }, (_, h) => `<div class="heat-cel heat-cab">${h}</div>`).join("");
        dados.matriz.forEach((linha, d) => {
            html += `<div class="heat-cel heat-dia">${DIAS[d].slice(0, 3)}</div>`;
            html += linha.map((v, h) => {
                const a = v ? 0.08 + 0.92 * (v / max) : 0;
                return `<div class="heat-cel" style="background:rgba(239,68,68,${a.toFixed(3)})" title="${DIAS[d]}, ${h}h: ${fmt(v)} sinistros"></div>`;
            }).join("");
        });
        el.innerHTML = html;
        if (nota) nota.textContent = "Quanto mais vermelho, mais sinistros naquele dia e hora." + (dados.sem_hora ? ` ${fmt(dados.sem_hora)} sem hora informada ficaram de fora.` : "");
    }

    function tabelaVias(tbody, vias) {
        if (!tbody) return;
        tbody.innerHTML = vias.map((v, i) =>
            `<tr><td>${i + 1}</td><td><a href="ficha.html?via=${encodeURIComponent(v.via)}">${esc(RiscoIA.formatVia(v.via))}</a></td>` +
            `<td>${fmt(v.sinistros)}</td><td>${fmt(v.obitos)}</td><td>${fmt(v.feridos_graves)}</td>` +
            `<td><a class="link-ficha" href="ficha.html?via=${encodeURIComponent(v.via)}">ficha →</a></td></tr>`
        ).join("") || '<tr><td colspan="6">Nenhuma via no recorte.</td></tr>';
    }

    // Os 3 recortes de vítimas mais citados em políticas de trânsito.
    function destaquesObitos(el, v) {
        if (!el) return;
        const mortos = v.por_gravidade.fatal || 0;
        if (!mortos) {
            el.innerHTML = "<p>Nenhum óbito no recorte.</p>";
            return;
        }
        const fatia = (grupos, chave) => grupos.find((g) => g.chave === chave)?.fatal || 0;
        const maiorFaixa = [...v.faixa_etaria].filter((g) => g.chave !== "NAO DISPONIVEL").sort((a, b) => b.fatal - a.fatal)[0];
        const itens = [
            ["Motociclistas", fatia(v.modo_transporte, "MOTOCICLETA")],
            ["Pedestres", fatia(v.tipo_de_vitima, "PEDESTRE")],
            ["Homens", fatia(v.sexo, "MASCULINO")]
        ];
        el.innerHTML = `<p class="destaque-total">${fmt(mortos)} mortos no recorte</p>` + itens.map(([nome, n]) =>
            `<div class="destaque"><strong>${pct(n, mortos)}</strong><span>${nome} (${fmt(n)})</span></div>`
        ).join("") + (maiorFaixa ? `<div class="destaque"><strong>${esc(maiorFaixa.chave)}</strong><span>faixa etária com mais óbitos (${fmt(maiorFaixa.fatal)})</span></div>` : "");
    }

    // ---------------------------------------------------------------------
    // Mapa (Leaflet): calor dos sinistros do recorte
    // ---------------------------------------------------------------------
    function criarMapa(id) {
        const el = document.getElementById(id);
        if (!el || typeof L === "undefined") return null;
        const mapa = L.map(el).setView([-21.1775, -47.8103], 12);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap contributors" }).addTo(mapa);
        return mapa;
    }

    function paramsGeo(f) {
        return { data_inicio: f.data_inicio, data_fim: f.data_fim, gravidade: f.gravidade, tp_sinistro_primario: f.tp_sinistro_primario,
                 tipo_via: f.tipo_via, logradouro: f.via, turno: f.turno, lat_min: f.lat_min, lat_max: f.lat_max, lon_min: f.lon_min, lon_max: f.lon_max };
    }

    // ---------------------------------------------------------------------
    // Explorar dados
    // ---------------------------------------------------------------------
    const CAMPOS_URL = ["data_inicio", "data_fim", "via", "turno", "gravidade", "tp_sinistro_primario", "tipo_via"];

    async function iniciarExplorar() {
        const form = document.getElementById("filtros");
        const campos = {
            data_inicio: document.getElementById("fDataInicio"), data_fim: document.getElementById("fDataFim"),
            gravidade: document.getElementById("fGravidade"), tp_sinistro_primario: document.getElementById("fTipo"),
            turno: document.getElementById("fTurno"), tipo_via: document.getElementById("fTipoVia"), via: document.getElementById("fVia")
        };
        const preset = document.getElementById("fPreset");

        const [geral, opcoes, viasLista] = await Promise.all([
            api("/analise/resumo"), api("/sinistros/opcoes").catch(() => null), api("/analise/vias?limit=500").catch(() => [])
        ]);
        if (!geral.sinistros) {
            document.getElementById("explorarSubtitulo").textContent = "Nenhum sinistro carregado ainda (rode scripts/carregar_infosiga.py).";
            return;
        }
        const preencher = (select, valores) => valores.forEach((v) => select.insertAdjacentHTML("beforeend", `<option value="${esc(v)}">${esc(rotulo(v))}</option>`));
        preencher(campos.tp_sinistro_primario, (opcoes?.tp_sinistro_primario || []).filter((v) => v !== "NAO DISPONIVEL"));
        preencher(campos.tipo_via, (opcoes?.tipo_via || []).filter((v) => v !== "NAO DISPONIVEL"));
        document.getElementById("listaVias").innerHTML = viasLista.map((v) => `<option value="${esc(v.via)}">`).join("");

        const fim = geral.data_fim;
        const aplicarPreset = (nome) => {
            const ano = fim.slice(0, 4);
            const inicio12 = new Date(fim);
            inicio12.setFullYear(inicio12.getFullYear() - 1);
            inicio12.setDate(inicio12.getDate() + 1);
            const mapa = {
                "12m": [inicio12.toISOString().slice(0, 10), fim],
                "ano-atual": [`${ano}-01-01`, fim],
                serie: ["2019-01-01", fim],
                tudo: [geral.data_inicio, fim]
            };
            if (mapa[nome]) [campos.data_inicio.value, campos.data_fim.value] = mapa[nome];
        };
        preset.addEventListener("change", () => { aplicarPreset(preset.value); carregar(); });
        [campos.data_inicio, campos.data_fim].forEach((c) => c.addEventListener("change", () => { preset.value = ""; }));

        // Filtros vindos da URL (ex.: link da ficha): sobrescrevem o padrão.
        const url = new URLSearchParams(location.search);
        aplicarPreset("serie");
        CAMPOS_URL.forEach((k) => { if (url.get(k) && campos[k]) campos[k].value = url.get(k); });
        if (url.get("data_inicio") || url.get("data_fim")) preset.value = "";

        const mapa = criarMapa("mapaAnalise");
        let camadaCalor = null;

        const lerFiltros = () => Object.fromEntries(Object.entries(campos).map(([k, el]) => [k, el.value.trim()]));

        async function carregar() {
            const f = lerFiltros();
            history.replaceState(null, "", "explorar.html" + qs(f));
            const q = qs(f);
            document.getElementById("linkExportar").href = RiscoIA.apiUrl("/analise/exportar.csv" + q);
            const partes = [];
            if (f.via) partes.push(`via ${RiscoIA.formatVia(f.via)}`);
            if (f.gravidade) partes.push({ fatal: "com óbito", grave: "com ferido grave", leve: "com ferido leve" }[f.gravidade]);
            if (f.tp_sinistro_primario) partes.push(rotulo(f.tp_sinistro_primario).toLowerCase());
            if (f.turno) partes.push(rotulo(f.turno).toLowerCase());
            if (f.tipo_via) partes.push(rotulo(f.tipo_via).toLowerCase());
            document.getElementById("filtrosResumo").textContent =
                `Recorte: ${dataBr(f.data_inicio)} a ${dataBr(f.data_fim)}` + (partes.length ? " · " + partes.join(" · ") : "") +
                (f.data_inicio && f.data_inicio < "2019-01-01" ? ". Atenção: antes de 2019 o InfoSiga só registra sinistros com óbito." : ".");

            const [res, serie, tipo, veiculo, hora, dia, diaHora, vias, vit] = await Promise.all([
                api("/analise/resumo" + q), api("/analise/serie" + qs({ ...f, granularidade: "mes" })),
                api("/analise/distribuicao" + qs({ ...f, dimensao: "tipo_sinistro" })),
                api("/analise/distribuicao" + qs({ ...f, dimensao: "veiculo" })),
                api("/analise/distribuicao" + qs({ ...f, dimensao: "hora" })),
                api("/analise/distribuicao" + qs({ ...f, dimensao: "dia_da_semana" })),
                api("/analise/dia-hora" + q), api("/analise/vias" + qs({ ...f, limit: 20 })), api("/analise/vitimas" + q)
            ]);
            kpisResumo(res);
            serieSinistrosObitos("cSerie", serie, (p) => p.slice(5, 7) + "/" + p.slice(0, 4));
            barras("cTipo", tipo, { horizontal: true });
            barras("cVeiculo", veiculo, { horizontal: true, rotuloFn: (k) => k, cor: COR.laranja });
            barras("cHora", hora, { rotuloFn: (k) => k });
            barras("cDia", DIAS.map((d) => dia.find((x) => x.chave === d) || { chave: d, sinistros: 0 }), { rotuloFn: (k) => k.slice(0, 3) });
            heatmapDiaHora(document.getElementById("heatDiaHora"), document.getElementById("heatNota"), diaHora);
            tabelaVias(document.querySelector("#tabelaVias tbody"), vias);

            kpis(document.getElementById("kpisVitimas"), [
                [fmt(vit.total), "pessoas envolvidas", ""],
                [fmt(vit.por_gravidade.fatal || 0), "mortos", ""],
                [fmt(vit.por_gravidade.grave || 0), "feridos graves", ""],
                [fmt(vit.por_gravidade.leve || 0), "feridos leves", ""],
                [fmt(vit.por_gravidade.ileso || 0), "ilesos", ""]
            ]);
            vitimasEmpilhadas("cFaixa", vit.faixa_etaria.filter((g) => g.chave !== "NAO DISPONIVEL"), { horizontal: false, rotuloFn: (k) => k });
            vitimasEmpilhadas("cModo", vit.modo_transporte);
            vitimasEmpilhadas("cTipoVitima", vit.tipo_de_vitima);
            vitimasEmpilhadas("cSexo", vit.sexo);
            destaquesObitos(document.getElementById("destaquesObitos"), vit);

            if (mapa) {
                const geo = await api("/sinistros/geojson" + qs({ ...paramsGeo(f), recentes_primeiro: true, limit: 20000 }));
                if (camadaCalor) mapa.removeLayer(camadaCalor);
                const pesos = (p) => (p.qtd_gravidade_fatal > 0 ? 4 : p.qtd_gravidade_grave > 0 ? 2 : 1);
                // Teto de intensidade proporcional ao volume: com milhares de
                // pontos, um teto fixo satura a cidade inteira de vermelho.
                const n = geo.features.length;
                camadaCalor = L.heatLayer(geo.features.map((x) => [x.geometry.coordinates[1], x.geometry.coordinates[0], pesos(x.properties)]),
                    { radius: 16, blur: 18, maxZoom: 15, max: Math.max(4, n / 400) }).addTo(mapa);
                document.getElementById("mapaNota").textContent =
                    `${fmt(res.com_coordenada)} de ${fmt(res.sinistros)} sinistros do recorte têm coordenada` +
                    (n < res.com_coordenada ? `; o mapa mostra os ${fmt(n)} mais recentes` : "") + ". Óbitos pesam 4x e feridos graves 2x no calor.";
            }
        }

        form.addEventListener("submit", (e) => { e.preventDefault(); carregar(); });
        document.getElementById("fLimpar").addEventListener("click", () => {
            Object.values(campos).forEach((el) => { el.value = ""; });
            preset.value = "serie";
            aplicarPreset("serie");
            carregar();
        });
        carregar();
    }

    // ---------------------------------------------------------------------
    // Ficha de via ou zona
    // ---------------------------------------------------------------------
    async function iniciarFicha() {
        const url = new URLSearchParams(location.search);
        const via = url.get("via");
        const celula = url.get("celula");
        const erro = document.getElementById("fichaErro");
        const falhar = (msg) => {
            document.getElementById("fichaTitulo").textContent = "Ficha indisponível";
            document.getElementById("fichaConteudo").hidden = true;
            erro.hidden = false;
            erro.textContent = msg;
        };
        if (!via && !celula) return falhar("Abra a ficha a partir do mapa, do Explorar dados ou do ranking de vias.");

        let filtro;
        let geometria = null;
        const risco = document.getElementById("fichaRisco");
        const mapa = criarMapa("mapaFicha");

        if (via) {
            filtro = { via };
            document.getElementById("fichaTipo").textContent = "FICHA DA VIA";
            document.getElementById("fichaTitulo").textContent = RiscoIA.formatVia(via);
            const vias = await api("/risco/vias?limit=1000").catch(() => []);
            const previsao = vias.find((v) => v.via.toUpperCase() === via.toUpperCase());
            if (previsao) {
                const nivel = RiscoIA.levelFromApi(previsao.nivel_risco);
                risco.innerHTML = `<span class="risk-tag-inline ${nivel}">RISCO PREVISTO ${nivel.toUpperCase()}</span>` +
                    `<strong>${fmt(previsao.acidentes_esperados)} acidentes previstos nos próximos 12 meses</strong>` +
                    `<p>Previsão do modelo de risco (base RENAEST) para a via inteira, com ${fmt(previsao.acidentes_historico)} acidentes geocodificados desde 2023.</p>`;
                const link = document.getElementById("linkSimular");
                link.href = "predicao.html?via=" + encodeURIComponent(previsao.via);
                link.hidden = false;
            } else {
                risco.innerHTML = "<strong>Sem previsão de risco para esta via</strong><p>Os modelos só cobrem as vias com 15 ou mais acidentes geocodificados na base RENAEST desde 2023.</p>";
            }
            document.getElementById("linkExplorar").href = "explorar.html" + qs({ via });
        } else {
            const zona = (await api("/risco/zonas" + qs({ celula })).catch(() => ({ features: [] }))).features[0];
            if (!zona) return falhar("Zona não encontrada no modelo de risco publicado.");
            geometria = zona.geometry;
            const anel = zona.geometry.coordinates[0];
            const lons = anel.map((c) => c[0]);
            const lats = anel.map((c) => c[1]);
            filtro = { lat_min: Math.min(...lats), lat_max: Math.max(...lats), lon_min: Math.min(...lons), lon_max: Math.max(...lons) };
            const p = zona.properties;
            const nivel = RiscoIA.levelFromApi(p.nivel_risco);
            document.getElementById("fichaTipo").textContent = "FICHA DA ZONA (~550 m)";
            document.getElementById("fichaTitulo").textContent = p.rua_principal ? "Zona da " + RiscoIA.formatVia(p.rua_principal) : "Zona " + celula;
            const veic = await api("/risco/veiculos").then((r) => Promise.all(r.veiculos.map((v) =>
                api("/risco/zonas" + qs({ celula, veiculo: v.veiculo })).then((z) => [v.veiculo, z.features[0]?.properties.fracao_veiculo]))))
                .catch(() => []);
            risco.innerHTML = `<span class="risk-tag-inline ${nivel}">RISCO PREVISTO ${nivel.toUpperCase()}</span>` +
                `<strong>${fmt(p.acidentes_esperados)} acidentes previstos (${esc(p.janela_previsao)})</strong>` +
                `<p>${fmt(p.acidentes_12m)} nos últimos 12 meses da base RENAEST.` +
                (p.em_alta ? ` <b class="em-alta">Em alta:</b> ${fmt(p.tendencia_razao, 1)}x o esperado nos últimos 6 meses.` : "") + "</p>" +
                (veic.length ? `<p class="ficha-veiculos">${veic.filter(([, f]) => f != null).map(([k, f]) => `${RiscoIA.LABELS.veiculo[k]}: ${fmt(f * 100)}%`).join(" · ")} dos acidentes</p>` : "");
            document.getElementById("linkExplorar").hidden = true;
            document.getElementById("blocoViasZona").hidden = false;
        }

        const q = qs(filtro);
        document.getElementById("linkExportar").href = RiscoIA.apiUrl("/analise/exportar.csv" + q);
        const [res, serie, tipo, veiculo, diaHora, vit, viasZona] = await Promise.all([
            api("/analise/resumo" + q), api("/analise/serie" + qs({ ...filtro, granularidade: "ano" })),
            api("/analise/distribuicao" + qs({ ...filtro, dimensao: "tipo_sinistro" })),
            api("/analise/distribuicao" + qs({ ...filtro, dimensao: "veiculo" })),
            api("/analise/dia-hora" + q), api("/analise/vitimas" + q),
            celula ? api("/analise/vias" + qs({ ...filtro, limit: 10 })) : Promise.resolve([])
        ]);
        if (!res.sinistros) return falhar("Nenhum sinistro do InfoSiga registrado " + (via ? "com esse nome de via." : "nessa zona."));
        document.getElementById("fichaSubtitulo").textContent =
            `${fmt(res.sinistros)} sinistros registrados pelo InfoSiga entre ${dataBr(res.data_inicio)} e ${dataBr(res.data_fim)}.`;
        kpisResumo(res);
        serieSinistrosObitos("cSerieAno", serie);
        heatmapDiaHora(document.getElementById("heatDiaHora"), document.getElementById("heatNota"), diaHora);
        barras("cTipo", tipo, { horizontal: true });
        barras("cVeiculo", veiculo, { horizontal: true, rotuloFn: (k) => k, cor: COR.laranja });
        vitimasEmpilhadas("cModo", vit.modo_transporte);
        vitimasEmpilhadas("cFaixa", vit.faixa_etaria.filter((g) => g.chave !== "NAO DISPONIVEL"), { horizontal: false, rotuloFn: (k) => k });
        tabelaVias(document.querySelector("#tabelaVias tbody"), viasZona);

        if (mapa) {
            const geo = await api("/sinistros/geojson" + qs({ ...paramsGeo(filtro), recentes_primeiro: true, limit: 5000 }));
            const camadas = [];
            if (geometria) {
                camadas.push(L.geoJSON(geometria, { style: { color: COR.destaque, weight: 2, fillOpacity: 0.12 } }));
            }
            camadas.push(L.geoJSON(geo, {
                pointToLayer: (f, latlng) => L.circleMarker(latlng, {
                    radius: 4, weight: 1, color: "#141414", fillOpacity: 0.85,
                    fillColor: f.properties.qtd_gravidade_fatal > 0 ? COR.fatal : f.properties.qtd_gravidade_grave > 0 ? COR.grave : COR.leve
                }).bindTooltip(`${dataBr(f.properties.data)} · ${esc(rotulo(f.properties.tp_sinistro_primario || "NAO DISPONIVEL"))}`)
            }));
            const grupo = L.featureGroup(camadas).addTo(mapa);
            if (grupo.getBounds().isValid()) mapa.fitBounds(grupo.getBounds(), { padding: [20, 20], maxZoom: 16 });
        }
    }

    // ---------------------------------------------------------------------
    // Comparar cidades
    // ---------------------------------------------------------------------
    const INDICADORES = {
        obitos_100k: { nome: "Óbitos por 100 mil hab.", desde: 2015 },
        graves_100k: { nome: "Feridos graves por 100 mil hab.", desde: 2019 },
        sinistros_100k: { nome: "Registros por 100 mil hab.", desde: 2019 }
    };

    async function iniciarComparar() {
        const selAno = document.getElementById("cAno");
        const selPop = document.getElementById("cPopMin");
        const selInd = document.getElementById("cIndicador");
        const aviso = document.getElementById("compararAviso");

        let base;
        try {
            base = await api("/analise/municipios");
        } catch (error) {
            aviso.textContent = error.message;
            return;
        }
        const padrao = base.ano;
        base.anos_disponiveis.filter((a) => a >= 2015).reverse().forEach((a) => {
            selAno.insertAdjacentHTML("beforeend", `<option value="${a}"${a === padrao ? " selected" : ""}>${a}</option>`);
        });

        async function carregar() {
            const indicador = selInd.value;
            const info = INDICADORES[indicador];
            const dados = await api("/analise/municipios" + qs({ ano: selAno.value, populacao_min: selPop.value }));
            const ref = dados.referencia;
            const lista = [...dados.municipios].sort((a, b) => (b[indicador] || 0) - (a[indicador] || 0));
            const posicao = ref ? lista.findIndex((m) => m.cod_ibge === ref.cod_ibge) + 1 : 0;

            const avisos = [];
            if (dados.meses_com_dados < 12) avisos.push(`${dados.ano} ainda está incompleto (${dados.meses_com_dados} meses): os valores são parciais, não anualizados.`);
            if (dados.ano < info.desde) avisos.push(`Antes de ${info.desde} o InfoSiga só registra sinistros com óbito: este indicador não é comparável nesse ano.`);
            if (indicador === "sinistros_100k") avisos.push("Registros por habitante dependem de quanto cada cidade notifica sinistros sem vítima: compare com cautela. Óbitos é o indicador mais comparável.");
            aviso.textContent = avisos.join(" ");
            aviso.hidden = !avisos.length;

            const numerador = { obitos_100k: "obitos", graves_100k: "feridos_graves", sinistros_100k: "sinistros" }[indicador];
            const popTotal = lista.reduce((s, m) => s + (m.populacao || 0), 0);
            const media = popTotal ? (lista.reduce((s, m) => s + m[numerador], 0) / popTotal) * 100000 : 0;
            kpis(document.getElementById("kpisComparar"), [
                [ref ? fmt(ref[indicador], 1) : "-", "Ribeirão Preto", info.nome],
                [posicao ? `${posicao}º de ${lista.length}` : "fora do grupo", "posição no ranking", "1º = maior valor"],
                [fmt(media, 1), "média do grupo", "ponderada pela população"],
                [lista[0] ? fmt(lista[0][indicador], 1) : "-", "maior valor", lista[0]?.municipio || ""],
                [lista.length ? fmt(lista[lista.length - 1][indicador], 1) : "-", "menor valor", lista[lista.length - 1]?.municipio || ""]
            ]);

            document.getElementById("tituloRanking").textContent =
                `${info.nome} em ${dados.ano}: cidades de SP com ${fmt(Number(selPop.value))} habitantes ou mais`;
            grafico("cRanking", {
                type: "bar",
                data: {
                    labels: lista.map((m) => m.municipio),
                    datasets: [{ label: info.nome, data: lista.map((m) => m[indicador]),
                                 backgroundColor: lista.map((m) => (ref && m.cod_ibge === ref.cod_ibge ? COR.destaque : "rgba(59,130,246,.6)")) }]
                },
                options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } }
            });

            document.querySelector("#tabelaCidades tbody").innerHTML = lista.map((m, i) =>
                `<tr class="${ref && m.cod_ibge === ref.cod_ibge ? "linha-destaque" : ""}"><td>${i + 1}</td><td>${esc(m.municipio)}</td>` +
                `<td>${fmt(m.populacao)}</td><td>${fmt(m.obitos)}</td><td>${fmt(m.obitos_100k, 1)}</td><td>${fmt(m.graves_100k, 1)}</td>` +
                `<td>${fmt(m.sinistros_100k, 1)}</td><td>${pct(m.notificacoes, m.sinistros)}</td></tr>`
            ).join("");

            // Evolução: Ribeirão Preto + as 4 cidades do grupo com população mais parecida.
            if (ref) {
                const vizinhas = lista.filter((m) => m.cod_ibge !== ref.cod_ibge)
                    .sort((a, b) => Math.abs(a.populacao - ref.populacao) - Math.abs(b.populacao - ref.populacao)).slice(0, 4);
                const series = await api("/analise/municipios/serie" + qs({ cod_ibge: [ref.cod_ibge, ...vizinhas.map((m) => m.cod_ibge)] }));
                // Ano incompleto fica de fora: com menos meses ele sempre "despenca".
                const completos = new Set(series[0].anos.filter((a) => a.meses_com_dados === 12).map((a) => a.ano));
                const anos = [...new Set(series.flatMap((s) => s.anos.map((a) => a.ano)))].filter((a) => a >= info.desde && completos.has(a)).sort();
                const paleta = ["#ef4444", "#38bdf8", "#a78bfa", "#22c55e", "#f59e0b"];
                const ordem = [ref.cod_ibge, ...vizinhas.map((m) => m.cod_ibge)];
                series.sort((a, b) => ordem.indexOf(a.cod_ibge) - ordem.indexOf(b.cod_ibge));
                grafico("cEvolucao", {
                    type: "line",
                    data: {
                        labels: anos,
                        datasets: series.map((s, i) => ({
                            label: s.municipio, borderColor: paleta[i], backgroundColor: paleta[i], tension: 0.2,
                            borderWidth: s.cod_ibge === ref.cod_ibge ? 3.5 : 1.8,
                            data: anos.map((a) => s.anos.find((x) => x.ano === a)?.[indicador] ?? null)
                        }))
                    },
                    options: { plugins: { legend: { position: "bottom" } }, scales: { y: { beginAtZero: true, title: { display: true, text: info.nome } } } }
                });
                const parcial = series[0].anos.find((a) => a.meses_com_dados < 12);
                document.getElementById("evolucaoNota").textContent =
                    "Cidades escolhidas pela população mais próxima da de Ribeirão Preto dentro do grupo selecionado." +
                    (parcial ? ` ${parcial.ano} ainda está incompleto (${parcial.meses_com_dados} meses) e fica fora deste gráfico.` : "");
            }
        }
        [selAno, selPop, selInd].forEach((el) => el.addEventListener("change", carregar));
        carregar();
    }

    // ---------------------------------------------------------------------
    // Dados e qualidade (transparência)
    // ---------------------------------------------------------------------
    async function iniciarDados() {
        const q = await api("/analise/qualidade");
        const anos = q.por_ano.filter((a) => a.ano >= 2015);
        const total = anos.reduce((s, a) => s + a.sinistros, 0);
        const inicio = q.fontes.length ? q.fontes[0].data_inicio : null;
        const fim = q.fontes.length ? q.fontes[q.fontes.length - 1].data_fim : null;
        const r = q.renaest;

        const fontes = [
            ["InfoSiga (Detran-SP / Governo de SP)", `${fmt(total)} sinistros e ${fmt(q.pessoas)} pessoas envolvidas em Ribeirão Preto, de ${dataBr(inicio)} a ${dataBr(fim)}, mais os totais anuais de todos os 645 municípios do estado.`,
             "Usado em: Explorar dados, fichas, perfil das vítimas, camada de sinistros do mapa e comparação entre cidades."],
            ["RENAEST (Senatran)", r ? `Base nacional de acidentes, recorte de Ribeirão Preto. Modelo treinado em ${dataBr(r.gerado_em.slice(0, 10))} a partir de ${r.fonte}.` : "Ainda não há modelo de risco publicado.",
             "Usado em: zonas de risco, previsão por via e por veículo, pontos críticos, simulação e previsão mensal."],
            ["IBGE", "Estimativas anuais de população dos municípios e Censo 2022 (2023 interpolado entre o Censo e a estimativa de 2024).",
             "Usado em: indicadores por 100 mil habitantes da comparação entre cidades."]
        ];
        document.getElementById("fontes").innerHTML = fontes.map(([t, d, u]) =>
            `<article class="fonte-card"><h3>${esc(t)}</h3><p>${esc(d)}</p><small>${esc(u)}</small></article>`).join("");

        // Limitações calculadas a partir dos próprios números.
        const lim = [];
        const soFatais = anos.filter((a) => a.ano < 2019).map((a) => a.ano);
        if (soFatais.length) lim.push(`De ${soFatais[0]} a ${soFatais[soFatais.length - 1]} o InfoSiga só tem os sinistros com óbito (${fmt(anos.filter((a) => a.ano < 2019).reduce((s, a) => s + a.sinistros, 0))} registros). Séries completas começam em 2019.`);
        const genericas = anos.reduce((s, a) => s + a.coordenada_generica, 0);
        if (genericas) lim.push(`${fmt(genericas)} sinistros (${pct(genericas, total)}) estão numa coordenada genérica do geocodificador: a mesma posição usada para dezenas de endereços diferentes. Eles contam nos totais, mas ficam fora do mapa e das fichas de zona.`);
        anos.filter((a) => a.ano >= 2019 && a.pct_coordenada < 90).forEach((a) =>
            lim.push(`Em ${a.ano}, só ${fmt(a.pct_coordenada, 1)}% dos sinistros têm coordenada: o mapa desse período mostra uma parte deles.`));
        const notifIni = anos.find((a) => a.ano === 2019);
        const notifFim = anos[anos.length - 1];
        if (notifIni && notifFim) lim.push(`A parcela de registros que são só notificação (sem vítimas classificadas) passou de ${fmt(notifIni.pct_notificacao, 1)}% em 2019 para ${fmt(notifFim.pct_notificacao, 1)}% em ${notifFim.ano}. Contar feridos leves ao longo dos anos subestima os anos recentes.`);
        if (fim && fim.slice(5, 7) !== "12") lim.push(`${fim.slice(0, 4)} ainda está incompleto (dados até ${dataBr(fim)}).`);
        if (r?.resumo_limpeza?.meses_ausentes?.length) lim.push(`Na RENAEST faltam os meses ${r.resumo_limpeza.meses_ausentes.join(", ")}; os modelos tratam esses meses como não observados.`);
        if (r?.veiculos) lim.push(`Na RENAEST, o tipo de veículo só é informado em ${fmt(r.veiculos.cobertura_tipo_veiculo * 100)}% dos acidentes desde 2023; a previsão por veículo supõe a mesma composição nos demais.`);
        lim.push("Nenhuma das bases registra por quanto tempo choveu, então o efeito do clima no risco não pode ser medido.");
        lim.push("Registros por habitante variam com o quanto cada cidade notifica sinistros sem vítima; para comparar cidades, óbitos é o indicador mais confiável.");
        document.getElementById("limitacoes").innerHTML = lim.map((t) => `<li>${esc(t)}</li>`).join("");

        grafico("cQualidade", {
            type: "line",
            data: {
                labels: anos.map((a) => a.ano),
                datasets: [
                    ["pct_coordenada", "Com coordenada", COR.azul], ["pct_vitimas_classificadas", "Com vítima classificada", COR.ileso],
                    ["pct_notificacao", "Só notificação", COR.laranja], ["pct_tipo_informado", "Tipo de sinistro informado", "#a78bfa"]
                ].map(([k, nome, cor]) => ({ label: nome, data: anos.map((a) => a[k]), borderColor: cor, backgroundColor: cor, tension: 0.2 }))
            },
            options: { plugins: { legend: { position: "bottom" } }, scales: { y: { min: 0, max: 100, title: { display: true, text: "% dos sinistros" } } } }
        });

        const p = (v) => (v == null ? "-" : fmt(v, 1) + "%");
        document.querySelector("#tabelaQualidade tbody").innerHTML = anos.map((a) =>
            `<tr><td>${a.ano}</td><td>${fmt(a.sinistros)}</td><td>${p(a.pct_coordenada)}</td><td>${fmt(a.coordenada_generica)}</td><td>${p(a.pct_vitimas_classificadas)}</td>` +
            `<td>${p(a.pct_notificacao)}</td><td>${p(a.pct_tipo_informado)}</td><td>${p(a.pct_hora)}</td><td>${fmt(a.pessoas)}</td>` +
            `<td>${p(a.pct_idade)}</td><td>${p(a.pct_gravidade_pessoa)}</td></tr>`).join("");

        if (r?.qualidade_por_ano) {
            document.getElementById("blocoRenaest").hidden = false;
            document.getElementById("renaestTexto").textContent =
                "Os modelos de risco usam a RENAEST porque ela foi a base entregue pelo time de dados para o treino. Comparada ao InfoSiga, ela registra quantidades parecidas, mas tem coordenada só de 2023 em diante e deixa de classificar os feridos não fatais a partir de 2023.";
            const infosiga = Object.fromEntries(anos.map((a) => [a.ano, a.sinistros]));
            document.querySelector("#tabelaRenaest tbody").innerHTML = r.qualidade_por_ano.map((a) =>
                `<tr><td>${a.ano}</td><td>${fmt(a.n)}</td><td>${fmt(infosiga[a.ano])}</td><td>${p(a.pct_coord_valida)}</td>` +
                `<td>${p(a.pct_obito)}</td><td>${p(a.pct_com_ferido)}</td><td>${p(a.pct_tp_acid_informado)}</td></tr>`).join("");
        }
    }

    const iniciar = { explorar: iniciarExplorar, ficha: iniciarFicha, comparar: iniciarComparar, dados: iniciarDados }[pagina];
    document.addEventListener("DOMContentLoaded", () => {
        iniciar().catch((error) => {
            const alvo = document.querySelector(".section-heading p");
            if (alvo) alvo.textContent = "Não foi possível carregar os dados agora: " + error.message;
        });
    });
})();
