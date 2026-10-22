/*
 * RiscoIA - testes básicos das funções puras de utils.js
 * -------------------------------------------------------------------------
 * Não existia nenhum teste automatizado no projeto original. Este arquivo
 * não usa nenhum framework (Jest, Mocha, etc.) de propósito, para não exigir
 * "npm install" antes de rodar - basta ter Node instalado.
 *
 * Como rodar:
 *   node tests/logic.test.js
 *
 * Um teste que falha imprime o motivo e o processo termina com código de
 * saída 1 (útil para plugar depois numa esteira de CI, se quiser).
 */

const assert = require("assert");
const RiscoIA = require("../utils.js");

let passed = 0;
let failed = 0;

function test(description, fn) {
    try {
        fn();
        console.log(`  OK  - ${description}`);
        passed++;
    } catch (error) {
        console.error(`FALHOU - ${description}`);
        console.error(`        ${error.message}`);
        failed++;
    }
}

console.log("RiscoIA - testes de lógica pura\n");

// --- calculateFallback -----------------------------------------------------
test("calculateFallback: base sem nenhum fator de risco fica em 30", () => {
    const prob = RiscoIA.calculateFallback({ via: "centro", horario: "fora-pico", clima: "nublado", dia: "Terça-feira" });
    assert.strictEqual(prob, 30);
});

test("calculateFallback: horário de pico aumenta o score", () => {
    const semPico = RiscoIA.calculateFallback({ via: "centro", horario: "fora-pico", clima: "sol", dia: "Terça-feira" });
    const comPico = RiscoIA.calculateFallback({ via: "centro", horario: "pico-manha", clima: "sol", dia: "Terça-feira" });
    assert.ok(comPico > semPico, "esperado que horário de pico aumente o risco");
});

test("calculateFallback: chuva aumenta o score", () => {
    const semChuva = RiscoIA.calculateFallback({ via: "centro", horario: "fora-pico", clima: "sol", dia: "Terça-feira" });
    const comChuva = RiscoIA.calculateFallback({ via: "centro", horario: "fora-pico", clima: "chuva", dia: "Terça-feira" });
    assert.ok(comChuva > semChuva, "esperado que chuva aumente o risco");
});

test("calculateFallback: fim de semana reduz o score em relação a sexta", () => {
    const sexta = RiscoIA.calculateFallback({ via: "centro", horario: "fora-pico", clima: "sol", dia: "Sexta-feira" });
    const domingo = RiscoIA.calculateFallback({ via: "centro", horario: "fora-pico", clima: "sol", dia: "Domingo" });
    assert.ok(domingo < sexta, "esperado que domingo tenha score menor que sexta");
});

test("calculateFallback: nunca ultrapassa 97 nem fica abaixo de 5", () => {
    const maximo = RiscoIA.calculateFallback({ via: "francisco-junqueira", horario: "pico-noite", clima: "chuva", dia: "Sexta-feira" });
    assert.ok(maximo <= 97);
    const minimo = RiscoIA.calculateFallback({ via: "botanico", horario: "fora-pico", clima: "sol", dia: "Domingo" });
    assert.ok(minimo >= 5);
});

// --- levelFromProb -----------------------------------------------------
test("levelFromProb: classifica corretamente os três níveis", () => {
    assert.strictEqual(RiscoIA.levelFromProb(10), "baixo");
    assert.strictEqual(RiscoIA.levelFromProb(39), "baixo");
    assert.strictEqual(RiscoIA.levelFromProb(40), "medio");
    assert.strictEqual(RiscoIA.levelFromProb(69), "medio");
    assert.strictEqual(RiscoIA.levelFromProb(70), "alto");
    assert.strictEqual(RiscoIA.levelFromProb(97), "alto");
});

// --- zonaVisivel (filtro das zonas de risco do mapa) -----------------------
const zonaMedia = { nivel_risco: "MEDIO", em_alta: false };
const zonaAltaQuente = { nivel_risco: "ALTO", em_alta: true };

test("zonaVisivel: 'todos' mostra qualquer zona", () => {
    assert.strictEqual(RiscoIA.zonaVisivel(zonaMedia, { nivel: "todos", soEmAlta: false }), true);
});

test("zonaVisivel: filtra por nível e por zonas em alta", () => {
    assert.strictEqual(RiscoIA.zonaVisivel(zonaMedia, { nivel: "alto" }), false);
    assert.strictEqual(RiscoIA.zonaVisivel(zonaMedia, { nivel: "alto-medio" }), true);
    assert.strictEqual(RiscoIA.zonaVisivel({ nivel_risco: "BAIXO" }, { nivel: "alto-medio" }), false);
    assert.strictEqual(RiscoIA.zonaVisivel(zonaMedia, { nivel: "todos", soEmAlta: true }), false);
    assert.strictEqual(RiscoIA.zonaVisivel(zonaAltaQuente, { nivel: "alto", soEmAlta: true }), true);
});

// --- helpers da API de risco --------------------------------------------------
test("formatVia: capitaliza nomes da base oficial e preserva siglas", () => {
    assert.strictEqual(RiscoIA.formatVia("AVENIDA DOUTOR FRANCISCO JUNQUEIRA"), "Avenida Doutor Francisco Junqueira");
    assert.strictEqual(RiscoIA.formatVia("SP 330"), "SP 330");
    assert.strictEqual(RiscoIA.formatVia("RUA DOS BANDEIRANTES"), "Rua dos Bandeirantes");
});

test("diaSemanaIndex: segunda = 0 ... domingo = 6 (mesma ordem da API)", () => {
    assert.strictEqual(RiscoIA.diaSemanaIndex("Segunda-feira"), 0);
    assert.strictEqual(RiscoIA.diaSemanaIndex("Domingo"), 6);
});

test("HORARIO_HORAS: cada faixa do formulário vira as horas do rótulo", () => {
    assert.deepStrictEqual(RiscoIA.HORARIO_HORAS["pico-noite"], [17, 18, 19]);
    RiscoIA.HORARIO_OPTIONS.forEach((opt) => assert.ok(RiscoIA.HORARIO_HORAS[opt.value].length > 0));
});

test("diaNoPlural: concorda com o dia da semana", () => {
    assert.strictEqual(RiscoIA.diaNoPlural("Sexta-feira"), "às sextas-feiras");
    assert.strictEqual(RiscoIA.diaNoPlural("Sábado"), "aos sábados");
});

test("levelFromApi: converte o nível da API para as classes do site", () => {
    assert.strictEqual(RiscoIA.levelFromApi("ALTO"), "alto");
    assert.strictEqual(RiscoIA.levelFromApi("MEDIO"), "medio");
    assert.strictEqual(RiscoIA.levelFromApi(undefined), "baixo");
});

test("escapeHtml: neutraliza HTML vindo da base", () => {
    assert.strictEqual(RiscoIA.escapeHtml('<b>"Rua" & Cia</b>'), "&lt;b&gt;&quot;Rua&quot; &amp; Cia&lt;/b&gt;");
    assert.strictEqual(RiscoIA.escapeHtml(null), "");
});

// --- isValidEmail -----------------------------------------------------
test("isValidEmail: aceita e-mails com formato válido", () => {
    assert.strictEqual(RiscoIA.isValidEmail("aluno@exemplo.com"), true);
});

test("isValidEmail: rejeita textos sem @ ou sem domínio", () => {
    assert.strictEqual(RiscoIA.isValidEmail("nao-e-email"), false);
    assert.strictEqual(RiscoIA.isValidEmail("sem-dominio@"), false);
    assert.strictEqual(RiscoIA.isValidEmail(""), false);
});

// --- funções de "condições atuais" -----------------------------------------------------
test("climaFromWeatherCode: mapeia os códigos WMO para os 3 climas do site", () => {
    assert.strictEqual(RiscoIA.climaFromWeatherCode(0), "sol");
    assert.strictEqual(RiscoIA.climaFromWeatherCode(2), "nublado");
    assert.strictEqual(RiscoIA.climaFromWeatherCode(61), "chuva");
    assert.strictEqual(RiscoIA.climaFromWeatherCode(95), "chuva");
});

test("horarioAtualBucket: classifica a hora do dia no bucket correto", () => {
    assert.strictEqual(RiscoIA.horarioAtualBucket(new Date(2026, 0, 5, 8, 0)), "pico-manha");
    assert.strictEqual(RiscoIA.horarioAtualBucket(new Date(2026, 0, 5, 13, 0)), "fora-pico");
    assert.strictEqual(RiscoIA.horarioAtualBucket(new Date(2026, 0, 5, 18, 0)), "pico-noite");
    assert.strictEqual(RiscoIA.horarioAtualBucket(new Date(2026, 0, 5, 2, 0)), "madrugada");
});

test("diaAtualPtBR: retorna o mesmo texto usado no <select> de dia da semana", () => {
    // 2026-01-05 é uma segunda-feira.
    assert.strictEqual(RiscoIA.diaAtualPtBR(new Date(2026, 0, 5)), "Segunda-feira");
    // 2026-01-11 é um domingo.
    assert.strictEqual(RiscoIA.diaAtualPtBR(new Date(2026, 0, 11)), "Domingo");
});

// --- decodeJwtPayload -----------------------------------------------------
// Token de exemplo: header/payload codificados em base64url "na mão" (sem
// assinatura válida - decodeJwtPayload só lê o payload, não verifica
// assinatura; quem confia na assinatura é sempre o backend).
function base64UrlEncode(obj) {
    return Buffer.from(JSON.stringify(obj)).toString("base64")
        .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

test("decodeJwtPayload: lê o payload de um JWT bem formado", () => {
    const payload = { sub: "usuario_teste", role: "user", exp: 9999999999 };
    const token = `${base64UrlEncode({ alg: "HS256" })}.${base64UrlEncode(payload)}.assinatura-fake`;
    const decoded = RiscoIA.decodeJwtPayload(token);
    assert.strictEqual(decoded.sub, "usuario_teste");
    assert.strictEqual(decoded.role, "user");
    assert.strictEqual(decoded.exp, 9999999999);
});

test("decodeJwtPayload: retorna null para um token inválido", () => {
    assert.strictEqual(RiscoIA.decodeJwtPayload("token-invalido"), null);
});

console.log(`\n${passed} passaram, ${failed} falharam.`);
process.exit(failed > 0 ? 1 : 0);
