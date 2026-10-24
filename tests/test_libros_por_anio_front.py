"""Spec 025 en la interfaz: año de las mediciones y libros por año (el front no se ejecuta aquí)."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
APP = (RAIZ / 'src' / 'igea_dgs' / 'web' / 'app.py').read_text(encoding='utf-8')
API = (SRC / 'api.ts').read_text(encoding='utf-8')
DEMANDA = (SRC / 'components' / 'DemandaMedida.tsx').read_text(encoding='utf-8')
AJUSTE = (SRC / 'components' / 'AjusteCabecera.tsx').read_text(encoding='utf-8')
CATALOGO = (SRC / 'clientesCatalogo.ts').read_text(encoding='utf-8')


def test_selector_de_anio_sin_elegir_al_entrar():
    """025:RF-22 — el año sale de las carpetas de cabecera y clientes, empieza sin elegir y se
    vacía al cambiar de proyecto o de alimentadores; sin él no se busca la máxima."""
    assert 'cabecera?.anios' in DEMANDA and 'clientes?.anios' in DEMANDA
    assert "const [anio, setAnio] = useState('')" in DEMANDA
    assert "setAnio('')" in DEMANDA
    assert '— elija el año —' in DEMANDA
    assert 'faltaAnio' in DEMANDA and '|| faltaAnio}' in DEMANDA


def test_todo_el_anio_y_solo_sus_meses():
    """025:RF-23 — elegido el año, «Todo <año>» y los meses con libro de ese año solamente."""
    assert 'elegirPeriodo(a)' in DEMANDA and 'Todo {anio}' in DEMANDA
    assert 'estadoCatalogoClientes(ws.demanda?.clientes, periodo, anio)' in DEMANDA
    assert 'startsWith(`${anio}-`)' in CATALOGO
    # Con todo el año, el cruce es por el mes de la máxima de cada uno (025:RF-10).
    assert r'/^\d{4}$/.test(periodo)' in CATALOGO


def test_el_plan_dice_el_anio_y_el_caso():
    """025:RF-24 — el plan del ajuste dice en qué caso se calibra y con qué año."""
    assert 'plan.caso' in AJUSTE and 'plan.anio_medicion' in AJUSTE


ENTRADAS = (SRC / 'components' / 'InputsPanel.tsx').read_text(encoding='utf-8')
INFORMES = (SRC / 'components' / 'InformesPF.tsx').read_text(encoding='utf-8')


def test_un_fichero_asignado_se_reemplaza_sin_quitarlo():
    """025:RF-39 — entradas, libros de demanda y libro de pérdidas: con uno asignado, el
    campo de subida y el de ruta siguen ahí para reemplazarlo."""
    # Antes, ``meta ? (nombre) : (subida)``: con un fichero asignado no había subida.
    assert '{meta ? (' not in ENTRADAS and 'Reemplazar: soltar otro fichero' in ENTRADAS
    assert 'reemplazarlo por una ruta de este equipo' in ENTRADAS
    libro = DEMANDA[DEMANDA.index('function Libro('):DEMANDA.index('function LibrosPorAnio')]
    assert "{meta ? 'Reemplazar: soltar' : 'Soltar'}" in libro and '(reemplaza la actual)' in libro
    assert '{libro ? <>' not in INFORMES and "{libro ? 'Reemplazar: soltar' : 'Soltar'}" in INFORMES


def test_los_campos_solo_se_bloquean_con_un_trabajo_y_lo_dicen():
    """025:RF-40 — desactivados solo mientras corre un trabajo que los invalidaría, y con el
    motivo a la vista."""
    assert 'disabled={locked || uploading !== null}' in ENTRADAS
    assert 'Mientras corre la conversión o la carga, las entradas no se cambian.' in ENTRADAS
    libro = DEMANDA[DEMANDA.index('function Libro('):DEMANDA.index('function LibrosPorAnio')]
    assert 'disabled={engineBusy}' in libro
    assert 'al terminar se pueden cambiar los libros' in libro


def test_libros_por_anio_con_su_estado_y_donde_dejar_uno_nuevo():
    """025:RF-34, 025:RF-35 — cabecera y clientes por año, con ruta, meses, qué traen y si se
    usan; y dónde dejar los libros de un año nuevo. El índice de cabecera es un trabajo."""
    assert 'function LibrosPorAnio' in DEMANDA
    for columna in ('<th>Año</th>', '<th>Libro</th>', '<th>Meses</th>', '<th>Qué trae</th>', '<th>Estado</th>'):
        assert columna in DEMANDA, columna
    assert '/AAAA/' in DEMANDA and 'Actualizar índice' in DEMANDA
    assert 'demandaCabeceraIndexar' in API and '/demanda/cabecera/indexar' in API
    assert "'/api/workspaces/{wid}/demanda/cabecera/indexar'" in APP


CARGAS = (SRC / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')


def test_la_escalera_se_pide_desde_el_informe_de_cargas():
    """025:RF-43, 025:RF-44 — si «Con proyecto <año>» no converge con sus cargas nuevas, el
    informe de cargas dice cuáles y ofrece la escalera en los casos de ese año, como trabajo
    de DIgSILENT bloqueado mientras corre otro; su resultado dice el escalón que converge."""
    informe = CARGAS[CARGAS.index('function Informe('):CARGAS.index('function Escalera(')]
    assert 'inf.no_convergen_juntas' in informe and '!simular' in informe
    assert 'Proponer obras en escalera' in informe and 'disabled={ocupado}' in informe
    assert 'anio_casos: resultado.informe.anio_casos ?? null' in CARGAS
    assert 'startJob(() => api.obrasEscalera(' in CARGAS
    assert '/pf/obras/escalera' in API and "'/api/workspaces/{wid}/pf/obras/escalera'" in APP
    assert "j.kind === 'obras_escalera'" in CARGAS and 'converge con «{a.obra}»' in CARGAS

def test_el_informe_de_cargas_dice_el_caso_cargas_nuevas():
    """025:RF-65, 025:RF-66 — el informe de cargas muestra «Cargas nuevas <año>»: con cuántas
    cargas converge y, de cada una que quedó inactiva, con cuál ya no converge y por qué."""
    bloque = CARGAS[CARGAS.index('function CargasNuevasCaso('):CARGAS.index('function Escalera(')]
    assert 'c.no_convergen' in bloque and '{x.texto ?? x.variacion}' in bloque
    assert 'ya no converge' in bloque and '<CargasNuevasCaso c={inf.cargas_nuevas} />' in CARGAS