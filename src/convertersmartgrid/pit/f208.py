"""Formato F-208 del PIT: estadística de fallas e índices de desempeño (107:RF-18, T26).

La estructura no está en el código: sale de la hoja F-208 transcrita en el registro normativo (regla
``pit.formato.F-208``). Cada bloque se reconoce por su título; sus columnas, por los rótulos de sus filas de cabecera,
y su primera fila de datos es la que sigue a la cabecera. Aquí solo vive el mapeo rótulo → campo de la fuente: si una
versión de la norma cambia un rótulo, el error lo nombra en lugar de llenar la columna equivocada.

Los datos salen de las fuentes importadas del área (el histórico de interrupciones de la spec 012 y los índices y
barras calculados), con su huella. Un bloque sin datos deja vacía cada celda de su primera fila y su hueco se nombra
con la causa: nunca un cero ni un bloque vacío en silencio. «Cumple» se calcula frente a la tolerancia; sin ella, no
se supone.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from typing import Any

from ..registro_normativo import RegistroError, RegistroNormativo
from . import PitError

__all__ = ['CODIGO', 'celdas_f208', 'estructura_f208']

CODIGO = 'F-208'
MOTOR = 'pit.f208'
#: Título del bloque en la plantilla → nombre del bloque.
_BLOQUES = {'interrupciones': 'interrupciones', 'saifi y saidi': 'indices',
            'barras con tension fuera de tolerancia': 'barras'}
#: Rótulo de la columna (cabeceras unidas, sin tildes ni mayúsculas) → campo de la fuente.
_CAMPOS = {
    'interrupciones': {'nominacion': 'nominacion', 'fecha': 'fecha', 'hora inicio': 'hora_inicio',
                       'hora fin': 'hora_fin', 'tipo de interrupcion': 'tipo', 'ens kwh': 'ens_kwh'},
    'indices': {'nominacion': 'nominacion', 'calculado saifi': 'saifi', 'calculado saidi': 'saidi',
                'tolerencias saifi': 'saifi_tolerancia', 'tolerancias saifi': 'saifi_tolerancia',
                'tolerencias saidi': 'saidi_tolerancia', 'tolerancias saidi': 'saidi_tolerancia',
                'cumple(1)': 'cumple'},
    'barras': {'nominacion set/barra': 'nominacion', 'caida de tension kv': 'caida_kv',
               'caida de tension %caida': 'caida_pct', 'tolerancias kv': 'tolerancia_kv',
               'tolerancias %caida': 'tolerancia_pct', 'cumple(1)': 'cumple'},
}
#: Valores que admite la nota (2) del formato para el tipo de interrupción.
TIPOS = ('Forzada', 'Programada')
_NUMERICOS = {'ens_kwh', 'saifi', 'saidi', 'saifi_tolerancia', 'saidi_tolerancia', 'caida_kv', 'caida_pct',
              'tolerancia_kv', 'tolerancia_pct'}
_CUMPLE = {'indices': (('saifi', 'saifi_tolerancia'), ('saidi', 'saidi_tolerancia')),
           'barras': (('caida_kv', 'tolerancia_kv'), ('caida_pct', 'tolerancia_pct'))}


def _normal(texto: str) -> str:
    sin_tildes = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return ' '.join(sin_tildes.lower().split())


def _es_dato(fila: Mapping[str, Any]) -> bool:
    """La primera fila de datos de la plantilla: «Línea 1», «L» o la etiqueta de repetición."""
    primera = _normal(str(fila['celdas'].get('A', '')))
    return primera in ('linea 1', 'l') or primera.startswith('linea ')


def estructura_f208(registro: RegistroNormativo, fecha: str | None = None) -> dict[str, Any]:
    """Los bloques del F-208 (título, filas de cabecera, columnas con su campo y primera fila de datos), leídos de la
    plantilla transcrita, con la regla de la que salen."""
    try:
        rv = registro.regla(f'pit.formato.{CODIGO}', fecha)
    except RegistroError as exc:
        raise PitError(f'{CODIGO}: su plantilla no está transcrita en el registro normativo ({exc})') from exc
    filas = rv.regla.valor.get('filas') if isinstance(rv.regla.valor, Mapping) else None
    if not filas:
        raise PitError(f'{CODIGO}: la regla pit.formato.{CODIGO} no trae las filas de su plantilla')
    bloques: list[dict[str, Any]] = []
    actual: dict[str, Any] | None = None
    for fila in filas:
        titulo = _normal(' '.join(fila['celdas'].values()))
        if titulo in _BLOQUES:
            actual = {'bloque': _BLOQUES[titulo], 'fila_titulo': fila['fila'], 'filas_cabecera': [], 'rotulos': {}}
            bloques.append(actual)
        elif actual is not None and 'primera_fila_datos' not in actual:
            if _es_dato(fila):
                actual['primera_fila_datos'] = fila['fila']
            else:
                actual['filas_cabecera'].append(fila['fila'])
                for letra, texto in fila['celdas'].items():
                    actual['rotulos'].setdefault(letra, {})[fila['fila']] = texto
    faltan = sorted(set(_BLOQUES.values()) - {b['bloque'] for b in bloques})
    if faltan or any('primera_fila_datos' not in b or not b['filas_cabecera'] for b in bloques):
        raise PitError(f'{CODIGO}: la plantilla transcrita no trae los bloques {faltan or "completos"}; '
                       'revisar la transcripción antes de llenar')
    for b in bloques:
        b['columnas'] = _columnas(b)
        del b['rotulos']
    return {'codigo': CODIGO, 'bloques': bloques,
            'regla': {'clave': rv.regla.clave, 'norma': rv.norma.acto, 'estado': rv.estado,
                      'pagina': rv.regla.pagina, 'huella': rv.huella()}}


def _columnas(bloque: dict[str, Any]) -> list[dict[str, str]]:
    """Cada columna con su rótulo: la cabecera superior se extiende a la derecha sobre las celdas combinadas."""
    letras = sorted(bloque['rotulos'], key=lambda x: (len(x), x))
    primera, resto = bloque['filas_cabecera'][0], bloque['filas_cabecera'][1:]
    columnas, arriba = [], ''
    for letra in letras:
        textos = bloque['rotulos'][letra]
        if primera in textos:
            arriba = textos[primera]
        elif not arriba:
            raise PitError(f'{CODIGO}, bloque {bloque["bloque"]}: la columna {letra} no tiene rótulo superior')
        # Sin rótulo en la fila superior, la columna está bajo la celda combinada de su izquierda: lo hereda.
        rotulo = ' '.join([arriba, *(textos[f] for f in resto if f in textos)])
        campo = _CAMPOS[bloque['bloque']].get(_normal(rotulo))
        if campo is None:
            raise PitError(f'{CODIGO}, bloque {bloque["bloque"]}: rótulo {rotulo!r} (columna {letra}) sin campo '
                           'conocido; la plantilla cambió y hay que revisar el mapeo')
        columnas.append({'letra': letra, 'rotulo': rotulo, 'campo': campo})
    return columnas


def _validar(fuentes: Mapping[str, Any]) -> dict[str, str]:
    fuente = fuentes.get('fuente') or {}
    if not str(fuente.get('nombre') or '').strip() or not str(fuente.get('huella') or '').strip():
        raise PitError(f'{CODIGO}: la fuente importada necesita su nombre y su huella (fuente={fuente!r})')
    for bloque in ('interrupciones', 'indices', 'barras'):
        for i, fila in enumerate(fuentes.get(bloque) or (), start=1):
            if bloque == 'interrupciones' and fila.get('tipo') not in (None, *TIPOS):
                raise PitError(f'{CODIGO}, interrupción {i}: tipo {fila.get("tipo")!r}; la nota (2) del formato '
                               'admite Forzada o Programada')
            for campo in _NUMERICOS & set(fila):
                valor = fila[campo]
                if valor is not None and (not isinstance(valor, (int, float)) or valor < 0):
                    raise PitError(f'{CODIGO}, {bloque} {i}: {campo}={valor!r} tiene que ser un número no negativo')
    return {'nombre': str(fuente['nombre']), 'huella': str(fuente['huella'])}


def _cumple(bloque: str, fila: Mapping[str, Any]) -> tuple[str | None, str]:
    pares = _CUMPLE[bloque]
    faltan = [tol for medida, tol in pares if fila.get(medida) is None or fila.get(tol) is None]
    if faltan:
        return None, f'sin tolerancia o sin valor calculado ({", ".join(faltan)}): «Cumple» no se supone'
    ok = all(fila[medida] <= fila[tol] for medida, tol in pares)
    return ('SI' if ok else 'NO'), ' y '.join(f'{m} <= {t}' for m, t in pares)


def celdas_f208(registro: RegistroNormativo, fuentes: Mapping[str, Any], fecha: str | None = None
                ) -> dict[str, Any]:
    """Las celdas del F-208 con su traza (fuente con su huella, cálculo, motor y regla) y los huecos de cada bloque.

    ``fuentes``: ``fuente`` (``nombre`` y ``huella``), ``interrupciones`` (``nominacion``, ``fecha``,
    ``hora_inicio``, ``hora_fin``, ``tipo``, ``ens_kwh``), ``indices`` (``nominacion``, ``saifi``, ``saidi`` y sus
    tolerancias) y ``barras`` (``nominacion``, ``caida_kv``, ``caida_pct`` y sus tolerancias).
    """
    fuente = _validar(fuentes)
    estructura = estructura_f208(registro, fecha)
    regla = estructura['regla']
    celdas, huecos = [], []
    for b in estructura['bloques']:
        filas = list(fuentes.get(b['bloque']) or ())
        if not filas:
            causa = f'sin {b["bloque"]} en la fuente importada {fuente["nombre"]}'
            huecos.append({'bloque': b['bloque'], 'causa': causa, 'fila_plantilla': b['primera_fila_datos']})
        for i, fila in enumerate(filas or [None], start=1):
            for col in b['columnas']:
                traza = {'fuente': fuente, 'motor': MOTOR, 'regla': regla, 'campo': col['campo'],
                         'calculo': 'dato de la fuente importada'}
                if fila is None:
                    valor, traza['motivo'] = None, causa
                elif col['campo'] == 'cumple':
                    valor, explicacion = _cumple(b['bloque'], fila)
                    traza['calculo'] = f'«Cumple» = SI si {explicacion}' if valor else 'sin cálculo'
                    if valor is None:
                        traza['motivo'] = explicacion
                else:
                    valor = fila.get(col['campo'])
                    if valor is None:
                        traza['motivo'] = f'la fuente no trae «{col["rotulo"]}»'
                celdas.append({'id': f'{CODIGO}!{b["bloque"]}:{i}:{col["campo"]}', 'cuadro': CODIGO,
                               'bloque': b['bloque'], 'fila': i, 'campo': col['campo'], 'columna': col['rotulo'],
                               'celda': f'{CODIGO}!{col["letra"]}{b["primera_fila_datos"] + i - 1}',
                               'valor': valor, 'traza': traza})
    return {'codigo': CODIGO, 'celdas': celdas, 'huecos': huecos, 'regla': regla}
