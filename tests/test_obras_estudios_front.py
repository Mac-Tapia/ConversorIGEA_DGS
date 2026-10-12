"""Spec 011, T17: el paso «4 · Obras y estudios» (contrato de la fuente del front).

Como en la spec 008, el front no se ejecuta en la suite: se comprueba en la fuente que
cada pieza está en su paso, que lo que el formulario ofrece es lo que pide la spec y que
cada llamada va a una ruta que la API define.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP_PY = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'app.py').read_text(encoding='utf-8')
CARGAS = (SRC / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
OBRAS = (SRC / 'components' / 'ObrasPF.tsx').read_text(encoding='utf-8')
ESTUDIOS = (SRC / 'components' / 'EstudiosPF.tsx').read_text(encoding='utf-8')
GUIONES = (SRC / 'components' / 'GuionesPF.tsx').read_text(encoding='utf-8')
TRANSF = (SRC / 'components' / 'TransferenciaPF.tsx').read_text(encoding='utf-8')
API = (SRC / 'api.ts').read_text(encoding='utf-8')


def _pos(texto: str, *piezas: str) -> list[int]:
    pos = [texto.find(p) for p in piezas]
    assert all(p >= 0 for p in pos), [p for p, i in zip(piezas, pos) if i < 0]
    return pos


def test_paso_4_despues_de_la_integracion_en_tres_partes():
    """011:RF-42, 011:RF-98 — el paso 4 va después del 3, con obras, estudios y transferencia
    en ese orden."""
    tres, cuatro, a, b, c = _pos(CARGAS, '<h3>3 · Integración de nuevas</h3>', '<h3>4 · Obras y estudios</h3>',
                                 '<h4>4.1 · Obras de mejora</h4>', '<h4>4.2 · Estudios</h4>',
                                 '<h4>4.3 · Transferencia de carga</h4>')
    assert tres < cuatro < a < b < c


def test_mismo_proyecto_y_mismos_alimentadores_marcados():
    """011:RF-42 — las tres partes reciben el proyecto y los alimentadores marcados en el
    paso 2; los estudios, también el ajuste que hace de base (RF-12)."""
    assert '<ObrasPF project={project} feeders={order} />' in CARGAS
    assert '<EstudiosPF project={project} feeders={order} ajusteJobId={baseJob?.id ?? null} />' in CARGAS
    assert '<TransferenciaPF project={project} feeders={order} />' in CARGAS


def test_cada_llamada_va_a_una_ruta_de_la_api():
    """011:RF-70, 011:RF-88, 011:RF-95, 011:RF-104 — lo que llaman los tres componentes
    existe en el servidor."""
    usadas = set(re.findall(r'api\.(\w+)\(', OBRAS + ESTUDIOS + TRANSF))
    assert {'obraAnadir', 'obraQuitar', 'obrasBibliotecas', 'obrasSimular', 'obrasAplicar',
            'estudiosCatalogo', 'estudiosPlan', 'estudiosEjecutar', 'transferencia'} <= usadas
    rutas = {
        'obraAnadir': "@app.post('/api/workspaces/{wid}/obras'",
        'obraQuitar': "@app.delete('/api/workspaces/{wid}/obras/{obra_id}'",
        'obrasBibliotecas': "@app.post('/api/workspaces/{wid}/pf/obras/bibliotecas'",
        'obrasSimular': "@app.post('/api/workspaces/{wid}/pf/obras/simular'",
        'obrasAplicar': "@app.post('/api/workspaces/{wid}/pf/obras/aplicar'",
        'estudiosCatalogo': "@app.get('/api/pf/estudios')",
        'estudiosPlan': "@app.post('/api/workspaces/{wid}/pf/estudios/plan')",
        'estudiosEjecutar': "@app.post('/api/workspaces/{wid}/pf/estudios/{token}/ejecutar'",
        'transferencia': "@app.post('/api/workspaces/{wid}/pf/transferencia'",
    }
    for funcion, decorador in rutas.items():
        assert f'  {funcion}: ' in API, funcion
        assert decorador in APP_PY, decorador
    assert '`${ws(id)}/pf/obras/bibliotecas`' in API and "'/api/pf/estudios'" in API


def test_obras_en_un_formulario_sin_libro():
    """011:RF-70 — las obras se escriben una a una en un formulario; no hay libro Excel."""
    assert '<form className="form-grid" onSubmit={anadir}>' in OBRAS
    assert 'FileDrop' not in OBRAS and '.xlsx' not in OBRAS


def test_las_seis_obras_y_solo_sin_y_con_proyecto():
    """011:RF-57, 011:RF-58 — las seis clases de obra, activables en «Sin proyecto» y «Con
    proyecto»; el «Caso base» no se ofrece."""
    for clase in ('condensador', 'reconectador', 'regulador', 'seccion', 'terna', 'tension'):
        assert f"clase: '{clase}'" in OBRAS, clase
    assert "export const CASOS_OBRA = ['Sin proyecto', 'Con proyecto'] as const;" in OBRAS
    assert "'Caso base'" not in OBRAS and "'Caso base'" not in TRANSF


def test_barras_tramos_y_tipos_leidos_de_digsilent():
    """011:RF-88 a 011:RF-91, 011:RF-94 — barras y tramos del alimentador elegido, tipos de la
    clase de la obra de las tres bibliotecas (con otro proyecto opcional) y, junto a cada
    tipo, sus datos y su origen."""
    assert "leido?.alimentadores?.[alimentador]" in OBRAS
    assert "(red?.barras ?? []).map((b) => b.nombre)" in OBRAS
    assert "(red?.tramos ?? [])" in OBRAS
    assert '.filter((t) => t.clase === claseTipo)' in OBRAS
    assert "{t.nombre} · {t.resumen || 'sin datos'} · {ORIGEN[t.origen]}" in OBRAS
    assert "otro_proyecto: otro.trim()" in OBRAS
    assert "global: 'biblioteca global', otro: 'otro proyecto'" in OBRAS


def test_tipo_de_otra_biblioteca_se_copia():
    """011:RF-92, 011:RF-93 — el formulario dice que un tipo de fuera se copia al proyecto, y el
    resultado dice si la copia ya estaba."""
    assert 'se copia al proyecto' in OBRAS
    assert "t.reutiliza ? ' (ya estaba)' : ''" in OBRAS


def test_pasos_del_regulador_a_cada_lado():
    """011:RF-76 — los pasos se piden a cada lado de la toma central (usuario, 2026-10-12)."""
    assert 'Pasos a cada lado de la toma central' in OBRAS


def test_obras_guardadas_se_revisan_quitan_y_simulan():
    """011:RF-95, 011:RF-69 — la lista de obras guardadas, con quitar, simular y aplicar."""
    assert 'const guardadas = ws.obras ?? [];' in OBRAS
    assert 'onClick={() => quitar(o.id)}>Quitar</button>' in OBRAS
    _pos(OBRAS, 'Simular las obras', 'Aplicar las obras')


def test_estudios_no_disponibles_con_lo_que_les_falta():
    """011:RF-24 — los estudios sin datos se listan con su motivo y no se pueden elegir."""
    assert 'catalogo.no_ofrecidos.map((e) =>' in ESTUDIOS
    assert '{e.nombre}</strong>: {e.motivo}' in ESTUDIOS
    assert 'catalogo.ofrecidos.map((e) =>' in ESTUDIOS


def test_limites_del_perfil_que_el_operador_cambia():
    """011:RF-35, 011:RF-39 — los límites salen del perfil y se pueden cambiar; también el
    límite de tiempo de cada estudio."""
    for clave in ('tension_min_pu', 'tension_max_pu', 'cargabilidad_max_pct'):
        assert f"['{clave}'," in ESTUDIOS
    assert 'limites: cambiados' in ESTUDIOS and 'limite_s:' in ESTUDIOS
    assert 'los del perfil de empresa' in ESTUDIOS


def test_transferencia_dos_alimentadores_y_el_caso():
    """011:RF-104, 011:RF-105 — dos alimentadores marcados distintos y el caso, «Sin
    proyecto», «Con proyecto» o los dos; el resultado por sentido."""
    assert "feeders: [uno, otro], casos" in TRANSF
    assert 'uno === otro' in TRANSF and 'CASOS_OBRA.map' in TRANSF
    assert '{s.cede} → {s.recibe}' in TRANSF


def test_guiones_del_operador_en_los_estudios():
    """011:RF-27, 011:RF-28, 011:RF-29 — en 4.2: leer los guiones, sus parámetros y objetos
    para escribir, ejecutar en «Sin proyecto» y «Con proyecto» (solo los casos que tienen el
    guion) y, por caso, su código y su ventana de salida."""
    assert '<GuionesPF project={project} />' in ESTUDIOS
    assert 'api.guiones(ws.id, project)' in GUIONES and 'api.guionEjecutar(ws.id, {' in GUIONES
    assert "@app.post('/api/workspaces/{wid}/pf/guiones'" in APP_PY
    assert "@app.post('/api/workspaces/{wid}/pf/guiones/ejecutar'" in APP_PY
    assert 'guion.parametros.map((p) =>' in GUIONES and 'guion.objetos.map((o) =>' in GUIONES
    assert "CASOS_OBRA.filter((c) => !guion || guion.casos.includes(ROL[c]))" in GUIONES
    assert 'r.salida.join(' in GUIONES and 'código {r.codigo_guion' in GUIONES

