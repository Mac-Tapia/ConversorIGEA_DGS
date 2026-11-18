"""Diagrama unifilar del PIT por alternativa y año, con el flujo de cada línea, en DXF y, si hay convertidor, en DWG
(107:RF-15; formato F-212 de la RCD 217-2013-OS/CD).

Por qué así:

- **El DXF es la entrega garantizada** (aclaración de RF-15): es abierto, lo lee AutoCAD y cualquier programa de CAD,
  y cumple los «ficheros compatibles con AutoCAD». Se escribe con ``ezdxf``, dependencia obligatoria del conversor.
- **El DWG es un añadido**: solo con el ODA File Converter que declare el perfil (``pit.convertidor_dwg``) o que esté
  en el PATH; nunca una ruta fija en el código ni un binario en el repositorio. Si no está o falla, la entrega queda
  completa con el DXF, el aviso dice cómo obtener el DWG y no queda ningún DWG vacío.
- **Lo que pinta, lo que pide la norma.** La 217-2013, art. 37 (pdf pág. 64), Formato F-212: «el diagrama de flujos
  de potencia por cada sistema y alternativa analizada para el año 10. Para la Alternativa seleccionada, dicho
  diagrama se presenta para de los años 1, 5, 10, 15, 20, 25 y 30, indicando el año en el que se incorpora cada nuevo
  Elemento (de preferencia utilizar una convención de colores)», con los transformadores (potencia MVA, relación de
  transformación, Vcc, taps de regulación, P y Q), las líneas (longitud, material y sección del conductor, P y Q),
  las barras (tensión nominal y calculada) y las cargas P y Q (``anios_f212`` y ``COLORES_DE_INGRESO``).
- **Nada se inventa.** Cada cifra sale de la red del área (``RedArea``) y del flujo (``ResultadoFlujo`` del motor);
  lo que falta (los taps, el material, la sección, el flujo de un elemento) se rotula «sin dato» y se avisa.
- **Sin escribir en el expediente.** ``generar`` devuelve la lista de ficheros, los avisos y la relación de sustento
  de cada fichero (descripción y uso), que el expediente lleva a su manifiesto; ``pit/expediente.py`` no cambia aquí.

Cada hoja es un espacio papel A3 (420 × 297 mm) con su marco, su rótulo del F-212 y su leyenda de colores.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ...dominio.pit import PitError
from ...aplicacion.pit.red_area import RedArea

__all__ = ['A3_MM', 'AVISO_SIN_DWG', 'CAPAS', 'COLORES_DE_INGRESO', 'CONVERTIDOR_EN_PATH', 'Hoja', 'ResultadoUnifilar',
           'anios_f212', 'convertidor_dwg', 'generar', 'ingresos_de', 'nombre_de_hoja']

#: Tamaño A3 apaisado, en milímetros, y el margen del marco.
A3_MM = (420.0, 297.0)
MARGEN_MM = 10.0
#: Capas del DXF: un lector las busca por su nombre.
CAPAS = {'marco': 'MARCO', 'rotulo': 'ROTULO', 'leyenda': 'LEYENDA', 'barra': 'BARRAS',
         'trafo': 'TRANSFORMADORES', 'linea': 'LINEAS', 'carga': 'CARGAS', 'red_externa': 'RED_EXTERNA',
         'compensacion': 'COMPENSACION'}
#: Color AutoCAD (ACI) de lo existente: 7 es negro sobre fondo blanco y blanco sobre negro.
COLOR_EXISTENTE = 7
#: Convención de colores del año de ingreso de cada elemento nuevo (F-212: «de preferencia utilizar una convención de
#: colores»): el primer año de ingreso con el primero, el segundo con el segundo… y se repite si hay más años.
COLORES_DE_INGRESO = (1, 3, 5, 6, 30, 4, 2, 140, 210, 41)
#: Los años del F-212: el 10 para todas las alternativas; 1, 5, 10, 15, 20, 25 y 30 para la seleccionada.
_ANIOS_ALTERNATIVA = (10,)
_ANIOS_SELECCIONADA = (1, 5, 10, 15, 20, 25, 30)
#: Nombre del ejecutable del ODA File Converter que se busca en el PATH.
CONVERTIDOR_EN_PATH = 'ODAFileConverter'
_VERSION_DWG = 'ACAD2018'
_PLAZO_CONVERSION_S = 600
AVISO_SIN_DWG = ('el DWG no se generó: {causa}. El DXF entregado es el unifilar completo y lo abre AutoCAD; para el '
                 'DWG, instale el ODA File Converter (gratuito, de la Open Design Alliance) y declare su ejecutable en '
                 'el perfil («pit.convertidor_dwg») o póngalo en el PATH, y vuelva a emitir; o abra el DXF en AutoCAD '
                 'y guárdelo como DWG.')
_PROHIBIDOS_EN_HOJA = re.compile(r'[<>/\\":;?*|=`]')


@dataclass
class Hoja:
    """Una alternativa en un año: su red, el flujo de ese año y la demanda que se puso en cada barra."""
    alternativa: str
    anio: int
    red: RedArea
    #: El resultado del motor (``red_pandapower.ResultadoFlujo`` u otro con ``converge``, ``tensiones_pu``,
    #: ``flujos`` y ``mensaje``).
    flujo: Any
    #: Barra → (P MW, Q Mvar) de la demanda del año.
    cargas: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    #: Elemento nuevo → año de ingreso (``ingresos_de``).
    ingresos: Mapping[str, int] = field(default_factory=dict)


@dataclass
class ResultadoUnifilar:
    #: Rutas relativas a la carpeta del expediente, en formato posix.
    ficheros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    #: Para la relación de sustento del expediente: fichero → descripción y uso.
    sustento: dict[str, dict[str, str]] = field(default_factory=dict)
    hojas: list[dict[str, Any]] = field(default_factory=list)
    dwg: bool = False

    def manifiesto(self) -> dict[str, Any]:
        """Lo que el manifiesto del expediente tiene que llevar del unifilar."""
        return {'formato': 'F-212', 'ficheros': list(self.ficheros), 'dwg': self.dwg, 'avisos': list(self.avisos),
                'hojas': [dict(h) for h in self.hojas]}


def anios_f212(inicio: int, *, seleccionada: bool) -> tuple[int, ...]:
    """Los años calendario del F-212 para un estudio que empieza en ``inicio`` (su año 1)."""
    return tuple(int(inicio) + n - 1 for n in (_ANIOS_SELECCIONADA if seleccionada else _ANIOS_ALTERNATIVA))


def ingresos_de(cambios: Iterable[Mapping[str, Any]]) -> tuple[dict[str, int], list[str]]:
    """Elemento → año de ingreso de las altas y reemplazos de una alternativa, y los avisos de las que no lo dicen.

    Acepta el cambio de ``alternativas`` (``elemento`` es el dict del elemento) y el de ``programa`` (su id)."""
    ingresos, avisos = {}, []
    for c in cambios:
        if c.get('accion') not in ('alta', 'reemplazo'):
            continue
        e = c.get('elemento')
        eid = str(e.get('id') if isinstance(e, Mapping) else e)
        anio = c.get('anio')
        if anio in (None, ''):
            avisos.append(f'{eid}: el cambio no dice su año de ingreso; el unifilar no lo rotula')
            continue
        ingresos[eid] = int(anio)
    return ingresos, avisos


def nombre_de_hoja(alternativa: str, anio: int) -> str:
    """El nombre del espacio papel: la alternativa y el año, sin los caracteres que el DXF no admite."""
    return f'{_PROHIBIDOS_EN_HOJA.sub("_", str(alternativa)).strip()} {int(anio)}'[:255]


def convertidor_dwg(perfil: Mapping[str, Any] | None, *,
                    buscar: Callable[[str], str | None] = shutil.which) -> tuple[str | None, str]:
    """El ejecutable del convertidor y de dónde sale: el perfil (``pit.convertidor_dwg``) o el PATH; si no, ``None``
    con la causa."""
    pit = (perfil or {}).get('pit') if isinstance(perfil, Mapping) else None
    declarado = str(((pit or {}) if isinstance(pit, Mapping) else {}).get('convertidor_dwg') or '').strip()
    if declarado:
        if Path(declarado).is_file():
            return declarado, 'perfil'
        return None, f'el convertidor que declara el perfil (pit.convertidor_dwg = {declarado}) no existe'
    en_path = buscar(CONVERTIDOR_EN_PATH)
    if en_path:
        return en_path, 'PATH'
    return None, f'no hay convertidor: el perfil no declara pit.convertidor_dwg y {CONVERTIDOR_EN_PATH} no está en el PATH'


# --------------------------------------------------------------------------- disposición


def _conexiones(red: RedArea) -> list[tuple[str, str, str, dict[str, Any]]]:
    """(tipo, barra de envío, barra de recibo, elemento) de líneas y transformadores; el de tres devanados, dos."""
    out = []
    for e in red.de_tipo('linea'):
        out.append(('linea', e['desde'], e['hasta'], e))
    for e in red.de_tipo('trafo2'):
        out.append(('trafo2', e['hv'], e['lv'], e))
    for e in red.de_tipo('trafo3'):
        out.append(('trafo3', e['hv'], e['mv'], e))
        out.append(('trafo3', e['hv'], e['lv'], e))
    return out


def _niveles(red: RedArea) -> dict[str, tuple[int, int]]:
    """Barra → (nivel, orden): por anchura desde la red externa; lo que no se alcanza, al final."""
    vecinos: dict[str, list[str]] = {b['id']: [] for b in red.de_tipo('barra')}
    for _t, a, b, _e in _conexiones(red):
        vecinos.setdefault(a, []).append(b)
        vecinos.setdefault(b, []).append(a)
    raices = [g['barra'] for g in red.de_tipo('red_externa')] or list(vecinos)[:1]
    nivel: dict[str, int] = {}
    cola = deque()
    for r in raices:
        if r in vecinos and r not in nivel:
            nivel[r] = 0
            cola.append(r)
    while cola:
        x = cola.popleft()
        for y in vecinos[x]:
            if y not in nivel:
                nivel[y] = nivel[x] + 1
                cola.append(y)
    ultimo = max(nivel.values(), default=-1) + 1
    for b in vecinos:
        nivel.setdefault(b, ultimo)
    orden: dict[int, int] = {}
    pos = {}
    for b in vecinos:  # el orden de entrada de la red: determinista
        n = nivel[b]
        pos[b] = (n, orden.get(n, 0))
        orden[n] = orden.get(n, 0) + 1
    return pos


def _num(v: Any, fmt: str) -> str:
    try:
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return 'sin dato'


def _pq(flujos: Mapping[str, Any], eid: str) -> str | None:
    pq = flujos.get(eid)
    if pq is None:
        return None
    return f'P = {float(pq[0]):.2f} MW  Q = {float(pq[1]):.2f} Mvar'


# --------------------------------------------------------------------------- dibujo


def _capas(doc) -> None:
    for nombre in CAPAS.values():
        if nombre not in doc.layers:
            doc.layers.add(nombre, color=COLOR_EXISTENTE)


def _texto(lay, texto: str, x: float, y: float, capa: str, color: int, alto: float = 2.0) -> None:
    lay.add_text(texto, height=alto, dxfattribs={'layer': capa, 'color': color, 'insert': (x, y)})


def _marco_y_rotulo(lay, hoja: Hoja, area: str, sistema: str, ingresos_presentes: list[int]) -> None:
    ancho, alto = A3_MM
    m = MARGEN_MM
    lay.add_lwpolyline([(m, m), (ancho - m, m), (ancho - m, alto - m), (m, alto - m)], close=True,
                       dxfattribs={'layer': CAPAS['marco'], 'color': COLOR_EXISTENTE})
    # Rótulo con los campos de la plantilla del F-212 (pit.formato.F-212, filas 1 a 7).
    x0, y0 = ancho - m - 150.0, m
    lay.add_lwpolyline([(x0, y0), (ancho - m, y0), (ancho - m, y0 + 36.0), (x0, y0 + 36.0)], close=True,
                       dxfattribs={'layer': CAPAS['rotulo'], 'color': COLOR_EXISTENTE})
    filas = ['OSINERGMIN   F-212', 'DIAGRAMA UNIFILAR DE ALTERNATIVAS', f'ÁREA DE DEMANDA: {area}',
             f'SISTEMA ELÉCTRICO: {sistema}', f'ALTERNATIVA : {hoja.alternativa}', f'AÑO : {hoja.anio}']
    for i, f in enumerate(filas):
        _texto(lay, f, x0 + 3.0, y0 + 31.0 - i * 5.5, CAPAS['rotulo'], COLOR_EXISTENTE, 2.5)
    # Leyenda de la convención de colores del año de ingreso.
    xl, yl = m + 5.0, m + 5.0
    _texto(lay, 'Existente', xl, yl, CAPAS['leyenda'], COLOR_EXISTENTE)
    for i, anio in enumerate(ingresos_presentes):
        _texto(lay, f'Ingresa en {anio}', xl + 40.0 * ((i + 1) % 5), yl + 5.0 * ((i + 1) // 5), CAPAS['leyenda'],
               _color(anio, ingresos_presentes))


def _color(anio: int | None, ingresos_presentes: Sequence[int]) -> int:
    if anio is None:
        return COLOR_EXISTENTE
    return COLORES_DE_INGRESO[list(ingresos_presentes).index(anio) % len(COLORES_DE_INGRESO)]


def _dibujar(lay, hoja: Hoja, area: str, sistema: str, ingresos_presentes: list[int]) -> list[str]:
    """Pinta la hoja y devuelve sus avisos."""
    avisos: list[str] = []
    red, flujo = hoja.red, hoja.flujo
    etiqueta = f'{hoja.alternativa}, año {hoja.anio}'
    converge = bool(getattr(flujo, 'converge', False))
    tensiones = dict(getattr(flujo, 'tensiones_pu', {}) or {}) if converge else {}
    flujos = dict(getattr(flujo, 'flujos', {}) or {}) if converge else {}
    if not converge:
        avisos.append(f'{etiqueta}: el flujo no converge ({getattr(flujo, "mensaje", "") or "sin mensaje"}); '
                      'el unifilar va sin flujos ni tensiones calculadas')
    _marco_y_rotulo(lay, hoja, area, sistema, ingresos_presentes)

    def color_de(eid: str) -> int:
        anio = hoja.ingresos.get(eid)
        if anio is not None and anio > hoja.anio:
            avisos.append(f'{etiqueta}: {eid} ingresa en {anio}, después del año de la hoja')
        return _color(anio, ingresos_presentes)

    def rotulo_ingreso(eid: str) -> list[str]:
        return [f'Ingresa en {hoja.ingresos[eid]}'] if eid in hoja.ingresos else []

    pos = _niveles(red)
    n_niveles = max((n for n, _o in pos.values()), default=0) + 1
    por_nivel: dict[int, int] = {}
    for n, _o in pos.values():
        por_nivel[n] = por_nivel.get(n, 0) + 1
    ancho, alto = A3_MM
    x_min, x_max = MARGEN_MM + 15.0, ancho - MARGEN_MM - 15.0
    y_max, y_min = alto - MARGEN_MM - 20.0, MARGEN_MM + 50.0
    paso_y = (y_max - y_min) / max(n_niveles - 1, 1)
    largo = 30.0
    coord: dict[str, tuple[float, float]] = {}
    for b, (n, o) in pos.items():
        paso_x = (x_max - x_min) / por_nivel[n]
        coord[b] = (x_min + paso_x * (o + 0.5), y_max - paso_y * n)
    for b in red.de_tipo('barra'):
        x, y = coord[b['id']]
        c = color_de(b['id'])
        lay.add_lwpolyline([(x - largo / 2, y), (x + largo / 2, y)],
                           dxfattribs={'layer': CAPAS['barra'], 'color': c, 'const_width': 0.8})
        v = tensiones.get(b['id'])
        calc = f'{v * float(b["kv"]):.2f} kV ({v:.4f} pu)' if v is not None else 'sin dato'
        if v is None and converge:
            avisos.append(f'{etiqueta}: la barra {b["id"]} queda sin tensión calculada')
        lineas = [b['id'], f'Vn = {_num(b["kv"], ".1f")} kV', f'V calc. = {calc}', *rotulo_ingreso(b['id'])]
        for i, t in enumerate(lineas):
            _texto(lay, t, x + largo / 2 + 1.0, y + 1.0 - i * 2.6, CAPAS['barra'], c, 1.8)
    for g in red.de_tipo('red_externa'):
        x, y = coord[g['barra']]
        lay.add_lwpolyline([(x - 4, y + 6), (x + 4, y + 6), (x + 4, y + 14), (x - 4, y + 14)], close=True,
                           dxfattribs={'layer': CAPAS['red_externa'], 'color': COLOR_EXISTENTE})
        lay.add_line((x, y), (x, y + 6), dxfattribs={'layer': CAPAS['red_externa'], 'color': COLOR_EXISTENTE})
        _texto(lay, f'{g["id"]}  {_num(g["vm_pu"], ".3f")} pu', x + 5, y + 9, CAPAS['red_externa'], COLOR_EXISTENTE,
               1.8)
    hechos: set[str] = set()
    for tipo, a, b, e in _conexiones(red):
        (xa, ya), (xb, yb) = coord[a], coord[b]
        eid = e['id']
        c = color_de(eid)
        pq = _pq(flujos, eid)
        if pq is None and converge and eid not in hechos:
            avisos.append(f'{etiqueta}: {eid} sin flujo calculado')
        flujo_txt = pq or 'P y Q: sin dato'
        xm, ym = (xa + xb) / 2, (ya + yb) / 2
        if tipo == 'linea':
            lay.add_line((xa, ya), (xb, yb), dxfattribs={'layer': CAPAS['linea'], 'color': c})
            faltan = [k for k in ('material', 'seccion_mm2') if e.get(k) in (None, '')]
            if faltan:
                avisos.append(f'{etiqueta}: la línea {eid} no trae {", ".join(faltan)}; se rotula «sin dato»')
            sec = f'{_num(e.get("seccion_mm2"), ".0f")} mm2' if e.get('seccion_mm2') not in (None, '') else 'sin dato'
            textos = [eid, f'{_num(e["longitud_km"], ".2f")} km', f'{e.get("material") or "sin dato"} {sec}',
                      flujo_txt, *rotulo_ingreso(eid)]
            capa = CAPAS['linea']
        else:
            r = 3.0
            lay.add_line((xa, ya), (xm, ym + r), dxfattribs={'layer': CAPAS['trafo'], 'color': c})
            lay.add_line((xm, ym - r), (xb, yb), dxfattribs={'layer': CAPAS['trafo'], 'color': c})
            lay.add_circle((xm, ym + r * 0.6), r, dxfattribs={'layer': CAPAS['trafo'], 'color': c})
            lay.add_circle((xm, ym - r * 0.6), r, dxfattribs={'layer': CAPAS['trafo'], 'color': c})
            if eid in hechos:
                continue  # el de tres devanados se rotula una vez
            if tipo == 'trafo3':
                mva = '/'.join(_num(e[k], '.1f') for k in ('sn_hv_mva', 'sn_mv_mva', 'sn_lv_mva'))
                rel = '/'.join(_num(e[k], '.1f') for k in ('vn_hv_kv', 'vn_mv_kv', 'vn_lv_kv'))
                vcc = '/'.join(_num(e[k], '.2f') for k in ('vk_hv_percent', 'vk_mv_percent', 'vk_lv_percent'))
            else:
                mva, rel = _num(e['sn_mva'], '.1f'), f'{_num(e["vn_hv_kv"], ".1f")}/{_num(e["vn_lv_kv"], ".1f")}'
                vcc = _num(e['vk_percent'], '.2f')
            taps = _taps(e)
            if taps == 'sin dato':
                avisos.append(f'{etiqueta}: el transformador {eid} no trae sus taps de regulación; se rotula «sin dato»')
            textos = [eid, f'{mva} MVA', f'{rel} kV', f'Vcc = {vcc} %', f'Taps: {taps}', flujo_txt,
                      *rotulo_ingreso(eid)]
            capa = CAPAS['trafo']
        hechos.add(eid)
        for i, t in enumerate(textos):
            _texto(lay, t, xm + 5.0, ym + 4.0 - i * 2.6, capa, c, 1.8)
    for e in red.de_tipo('compensacion'):
        x, y = coord[e['barra']]
        c = color_de(e['id'])
        lay.add_line((x - 8, y), (x - 8, y - 6), dxfattribs={'layer': CAPAS['compensacion'], 'color': c})
        _texto(lay, f'{e["id"]}  {_num(e["q_mvar"], ".2f")} Mvar', x - 20, y - 9, CAPAS['compensacion'], c, 1.8)
    for barra, (p, q) in sorted(hoja.cargas.items()):
        if barra not in coord:
            avisos.append(f'{etiqueta}: la carga va a la barra {barra}, que no está en la red')
            continue
        x, y = coord[barra]
        lay.add_line((x + 8, y), (x + 8, y - 7), dxfattribs={'layer': CAPAS['carga'], 'color': COLOR_EXISTENTE})
        lay.add_solid([(x + 6.5, y - 7), (x + 9.5, y - 7), (x + 8, y - 10)],
                      dxfattribs={'layer': CAPAS['carga'], 'color': COLOR_EXISTENTE})
        _texto(lay, f'Carga {barra}: P = {float(p):.2f} MW  Q = {float(q):.2f} Mvar', x + 10, y - 9,
               CAPAS['carga'], COLOR_EXISTENTE, 1.8)
    return list(dict.fromkeys(avisos))


def _taps(e: Mapping[str, Any]) -> str:
    if all(e.get(k) not in (None, '') for k in ('tap_min', 'tap_max')):
        paso = f', paso {_num(e["tap_paso_percent"], ".2f")} %' if e.get('tap_paso_percent') not in (None, '') else ''
        return f'{_num(e["tap_min"], ".0f")} a {_num(e["tap_max"], ".0f")}{paso}'
    return 'sin dato'


# --------------------------------------------------------------------------- DWG


def _a_dwg(dxf: Path, exe: str, ejecutar: Callable[..., Any]) -> tuple[Path | None, str]:
    """Convierte con el ODA File Converter en carpetas temporales fuera del expediente; solo deja el DWG si no está
    vacío."""
    with tempfile.TemporaryDirectory(prefix='csg_dwg_') as tmp:
        entrada, salida = Path(tmp) / 'dxf', Path(tmp) / 'dwg'
        entrada.mkdir()
        salida.mkdir()
        shutil.copy2(dxf, entrada / dxf.name)
        orden = [exe, str(entrada), str(salida), _VERSION_DWG, 'DWG', '0', '1', '*.DXF']
        try:
            r = ejecutar(orden, capture_output=True, text=True, timeout=_PLAZO_CONVERSION_S, check=False)
        except subprocess.TimeoutExpired:
            return None, f'el convertidor no terminó en {_PLAZO_CONVERSION_S} s'
        except OSError as exc:
            return None, f'el convertidor no arrancó ({exc})'
        if getattr(r, 'returncode', 1) != 0:
            detalle = (str(getattr(r, 'stderr', '') or getattr(r, 'stdout', '') or '').strip()[:200])
            return None, f'el convertidor terminó con código {r.returncode}' + (f': {detalle}' if detalle else '')
        hecho = next((p for p in salida.iterdir() if p.suffix.lower() == '.dwg'), None)
        if hecho is None or hecho.stat().st_size == 0:
            return None, 'el convertidor no dejó un DWG con contenido'
        destino = dxf.with_suffix('.dwg')
        shutil.copy2(hecho, destino)
        return destino, ''


# --------------------------------------------------------------------------- entrada


def generar(carpeta: Path | str, hojas: Sequence[Hoja], *, area: str, sistema: str,
            perfil: Mapping[str, Any] | None = None, subcarpeta: str = 'unifilar', nombre: str = 'F-212_unifilar',
            buscar: Callable[[str], str | None] = shutil.which,
            ejecutar: Callable[..., Any] = subprocess.run) -> ResultadoUnifilar:
    """Escribe el unifilar (un espacio papel A3 por alternativa y año) en ``carpeta/subcarpeta`` y, si hay
    convertidor, su DWG. Devuelve lo que lleva el manifiesto del expediente."""
    import ezdxf  # dependencia obligatoria (107:RF-15)

    if not hojas:
        raise PitError('el unifilar necesita al menos una alternativa y un año (107:RF-15)')
    vistas = set()
    for h in hojas:
        clave = nombre_de_hoja(h.alternativa, h.anio)
        if clave in vistas:
            raise PitError(f'la hoja «{clave}» está dos veces: una por alternativa y año')
        vistas.add(clave)
    carpeta = Path(carpeta)
    destino = carpeta / subcarpeta
    destino.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.new('R2018', setup=True, units=4)  # milímetros
    _capas(doc)
    res = ResultadoUnifilar()
    ingresos_presentes = sorted({a for h in hojas for a in h.ingresos.values()})
    for h in hojas:
        clave = nombre_de_hoja(h.alternativa, h.anio)
        lay = doc.layouts.new(clave)
        lay.page_setup(size=A3_MM, margins=(0, 0, 0, 0), units='mm')
        res.avisos += _dibujar(lay, h, area, sistema, ingresos_presentes)
        res.hojas.append({'hoja': clave, 'alternativa': h.alternativa, 'anio': int(h.anio)})
    if 'Layout1' in doc.layouts and len(doc.layouts) > 2:
        doc.layouts.delete('Layout1')  # la hoja vacía que crea ezdxf
    dxf = destino / f'{nombre}.dxf'
    doc.saveas(dxf)
    rel = dxf.relative_to(carpeta).as_posix()
    res.ficheros.append(rel)
    res.sustento[rel] = {'descripcion': f'Diagrama unifilar F-212 en DXF: {len(hojas)} hojas A3, una por alternativa '
                                        'y año, con el flujo de potencia de cada línea y transformador',
                         'uso': 'formato F-212 del expediente (107:RF-15); lo abre AutoCAD y cualquier programa de CAD'}
    exe, causa = convertidor_dwg(perfil, buscar=buscar)
    if exe is not None:
        dwg, causa = _a_dwg(dxf, exe, ejecutar)
        if dwg is not None:
            rel_dwg = dwg.relative_to(carpeta).as_posix()
            res.ficheros.append(rel_dwg)
            res.sustento[rel_dwg] = {'descripcion': 'El mismo unifilar F-212 en DWG, convertido del DXF con el ODA '
                                                    'File Converter',
                                     'uso': 'formato F-212 del expediente en el formato nativo de AutoCAD (107:RF-15)'}
            res.dwg = True
    if not res.dwg:
        sobra = dxf.with_suffix('.dwg')
        if sobra.exists():
            sobra.unlink()  # de una emisión anterior: no queda un DWG que no corresponde a este DXF
        res.avisos.append(AVISO_SIN_DWG.format(causa=causa))
    return res
