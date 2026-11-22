"""Contrato neutro de la red de transmisión de un área (``RedArea``) y su lector del libro de la red (107:RF-2, RF-4,
RF-12).

Por qué un contrato propio. La red unida de MT y ``oraculo.red_pandapower`` modelan una red externa por barra de SET:
no traen las líneas de 60 kV o más ni los transformadores de potencia con sus parámetros. El PIT necesita esa red, la
llene el proyecto de transmisión de DIgSILENT (``tools/pit_pf.py --exportar-red``) o un libro declarado en el perfil.

Lo que no tiene sus parámetros no se modela con un valor supuesto: queda en ``faltantes`` con el dato que le falta, y
la red no se da por completa (107:RF-4). Cada elemento modelado lleva su titular, su área y su fuente.

El libro de la red se lee en cualquier formato (``.xlsx``, ``.xlsm``, ``.xls``, ``.xlsb``) con el lector común
(``demanda_medida.abrir_libro``) y en todas sus hojas, o solo en las que declare el perfil (107:RF-12).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..demanda_medida import abrir_libro, filas_de_hoja
from ..libros_por_anio import DemandaError
from ...dominio.pit import PitError
from ...dominio.pit.ambito import Ambito

__all__ = ['REQUERIDOS', 'LibroRed', 'RedArea', 'desde_ambito', 'leer_libro_red']

#: Lo que cada tipo de elemento necesita para entrar en el cálculo; las barras a las que se conecta, aparte.
REQUERIDOS: dict[str, tuple[str, ...]] = {
    'barra': ('kv',),
    'red_externa': ('barra', 'vm_pu'),
    'linea': ('desde', 'hasta', 'longitud_km', 'r_ohm_per_km', 'x_ohm_per_km', 'c_nf_per_km', 'max_i_ka'),
    'trafo2': ('hv', 'lv', 'sn_mva', 'vn_hv_kv', 'vn_lv_kv', 'vk_percent', 'vkr_percent', 'pfe_kw', 'i0_percent'),
    'trafo3': ('hv', 'mv', 'lv', 'sn_hv_mva', 'sn_mv_mva', 'sn_lv_mva', 'vn_hv_kv', 'vn_mv_kv', 'vn_lv_kv',
               'vk_hv_percent', 'vk_mv_percent', 'vk_lv_percent', 'vkr_hv_percent', 'vkr_mv_percent',
               'vkr_lv_percent', 'pfe_kw', 'i0_percent'),
    'compensacion': ('barra', 'q_mvar'),
    'celda': (),
    # 107:RF-25: el acoplamiento de barras de una subestación (``ElmCoup`` de DIgSILENT) con su estado; cerrado, sus
    # dos barras son una en el flujo. Sin estado no se supone cerrado ni abierto: queda en faltantes.
    'union': ('desde', 'hasta', 'cerrado'),
    # 107:RF-26: una rama serie entre dos barras (condensador serie ``ElmScap`` o reactancia serie ``ElmSind`` de
    # DIgSILENT), con su resistencia y su reactancia en ohmios; la de un condensador, negativa.
    'serie': ('desde', 'hasta', 'r_ohm', 'x_ohm'),
}
_BARRAS = {'red_externa': ('barra',), 'linea': ('desde', 'hasta'), 'trafo2': ('hv', 'lv'),
           'trafo3': ('hv', 'mv', 'lv'), 'compensacion': ('barra',), 'union': ('desde', 'hasta'),
           'serie': ('desde', 'hasta')}
_TEXTO = {'id', 'tipo', 'set', 'rol', 'titular', 'desde', 'hasta', 'hv', 'mv', 'lv', 'barra', 'funcion', 'areas'}
#: Las claves del contrato: el encabezado de cada columna cuando el perfil no declara ``columnas``.
_CONTRATO = _TEXTO | {k for claves in REQUERIDOS.values() for k in claves}
#: Columnas que el diagnóstico de tensión usa si están (107 T7, PIT-TEN): la entrega de suministro y el tipo de red de
#: cada barra, su tensión de operación del COES y las tomas de cada transformador. Sin ``columnas`` declaradas se toman
#: cuando el libro las trae; su ausencia no es un error del libro: es un hueco nombrado por barra en el diagnóstico.
#: ``tipo_barra`` (SL, PV o PQ, el ``bustp`` de DIgSILENT) dice qué red externa es la referencia del flujo cuando la
#: red trae más de una (``red_pandapower.referencias``, 107:RF-3).
OPCIONALES_TEXTO = frozenset({'entrega', 'tipo_red', 'tap_side', 'tipo_barra'})
#: ``p_mw`` (con ``q_mvar``) es la consigna de una red externa PQ o PV que no es la referencia: entra como inyección
#: (107:RF-25).
OPCIONALES = OPCIONALES_TEXTO | {'tap_min', 'tap_max', 'tap_neutral', 'tap_step_percent', 'tension_operacion_kv',
                                 'p_mw'}
#: Filas en las que se busca la cabecera de cada hoja, como ``costos_fuentes._FILAS_CABECERA``.
_FILAS_CABECERA = 30


@dataclass
class RedArea:
    area: str
    #: Por tipo, los elementos que se pueden calcular, en el orden de entrada.
    elementos: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    #: ``{'id', 'tipo', 'falta': [...]}`` de lo que no se modela.
    faltantes: list[dict[str, Any]] = field(default_factory=list)
    #: Modelados, pero sin diagnóstico completo (compartidos sin asignar).
    incompletos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def completa(self) -> bool:
        return not self.faltantes and not self.incompletos

    def ids(self) -> set[str]:
        return {e['id'] for lista in self.elementos.values() for e in lista}

    def de_tipo(self, tipo: str) -> list[dict[str, Any]]:
        return self.elementos.get(tipo, [])

    def barras_de_carga(self) -> dict[str, str]:
        """SET → barra que recibe su demanda (la barra con ``rol='carga'``)."""
        return {str(b['set']): b['id'] for b in self.de_tipo('barra') if b.get('rol') == 'carga' and b.get('set')}


def desde_ambito(ambito: Ambito, fuente: Mapping[str, Any] | None = None) -> RedArea:
    """De los elementos del ámbito a la red: lo que no tiene sus datos o sus barras queda en ``faltantes``."""
    red = RedArea(ambito.area.codigo, incompletos=list(ambito.compartidos_sin_asignar), avisos=list(ambito.avisos))
    candidatos = []
    for e in ambito.elementos:
        tipo = str(e.get('tipo') or '')
        if tipo not in REQUERIDOS:
            red.faltantes.append({'id': e.get('id'), 'tipo': tipo, 'falta': [f'tipo «{tipo}» desconocido']})
            continue
        falta = [k for k in REQUERIDOS[tipo] if e.get(k) in (None, '')]
        if not str(e.get('titular') or '').strip():
            falta.append('titular')
        if falta:
            red.faltantes.append({'id': e.get('id'), 'tipo': tipo, 'falta': falta})
            continue
        candidatos.append(e)
    barras = {e['id'] for e in candidatos if e['tipo'] == 'barra'}
    for e in candidatos:
        sueltas = [f'barra {e[k]} fuera del ámbito' for k in _BARRAS.get(e['tipo'], ()) if e[k] not in barras]
        if sueltas:
            red.faltantes.append({'id': e['id'], 'tipo': e['tipo'], 'falta': sueltas})
            continue
        datos = {**e, 'area': ambito.area.codigo, 'fuente': dict(e.get('fuente') or fuente or {})}
        red.elementos.setdefault(e['tipo'], []).append(datos)
    return red


def _valor(clave: str, v: Any) -> Any:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if clave == 'areas':
        return [x.strip() for x in str(v).split(',') if x.strip()]
    if clave in _TEXTO or clave in OPCIONALES_TEXTO:
        if isinstance(v, float) and v.is_integer():
            v = int(v)  # calamine da 10.0 donde la celda dice 10: el código sigue siendo «10»
        return str(v).strip()
    try:
        return float(str(v).replace(',', '.')) if isinstance(v, str) else float(v)
    except ValueError:
        raise PitError(f'la columna de «{clave}» tiene {v!r}, que no es un número') from None


class LibroRed(list):
    """Los elementos leídos del libro de la red (una lista), con las hojas que se tomaron y los avisos (107:RF-12)."""

    def __init__(self, elementos: Iterable[dict[str, Any]] = (), *, hojas: Iterable[str] = (),
                 avisos: Iterable[str] = ()) -> None:
        super().__init__(elementos)
        self.hojas: list[str] = list(hojas)
        self.avisos: list[str] = list(avisos)


def _texto(v: Any) -> str:
    return '' if v is None else str(v).strip()


def _cabecera(filas: list[list[Any]], nombres: Mapping[str, str], fila: int) -> tuple[int, list[str]] | None:
    """La fila de cabecera: la declarada (desde 1) o, por contenido, la de las ``_FILAS_CABECERA`` primeras que trae
    las columnas ``id`` y ``tipo`` y más columnas declaradas."""
    if fila:
        return (fila - 1, [_texto(v) for v in filas[fila - 1]]) if fila <= len(filas) else None
    mejor: tuple[int, int, list[str]] | None = None
    for i, f in enumerate(filas[:_FILAS_CABECERA]):
        cab = [_texto(v) for v in f]
        if nombres['id'] in cab and nombres['tipo'] in cab:
            n = sum(1 for v in nombres.values() if v in cab)
            if mejor is None or n > mejor[0]:
                mejor = (n, i, cab)
    return (mejor[1], mejor[2]) if mejor else None


def _vistas(filas: list[list[Any]]) -> list[str]:
    """Lo que la hoja trae como cabecera (la fila de texto más llena de las primeras), para nombrarlo en el error."""
    mejor: list[str] = []
    for f in filas[:_FILAS_CABECERA]:
        cab = [_texto(v) for v in f if _texto(v)]
        if len(cab) > len(mejor):
            mejor = cab
    return mejor


def leer_libro_red(ruta: Path | str, cfg: Mapping[str, Any]) -> LibroRed:
    """Los elementos de la red del libro que declara el perfil (``pit.libro_red``), con su libro, hoja, fila y huella.

    El libro puede ser ``.xlsx``, ``.xlsm``, ``.xls`` o ``.xlsb``: lo abre el lector común
    (``demanda_medida.abrir_libro``, python-calamine). ``cfg``:

    - ``hoja``: una hoja (se respeta, y lo que le falte es un error), una lista de hojas o nada (se recorren todas).
      Al recorrer, se toman las hojas con las columnas del contrato y cada una que no las tiene queda en ``avisos``.
    - ``fila_cabecera`` (desde 1): opcional; sin ella, la cabecera se busca por contenido en las primeras filas.
    - ``columnas``: clave del contrato → encabezado del libro; sin ellas, el encabezado es la propia clave.

    Si ninguna hoja casa, ``PitError`` con las hojas y las cabeceras que trae el libro (107:RF-12).
    """
    ruta = Path(ruta)
    try:
        libro = abrir_libro(ruta)
    except DemandaError as exc:
        raise PitError(f'el libro de la red no se puede leer: {exc}') from None
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    declaradas = cfg.get('columnas') or {k: k for k in sorted(_CONTRATO)}
    nombres = {k: _texto(v) for k, v in declaradas.items() if _texto(v)}
    for clave in ('id', 'tipo'):
        if clave not in nombres:
            raise PitError(f'pit.libro_red.columnas.{clave}: sin esa columna no se sabe qué elemento es cada fila')
    hojas = list(libro.sheet_names)
    pedida = cfg.get('hoja')
    estricta = isinstance(pedida, str) and bool(pedida.strip())
    if estricta:
        recorrer = [pedida.strip()]
    elif pedida:
        recorrer = [_texto(h) for h in pedida]
    else:
        recorrer = hojas
    ausentes = [h for h in recorrer if h not in hojas]
    if ausentes:
        raise PitError(f'el libro de la red {ruta.name} no tiene la hoja {", ".join(map(repr, ausentes))} '
                       f'(pit.libro_red.hoja); trae {", ".join(map(repr, hojas)) or "ninguna"}')
    fila_cfg = int(cfg.get('fila_cabecera') or 0)
    out = LibroRed()
    vistas: dict[str, list[str]] = {}
    origen: dict[str, tuple[str, int]] = {}
    for hoja in recorrer:
        try:
            filas = filas_de_hoja(libro, hoja)
        except Exception as exc:  # noqa: BLE001 - calamine da errores propios (p. ej. una hoja de gráfico)
            if estricta:
                raise PitError(f'{ruta.name} / {hoja}: no se pudo leer la hoja ({exc})') from None
            out.avisos.append(f'{ruta.name} / {hoja}: no se pudo leer la hoja ({exc}); no se toma (107:RF-12)')
            continue
        hallada = _cabecera(filas, nombres, fila_cfg)
        if hallada is None and estricta:
            donde = (f'la fila de cabecera {fila_cfg}' if fila_cfg
                     else f'ninguna fila, entre las {_FILAS_CABECERA} primeras,')
            raise PitError(f'la hoja {hoja!r} no llega a {donde} con las columnas «{nombres["id"]}» y '
                           f'«{nombres["tipo"]}» (pit.libro_red)')
        if not estricta and (hallada is None or not {nombres['id'], nombres['tipo']} <= set(hallada[1])):
            vistas[hoja] = _vistas(filas)
            out.avisos.append(f'{ruta.name} / {hoja}: sin las columnas del contrato («{nombres["id"]}» y '
                              f'«{nombres["tipo"]}»); la hoja no se toma (107:RF-12)')
            continue
        i_cab, cab = hallada
        faltan = [k for k, n in nombres.items() if n not in cab]
        if faltan and estricta:
            raise PitError(f'la hoja {hoja!r} no tiene la columna «{nombres[faltan[0]]}» '
                           f'(pit.libro_red.columnas.{faltan[0]})')
        if faltan:
            out.avisos.append(f'{ruta.name} / {hoja}: sin las columnas {", ".join(f"«{nombres[k]}»" for k in faltan)}'
                              '; sus elementos quedan sin esos datos (107:RF-12)')
        columnas = {k: cab.index(n) for k, n in nombres.items() if n in cab}
        if not cfg.get('columnas'):
            columnas.update({k: cab.index(k) for k in sorted(OPCIONALES) if k in cab and k not in columnas})
        out.hojas.append(hoja)
        for n, fila in enumerate(filas[i_cab + 1:], start=i_cab + 2):
            e = {k: _valor(k, fila[j] if j < len(fila) else None) for k, j in columnas.items()}
            if not e.get('id'):
                continue
            if e['id'] in origen:
                h0, n0 = origen[e['id']]
                out.avisos.append(f'{ruta.name} / {hoja}, fila {n}: «{e["id"]}» ya está en la hoja {h0!r}, fila {n0}; '
                                  'se toma la primera (107:RF-12)')
                continue
            origen[e['id']] = (hoja, n)
            e = {k: v for k, v in e.items() if v is not None}
            e['fuente'] = {'libro': ruta.name, 'hoja': hoja, 'fila': n, 'sha256': huella}
            out.append(e)
    if not out.hojas:
        detalle = '; '.join(f'«{h}»: {", ".join(vistas.get(h, [])[:12]) or "sin cabecera"}' for h in recorrer)
        raise PitError(f'el libro de la red {ruta.name} no tiene ninguna hoja con las columnas «{nombres["id"]}» y '
                       f'«{nombres["tipo"]}» (pit.libro_red.columnas); hojas y cabeceras: {detalle or "ninguna hoja"}')
    return out
