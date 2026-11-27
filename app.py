"""
=============================================================================
PROYECTO   : Observatorio Automatizado Estación Magallanes
MÓDULO     : app.py (Visor Web Institucional / Panel de Control)
VERSIÓN    : 23.1 (LEYENDA SVG SINCRONIZADA Y FICHA FLOTANTE EN ALADIN)
=============================================================================
"""

import streamlit as st
import streamlit.components.v1 as components
import os
import json
import math
import re
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Estación Magallanes", layout="wide", page_icon="🔭")
st.markdown(
    """
    <style>
    .stApp {
        background-color: #0e1117;
        color: #c9d1d9;
        font-size: 1.05rem;
    }
    section[data-testid="stSidebar"] {
        font-size: 1.02rem;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

EPOCA_MJD = datetime(1858, 11, 17, tzinfo=timezone.utc)
LAT_PUNTA_ARENAS = -53.1500   # 53° 09' S
LON_PUNTA_ARENAS = -70.9000   # 70° 54' W
DEC_LIMITE_NORTE_PA = 90.0 + LAT_PUNTA_ARENAS  # +36.85°

OPCIONES_TIPO = [
    "👁️ Todos los tipos",
    "✅ Supernovas Confirmadas (TNS)",
    "🚨 Supernovas Candidatas (ZTF/LSST)",
    "🌀 Agujeros Negros (TDE)",
    "💥 Novas / Cataclísmicas",
    "🚀 Blazares",
    "🕳️ AGN (Cuásar)",
    "🔥 Flares VIP",
]

OPCIONES_RED = [
    "🌐 Todas las redes",
    "TNS_GLOBAL",
    "LSST",
    "ZTF",
]

CONFIG_CATEGORIAS_MAPA = {
    "Confirmada TNS": {"color": "#00FF00", "symbol": "star-diamond", "aladin_shape": "rhomb", "aladin_size": 13},
    "Candidata": {"color": "#FF3333", "symbol": "cross", "aladin_shape": "plus", "aladin_size": 15},
    "Blazar (Chorro)": {"color": "#FF00FF", "symbol": "triangle-down", "aladin_shape": "triangle", "aladin_size": 12},
    "AGN (Cuásar)": {"color": "#FF9900", "symbol": "triangle-up", "aladin_shape": "square", "aladin_size": 10},
    "Agujero Negro (TDE)": {"color": "#FFD700", "symbol": "x", "aladin_shape": "cross", "aladin_size": 15},
    "Nova / Cataclísmica": {"color": "#00BFFF", "symbol": "star", "aladin_shape": "circle", "aladin_size": 10},
    "Flare (Enana M VIP)": {"color": "#FF0055", "symbol": "hexagon", "aladin_shape": "rhomb", "aladin_size": 14},
}


# =====================================================================
# GEOMETRÍA ASTRONÓMICA LOCAL (PUNTA ARENAS) Y VISORES ALADIN LITE V3
# =====================================================================
def azimut_a_cardinal(az_deg):
    direcciones = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    idx = int((az_deg + 22.5) // 45) % 8
    return direcciones[idx]


@st.cache_data
def calcular_curva_galactica(b_deg, paso=2):
    """
    Proyecta una línea de latitud galáctica constante b (en grados) a coordenadas
    ecuatoriales J2000 (RA, Dec) usando trigonometría esférica pura.
    """
    ra_ngp = math.radians(192.85948)
    dec_ngp = math.radians(27.12825)
    l_ncp = math.radians(122.93192)
    b = math.radians(b_deg)

    ras, decs = [], []
    prev_ra = None
    for l_deg in range(0, 361, paso):
        l_rad = math.radians(l_deg)
        dl = l_ncp - l_rad
        sin_dec = math.sin(b) * math.sin(dec_ngp) + math.cos(b) * math.cos(dec_ngp) * math.cos(dl)
        sin_dec = max(-1.0, min(1.0, sin_dec))
        dec_deg = math.degrees(math.asin(sin_dec))

        y = math.cos(b) * math.sin(dl)
        x = math.sin(b) * math.cos(dec_ngp) - math.cos(b) * math.sin(dec_ngp) * math.cos(dl)
        ra_deg = (math.degrees(ra_ngp + math.atan2(y, x))) % 360.0

        if prev_ra is not None and abs(ra_deg - prev_ra) > 180.0:
            ras.append(None)
            decs.append(None)

        ras.append(round(ra_deg, 3))
        decs.append(round(dec_deg, 3))
        prev_ra = ra_deg

    return ras, decs


def calcular_observabilidad_magallanes(ra_deg, dec_deg):
    """
    Calcula en tiempo real la geometría de observación desde Punta Arenas
    (53° 09' S, 70° 54' W, UTC-3) sin llamadas externas.
    """
    ahora_utc = datetime.now(timezone.utc)
    ahora_local = (ahora_utc - timedelta(hours=3)).replace(tzinfo=None)
    mjd_ahora = (ahora_utc - EPOCA_MJD).total_seconds() / 86400.0

    dias_j2000 = mjd_ahora - 51544.5
    gmst_deg = (280.46061837 + 360.98564736629 * dias_j2000) % 360.0
    lst_deg = (gmst_deg + LON_PUNTA_ARENAS) % 360.0

    ha_deg = ((lst_deg - ra_deg + 180.0) % 360.0) - 180.0

    phi = math.radians(LAT_PUNTA_ARENAS)
    dec = math.radians(dec_deg)
    ha = math.radians(ha_deg)

    sin_h = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(ha)
    sin_h = max(-1.0, min(1.0, sin_h))
    alt_deg = math.degrees(math.asin(sin_h))

    cos_h = math.cos(math.radians(alt_deg))
    if cos_h > 1e-6:
        cos_az = (math.sin(dec) - sin_h * math.sin(phi)) / (cos_h * math.cos(phi))
        cos_az = max(-1.0, min(1.0, cos_az))
        az_deg = math.degrees(math.acos(cos_az))
        if math.sin(ha) > 0:
            az_deg = 360.0 - az_deg
    else:
        az_deg = 0.0

    cardinal = azimut_a_cardinal(az_deg)
    estado_alt = "Sobre horiz." if alt_deg > 0.0 else "Bajo horiz."

    alt_max = 90.0 - abs(LAT_PUNTA_ARENAS - dec_deg)
    alt_min = math.degrees(math.asin(max(-1.0, min(1.0, -math.cos(phi + dec)))))

    if alt_max <= 0.0:
        condicion = "⛔ Inobservable"
        detalle_cond = "Solo hemisferio Norte"
        transito_str = "No visible"
        transito_detalle = "Bajo horizonte local"
        alt_max_str = f"{alt_max:.1f}°"
        masa_aire = "No culmina"
    else:
        if alt_min > 0.0:
            condicion = "♾️ Circumpolar"
            detalle_cond = "Visible todo el año"
        else:
            condicion = "🌓 Estacional"
            detalle_cond = "Sale y se pone"

        delta_ha_deg = (-ha_deg) % 360.0
        horas_solares = (delta_ha_deg / 15.0) / 1.00273790935
        dt_transito = ahora_local + timedelta(hours=horas_solares)
        prefijo_dia = "Hoy" if dt_transito.date() == ahora_local.date() else "Mañana"
        transito_str = f"{prefijo_dia} {dt_transito.strftime('%H:%M')}"

        if abs(dec_deg - LAT_PUNTA_ARENAS) < 0.5:
            dir_culm = "Cenit"
        elif dec_deg > LAT_PUNTA_ARENAS:
            dir_culm = "Norte"
        else:
            dir_culm = "Sur"

        transito_detalle = f"Local · Hacia el {dir_culm}"
        alt_max_str = f"{alt_max:.1f}°"
        masa_aire = f"X = {1.0 / math.sin(math.radians(alt_max)):.2f}" if alt_max > 5.0 else "Muy baja (<5°)"

    return {
        "condicion": condicion,
        "detalle_cond": detalle_cond,
        "alt_actual_str": f"{alt_deg:+.1f}°",
        "alt_actual_detalle": f"{estado_alt} · Az {az_deg:.0f}° ({cardinal})",
        "transito_str": transito_str,
        "transito_detalle": transito_detalle,
        "alt_max_str": alt_max_str,
        "masa_aire": masa_aire,
    }


def renderizar_mapa_universo_aladin(capas_aladin, altura_px=650):
    """
    Mapa interactivo de todo el cielo en Aladin Lite v3 con:
    - Fondo real del universo (Mellinger Color, DSS2 Color, 2MASS IR).
    - Leyenda con iconos SVG idénticos a la simbología del mapa y activación por clic.
    - Ficha técnica flotante en modo oscuro (reemplaza el popup blanco nativo).
    """
    capas_json = json.dumps(capas_aladin, ensure_ascii=False).replace("</", "<\\/")
    altura_mapa = altura_px - 96

    plantilla_html = """
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8" />
      <style>
        * { box-sizing: border-box; }
        html, body {
          margin: 0;
          padding: 0;
          background-color: #0e1117;
          color: #c9d1d9;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          overflow: hidden;
        }
        /* Bloquea el popup blanco nativo de Aladin */
        .aladin-popup-container {
          display: none !important;
        }
        .toolbar {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          align-items: center;
          padding: 8px 10px;
          background: #161b22;
          border: 1px solid #30363d;
          border-bottom: none;
          border-radius: 8px 8px 0 0;
        }
        .sep {
          width: 1px;
          height: 18px;
          background: #30363d;
          margin: 0 3px;
        }
        .btn {
          background: #21262d;
          color: #c9d1d9;
          border: 1px solid #30363d;
          border-radius: 5px;
          padding: 4px 9px;
          font-size: 12px;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .btn:hover:not(:disabled) {
          background: #30363d;
          color: #ffffff;
        }
        .btn.active {
          background: #0d419d;
          border-color: #58a6ff;
          color: #ffffff;
          font-weight: 600;
        }
        .hint-toolbar {
          margin-left: auto;
          font-size: 11.5px;
          color: #8b949e;
        }
        .legend-bar {
          display: flex;
          flex-wrap: wrap;
          gap: 8px 14px;
          align-items: center;
          padding: 7px 12px;
          background: #12161d;
          border-left: 1px solid #30363d;
          border-right: 1px solid #30363d;
          font-size: 12.5px;
          color: #c9d1d9;
        }
        .legend-item {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          cursor: pointer;
          user-select: none;
          padding: 2px 6px;
          border-radius: 5px;
          border: 1px solid transparent;
          transition: opacity 0.15s ease, background 0.15s ease;
        }
        .legend-item:hover {
          background: #1f2630;
          border-color: #30363d;
        }
        .legend-item.hidden-layer {
          opacity: 0.35;
          text-decoration: line-through;
        }
        .legend-svg {
          display: inline-block;
          vertical-align: middle;
          flex-shrink: 0;
        }
        .map-wrapper {
          position: relative;
          width: 100%;
          height: __ALTURA_DIV__px;
        }
        #aladin-allsky {
          width: 100%;
          height: 100%;
          border: 1px solid #30363d;
          border-radius: 0 0 8px 8px;
          background: #000000;
        }
        /* Ficha técnica flotante en modo oscuro */
        .info-card {
          display: none;
          position: absolute;
          bottom: 40px;
          left: 14px;
          z-index: 30;
          width: 365px;
          max-width: calc(100% - 28px);
          background: rgba(18, 22, 29, 0.96);
          border: 1px solid #30363d;
          border-left: 4px solid #58a6ff;
          border-radius: 8px;
          box-shadow: 0 8px 26px rgba(0, 0, 0, 0.72);
          padding: 12px 14px;
          color: #e6edf3;
          backdrop-filter: blur(6px);
        }
        .info-card.visible {
          display: block;
        }
        .card-header {
          display: flex;
          align-items: center;
          gap: 8px;
          padding-bottom: 8px;
          margin-bottom: 8px;
          border-bottom: 1px solid #2a313c;
        }
        .card-title {
          font-size: 14.5px;
          font-weight: 700;
          color: #ffffff;
          word-break: break-word;
        }
        .card-badge {
          font-size: 11px;
          font-weight: 600;
          padding: 2px 7px;
          border-radius: 999px;
          background: #21262d;
          border: 1px solid #3d444d;
          color: #c9d1d9;
          white-space: nowrap;
        }
        .card-close {
          margin-left: auto;
          background: transparent;
          border: none;
          color: #8b949e;
          font-size: 16px;
          line-height: 1;
          cursor: pointer;
          padding: 2px 6px;
          border-radius: 4px;
        }
        .card-close:hover {
          background: #21262d;
          color: #ffffff;
        }
        .card-grid {
          display: grid;
          grid-template-columns: 96px 1fr;
          gap: 5px 10px;
          font-size: 12.5px;
          line-height: 1.38;
        }
        .card-label {
          color: #8b949e;
          font-weight: 600;
        }
        .card-val {
          color: #e6edf3;
          overflow-wrap: anywhere;
        }
        .card-val.escudo {
          color: #ff6b6b;
          font-weight: 600;
        }
        .card-actions {
          display: flex;
          gap: 8px;
          margin-top: 11px;
          padding-top: 9px;
          border-top: 1px solid #2a313c;
        }
        .btn-card-primary {
          flex: 1;
          background: #143625;
          border: 1px solid #2ea043;
          color: #d2fedb;
          border-radius: 5px;
          padding: 6px 10px;
          font-size: 12px;
          font-weight: 600;
          cursor: pointer;
        }
        .btn-card-primary:hover {
          background: #1c4d34;
          color: #ffffff;
        }
        .btn-card-sec {
          background: #21262d;
          border: 1px solid #30363d;
          color: #c9d1d9;
          border-radius: 5px;
          padding: 6px 10px;
          font-size: 12px;
          cursor: pointer;
        }
        .btn-card-sec:hover {
          background: #30363d;
          color: #ffffff;
        }
      </style>
    </head>
    <body>
      <div class="toolbar">
        <button class="btn btn-survey active" id="btn-mel" title="Panorama óptico real de toda la Vía Láctea" onclick="cambiarSurvey('CDS/P/Mellinger/color', 'btn-mel')">Vía Láctea (Mellinger)</button>
        <button class="btn btn-survey" id="btn-dss2" title="Cielo profundo óptico (ideal al acercar zoom)" onclick="cambiarSurvey('CDS/P/DSS2/color', 'btn-dss2')">DSS2 Color</button>
        <button class="btn btn-survey" id="btn-2mass" title="Estructura infrarroja del disco galáctico" onclick="cambiarSurvey('CDS/P/2MASS/color', 'btn-2mass')">2MASS IR</button>
        <span class="sep"></span>
        <button class="btn btn-proj active" id="btn-ait" title="Proyección elíptica de cielo completo" onclick="cambiarProyeccion('AIT', 360, 'btn-ait')">🌌 Aitoff</button>
        <button class="btn btn-proj" id="btn-sin" title="Globo celeste 3D interactivo" onclick="cambiarProyeccion('SIN', 180, 'btn-sin')">🌐 Esfera 3D</button>
        <span class="sep"></span>
        <button class="btn btn-frame active" id="btn-icrs" title="Coordenadas Ecuatoriales (RA/Dec)" onclick="cambiarMarco('ICRS', 'btn-icrs')">Ecuatorial</button>
        <button class="btn btn-frame" id="btn-gal" title="Coordenadas Galácticas (Vía Láctea horizontal)" onclick="cambiarMarco('galactic', 'btn-gal')">Galáctico</button>
        <button class="btn" title="Restaurar vista de cielo completo" onclick="vistaCompleta()">🔄 Cielo Completo</button>
        <span class="hint-toolbar">Haz clic en un marcador para ver su ficha · clic en la leyenda para filtrar</span>
      </div>
      <div class="legend-bar" id="legend-bar"></div>
      <div class="map-wrapper">
        <div id="aladin-allsky"></div>
        <div class="info-card" id="info-card">
          <div class="card-header">
            <span id="card-icon"></span>
            <span class="card-title" id="card-title"></span>
            <span class="card-badge" id="card-survey"></span>
            <button class="card-close" title="Cerrar ficha" onclick="cerrarFicha()">✕</button>
          </div>
          <div class="card-grid" id="card-grid"></div>
          <div class="card-actions">
            <button class="btn-card-primary" onclick="acercarSeleccionado()">🎯 Acercar en DSS2 (7')</button>
            <button class="btn-card-sec" onclick="vistaCompleta()">🌌 Volver</button>
          </div>
        </div>
      </div>

      <script src="https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js" charset="utf-8"></script>
      <script>
        const capasData = __CAPAS_JSON__;
        let aladinAllSky = null;
        let ultimoObjeto = null;
        const catalogosPorNombre = {};

        function escapeHtml(txt) {
          return String(txt || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
        }

        function crearIconoSvg(shape, color, sizePx) {
          const s = sizePx || 14;
          let figura = '';
          if (shape === 'rhomb') {
            figura = '<polygon points="8,1.5 14.5,8 8,14.5 1.5,8" fill="none" stroke="' + color + '" stroke-width="2"/>';
          } else if (shape === 'plus') {
            figura = '<line x1="8" y1="2" x2="8" y2="14" stroke="' + color + '" stroke-width="2.2"/>' +
                     '<line x1="2" y1="8" x2="14" y2="8" stroke="' + color + '" stroke-width="2.2"/>';
          } else if (shape === 'triangle') {
            figura = '<polygon points="8,2 14.5,13.5 1.5,13.5" fill="none" stroke="' + color + '" stroke-width="2"/>';
          } else if (shape === 'square') {
            figura = '<rect x="2.5" y="2.5" width="11" height="11" fill="none" stroke="' + color + '" stroke-width="2"/>';
          } else if (shape === 'cross') {
            figura = '<line x1="3" y1="3" x2="13" y2="13" stroke="' + color + '" stroke-width="2.2"/>' +
                     '<line x1="13" y1="3" x2="3" y2="13" stroke="' + color + '" stroke-width="2.2"/>';
          } else {
            figura = '<circle cx="8" cy="8" r="5.5" fill="none" stroke="' + color + '" stroke-width="2"/>';
          }
          return '<svg class="legend-svg" width="' + s + '" height="' + s + '" viewBox="0 0 16 16">' + figura + '</svg>';
        }

        // Construir leyenda con simbología exacta y filtro interactivo por clic
        const legendBar = document.getElementById('legend-bar');
        capasData.forEach(capa => {
          if (!capa.eventos || capa.eventos.length === 0) return;
          const item = document.createElement('span');
          item.className = 'legend-item';
          item.title = 'Clic para ocultar/mostrar esta categoría';
          item.innerHTML = crearIconoSvg(capa.shape, capa.color, 15) +
            '<span>' + escapeHtml(capa.nombre) + ' (' + capa.eventos.length + ')</span>';
          item.onclick = function() {
            const catObj = catalogosPorNombre[capa.nombre];
            if (!catObj) return;
            const oculto = item.classList.toggle('hidden-layer');
            try {
              if (oculto) { catObj.hide(); } else { catObj.show(); }
            } catch (e) {}
          };
          legendBar.appendChild(item);
        });

        function marcarActivo(selector, btnId) {
          document.querySelectorAll(selector).forEach(b => b.classList.remove('active'));
          const el = document.getElementById(btnId);
          if (el) el.classList.add('active');
        }

        function cerrarFicha() {
          const card = document.getElementById('info-card');
          if (card) card.classList.remove('visible');
        }

        function mostrarFicha(obj) {
          if (!obj || !obj.data) return;
          const d = obj.data;
          ultimoObjeto = {
            ra: obj.ra,
            dec: obj.dec,
            nombre: d.oid || 'Evento'
          };

          const card = document.getElementById('info-card');
          card.style.borderLeftColor = d.color || '#58a6ff';
          document.getElementById('card-icon').innerHTML = crearIconoSvg(d.shape || 'circle', d.color || '#58a6ff', 17);
          document.getElementById('card-title').textContent = d.oid || 'Evento';
          document.getElementById('card-survey').textContent = d.survey || '';

          const filas = [
            ['Categoría', d.categoria, ''],
            ['Análisis', d.analisis, ''],
            ['Fecha', d.fecha, ''],
            ['Coordenadas', d.coords, '']
          ];
          if (d.escudo) filas.push(['Escudo TNS', d.escudo, 'escudo']);
          if (d.z) filas.push(['Redshift (z)', d.z, '']);
          if (d.dist) filas.push(['Distancia', d.dist, '']);

          const grid = document.getElementById('card-grid');
          grid.innerHTML = filas.map(f =>
            '<div class="card-label">' + escapeHtml(f[0]) + '</div>' +
            '<div class="card-val ' + f[2] + '">' + escapeHtml(f[1]) + '</div>'
          ).join('');

          card.classList.add('visible');
        }

        if (typeof A !== 'undefined' && A.init) {
          A.init.then(() => {
            aladinAllSky = A.aladin('#aladin-allsky', {
              survey: 'CDS/P/Mellinger/color',
              projection: 'AIT',
              fov: 360,
              cooFrame: 'ICRS',
              showCooGrid: true,
              showCooGridControl: true,
              showProjectionControl: true,
              showLayersControl: true,
              showFullscreenControl: true,
              showZoomControl: true,
              showReticle: false,
              showGotoControl: false,
              showShareControl: false
            });

            capasData.forEach(capa => {
              if (!capa.eventos || capa.eventos.length === 0) return;
              const cat = A.catalog({
                name: capa.nombre + ' (' + capa.eventos.length + ')',
                color: capa.color,
                sourceSize: capa.size,
                shape: capa.shape,
                onClick: function(source) {
                  if (source) mostrarFicha(source);
                }
              });
              aladinAllSky.addCatalog(cat);
              catalogosPorNombre[capa.nombre] = cat;

              const fuentes = capa.eventos.map(ev => A.source(ev.ra, ev.dec, {
                oid: ev.oid,
                survey: ev.survey,
                categoria: capa.nombre,
                color: capa.color,
                shape: capa.shape,
                analisis: ev.analisis,
                fecha: ev.fecha,
                coords: ev.coords,
                escudo: ev.escudo || '',
                z: ev.z || '',
                dist: ev.dist || ''
              }));
              cat.addSources(fuentes);
            });

            aladinAllSky.on('objectClicked', function(obj) {
              if (obj && obj.data && obj.data.oid) {
                mostrarFicha(obj);
              } else {
                cerrarFicha();
              }
            });
          });
        } else {
          document.getElementById('aladin-allsky').innerHTML =
            '<div style="padding:24px;color:#8b949e;text-align:center;">No se pudo cargar el mapa del universo desde el CDS. Usa la vista "Grilla Analítica".</div>';
        }

        function cambiarSurvey(hipsId, btnId) {
          if (!aladinAllSky) return;
          try { aladinAllSky.setImageSurvey(hipsId); } catch (e) {}
          marcarActivo('.btn-survey', btnId);
        }

        function cambiarProyeccion(proj, fovDeg, btnId) {
          if (!aladinAllSky) return;
          try {
            aladinAllSky.setProjection(proj);
            aladinAllSky.setFoV(fovDeg);
          } catch (e) {}
          marcarActivo('.btn-proj', btnId);
        }

        function cambiarMarco(frame, btnId) {
          if (!aladinAllSky) return;
          try { aladinAllSky.setFrame(frame); } catch (e) {}
          marcarActivo('.btn-frame', btnId);
        }

        function vistaCompleta() {
          if (!aladinAllSky) return;
          try {
            aladinAllSky.setProjection('AIT');
            aladinAllSky.setFrame('ICRS');
            aladinAllSky.setImageSurvey('CDS/P/Mellinger/color');
            aladinAllSky.gotoRaDec(180, 0);
            aladinAllSky.setFoV(360);
          } catch (e) {}
          marcarActivo('.btn-survey', 'btn-mel');
          marcarActivo('.btn-proj', 'btn-ait');
          marcarActivo('.btn-frame', 'btn-icrs');
        }

        function acercarSeleccionado() {
          if (!aladinAllSky || !ultimoObjeto) return;
          try {
            aladinAllSky.setProjection('SIN');
            aladinAllSky.setImageSurvey('CDS/P/DSS2/color');
            aladinAllSky.gotoRaDec(ultimoObjeto.ra, ultimoObjeto.dec);
            aladinAllSky.setFoV(0.1167);
          } catch (e) {}
          marcarActivo('.btn-survey', 'btn-dss2');
          marcarActivo('.btn-proj', 'btn-sin');
        }
      </script>
    </body>
    </html>
    """

    html_final = (
        plantilla_html
        .replace("__CAPAS_JSON__", capas_json)
        .replace("__ALTURA_DIV__", str(altura_mapa))
    )
    components.html(html_final, height=altura_px)


def renderizar_visor_aladin(ra_deg, dec_deg, oid_str, altura_px=470):
    """
    Incrustación interactiva de Aladin Lite v3 (CDS Estrasburgo) para un objeto
    individual, con retícula, círculo hueco de 15" y cambio rápido de sondeos.
    """
    oid_js = json.dumps(str(oid_str))
    html_aladin = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
      <meta charset="utf-8" />
      <style>
        html, body {{
          margin: 0;
          padding: 0;
          background-color: #0e1117;
          color: #c9d1d9;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          overflow: hidden;
        }}
        .toolbar {{
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          align-items: center;
          padding: 8px 10px;
          background: #161b22;
          border: 1px solid #30363d;
          border-bottom: none;
          border-radius: 8px 8px 0 0;
        }}
        .btn-survey {{
          background: #21262d;
          color: #c9d1d9;
          border: 1px solid #30363d;
          border-radius: 5px;
          padding: 4px 9px;
          font-size: 12px;
          cursor: pointer;
          transition: all 0.15s ease;
        }}
        .btn-survey:hover {{
          background: #30363d;
          color: #ffffff;
        }}
        .btn-survey.active {{
          background: #0d419d;
          border-color: #58a6ff;
          color: #ffffff;
          font-weight: 600;
        }}
        .coords-badge {{
          margin-left: auto;
          font-size: 11.5px;
          color: #8b949e;
          font-family: monospace;
        }}
        #aladin-lite-div {{
          width: 100%;
          height: {altura_px - 46}px;
          border: 1px solid #30363d;
          border-radius: 0 0 8px 8px;
          background: #000000;
        }}
      </style>
    </head>
    <body>
      <div class="toolbar">
        <button class="btn-survey active" id="btn-dss2" title="Cobertura completa Norte y Sur" onclick="setSurvey('CDS/P/DSS2/color', 'btn-dss2')">DSS2 Color</button>
        <button class="btn-survey" id="btn-legacy" title="Óptico profundo DECam/BASS (Norte y Sur extragaláctico)" onclick="setSurvey('CDS/P/DESI-Legacy-Surveys/DR10/color', 'btn-legacy')">Legacy DR10</button>
        <button class="btn-survey" id="btn-ps1" title="Óptico profundo (cobertura Dec > -30°)" onclick="setSurvey('CDS/P/PanSTARRS/DR1/color-z-zg-g', 'btn-ps1')">Pan-STARRS</button>
        <button class="btn-survey" id="btn-2mass" title="Infrarrojo cercano todo el cielo" onclick="setSurvey('CDS/P/2MASS/color', 'btn-2mass')">2MASS IR</button>
        <button class="btn-survey" title="Centrar en campo de 5 arcmin" onclick="setZoom(0.08333)">🎯 5'</button>
        <button class="btn-survey" title="Acercar a galaxia anfitriona (1.5 arcmin)" onclick="setZoom(0.025)">🔍 1.5'</button>
        <span class="coords-badge">RA {float(ra_deg):.5f}° | Dec {float(dec_deg):.5f}°</span>
      </div>
      <div id="aladin-lite-div"></div>

      <script src="https://aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js" charset="utf-8"></script>
      <script>
        let aladinInstance = null;
        const targetRa = {float(ra_deg)};
        const targetDec = {float(dec_deg)};
        const objName = {oid_js};

        if (typeof A !== 'undefined' && A.init) {{
          A.init.then(() => {{
            aladinInstance = A.aladin('#aladin-lite-div', {{
              survey: 'CDS/P/DSS2/color',
              fov: 0.08333,
              target: targetRa + ' ' + targetDec,
              cooFrame: 'ICRS',
              showReticle: true,
              reticleColor: '#00ffff',
              reticleSize: 26,
              showCooGridControl: true,
              showFullscreenControl: true,
              showLayersControl: true,
              showZoomControl: true,
              showGotoControl: false,
              showShareControl: false
            }});

            const overlay = A.graphicOverlay({{
              name: objName,
              color: '#00ffff',
              lineWidth: 2
            }});
            aladinInstance.addOverlay(overlay);
            overlay.add(A.circle(targetRa, targetDec, 0.00417));
          }});
        }} else {{
          document.getElementById('aladin-lite-div').innerHTML =
            '<div style="padding:20px;color:#8b949e;text-align:center;">No se pudo cargar Aladin Lite desde el servidor del CDS.</div>';
        }}

        function setSurvey(hipsId, btnId) {{
          if (!aladinInstance) return;
          aladinInstance.setImageSurvey(hipsId);
          document.querySelectorAll('.btn-survey').forEach(b => b.classList.remove('active'));
          const activeBtn = document.getElementById(btnId);
          if (activeBtn) activeBtn.classList.add('active');
        }}

        function setZoom(fovDeg) {{
          if (!aladinInstance) return;
          aladinInstance.gotoRaDec(targetRa, targetDec);
          aladinInstance.setFoV(fovDeg);
        }}
      </script>
    </body>
    </html>
    """
    components.html(html_aladin, height=altura_px)


# =====================================================================
# FUNCIONES DE LECTURA LOCAL Y NORMALIZACIÓN EN CACHÉ
# =====================================================================
def mjd_a_local(mjd_val):
    if mjd_val is None:
        return None
    try:
        dt_utc = EPOCA_MJD + timedelta(days=float(mjd_val))
        return (dt_utc - timedelta(hours=3)).replace(tzinfo=None)
    except Exception:
        return None


def clasificar_categoria_ui(ev):
    t = str(ev.get("tipo", "")).lower().strip()
    survey = str(ev.get("survey", "")).strip()
    vip = bool(ev.get("vip", False))

    if t == "tde":
        return "🌀 Agujeros Negros (TDE)"
    if t == "nova":
        return "💥 Novas / Cataclísmicas"
    if t == "blazar":
        return "🚀 Blazares"
    if t == "agn":
        return "🕳️ AGN (Cuásar)"
    if t == "flare":
        return "🔥 Flares VIP" if vip else None
    if t == "supernova" and survey == "TNS_GLOBAL":
        return "✅ Supernovas Confirmadas (TNS)"
    if t == "supernova":
        return "🚨 Supernovas Candidatas (ZTF/LSST)"
    return None


def clasificar_categoria_mapa(ev):
    t = str(ev.get("tipo", "")).lower().strip()
    survey = str(ev.get("survey", "")).strip()
    vip = bool(ev.get("vip", False))

    if t == "tde":
        return "Agujero Negro (TDE)"
    if t == "nova":
        return "Nova / Cataclísmica"
    if t == "blazar":
        return "Blazar (Chorro)"
    if t == "agn":
        return "AGN (Cuásar)"
    if t == "flare":
        return "Flare (Enana M VIP)" if vip else None
    if t == "supernova" and survey == "TNS_GLOBAL":
        return "Confirmada TNS"
    if t == "supernova":
        return "Candidata"
    return None


@st.cache_data(ttl=300)
def leer_catalogo_maestro():
    if os.path.exists("catalogo_maestro.json"):
        try:
            with open("catalogo_maestro.json", "r", encoding="utf-8") as f:
                datos = json.load(f)
            preparados = []
            for ev in datos:
                item = dict(ev)
                dt_local = mjd_a_local(item.get("mjd_deteccion"))
                item["_dt_local"] = dt_local
                item["_fecha_local"] = dt_local.date() if dt_local else None
                item["_cat_ui"] = clasificar_categoria_ui(item)
                oid_txt = str(item.get("oid", ""))
                texto_busqueda = " ".join(
                    [
                        oid_txt,
                        oid_txt.replace(" ", ""),
                        str(item.get("analisis", "")),
                        str(item.get("tipo", "")),
                        str(item.get("survey", "")),
                        str(item["_cat_ui"] or ""),
                    ]
                ).lower()
                item["_search_blob"] = texto_busqueda
                preparados.append(item)
            return preparados
        except Exception:
            pass
    return []


@st.cache_data(ttl=300)
def leer_archivo_texto(ruta):
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return None


def extraer_metadatos_circular(oid):
    oid_limpio = str(oid).replace(" ", "_").replace("/", "-")
    cont_circ = leer_archivo_texto(f"alertas/CIRCULAR_{oid_limpio}.txt")
    escudo, z_val, dist_val = "", "", ""
    if not cont_circ:
        return escudo, z_val, dist_val

    match_escudo = re.search(r"Nombre Oficial Asignado\s*:\s*(.*)", cont_circ)
    if match_escudo:
        escudo = match_escudo.group(1).strip()

    match_z_lab = re.search(r"REDSHIFT \(z\)\s*:\s*(.*)", cont_circ)
    match_z_tns = re.search(r"z = (.*?)\)", cont_circ)
    if match_z_lab and "Desconocido" not in match_z_lab.group(1):
        z_val = match_z_lab.group(1).strip()
    elif match_z_tns and "None" not in str(match_z_tns.group(1)) and "Desconocido" not in str(match_z_tns.group(1)):
        z_val = match_z_tns.group(1).strip()

    match_mpc = re.search(r"(Entre \d+\.\d+ y \d+\.\d+ Megaparsecs)", cont_circ)
    match_dist_local = re.search(r"^DISTANCIA\s*:\s*(.*)", cont_circ, re.MULTILINE)
    if match_mpc:
        dist_val = match_mpc.group(1).replace("Megaparsecs", "Mpc")
    elif match_dist_local and "Desconocida" not in match_dist_local.group(1):
        dist_val = match_dist_local.group(1).strip()

    return escudo, z_val, dist_val


def obtener_estado_red(ruta_log):
    contenido = leer_archivo_texto(ruta_log)
    if not contenido:
        return "Desconocido", "⚪"

    lineas = contenido.split("\n")
    sesion_actual = []
    for linea in reversed(lineas):
        if not linea.strip():
            continue
        sesion_actual.insert(0, linea)
        if "APUNTANDO TELESCOPIO" in linea:
            break

    texto_final = "\n".join(sesion_actual)
    if "Error" in texto_final or "Timeout" in texto_final:
        return "Error / Caída", "🔴"
    elif any(
        x in texto_final
        for x in [
            "Procesadas",
            "Conexión exitosa",
            "Patrullaje",
            "Procesando evento",
            "Sincronización TNS",
            "Procesamiento TNS finalizado",
        ]
    ):
        return "Operativa", "🟢"
    return "En reposo", "🟡"


# =====================================================================
# BARRA LATERAL DE NAVEGACIÓN, BÚSQUEDA GLOBAL Y FILTROS UNIFICADOS
# =====================================================================
try:
    st.sidebar.image("logo.jpeg", width="stretch")
except Exception:
    pass
st.sidebar.markdown("[⬅️ Volver a la Estación Magallanes](https://www.estacionmagallanes.org)")
st.sidebar.divider()

if st.sidebar.button("🔄 Sincronizar Radar", width="stretch"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.title("Panel de Control")
vista = st.sidebar.selectbox(
    "Selecciona una vista:",
    [
        "Dashboard Principal (Telemetría)",
        "Feed de Alertas y Circulares",
        "Bitácoras del Sistema",
        "Acerca del Observatorio",
    ],
)

st.sidebar.divider()
st.sidebar.markdown("### 🔎 Búsqueda y Filtros")

busqueda_global = st.sidebar.text_input(
    "Buscar objeto, subtipo o red:",
    value="",
    placeholder="Ej: 2026akbp, TDE, SN Ia, ZTF18...",
    help="Al escribir un término, la consulta busca automáticamente en todo el historial ignorando el filtro de fecha.",
).strip()

hora_magallanes = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(tzinfo=None)
hoy_local = hora_magallanes.date()

modo_temporal = st.sidebar.radio(
    "📅 Alcance Temporal (Hora Magallanes):",
    ["Día específico", "Rango de fechas", "Todo el historial"],
    index=0,
)

fecha_seleccionada = hoy_local
fecha_inicio = hoy_local - timedelta(days=7)
fecha_fin = hoy_local

if modo_temporal == "Día específico":
    fecha_seleccionada = st.sidebar.date_input("Fecha:", hoy_local)
elif modo_temporal == "Rango de fechas":
    fecha_inicio = st.sidebar.date_input("Desde:", hoy_local - timedelta(days=7))
    fecha_fin = st.sidebar.date_input("Hasta:", hoy_local)
    if fecha_inicio > fecha_fin:
        fecha_inicio, fecha_fin = fecha_fin, fecha_inicio
        st.sidebar.warning("Se invirtió el rango porque la fecha inicial era mayor que la final.")

if busqueda_global:
    st.sidebar.caption("🌐 Búsqueda global activa: consultando todo el historial.")

filtro_tipo_global = st.sidebar.selectbox("Clasificación Astrofísica:", OPCIONES_TIPO)
filtro_red_global = st.sidebar.selectbox("Red de Origen:", OPCIONES_RED)

# =====================================================================
# MOTOR DE FILTRADO UNIFICADO EN RAM
# =====================================================================
catalogo_datos = leer_catalogo_maestro()

tokens_busqueda = [tok for tok in busqueda_global.lower().split() if tok]
catalogo_filtrado = []

for ev in catalogo_datos:
    if not tokens_busqueda:
        fecha_ev = ev.get("_fecha_local")
        if modo_temporal == "Día específico":
            if fecha_ev != fecha_seleccionada:
                continue
        elif modo_temporal == "Rango de fechas":
            if not fecha_ev or not (fecha_inicio <= fecha_ev <= fecha_fin):
                continue

    if tokens_busqueda:
        blob = ev.get("_search_blob", "")
        if not all(tok in blob for tok in tokens_busqueda):
            continue

    if filtro_tipo_global != "👁️ Todos los tipos":
        if ev.get("_cat_ui") != filtro_tipo_global:
            continue

    if filtro_red_global != "🌐 Todas las redes":
        if ev.get("survey") != filtro_red_global:
            continue

    catalogo_filtrado.append(ev)

catalogo_filtrado.sort(key=lambda x: float(x.get("mjd_deteccion") or 0.0), reverse=True)

if busqueda_global:
    etiqueta_alcance = f'Búsqueda global: "{busqueda_global}"'
elif modo_temporal == "Día específico":
    etiqueta_alcance = fecha_seleccionada.strftime("%Y-%m-%d")
elif modo_temporal == "Rango de fechas":
    etiqueta_alcance = f"{fecha_inicio.strftime('%Y-%m-%d')} al {fecha_fin.strftime('%Y-%m-%d')}"
else:
    etiqueta_alcance = "Historial Completo"

filtros_extra = []
if filtro_tipo_global != "👁️ Todos los tipos":
    filtros_extra.append(filtro_tipo_global)
if filtro_red_global != "🌐 Todas las redes":
    filtros_extra.append(f"Red: {filtro_red_global}")
sufijo_filtros = f" | {' · '.join(filtros_extra)}" if filtros_extra else ""


# =====================================================================
# VISTA 1: DASHBOARD PRINCIPAL Y MAPA ESTELAR DUAL
# =====================================================================
if vista == "Dashboard Principal (Telemetría)":
    st.title("🛰️ Estación Magallanes - Telemetría")

    estado_ztf, icono_ztf = obtener_estado_red("bitacoras/bitacora_ZTF.log")
    estado_lsst, icono_lsst = obtener_estado_red("bitacoras/bitacora_LSST.log")
    estado_tns, icono_tns = obtener_estado_red("bitacoras/bitacora_TNS_GLOBAL.log")

    col_red1, col_red2, col_red3 = st.columns(3)
    col_red1.metric("ZTF (Norte)", estado_ztf, icono_ztf)
    col_red2.metric("LSST / Rubin (Sur)", estado_lsst, icono_lsst)
    col_red3.metric("TNS (IAU Global)", estado_tns, icono_tns)

    st.divider()

    total_tns = sum(1 for e in catalogo_filtrado if e.get("survey") == "TNS_GLOBAL" and e.get("tipo") == "supernova")
    total_cand = sum(1 for e in catalogo_filtrado if e.get("survey") != "TNS_GLOBAL" and e.get("tipo") == "supernova")
    total_novas = sum(1 for e in catalogo_filtrado if e.get("tipo") == "nova")
    total_agn = sum(1 for e in catalogo_filtrado if e.get("tipo") in ["agn", "blazar"])
    total_tdes = sum(1 for e in catalogo_filtrado if e.get("tipo") == "tde")
    total_flares = sum(1 for e in catalogo_filtrado if e.get("tipo") == "flare" and e.get("vip", False))

    st.subheader(f"📊 Resumen del Catálogo Activo ({etiqueta_alcance}{sufijo_filtros})")
    col_det1, col_det2, col_det3, col_det4, col_det5, col_det6 = st.columns(6)
    col_det1.metric("✅ Supernovas (TNS)", str(total_tns), "Confirmadas", delta_color="normal")
    col_det2.metric("🚨 Candidatas (ZTF/LSST)", str(total_cand), "Requiere ATel", delta_color="inverse")
    col_det3.metric("💥 Novas", str(total_novas), "Erupción", delta_color="normal")
    col_det4.metric("🕳️ AGN/Blazar", str(total_agn), "Extragaláctico", delta_color="normal")
    col_det5.metric("🌀 Agujeros Negros", str(total_tdes), "Disrupción TDE", delta_color="normal")
    col_det6.metric("🔥 Flares VIP", str(total_flares), "Estelar", delta_color="normal")

    with st.expander("📖 Glosario de Terminología Astrofísica"):
        st.markdown(
            """
- **TNS (Transient Name Server):** Nodo oficial de la IAU para reportar supernovas y transitorios confirmados.
- **ZTF (Zwicky Transient Facility):** Observatorio robótico en el hemisferio norte (Palomar).
- **LSST (Legacy Survey of Space and Time):** Observatorio Vera C. Rubin (hemisferio sur).
- **SN (Supernova):** Explosión termonuclear o colapso de núcleo de una estrella.
- **TDE (Tidal Disruption Event):** Evento de disrupción de marea donde un agujero negro supermasivo destroza y devora una estrella.
- **AGN (Active Galactic Nucleus) / Cuásar:** Núcleo galáctico activo alimentado por un agujero negro supermasivo.
- **Blazar:** Tipo de AGN cuyo chorro relativista apunta directamente hacia la Tierra.
- **Nova / CV (Variable Cataclísmica):** Erupción superficial en una enana blanca por acreción de materia.
- **Flare VIP (Enana M):** Erupción estelar violenta en estrellas frías y pequeñas (Alta prioridad local).
            """
        )

    st.subheader(f"🌌 Mapa Celeste de Detecciones ({len(catalogo_filtrado)} eventos en vista)")

    if catalogo_filtrado:
        modo_mapa = st.radio(
            "Modo de visualización:",
            [
                "🌌 Universo Interactivo (Aladin Todo-Cielo)",
                "📈 Grilla Analítica (Plano Galáctico y Horizonte)",
            ],
            horizontal=True,
            label_visibility="collapsed",
        )

        if modo_mapa.startswith("🌌"):
            limite_aladin = 1500
            eventos_para_aladin = catalogo_filtrado[:limite_aladin]
            if len(catalogo_filtrado) > limite_aladin:
                st.caption(
                    f"Mostrando los {limite_aladin} eventos más recientes en el mapa interactivo del universo para preservar fluidez. "
                    "Cambia a **📈 Grilla Analítica** para inspeccionar el historial completo con WebGL."
                )

            enriquecer = len(eventos_para_aladin) <= 600
            agrupados_aladin = {nombre: [] for nombre in CONFIG_CATEGORIAS_MAPA}

            for ev in eventos_para_aladin:
                cat = clasificar_categoria_mapa(ev)
                ra_v, dec_v = ev.get("ra"), ev.get("dec")
                if not cat or ra_v is None or dec_v is None:
                    continue

                dt_local = ev.get("_dt_local")
                fecha_txt = dt_local.strftime("%Y-%m-%d %H:%M Local") if dt_local else "Fecha no disp."
                escudo, z_val, dist_val = extraer_metadatos_circular(ev.get("oid")) if enriquecer else ("", "", "")

                agrupados_aladin[cat].append(
                    {
                        "ra": round(float(ra_v), 5),
                        "dec": round(float(dec_v), 5),
                        "oid": str(ev.get("oid", "")),
                        "survey": str(ev.get("survey", "")),
                        "analisis": str(ev.get("analisis", "")),
                        "fecha": fecha_txt,
                        "coords": f"RA {float(ra_v):.4f}° | Dec {float(dec_v):.4f}°",
                        "escudo": escudo,
                        "z": z_val,
                        "dist": dist_val,
                    }
                )

            capas_aladin = []
            for nombre_cat, cfg in CONFIG_CATEGORIAS_MAPA.items():
                if agrupados_aladin[nombre_cat]:
                    capas_aladin.append(
                        {
                            "nombre": nombre_cat,
                            "color": cfg["color"],
                            "shape": cfg["aladin_shape"],
                            "size": cfg["aladin_size"],
                            "eventos": agrupados_aladin[nombre_cat],
                        }
                    )

            renderizar_mapa_universo_aladin(capas_aladin, altura_px=650)

        else:
            datos_plotly = {
                nombre_cat: {
                    "ra": [],
                    "dec": [],
                    "text": [],
                    "color": cfg["color"],
                    "symbol": cfg["symbol"],
                }
                for nombre_cat, cfg in CONFIG_CATEGORIAS_MAPA.items()
            }

            enriquecer_con_circulares = len(catalogo_filtrado) <= 600

            for ev in catalogo_filtrado:
                cat = clasificar_categoria_mapa(ev)
                ra_v, dec_v = ev.get("ra"), ev.get("dec")
                if not cat or ra_v is None or dec_v is None:
                    continue

                survey = ev.get("survey", "")
                dt_local = ev.get("_dt_local")
                fecha_txt = dt_local.strftime("%Y-%m-%d %H:%M Local") if dt_local else "Fecha no disp."
                mjd_val = ev.get("mjd_deteccion")
                mjd_str = f"MJD: {float(mjd_val):.4f}" if mjd_val else "MJD: No disp."

                extra_info = ""
                if enriquecer_con_circulares:
                    escudo, z_val, dist_val = extraer_metadatos_circular(ev.get("oid"))
                    if escudo:
                        extra_info += f"<br><b style='color:#ff3333;'>🛡️ Escudo TNS: {escudo}</b>"
                    if z_val:
                        extra_info += f"<br><b>z:</b> {z_val}"
                    if dist_val:
                        extra_info += f"<br><b>D:</b> {dist_val}"

                hover_txt = (
                    f"<b>{ev.get('oid')}</b> [{survey}]<br>"
                    f"{ev.get('analisis')}<br>"
                    f"Fecha: {fecha_txt} | {mjd_str}<br>"
                    f"RA: {float(ra_v):.4f}° | Dec: {float(dec_v):.4f}°{extra_info}"
                )

                datos_plotly[cat]["ra"].append(float(ra_v))
                datos_plotly[cat]["dec"].append(float(dec_v))
                datos_plotly[cat]["text"].append(hover_txt)

            total_puntos_mapa = sum(len(d["ra"]) for d in datos_plotly.values())
            usar_webgl = total_puntos_mapa > 1000
            clase_traza = go.Scattergl if usar_webgl else go.Scatter

            fig = go.Figure()

            ra_g0, dec_g0 = calcular_curva_galactica(0.0)
            ra_gp, dec_gp = calcular_curva_galactica(10.0)
            ra_gm, dec_gm = calcular_curva_galactica(-10.0)

            fig.add_trace(
                go.Scatter(
                    x=ra_g0,
                    y=dec_g0,
                    mode="lines",
                    name="Plano Galáctico (b=0°, ±10°)",
                    legendgroup="plano_galactico",
                    hoverinfo="skip",
                    line=dict(color="rgba(140, 195, 255, 0.55)", width=1.6, dash="dash"),
                )
            )
            for rx, dy in [(ra_gp, dec_gp), (ra_gm, dec_gm)]:
                fig.add_trace(
                    go.Scatter(
                        x=rx,
                        y=dy,
                        mode="lines",
                        legendgroup="plano_galactico",
                        showlegend=False,
                        hoverinfo="skip",
                        line=dict(color="rgba(140, 195, 255, 0.25)", width=1.0, dash="dot"),
                    )
                )

            fig.add_hrect(
                y0=DEC_LIMITE_NORTE_PA,
                y1=90,
                fillcolor="rgba(255, 190, 0, 0.05)",
                line_width=0,
            )
            fig.add_hline(
                y=DEC_LIMITE_NORTE_PA,
                line_dash="dot",
                line_color="rgba(255, 204, 0, 0.65)",
                annotation_text="Horizonte Norte Punta Arenas (+36.85°) · Superior no visible desde Magallanes",
                annotation_position="top left",
                annotation_font_color="rgba(255, 214, 102, 0.85)",
                annotation_font_size=11,
            )

            for nombre_cat, datos in datos_plotly.items():
                if len(datos["ra"]) > 0:
                    fig.add_trace(
                        clase_traza(
                            x=datos["ra"],
                            y=datos["dec"],
                            mode="markers",
                            name=f"{nombre_cat} ({len(datos['ra'])})",
                            text=datos["text"],
                            hoverinfo="text",
                            marker=dict(
                                symbol=datos["symbol"],
                                size=14 if ("Candidata" in nombre_cat or "TDE" in nombre_cat) else 11,
                                color=datos["color"],
                                opacity=0.82,
                                line=dict(width=1, color="white"),
                            ),
                        )
                    )

            fig.update_layout(
                plot_bgcolor="#0e1117",
                paper_bgcolor="#0e1117",
                font=dict(color="lightgray", size=13),
                height=600,
                xaxis=dict(title="Ascensión Recta (Grados)", range=[0, 360], gridcolor="rgba(255,255,255,0.1)"),
                yaxis=dict(title="Declinación (Grados)", range=[-90, 90], gridcolor="rgba(255,255,255,0.1)"),
                legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="left", x=0),
                margin=dict(l=40, r=40, t=58, b=40),
                hovermode="closest",
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"No hay eventos astronómicos registrados para la selección actual ({etiqueta_alcance}{sufijo_filtros}).")


# =====================================================================
# VISTA 2: FEED DE ALERTAS Y CIRCULARES
# =====================================================================
elif vista == "Feed de Alertas y Circulares":
    st.title("📋 Alertas y Circulares de Detecciones")
    st.caption(f"Consulta activa: **{etiqueta_alcance}{sufijo_filtros}** — **{len(catalogo_filtrado)}** evento(s) coincidente(s).")

    if catalogo_filtrado:
        with st.expander(f"📑 Tabla rápida de resultados ({len(catalogo_filtrado)} eventos)"):
            filas_tabla = []
            for e in catalogo_filtrado:
                dt_loc = e.get("_dt_local")
                filas_tabla.append(
                    {
                        "Fecha Local": dt_loc.strftime("%Y-%m-%d %H:%M") if dt_loc else "Desconocida",
                        "Objeto": e.get("oid"),
                        "Red": e.get("survey"),
                        "Tipo": str(e.get("tipo", "")).upper(),
                        "Clasificación / Análisis": e.get("analisis"),
                        "RA (°)": round(float(e["ra"]), 4) if e.get("ra") is not None else None,
                        "Dec (°)": round(float(e["dec"]), 4) if e.get("dec") is not None else None,
                    }
                )
            st.dataframe(filas_tabla, use_container_width=True, hide_index=True)

        opciones = {}
        for e in catalogo_filtrado:
            survey_origen = e.get("survey", "Desconocido")
            oid_str = str(e.get("oid", ""))
            oid_para_check = oid_str.replace(" ", "_").replace("/", "-")
            dt_local = e.get("_dt_local")
            fecha_hora_str = dt_local.strftime("%Y-%m-%d %H:%M Local") if dt_local else "Fecha desc."

            if survey_origen == "TNS_GLOBAL":
                prefijo = "✅ [TNS]"
            elif survey_origen == "ZTF":
                prefijo = "🚨 [ZTF]"
            elif survey_origen == "LSST":
                prefijo = "🚨 [LSST]"
            else:
                prefijo = f"🚨 [{survey_origen}]"

            ruta_espectro_check = f"data/quimica_halfa_{oid_para_check}.png"
            indicador_espectro = " 🌈 [Espectro]" if os.path.exists(ruta_espectro_check) else ""
            analisis_corto = str(e.get("analisis", "")).strip()
            etiqueta_clase = analisis_corto if survey_origen == "TNS_GLOBAL" and analisis_corto else str(e.get("tipo", "")).upper()

            clave = f"[{fecha_hora_str}] {prefijo} {oid_str} — {etiqueta_clase}{indicador_espectro}"
            opciones[clave] = e

        seleccion = st.selectbox(f"Selecciona un evento ({len(opciones)} encontrados):", list(opciones.keys()))
        evento_actual = opciones[seleccion]

        oid_limpio = str(evento_actual.get("oid")).replace(" ", "_").replace("/", "-")
        survey = evento_actual.get("survey")
        ra_obj = evento_actual.get("ra")
        dec_obj = evento_actual.get("dec")

        st.info(
            "💡 **Nota sobre sincronización temporal:** La fecha y hora mostradas en el catálogo corresponden al instante "
            "en que la luz del evento impactó el espejo del observatorio (o la época oficial de actualización en TNS si no "
            "hay fotometría pública). Las bitácoras de la Estación Magallanes reflejan la hora de procesamiento local."
        )

        ruta_circular = f"alertas/CIRCULAR_{oid_limpio}.txt"
        ruta_atel = f"alertas_comunidad/ALERTA_ATEL_{oid_limpio}.txt"
        ruta_aavso = f"alertas_comunidad/ALERTA_AAVSO_{oid_limpio}.txt"

        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("📄 Documentación y Telegramas")

            cont_circ_temp = leer_archivo_texto(ruta_circular)
            if cont_circ_temp and "INTERVENCIÓN DEL ESCUDO TNS" in cont_circ_temp:
                st.error(
                    "🛡️ **BLOQUEO ACTIVO:** El Escudo TNS detectó duplicidad astronómica y abortó automáticamente "
                    "la emisión del Telegrama (ATel) para proteger la reputación de la Estación Magallanes."
                )

            if evento_actual.get("tipo") == "flare":
                tab1, tab2 = st.tabs(["Circular Interna (Análisis)", "🚨 Alerta AAVSO (Solicitud)"])
            elif survey == "TNS_GLOBAL":
                tab1, tab2 = st.tabs(["Circular Interna (Análisis)", "✅ Registro TNS (Informativo)"])
            else:
                tab1, tab2 = st.tabs(["Circular Interna (Análisis)", "🚨 Borrador ATel (Urgente)"])

            with tab1:
                cont_circ = leer_archivo_texto(ruta_circular)
                if cont_circ:
                    st.code(cont_circ, language="text")
                else:
                    st.warning("Circular en procesamiento...")

            with tab2:
                ruta_alerta = ruta_aavso if evento_actual.get("tipo") == "flare" else ruta_atel
                cont_alerta = leer_archivo_texto(ruta_alerta)
                if cont_alerta:
                    st.code(cont_alerta, language="text")
                elif survey == "TNS_GLOBAL":
                    st.info("Evento ya confirmado espectroscópicamente por la IAU en TNS; no requiere emisión de telegrama ATel.")
                else:
                    st.info("El borrador comunitario no aplica o no ha sido generado debido a bloqueos del Escudo.")

        with col2:
            st.subheader("📊 Evidencia y Contexto Celeste")

            if ra_obj is not None and dec_obj is not None:
                obs_pa = calcular_observabilidad_magallanes(float(ra_obj), float(dec_obj))
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Punta Arenas", obs_pa["condicion"], obs_pa["detalle_cond"])
                m2.metric("Altura Actual", obs_pa["alt_actual_str"], obs_pa["alt_actual_detalle"])
                m3.metric("Culminación", obs_pa["transito_str"], obs_pa["transito_detalle"])
                m4.metric("Altura Máx.", obs_pa["alt_max_str"], obs_pa["masa_aire"])

            ruta_grafico = f"data/curva_luz_{oid_limpio}.png"
            ruta_halfa = f"data/quimica_halfa_{oid_limpio}.png"

            opciones_evidencia = []
            if os.path.exists(ruta_grafico):
                opciones_evidencia.append("Curva de Luz y Carta")
            if os.path.exists(ruta_halfa):
                opciones_evidencia.append("Espectroscopía Taxonómica")

            if not opciones_evidencia:
                st.warning("Gráfica fotométrica reservada o no disponible en la red de origen.")
            elif len(opciones_evidencia) == 1:
                st.image(
                    ruta_grafico if opciones_evidencia[0].startswith("Curva") else ruta_halfa,
                    use_container_width=True,
                )
            else:
                seleccion_evidencia = st.radio(
                    "Evidencia gráfica:",
                    opciones_evidencia,
                    horizontal=True,
                    label_visibility="collapsed",
                )
                if seleccion_evidencia == "Curva de Luz y Carta":
                    st.image(ruta_grafico, use_container_width=True)
                else:
                    st.image(ruta_halfa, use_container_width=True)

            if ra_obj is not None and dec_obj is not None:
                st.markdown("##### 🌌 Visor Celeste Interactivo (Aladin Lite)")
                renderizar_visor_aladin(
                    float(ra_obj),
                    float(dec_obj),
                    evento_actual.get("oid", ""),
                    altura_px=470,
                )
    else:
        st.info(f"No hay alertas registradas para la selección actual ({etiqueta_alcance}{sufijo_filtros}).")


# =====================================================================
# VISTA 3: BITÁCORAS DEL SISTEMA
# =====================================================================
elif vista == "Bitácoras del Sistema":
    st.title("📜 Monitoreo de Operaciones en Tiempo Real")
    st.info("🕒 **Sincronización:** El sistema de búsqueda opera en UTC. La visualización ha sido convertida a hora local (Punta Arenas: UTC-3).")

    def parse_logs_con_timezone(ruta_log, red_name, red_code):
        parsed = []
        contenido = leer_archivo_texto(ruta_log)
        if not contenido:
            return parsed

        for linea in contenido.split("\n"):
            if "-> Procesadas" in linea or "===" in linea or not linea.strip():
                continue
            try:
                if linea.startswith("["):
                    fecha_hora_str = linea[1:20]
                    mensaje = linea[22:].strip()
                    dt_utc = datetime.strptime(fecha_hora_str, "%Y-%m-%d %H:%M:%S")
                    dt_local = dt_utc - timedelta(hours=3)

                    parsed.append(
                        {
                            "timestamp_sort": dt_local,
                            "fecha_date": dt_local.date(),
                            "fecha_local": dt_local.strftime("%Y-%m-%d"),
                            "hora_local": dt_local.strftime("%H:%M"),
                            "hora_utc": dt_utc.strftime("%H:%M"),
                            "msg": mensaje,
                            "red": red_name,
                            "red_code": red_code,
                        }
                    )
            except Exception:
                pass
        return parsed

    logs_ztf = parse_logs_con_timezone("bitacoras/bitacora_ZTF.log", "ZTF (Norte)", "ZTF")
    logs_lsst = parse_logs_con_timezone("bitacoras/bitacora_LSST.log", "LSST / Rubin (Sur)", "LSST")
    logs_tns = parse_logs_con_timezone("bitacoras/bitacora_TNS_GLOBAL.log", "TNS Global (Confirmaciones)", "TNS_GLOBAL")

    def agrupar_en_ciclos(logs):
        ciclos_agrupados = []
        ciclo_actual = None
        for log in logs:
            if "APUNTANDO TELESCOPIO" in log["msg"]:
                if ciclo_actual is not None:
                    ciclos_agrupados.append(ciclo_actual)
                ciclo_actual = {
                    "red": log["red"],
                    "red_code": log["red_code"],
                    "fecha_date": log["fecha_date"],
                    "fecha_local": log["fecha_local"],
                    "inicio_local": log["hora_local"],
                    "inicio_utc": log["hora_utc"],
                    "timestamp_sort": log["timestamp_sort"],
                    "logs": [log],
                    "candidatos": 0,
                    "errores": 0,
                }
            else:
                if ciclo_actual is None:
                    ciclo_actual = {
                        "red": log["red"],
                        "red_code": log["red_code"],
                        "fecha_date": log["fecha_date"],
                        "fecha_local": log["fecha_local"],
                        "inicio_local": log["hora_local"],
                        "inicio_utc": log["hora_utc"],
                        "timestamp_sort": log["timestamp_sort"],
                        "logs": [],
                        "candidatos": 0,
                        "errores": 0,
                    }
                ciclo_actual["logs"].append(log)

            msg_low = log["msg"].lower()
            if "procesando evento de interés" in msg_low or "descargando ficha" in msg_low or "reclasificado" in msg_low:
                ciclo_actual["candidatos"] += 1
            if "error" in msg_low or "denegado" in msg_low or "timeout" in msg_low:
                ciclo_actual["errores"] += 1

        if ciclo_actual is not None:
            ciclos_agrupados.append(ciclo_actual)
        return ciclos_agrupados

    todos_los_ciclos = agrupar_en_ciclos(logs_ztf) + agrupar_en_ciclos(logs_lsst) + agrupar_en_ciclos(logs_tns)
    todos_los_ciclos.sort(key=lambda x: x["timestamp_sort"], reverse=True)

    ciclos_filtrados = []
    for c in todos_los_ciclos:
        if filtro_red_global != "🌐 Todas las redes" and c["red_code"] != filtro_red_global:
            continue

        if tokens_busqueda:
            texto_ciclo = (c["red"] + " " + " ".join(l["msg"] for l in c["logs"])).lower()
            if not all(tok in texto_ciclo for tok in tokens_busqueda):
                continue
        else:
            if modo_temporal == "Día específico" and c["fecha_date"] != fecha_seleccionada:
                continue
            if modo_temporal == "Rango de fechas" and not (fecha_inicio <= c["fecha_date"] <= fecha_fin):
                continue

        ciclos_filtrados.append(c)

    total_patrullajes = len(ciclos_filtrados)
    total_candidatos = sum(c["candidatos"] for c in ciclos_filtrados)
    total_errores = sum(c["errores"] for c in ciclos_filtrados)

    st.subheader(f"📊 Métricas de Patrullaje ({etiqueta_alcance})")
    col1, col2, col3 = st.columns(3)
    col1.metric("📡 Ciclos de Patrullaje", str(total_patrullajes))
    col2.metric("🌌 Alertas Analizadas", str(total_candidatos))
    col3.metric("🚨 Errores de Red", str(total_errores))
    st.divider()

    st.subheader("⏱️ Secuencia de Eventos (Timeline)")
    limite_visualizacion = 80
    if len(ciclos_filtrados) > limite_visualizacion:
        st.caption(f"Mostrando los {limite_visualizacion} ciclos más recientes de {len(ciclos_filtrados)} encontrados.")

    if ciclos_filtrados:
        for ciclo in ciclos_filtrados[:limite_visualizacion]:
            with st.container():
                if "ZTF" in ciclo["red"]:
                    color_red = "🔵"
                elif "LSST" in ciclo["red"]:
                    color_red = "🟠"
                else:
                    color_red = "🟣"

                st.markdown(
                    f"#### {color_red} [{ciclo['fecha_local']} · {ciclo['inicio_local']} Local | {ciclo['inicio_utc']} UTC] {ciclo['red']}"
                )

                if ciclo["errores"] > 0:
                    st.error(
                        f"⚠️ **Atención:** Se detectaron {ciclo['errores']} incidentes/errores de conexión. | ⚡ {ciclo['candidatos']} alertas evaluadas."
                    )
                elif ciclo["candidatos"] > 0:
                    st.success(
                        f"✅ Ciclo operativo y sin errores. | ⚡ **{ciclo['candidatos']} anomalías astrofísicas** procesadas."
                    )
                else:
                    st.info("💤 Ciclo completado sin anomalías detectadas ni errores.")

                with st.expander("👨‍💻 Auditar Registro Técnico (Modo Terminal)"):
                    log_text = ""
                    for log in ciclo["logs"]:
                        log_text += f"[{log['hora_local']} Local | {log['hora_utc']} UTC] {log['msg']}\n"
                    st.code(log_text, language="text")
                st.write("---")
    else:
        st.warning(f"El observatorio no registró patrullajes para la selección actual ({etiqueta_alcance}).")


# =====================================================================
# VISTA 4: ACERCA DE
# =====================================================================
elif vista == "Acerca del Observatorio":
    st.title("🔭 Estación Magallanes")
    st.subheader("Laboratorio de Astrofísica y Ciencia Ciudadana")
    st.divider()

    st.header("Explorando el Universo Dinámico desde el Fin del Mundo")
    st.markdown(
        """
    La **Estación Magallanes** es un nodo de investigación independiente y de ciencia ciudadana astrofísica. Operando ininterrumpidamente desde Punta Arenas, en la Patagonia Chilena, nuestro objetivo es transformar inmensos volúmenes de datos crudos en información a disposición de toda la comunidad.
    
    Nuestro motor principal es un algoritmo de minería de datos que actúa como un **Broker Astrofísico local**. Integrando modelos de Inteligencia Artificial de frontera (como ALeRCE), procesamos "ríos de datos" masivos para interceptar alertas astronómicas en tiempo real, cazando eventos cósmicos catastróficos y transitorios milisegundos después de ser detectados, antes de que se desvanezcan en el cielo nocturno.
    """
    )
    st.divider()

    st.header("Nuestros Objetivos Científicos")
    st.markdown(
        """
- **Física Estelar y Habitabilidad Exoplanetaria:** Monitoreamos las llamaradas magnéticas extremas (*Flares*) en estrellas Enanas Rojas (Tipo M). Analizamos en tiempo real cómo estas violentas inyecciones de radiación UV impactan la atmósfera, viabilidad y habitabilidad de los sistemas exoplanetarios confirmados que orbitan estos soles.
- **Evolución y Destrucción Estelar Masiva:** El laboratorio automatizado rastrea y procesa sin descanso alertas de Supernovas (Colapso de núcleo y termonucleares) y Variables Cataclísmicas. Para garantizar la máxima precisión, cruzamos nuestra telemetría extragaláctica directamente con el Servidor de Nombres de Transitorios (TNS), aportando al seguimiento de eventos que actúan como "candelas estándar" para medir la expansión del universo.
- **Astrofísica de Altas Energías (Agujeros Negros Supermasivos):** Monitoreamos los confines del universo observable detectando variabilidad en Núcleos Galácticos Activos (AGN). Nuestro algoritmo aísla y clasifica Cuásares hiperluminosos y Blazares, eventos extremos donde agujeros negros supermasivos devoran materia y emiten chorros de radiación relativista que apuntan directamente hacia la Tierra.
- **Democratización de Datos y Ciencia Ciudadana:** Más allá de la observación pura, nuestro objetivo es actuar como un **Broker Astrofísico local**. Utilizamos Inteligencia Artificial para filtrar el "ruido cósmico", transformando terabytes de datos crudos de observatorios profesionales en conocimiento accesible para astrónomos aficionados, educadores y la comunidad científica independiente.
    """
    )
    st.divider()

    st.header("Arquitectura del Flujo de Datos")
    st.markdown(
        "Nuestros radares barren las corrientes de alertas de las instituciones más prestigiosas del mundo, conectándonos directamente a los grandes sondeos para democratizar el seguimiento astronómico:"
    )
    st.markdown(
        """
- **Zwicky Transient Facility (ZTF):** Captura de explosiones en el hemisferio norte (Palomar, California).
- **ALeRCE:** Nuestra principal red neuronal de clasificación predictiva, desarrollada en Chile.
- **Transient Name Server (TNS) / IAU:** Nuestro radar global oficial de descubrimientos de supernovas.
- **Observatorio Vera C. Rubin (LSST):** En preparación para el aluvión de datos astronómicos más grande de la historia humana (Cerro Pachón, Chile).
    """
    )
    st.info(
        "*Este sistema de automatización de código abierto fue construido para tender un puente sólido entre la ciencia de frontera y la observación independiente. Si deseas integrar nuestra telemetría a tu observatorio o colaborar en el análisis espectroscópico de nuestros candidatos, la puerta está abierta.*"
    )
    st.divider()

    st.header("Glosario Taxonómico: Clasificación de Alertas")
    st.markdown(
        "Los eventos que detectamos siguen una clasificación oficial. Aquí detallamos cada categoría para que puedas interpretar nuestra telemetría de forma independiente:"
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("Eventos Estelares")
        st.markdown(
            """
- **Mdwarf-flare (Llamarada de Enana Roja):** Eventos de extrema inestabilidad magnética en estrellas de baja masa (Tipo M). Son el objetivo principal de la Estación Magallanes para estudiar el impacto de la radiación UV en posibles exoplanetas.
- **CV / Nova (Variable Cataclísmica):** Un sistema estelar binario donde una enana blanca "roba" material de una estrella compañera, generando explosiones termonucleares periódicas **en su superficie sin destruir la estrella.**
- **VS (Variable Star):** Clasificación genérica para cualquier tipo de fluctuación lumínica de origen estelar (utilizado en sondeos iniciales).
        """
        )
    with col2:
        st.subheader("Eventos Extragalácticos")
        st.markdown(
            """
- **SN Ia (Supernova Tipo Ia):** La explosión termonuclear completa de una enana blanca. Son fundamentales en cosmología como "candelas estándar" para medir la expansión del universo.
- **SN II / SN Ibc (Supernovas de Colapso de Núcleo):** La muerte violenta de estrellas supermasivas que agotan su combustible, colapsando bajo su propia gravedad.
- **SLSN (Supernova Superluminosa):** Explosiones estelares extremadamente raras y energéticas, hasta 100 veces más brillantes que una supernova normal.
- **TDE (Tidal Disruption Event):** Evento donde un agujero negro supermasivo destroza y devora una estrella por fuerzas de marea.
        """
        )
    with col3:
        st.subheader("Núcleos Galácticos Activos")
        st.markdown(
            """
- **AGN / QSO (Cuásar):** Un núcleo galáctico extremadamente luminoso impulsado por un agujero negro supermasivo devorando materia.
- **Blazar:** Un tipo de cuásar cuyo chorro de radiación relativista apunta directamente hacia la Tierra.
        """
        )

    st.divider()

    col_foot1, col_foot2 = st.columns(2)
    with col_foot1:
        st.markdown("**Estación Magallanes | Punta Arenas, Chile** (53° 09' S, 70° 54' W)")
        st.markdown("Contacto: contacto@estacionmagallanes.org")
    with col_foot2:
        st.link_button(
            "💻 Ver Repositorio en GitHub",
            "https://github.com/Edgardo-Casanova/estacion-magallanes",
            use_container_width=True,
        )
        st.link_button(
            "🌐 Visitar Sitio Web Oficial",
            "https://www.estacionmagallanes.org",
            use_container_width=True,
        )
