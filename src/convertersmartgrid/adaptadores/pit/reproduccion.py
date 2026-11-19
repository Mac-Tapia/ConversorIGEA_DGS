"""Reproducción de un cuadro publicado del PIT y cotejo de una muestra por un revisor independiente (107 T15 y T16).

Por qué así (orden del usuario del 2026-11-19): «lo que no puede cerrar debe usar los archivos que descargaste de la
página de Osinergmin del PIT, en los entregables; lo que publique o no Osinergmin u otras entidades no debería ser una
limitación o exigencia para cierre». La aceptación ya no espera «datos autorizados por la empresa»: toma un expediente
PUBLICADO (los formatos de la propuesta de un área que el regulador cuelga en su página), lee sus formatos de entrada y
deja que el conversor calcule, con su propio código, los cuadros que en el expediente se derivan de ellos. Lo que sale se
compara fila por fila y celda por celda con el cuadro publicado, y cada diferencia lleva su causa.

- **Qué se reproduce**: los resúmenes F-119 a F-122 (regulados más libres, por nivel y por barra) con
  ``demanda_resumen.resumen_demanda``, el mismo cálculo que arma el expediente; las entradas son los F-109 a F-112 y
  F-115 a F-118 publicados del mismo libro. Si la nota del formato cambia en otra norma, cambia ``resumen_demanda`` y
  esta comparación lo dirá.
- **Lectura por contenido**: la hoja se busca por su código (el nombre de la hoja o el rótulo de su primera fila), la
  cabecera por sus rótulos (SISTEMA, SUBESTACIÓN, BARRA, TENSIÓN; AÑO y los niveles) y los años por la fila de años
  consecutivos que sigue: ningún área, año ni tensión está en el código (107:RF-11). Las hojas con otro nombre que
  repiten un código («F-110 (SET)») son vistas de trabajo de la empresa y no se leen.
- **Huella**: la referencia publicada entra con el sha256 del libro tal como se descargó, para que la reproducción no
  se confunda con la de otra versión del expediente (memoria «ficheros reemplazables por periodo»).
- **Cotejo independiente (T16)**: el acta la escribe un revisor distinto del implementador, que lee las celdas del libro
  publicado por su cuenta; ``cotejar`` comprueba que cada celda de su muestra existe en la reproducción, recalcula la
  diferencia con el valor del conversor y la convierte en observaciones de la vía de T11 (``observaciones.registrar``),
  enlazadas con la traza de la celda. Un acta sin origen declarado o firmada por el propio implementador se rechaza.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ...aplicacion.demanda_medida import abrir_libro, filas_de_hoja
from ...dominio.pit import PitError
from ...dominio.pit.observaciones import Observacion, escribir_observaciones, registrar
from ...dominio.util import publicar_duradero
from ...dominio.registro_normativo import RegistroNormativo
from .demanda_resumen import resumen_demanda

__all__ = ['ORIGEN_REVISOR', 'REGULADOS', 'LIBRES', 'RESUMENES', 'cotejar', 'escribir_en_expediente',
           'leer_formato_publicado', 'reproducir_resumenes']

#: Los formatos de entrada de los resúmenes y su magnitud (la que lee ``resumen_demanda``).
REGULADOS = {'F-109': 'energia_mwh', 'F-110': 'potencia_mw', 'F-111': 'potencia_mw', 'F-112': 'potencia_mw'}
LIBRES = {'F-115': 'energia_mwh', 'F-116': 'potencia_mw', 'F-117': 'potencia_mw', 'F-118': 'potencia_mw'}
#: Los cuadros reproducidos y de qué formatos salen (la nota de cada plantilla).
RESUMENES = {'F-119': ('F-109', 'F-115'), 'F-120': ('F-110', 'F-116'), 'F-121': ('F-111', 'F-117'),
             'F-122': ('F-112', 'F-118')}
#: Origen que debe declarar el acta del cotejo (memoria «maestro hace de humano»: el origen nunca se calla).
ORIGEN_REVISOR = 'maestro/revisor independiente'
#: Igualdad de dos cifras: la del libro sale de sumas de Excel en otro orden; más allá de esto es una diferencia.
TOLERANCIA_REL = 1e-9
TOLERANCIA_ABS = 1e-9
_NIVELES_F119 = ('mat', 'at', 'mt')
_ANIO_MIN, _ANIO_MAX = 1900, 2200
_COLUMNA = re.compile(r'[A-Z]{1,3}')


def _normal(v: Any) -> str:
    texto = unicodedata.normalize('NFKD', str(v or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', re.sub(r'\(.*?\)', ' ', texto)).strip()


def _letra(i: int) -> str:
    """Índice de columna (0 = A) a su letra de Excel."""
    letra = ''
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        letra = chr(ord('A') + r) + letra
    return letra


def _numero(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _hoja_del_codigo(libro: Any, codigo: str, nombre: str) -> str:
    exactas = [h for h in libro.sheet_names if h.strip() == codigo]
    if len(exactas) == 1:
        return exactas[0]
    rotuladas = []
    for h in libro.sheet_names:
        filas = filas_de_hoja(libro, h)[:3]
        if any(str(c).strip() == codigo for f in filas for c in f):
            rotuladas.append(h)
    if len(rotuladas) == 1:
        return rotuladas[0]
    raise PitError(f'{nombre}: {"varias hojas" if rotuladas else "ninguna hoja"} con el código {codigo}'
                   + (f' ({", ".join(rotuladas)})' if rotuladas else '') + '; se busca por el nombre o el rótulo')


def _anios(fila: Sequence[Any]) -> dict[int, int]:
    """Columna → año de una fila de años consecutivos (la de la cabecera de la serie)."""
    anios = {i: int(v) for i, v in enumerate(fila)
             if _numero(v) is not None and float(v).is_integer() and _ANIO_MIN <= v <= _ANIO_MAX}
    valores = list(anios.values())
    if len(valores) < 2 or valores != list(range(valores[0], valores[0] + len(valores))):
        return {}
    return anios


def leer_formato_publicado(ruta: Path | str, codigo: str) -> dict[str, Any]:
    """Las filas de un formato publicado del PIT con su fila de Excel y la huella del libro.

    Formatos por barra (F-109 a F-122 salvo el F-119): cada fila con ``sistema``, ``set``, ``barra``, ``tension_kv``,
    ``usuario`` (si la plantilla lo trae) y ``serie`` (un valor por año de la cabecera), más ``fila`` y ``columnas``
    (año → letra). El F-119 y los de su forma (AÑO y una columna por nivel) dan ``anio`` y una clave por nivel.
    """
    ruta = Path(ruta)
    libro = abrir_libro(ruta)
    hoja = _hoja_del_codigo(libro, codigo, ruta.name)
    filas = filas_de_hoja(libro, hoja)
    base = {'codigo': codigo, 'hoja': hoja, 'libro': ruta.name,
            'sha256': hashlib.sha256(ruta.read_bytes()).hexdigest()}
    for n, f in enumerate(filas):
        rotulos = [_normal(c) for c in f]
        if 'BARRA' in rotulos and 'SISTEMA' in rotulos:
            return {**base, **_por_barra(filas, n, rotulos, ruta.name, codigo)}
        if 'TOTAL' in rotulos and any(r in ('ANO', 'ANIO') for r in rotulos):
            return {**base, **_por_nivel(filas, n, rotulos, ruta.name, codigo)}
    raise PitError(f'{ruta.name}, hoja {hoja}: sin la cabecera del formato (SISTEMA y BARRA, o AÑO y TOTAL)')


def _fin_de_datos(f: Sequence[Any]) -> bool:
    primera = next((str(c).strip() for c in f if str(c or '').strip()), '')
    return primera.startswith('(')


def _por_barra(filas: list[list[Any]], n: int, rotulos: list[str], nombre: str, codigo: str) -> dict[str, Any]:
    col = {}
    for i, r in enumerate(rotulos):
        for campo, prefijo in (('sistema', 'SISTEMA'), ('set', 'SUBESTACION'), ('barra', 'BARRA'),
                               ('tension_kv', 'TENSION'), ('usuario', 'NOMBRE')):
            if r.startswith(prefijo) and campo not in col:
                col[campo] = i
    faltan = [c for c in ('sistema', 'set', 'barra', 'tension_kv') if c not in col]
    if faltan:
        raise PitError(f'{nombre}, {codigo}: la cabecera no trae {", ".join(faltan)}')
    anios, n_anios = {}, None
    for k in range(n, min(n + 3, len(filas))):
        anios = _anios(filas[k])
        if anios:
            n_anios = k
            break
    if n_anios is None:
        raise PitError(f'{nombre}, {codigo}: sin la fila de años consecutivos bajo la cabecera (fila {n + 1})')
    datos, totales = [], []
    for k in range(n_anios + 1, len(filas)):
        f = filas[k]
        if _fin_de_datos(f):
            break
        texto = {c: str(f[i]).strip() if i < len(f) and f[i] is not None else '' for c, i in col.items()}
        serie = [_numero(f[i]) if i < len(f) else None for i in anios]
        if not any(texto.values()) and all(v is None for v in serie):
            continue
        if 'TOTAL' in _normal(texto['sistema']) or not texto['barra']:
            totales.append({'fila': k + 1, 'rotulo': texto['sistema'] or texto['set']})
            continue
        datos.append({'sistema': texto['sistema'], 'set': texto['set'], 'barra': texto['barra'],
                      'tension_kv': _numero(f[col['tension_kv']]), 'usuario': texto.get('usuario') or None,
                      'serie': serie, 'fila': k + 1})
    return {'forma': 'por_barra', 'anios': list(anios.values()),
            'columnas': {a: _letra(i) for i, a in anios.items()}, 'filas': datos, 'totales': totales}


def _por_nivel(filas: list[list[Any]], n: int, rotulos: list[str], nombre: str, codigo: str) -> dict[str, Any]:
    col = {}
    for i, r in enumerate(rotulos):
        clave = 'anio' if r in ('ANO', 'ANIO') else r.lower()
        if clave in ('anio', 'total', *_NIVELES_F119) and clave not in col:
            col[clave] = i
    faltan = [c for c in ('anio', 'total', *_NIVELES_F119) if c not in col]
    if faltan:
        raise PitError(f'{nombre}, {codigo}: la cabecera no trae {", ".join(faltan)}')
    datos = []
    for k in range(n + 1, len(filas)):
        f = filas[k]
        if _fin_de_datos(f):
            break
        anio = _numero(f[col['anio']]) if col['anio'] < len(f) else None
        if anio is None:
            continue
        datos.append({'anio': int(anio), 'fila': k + 1,
                      **{f'{c}_gwh': _numero(f[i]) if i < len(f) else None for c, i in col.items() if c != 'anio'}})
    return {'forma': 'por_nivel', 'columnas': {c: _letra(i) for c, i in col.items()}, 'filas': datos}


def _clave(f: Mapping[str, Any]) -> tuple[str, str, str, float | None]:
    return (_normal(f.get('sistema')), _normal(f.get('set')), _normal(f.get('barra')), f.get('tension_kv'))


def _iguales(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, rel_tol=TOLERANCIA_REL, abs_tol=TOLERANCIA_ABS)


def _entradas(formatos: Mapping[str, Mapping[str, Any]], codigos: Mapping[str, str]) -> dict[str, list[dict[str, Any]]]:
    return {c: [{'sistema': f['sistema'], 'set': f['set'], 'barra': f['barra'], 'tension_kv': f['tension_kv'],
                 magnitud: f['serie']} for f in formatos[c]['filas']] for c, magnitud in codigos.items()}


def _causa_por_barra(pub: float | None, conv: float | None, regulado: float | None, libre: float | None) -> str:
    """La causa de una diferencia de un resumen por barra, deducida de sus dos entradas publicadas."""
    if pub is None:
        return 'el cuadro publicado deja la celda vacía y las entradas publicadas dan valor'
    if conv is None:
        return 'el conversor no da valor: falta el regulado o el libre de ese año en las entradas publicadas'
    if regulado is not None and _iguales(pub, regulado):
        return 'el publicado lleva solo el regulado: no suma el libre de esa barra'
    if libre is not None and _iguales(pub, libre):
        return 'el publicado lleva solo el libre: no suma el regulado de esa barra'
    return 'el publicado no es la suma de sus entradas publicadas (regulado + libre): cifra propia del expediente'


def reproducir_resumenes(registro: RegistroNormativo, ruta: Path | str, fecha: str | None = None) -> dict[str, Any]:
    """F-119 a F-122 calculados por el conversor desde las entradas publicadas del mismo libro, frente al publicado.

    Devuelve la referencia (libro, sha256), y por cuadro sus celdas comparadas (``celdas``: id «F-xxx!B8», fila y
    columna de Excel, clave, publicado, conversor, diferencia, igual) y sus ``diferencias``, cada una con su causa.
    """
    ruta = Path(ruta)
    formatos = {c: leer_formato_publicado(ruta, c) for c in (*REGULADOS, *LIBRES, *RESUMENES)}
    anios = formatos['F-109']['anios']
    for c in (*REGULADOS, *LIBRES, *(r for r in RESUMENES if r != 'F-119')):
        if formatos[c]['anios'] != anios:
            raise PitError(f'{ruta.name}: {c} trae los años {formatos[c]["anios"][:1]}…, distintos de los del F-109; '
                           'no se suman series de horizontes distintos')
    cadena = {'horizonte': len(anios) - 1, 'filas': _entradas(formatos, REGULADOS)}
    libres = _entradas(formatos, LIBRES)
    resumen = resumen_demanda(registro, cadena, libres, fecha)
    parcial, resto, tensiones = (_f119_parcial(registro, cadena, libres, fecha) if resumen['sin_nivel']
                                 else (None, [0.0] * len(anios), []))
    cuadros = {'F-119': _comparar_f119(formatos['F-119'], resumen, anios, parcial, resto, tensiones)}
    for codigo in ('F-120', 'F-121', 'F-122'):
        regulado, libre = RESUMENES[codigo]
        cuadros[codigo] = _comparar_por_barra(codigo, formatos[codigo], resumen['filas'][codigo], formatos[regulado],
                                              formatos[libre])
    return {'referencia': {'libro': ruta.name, 'sha256': formatos['F-109']['sha256'],
                           'hojas': {c: f['hoja'] for c, f in formatos.items()}},
            'anios': anios, 'calculo': 'demanda_resumen.resumen_demanda', 'sin_nivel': resumen['sin_nivel'],
            'cuadros': cuadros,
            'resumen': {c: {'celdas': len(q['celdas']), 'iguales': sum(x['igual'] for x in q['celdas']),
                            'diferencias': len(q['diferencias']), 'filas_publicadas': q['filas_publicadas'],
                            'filas_reproducidas': q['filas_reproducidas']} for c, q in cuadros.items()}}


def _celda(codigo: str, columna: str, fila: int, clave: Any, pub: float | None, conv: float | None,
           extra: Mapping[str, Any]) -> dict[str, Any]:
    diferencia = conv - pub if pub is not None and conv is not None else None
    return {'id': f'{codigo}!{columna}{fila}', 'cuadro': codigo, 'columna': columna, 'fila': fila, 'clave': clave,
            'publicado': pub, 'conversor': conv, 'diferencia': diferencia, 'igual': _iguales(pub, conv), **extra}


def _sin_nivel(registro: RegistroNormativo, fecha: str | None) -> Any:
    """Si una tensión no está en la regla de niveles regulatorios (num. 12.1.1)."""
    niveles = registro.regla('pit.niveles_tension_kv', fecha).regla.valor
    kvs = [float(v) for lista in niveles.values() for v in lista]
    return lambda kv: not isinstance(kv, (int, float)) or not any(math.isclose(kv, v, rel_tol=1e-3) for v in kvs)


def _f119_parcial(registro: RegistroNormativo, cadena: Mapping[str, Any], libres: Mapping[str, Any],
                  fecha: str | None) -> tuple[list[dict[str, Any]], list[float], list[float]]:
    """El F-119 del conversor solo con las barras que tienen nivel, y la energía (GWh) y las tensiones de las que no.

    Sirve para explicar una diferencia: ``resumen_demanda`` no clasifica por aproximación una tensión que la regla no
    trae, así que con una sola barra así el F-119 entero queda vacío; aquí se ve en qué nivel la sumó el publicado."""
    fuera = _sin_nivel(registro, fecha)
    horizonte = int(cadena['horizonte'])
    resto = [0.0] * (horizonte + 1)
    tensiones: list[float] = []
    filtradas: dict[str, list[Mapping[str, Any]]] = {}
    for codigo, filas in (('F-109', cadena['filas']['F-109']), ('F-115', libres['F-115'])):
        filtradas[codigo] = []
        for f in filas:
            if fuera(f.get('tension_kv')):
                resto = [a + (b or 0.0) / 1000 for a, b in zip(resto, f['energia_mwh'])]
                if f.get('tension_kv') not in tensiones:
                    tensiones.append(f.get('tension_kv'))
            else:
                filtradas[codigo].append(f)
    parcial = resumen_demanda(registro, {**cadena, 'filas': {**cadena['filas'], 'F-109': filtradas['F-109']}},
                              {**libres, 'F-115': filtradas['F-115']}, fecha)
    return parcial['f119'], resto, tensiones


def _comparar_f119(pub: Mapping[str, Any], resumen: Mapping[str, Any], anios: Sequence[int],
                   parcial: Sequence[Mapping[str, Any]] | None, resto: Sequence[float],
                   tensiones: Sequence[float]) -> dict[str, Any]:
    celdas, diferencias = [], []
    por_anio = {f['anio']: f for f in pub['filas']}
    kv = ', '.join(f'{t:g}' for t in tensiones if isinstance(t, (int, float)))
    for i, anio in enumerate(anios):
        f = por_anio.get(anio)
        conv = resumen['f119'][i]
        if f is None:
            diferencias.append({'id': None, 'cuadro': 'F-119', 'clave': anio,
                                'causa': 'el año está en las entradas publicadas y no en el F-119 publicado'})
            continue
        for nivel in (*_NIVELES_F119, 'total'):
            campo = f'{nivel}_gwh'
            sin_ellas = parcial[i][campo] if parcial is not None else None
            c = _celda('F-119', pub['columnas'][nivel], f['fila'], anio, f[campo], conv[campo],
                       {'campo': campo, 'calculo': 'F-109 + F-115 por nivel de la regla pit.niveles_tension_kv',
                        **({'conversor_sin_barras_sin_nivel': sin_ellas} if parcial is not None else {})})
            celdas.append(c)
            if c['igual']:
                continue
            if parcial is not None and _iguales(f[campo], sin_ellas):
                causa = (f'la regla de niveles no clasifica {kv} kV y el conversor no la clasifica por aproximación '
                         '(F-119 vacío); sin esas barras da la cifra publicada: el publicado no las pone en este nivel')
            elif parcial is not None and sin_ellas is not None and _iguales(f[campo], sin_ellas + resto[i]):
                causa = (f'el publicado suma aquí las barras de {kv} kV, que la regla de niveles no trae; el conversor '
                         'no las clasifica por aproximación (F-119 vacío); con ellas en este nivel da la cifra publicada')
            else:
                causa = conv['_motivos'].get(campo) or ('el publicado no es la suma por nivel de sus entradas publicadas: '
                                                        'cifra propia del expediente')
            diferencias.append({**c, 'causa': causa})
    return {'celdas': celdas, 'diferencias': diferencias, 'filas_publicadas': len(pub['filas']),
            'filas_reproducidas': len(anios)}


def _sumar_series(series: Sequence[Sequence[float | None]], n: int) -> list[float | None]:
    total: list[float | None] = [0.0] * n
    for s in series:
        total = [a + b if a is not None and b is not None else None for a, b in zip(total, s)]
    return total


def _comparar_por_barra(codigo: str, pub: Mapping[str, Any], reproducidas: Sequence[Mapping[str, Any]],
                        regulado: Mapping[str, Any], libre: Mapping[str, Any]) -> dict[str, Any]:
    n = len(pub['anios'])
    entrada_reg, entrada_lib = RESUMENES[codigo]
    publicadas: dict[tuple, Mapping[str, Any]] = {}
    sin_sistema: dict[tuple, list[Mapping[str, Any]]] = {}
    for f in pub['filas']:
        publicadas.setdefault(_clave(f), f)
        sin_sistema.setdefault(_clave(f)[1:], []).append(f)
    entradas = [(f, entrada_reg) for f in regulado['filas']] + [(f, entrada_lib) for f in libre['filas']]

    def de(k: tuple, fuente: str) -> list[float | None]:
        return _sumar_series([f['serie'] for f, c in entradas if c == fuente and _clave(f) == k], n)

    def otra_tension(k: tuple) -> list[tuple[Any, list[float | None]]]:
        """Las entradas de la misma SET y barra con otra tensión: (tensión, su serie sumada)."""
        por_kv: dict[Any, list[Sequence[float | None]]] = {}
        for f, _c in entradas:
            kf = _clave(f)
            if kf[1:3] == k[1:3] and kf[3] != k[3]:
                por_kv.setdefault(kf[3], []).append(f['serie'])
        return [(kv, _sumar_series(s, n)) for kv, s in por_kv.items()]

    celdas, diferencias, vistas = [], [], set()
    for r in reproducidas:
        k = _clave(r)
        f = publicadas.get(k)
        if f is None and len(sin_sistema.get(k[1:], ())) == 1:
            f = sin_sistema[k[1:]][0]
            diferencias.append({'id': f'{codigo}!A{f["fila"]}', 'cuadro': codigo, 'clave': list(k),
                                'causa': f'el cuadro publicado pone la barra en el sistema «{f["sistema"]}» y sus '
                                         f'entradas publicadas ({entrada_reg}, {entrada_lib}) en «{r.get("sistema")}»; '
                                         'se compara por SET, barra y tensión'})
        if f is None:
            hermanas = [p for p in pub['filas'] if _clave(p)[1:3] == k[1:3]]
            con_kv = hermanas and isinstance(k[3], (int, float)) and isinstance(hermanas[0]['tension_kv'], (int, float))
            diferencias.append({'id': None, 'cuadro': codigo, 'clave': list(k), 'causa': (
                f'la entrada publicada declara {k[3]:g} kV en la barra {r.get("barra")}; el publicado la suma en su '
                f'fila de {hermanas[0]["tension_kv"]:g} kV (fila {hermanas[0]["fila"]})' if con_kv else
                f'la barra sale de {entrada_reg} o {entrada_lib} publicados y no figura en el cuadro publicado')})
            continue
        vistas.add(_clave(f))
        reg, lib, otras = de(k, entrada_reg), de(k, entrada_lib), otra_tension(k)
        for j, anio in enumerate(pub['anios']):
            p, c = f['serie'][j], r['potencia_mw'][j]
            celda = _celda(codigo, pub['columnas'][anio], f['fila'], list(k), p, c,
                           {'anio': anio, 'campo': 'potencia_mw', 'calculo': f'{entrada_reg} + {entrada_lib} de la barra'})
            celdas.append(celda)
            if celda['igual']:
                continue
            causa = next((f'el publicado suma en esta fila, por el nombre de la barra, la entrada de {kv:g} kV de la '
                          'misma barra (la entrada publicada declara otra tensión)'
                          for kv, s in otras if isinstance(kv, (int, float)) and p is not None and c is not None
                          and s[j] is not None and _iguales(p - c, s[j])), None)
            diferencias.append({**celda, 'causa': causa or _causa_por_barra(p, c, reg[j], lib[j])})
    for k, f in publicadas.items():
        if k in vistas:
            continue
        diferencias.append({'id': f'{codigo}!A{f["fila"]}', 'cuadro': codigo, 'clave': list(k), 'causa': (
            f'fila del publicado sin sistema ni subestación (barra «{f["barra"]}»): resto de fórmula, no una barra'
            if not k[0] and not k[1] else
            f'la barra está en el cuadro publicado y en ninguna de sus entradas publicadas ({entrada_reg}, {entrada_lib})')})
    return {'celdas': celdas, 'diferencias': diferencias, 'filas_publicadas': len(pub['filas']),
            'filas_reproducidas': len(reproducidas)}


def cotejar(reproduccion: Mapping[str, Any], acta: Mapping[str, Any], *, implementador: str) -> dict[str, Any]:
    """El cotejo de una muestra de celdas por un revisor independiente, como observaciones de la vía de T11.

    ``acta``: ``revisor``, ``origen`` (debe ser ``ORIGEN_REVISOR``), ``fecha`` (AAAA-MM-DD) y ``muestra``: por celda,
    ``id`` («F-119!B8»), ``publicado`` (lo que leyó el revisor en el libro) y ``observacion``. Cada celda se compara con
    la reproducción: el valor del conversor, la diferencia y si el revisor leyó lo mismo que la reproducción.
    """
    revisor = str(acta.get('revisor') or '').strip()
    if not revisor:
        raise PitError('el acta del cotejo no nombra a su revisor')
    if revisor.casefold() == str(implementador or '').strip().casefold():
        raise PitError(f'el revisor {revisor!r} es el implementador: el cotejo tiene que hacerlo otro')
    if acta.get('origen') != ORIGEN_REVISOR:
        raise PitError(f'el acta declara el origen {acta.get("origen")!r}; tiene que ser {ORIGEN_REVISOR!r}')
    muestra = list(acta.get('muestra') or ())
    if not muestra:
        raise PitError('el acta del cotejo no trae ninguna celda')
    celdas = {c['id']: c for q in reproduccion['cuadros'].values() for c in q['celdas']}
    filas, datos = [], []
    for n, m in enumerate(muestra, 1):
        ident = str(m.get('id') or '')
        c = celdas.get(ident)
        if c is None:
            raise PitError(f'celda {ident!r} del acta: la reproducción no la tiene')
        leido = _numero(m.get('publicado'))
        diferencia = c['conversor'] - leido if leido is not None and c['conversor'] is not None else None
        fila = {'id': ident, 'clave': c['clave'], 'publicado_revisor': leido, 'publicado_reproduccion': c['publicado'],
                'conversor': c['conversor'], 'diferencia': diferencia,
                'lectura_coincide': _iguales(leido, c['publicado']),
                'conversor_coincide': _iguales(leido, c['conversor']),
                'observacion': str(m.get('observacion') or '').strip()}
        filas.append(fila)
        respuesta = ('conforme: el conversor da la cifra publicada' if fila['conversor_coincide'] else
                     f'diferencia {diferencia!r}: '
                     + next((d['causa'] for q in reproduccion['cuadros'].values() for d in q['diferencias']
                             if d.get('id') == ident), 'sin causa en la reproducción; revisar'))
        datos.append({'numero': f'C-{n}', 'fecha': acta.get('fecha'), 'afecta': 'celda', 'referencia': ident,
                      'texto': fila['observacion'] or f'cotejo de {ident}: publicado {leido!r}',
                      'respuesta': respuesta})
    observaciones: list[Observacion] = registrar(datos, {'celda': celdas})
    return {'revisor': revisor, 'origen': ORIGEN_REVISOR, 'implementador': implementador, 'fecha': acta.get('fecha'),
            'referencia': reproduccion['referencia'], 'muestra': filas,
            'conformes': sum(f['conversor_coincide'] for f in filas), 'observaciones': observaciones}


def escribir_en_expediente(carpeta: Path | str, reproduccion: Mapping[str, Any],
                           cotejo: Mapping[str, Any] | None = None) -> list[Path]:
    """Deja en el expediente la reproducción (cuadro reproducido celda a celda, referencia publicada con su huella y
    cada diferencia con su causa) y, si lo hay, el acta del cotejo con sus observaciones (vía de T11).

    Una diferencia sin causa no se emite: la aceptación es justamente que cada una esté explicada. JSON con claves
    ordenadas y sin hora de reloj: la misma reproducción da los mismos bytes (107:RF-9)."""
    sin_causa = [d.get('id') or d.get('clave') for q in reproduccion['cuadros'].values() for d in q['diferencias']
                 if not str(d.get('causa') or '').strip()]
    if sin_causa:
        raise PitError(f'diferencias sin causa: {sin_causa[:5]}; la reproducción no se emite así')
    carpeta = Path(carpeta) / 'reproduccion_publicada'
    carpeta.mkdir(parents=True, exist_ok=True)
    sha = reproduccion['referencia']['sha256'][:12]
    escritos = [carpeta / f'resumenes_{sha}.json']
    texto = json.dumps(reproduccion, ensure_ascii=False, indent=1, sort_keys=True, default=str) + '\n'
    publicar_duradero(escritos[0], texto.encode('utf-8'))
    if cotejo is not None:
        acta = {k: v for k, v in cotejo.items() if k != 'observaciones'}
        escritos.append(carpeta / f'cotejo_{sha}.json')
        publicar_duradero(escritos[-1], (json.dumps(acta, ensure_ascii=False, indent=1, sort_keys=True, default=str)
                                         + '\n').encode('utf-8'))
        escritos.append(escribir_observaciones(carpeta / f'observaciones_cotejo_{sha}.json', cotejo['observaciones']))
    return escritos
