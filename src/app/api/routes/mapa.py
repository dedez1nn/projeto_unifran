import json
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.models import Sinistro
from app.db.session import get_db

router = APIRouter(tags=["mapa"])

_DATA_DIR = Path(__file__).resolve().parents[4] / "data"
_BOUNDARY_PATH = _DATA_DIR / "municipio_ribeirao_preto.geojson"
_BOUNDARY_GEOJSON = json.loads(_BOUNDARY_PATH.read_text(encoding="utf-8"))

_SEVERITY_COLORS = {
    "fatal": "#d03b3b",
    "grave": "#ec835a",
    "leve": "#fab219",
    "ileso": "#0ca30c",
    "nao_informado": "#8a94a3",
}

# Peso do calor por gravidade: acidentes maiores (mais vítimas/mais graves)
# pesam mais e aparecem mais "quentes", em vez de todo ponto valer o mesmo.
_SEVERITY_WEIGHTS = {"fatal": 4, "grave": 2, "leve": 1, "ileso": 0.3}
_HEAT_FLOOR = 0.2  # piso p/ sinistros sem gravidade informada não somirem do calor

_PAGE_TEMPLATE = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<title>Mapa de sinistros — Ribeirão Preto</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<style>
  html, body {{ margin: 0; height: 100%; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
  #map {{ position: absolute; inset: 0; background: #eef1f3; }}
  .panel {{
    position: absolute; top: 12px; right: 12px; z-index: 1000;
    background: #ffffffee; border: 1px solid #d8dee2; border-radius: 10px;
    padding: 10px 12px; font-size: 12.5px; color: #10161c; box-shadow: 0 4px 16px rgba(0,0,0,.15);
    width: 200px;
  }}
  .panel h1 {{ font-size: 13px; margin: 0 0 8px; }}
  .panel label {{ display: flex; align-items: center; gap: 6px; margin: 4px 0; cursor: pointer; }}
  .legend-dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
  .legend {{ margin-top: 8px; padding-top: 8px; border-top: 1px solid #dde3e7; }}
  .legend-row {{ display: flex; align-items: center; gap: 6px; margin: 3px 0; color: #2b333b; }}
  .stat {{ margin-top: 8px; padding-top: 8px; border-top: 1px solid #dde3e7; color: #4b5763; }}
  .hint {{ margin-top: 6px; color: #7c8894; font-size: 11.5px; line-height: 1.4; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="panel">
  <h1>Sinistros de trânsito — Ribeirão Preto</h1>
  <label><input type="checkbox" id="toggle-municipio" checked> Município (contorno)</label>
  <label><input type="checkbox" id="toggle-heat" checked> Calor por gravidade</label>
  <label><input type="checkbox" id="toggle-points"> Pontos individuais (detalhe)</label>
  <div id="legenda" class="legend"></div>
  <div class="stat">{total_geo} de {total} sinistros com coordenadas</div>
  <div class="hint">Afastado, o calor agrega os acidentes por gravidade. Perto do zoom máximo, cada acidente vira um ponto colorido — passe o mouse sobre ele para ver os detalhes.</div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<script>
const pontos = {pontos_json};
const cores = {cores_json};
const limiteMunicipio = {boundary_json};

const LEGENDA_LABELS = {{ fatal: 'Fatal', grave: 'Grave', leve: 'Leve', ileso: 'Ileso', nao_informado: 'Não informado' }};
const legendaEl = document.getElementById('legenda');
Object.keys(LEGENDA_LABELS).forEach(sev => {{
  const linha = document.createElement('div');
  linha.className = 'legend-row';
  linha.innerHTML = '<span class="legend-dot" style="background:' + cores[sev] + '"></span>' + LEGENDA_LABELS[sev];
  legendaEl.appendChild(linha);
}});

const map = L.map('map', {{ zoomSnap: 0.25 }});
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · limites: IBGE'
}}).addTo(map);

const municipioLayer = L.geoJSON(limiteMunicipio, {{
  style: {{
    color: '#1c5cab',
    weight: 2,
    opacity: 0.9,
    fillColor: '#2a78d6',
    fillOpacity: 0.08,
  }},
}});
municipioLayer.addTo(map);
map.fitBounds(municipioLayer.getBounds(), {{ padding: [16, 16] }});

function escapeHtml(str) {{
  return String(str)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}}

function severidade(p) {{
  if (p.fatal > 0) return 'fatal';
  if (p.grave > 0) return 'grave';
  if (p.leve > 0) return 'leve';
  if (p.ileso > 0) return 'ileso';
  return 'nao_informado';
}}

function pesoCalor(p) {{
  const peso = (p.fatal || 0) * {peso_fatal} + (p.grave || 0) * {peso_grave} +
    (p.leve || 0) * {peso_leve} + (p.ileso || 0) * {peso_ileso};
  return Math.max(peso, {piso_calor});
}}

function hexParaRgb(hex) {{
  const v = parseInt(hex.slice(1), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}}

// Uma camada de calor por gravidade (cor fixa, não misturada), em vez de uma
// única camada com peso somado — assim uma ocorrência isolada de qualquer
// gravidade já aparece na cor certa e com a mesma opacidade das demais, sem
// depender de acúmulo de vizinhos para "acender" a cor (o que antes deixava
// pontos leves/ilesos pálidos e nunca mostrava verde de fato).
const ORDEM_CAMADAS_CALOR = ['nao_informado', 'ileso', 'leve', 'grave', 'fatal'];
const camadasCalor = ORDEM_CAMADAS_CALOR.map(sev => {{
  const [r, g, b] = hexParaRgb(cores[sev]);
  const pontosSev = pontos.filter(p => severidade(p) === sev).map(p => [p.lat, p.lon, 1]);
  return L.heatLayer(pontosSev, {{
    radius: 34,
    blur: 26,
    max: 1,
    maxZoom: 15,
    gradient: {{
      0.15: `rgba(${{r}},${{g}},${{b}},0.12)`,
      0.4: `rgba(${{r}},${{g}},${{b}},0.5)`,
      0.7: `rgba(${{r}},${{g}},${{b}},0.85)`,
      1.0: `rgba(${{r}},${{g}},${{b}},0.92)`,
    }},
  }});
}});
const heatLayer = L.layerGroup(camadasCalor);

const MARCADOR_RAIO_MIN = 3;
const MARCADOR_RAIO_MAX = 9;
const MARCADOR_GAP_PX = 2;

const markersLayer = L.layerGroup();
const marcadores = pontos.map(p => {{
  const sev = severidade(p);
  const peso = pesoCalor(p);
  const marker = L.circleMarker([p.lat, p.lon], {{
    radius: MARCADOR_RAIO_MIN,
    color: '#141414',
    weight: 1,
    fillColor: cores[sev],
    fillOpacity: 1,
  }});
  const linhas = [
    '<strong>' + escapeHtml(p.logradouro || 'Via não informada') + '</strong>',
    escapeHtml(p.data || 'data não informada') + (p.turno ? ' · ' + escapeHtml(p.turno) : ''),
    escapeHtml(p.tipo_primario || p.tipo_registro || ''),
    'Gravidade: ' + escapeHtml(sev.replace('_', ' ')),
  ].filter(Boolean);
  marker.bindTooltip(linhas.join('<br>'), {{ sticky: true, direction: 'top', opacity: 0.95 }});
  markersLayer.addLayer(marker);
  return {{ marker: marker, peso: peso }};
}});

// Raio mínimo fixo (sempre visível), mas o raio "desejado" pelo peso do
// sinistro só cresce até onde não invadir a área do ponto vizinho mais
// próximo — ou seja, o limite do raio é a colisão com outro sinistro.
function recalcularRaiosMarcadores() {{
  if (!marcadores.length) return;
  const posicoes = marcadores.map(m => map.latLngToContainerPoint(m.marker.getLatLng()));
  marcadores.forEach((item, i) => {{
    let distanciaMaisProxima = Infinity;
    for (let j = 0; j < marcadores.length; j++) {{
      if (i === j) continue;
      const dx = posicoes[i].x - posicoes[j].x;
      const dy = posicoes[i].y - posicoes[j].y;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < distanciaMaisProxima) distanciaMaisProxima = d;
    }}
    const raioDesejado = MARCADOR_RAIO_MIN + item.peso * 0.6;
    const limiteColisao = isFinite(distanciaMaisProxima)
      ? Math.max(MARCADOR_RAIO_MIN, distanciaMaisProxima / 2 - MARCADOR_GAP_PX)
      : MARCADOR_RAIO_MAX;
    const raio = Math.min(Math.max(raioDesejado, MARCADOR_RAIO_MIN), Math.min(limiteColisao, MARCADOR_RAIO_MAX));
    item.marker.setRadius(raio);
  }});
}}

// Perto do zoom máximo (mapa "aberto" o suficiente pra distinguir cada
// ocorrência), troca o calor agregado por pontos individuais coloridos por
// gravidade — é quando faz sentido ver "um acidente = um ponto".
const ZOOM_LIMIAR_PONTOS = map.getMaxZoom() - 2;

function aplicarCamadaPorZoom() {{
  const emZoomMaximo = map.getZoom() >= ZOOM_LIMIAR_PONTOS;
  if (emZoomMaximo) {{
    if (!map.hasLayer(markersLayer)) markersLayer.addTo(map);
    if (map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
  }} else {{
    if (!map.hasLayer(heatLayer)) heatLayer.addTo(map);
    if (map.hasLayer(markersLayer)) map.removeLayer(markersLayer);
  }}
  document.getElementById('toggle-heat').checked = !emZoomMaximo;
  document.getElementById('toggle-points').checked = emZoomMaximo;
}}

recalcularRaiosMarcadores();
aplicarCamadaPorZoom();
map.on('zoomend', recalcularRaiosMarcadores);
map.on('zoomend', aplicarCamadaPorZoom);

document.getElementById('toggle-municipio').addEventListener('change', e => {{
  if (e.target.checked) municipioLayer.addTo(map); else map.removeLayer(municipioLayer);
}});
document.getElementById('toggle-heat').addEventListener('change', e => {{
  if (e.target.checked) heatLayer.addTo(map); else map.removeLayer(heatLayer);
}});
document.getElementById('toggle-points').addEventListener('change', e => {{
  if (e.target.checked) markersLayer.addTo(map); else map.removeLayer(markersLayer);
}});
</script>
</body>
</html>
"""


def _pontos_from_rows(rows: list[Sinistro]) -> list[dict]:
    return [
        {
            "lat": r.latitude,
            "lon": r.longitude,
            "data": r.data_sinistro.isoformat() if r.data_sinistro else None,
            "turno": r.turno,
            "logradouro": (r.logradouro or "").title(),
            "tipo_registro": r.tipo_registro,
            "tipo_primario": r.tp_sinistro_primario,
            "fatal": r.qtd_gravidade_fatal or 0,
            "grave": r.qtd_gravidade_grave or 0,
            "leve": r.qtd_gravidade_leve or 0,
            "ileso": r.qtd_gravidade_ileso or 0,
        }
        for r in rows
    ]


def _json_for_script(obj) -> str:
    """`json.dumps` não escapa `</script>`, `<!--` etc. — um valor de campo
    (ex: logradouro vindo do CSV) contendo essa substring quebraria o bloco
    <script> e injetaria HTML/JS arbitrário. Escapar `<`, `>` e `&` como
    sequências \\uXXXX neutraliza isso sem alterar o JSON decodificado.
    """
    return (
        json.dumps(obj, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def build_mapa_html(pontos: list[dict], total: int) -> str:
    """Monta o HTML autocontido do mapa (Leaflet + OpenStreetMap) a partir dos
    pontos já serializados. Usada tanto pelo endpoint `/mapa` quanto pelo
    script de exportação para arquivo estático.
    """
    return _PAGE_TEMPLATE.format(
        pontos_json=_json_for_script(pontos),
        cores_json=_json_for_script(_SEVERITY_COLORS),
        boundary_json=_json_for_script(_BOUNDARY_GEOJSON),
        total_geo=len(pontos),
        total=total,
        peso_fatal=_SEVERITY_WEIGHTS["fatal"],
        peso_grave=_SEVERITY_WEIGHTS["grave"],
        peso_leve=_SEVERITY_WEIGHTS["leve"],
        peso_ileso=_SEVERITY_WEIGHTS["ileso"],
        piso_calor=_HEAT_FLOOR,
    )


@router.get("/mapa", response_class=HTMLResponse)
def mapa(db: Session = Depends(get_db)) -> str:
    """Mapa navegável (Leaflet + OpenStreetMap) dos sinistros geocodificados.

    Desenha o contorno do município inteiro (malha do IBGE, cod. 3543402) como
    referência geográfica, e um calor ponderado pela gravidade de cada
    sinistro — acidentes com fatalidades/feridos graves pesam mais no calor
    do que uma simples contagem de pontos pesaria.

    Diferente da prévia estática em Artifact, esta página carrega tiles reais
    e por isso só funciona servida diretamente (fora do sandbox de artifacts),
    com o navegador tendo acesso à internet para buscar os tiles do OSM.
    """
    total = db.query(Sinistro).count()
    rows = (
        db.query(Sinistro)
        .filter(Sinistro.latitude.is_not(None), Sinistro.longitude.is_not(None),
                Sinistro.coordenada_generica.is_not(True))
        .all()
    )
    html = build_mapa_html(_pontos_from_rows(rows), total)
    return HTMLResponse(content=html)
