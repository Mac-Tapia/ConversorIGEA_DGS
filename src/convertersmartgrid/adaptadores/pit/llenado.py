"""Llenado de los formatos que exige el estudio del PIT (107:RF-9, aclaración; 107-T19b).

Qué formatos lleva el estudio del plan no está en el código: sale de la regla ``pit.plan.formatos_exigidos`` del
registro (en el real, el num. 5.7 de la Norma Tarifas). Cada formato exigido sale de una de dos maneras:
- **llenado**, si tiene mapeo campo → celda (``MAPEADORES``) y se entregó su fuente;
- **plantilla**, nombrada con su causa: no transcrito, sin datos de origen o sin mapeo todavía.

Nunca sale vacío en silencio. Los que aún no tienen mapeo se listan en ``pendientes_de_mapeo``: mientras quede uno,
T19 no se cierra (condición del auditor ca, 2026-11-14).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ...dominio.registro_normativo import RegistroError, RegistroNormativo
from ...dominio.pit import PitError
from .cuadros import codigos_de_grupos, formatos_aplicables
from ...dominio.pit.f208 import CODIGO as F208
from ...dominio.pit.f208 import celdas_f208
from .formatos_red import datos_f001, datos_f002, datos_f003
from .plantillas import celdas_de_formato

__all__ = ['CAUSAS_DE_PENDIENTE', 'MAPEADORES', 'formatos_exigidos', 'llenar_formatos']

Mapeador = Callable[[RegistroNormativo, Mapping[str, Any], 'str | None'], dict[str, Any]]


def _f208(registro: RegistroNormativo, fuente: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    return celdas_f208(registro, fuente, fecha)


def _f001(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    datos, sin_nivel = datos_f001(entrada['red'], registro, entrada['fuente'], fecha)
    resultado = celdas_de_formato(registro, 'F-001', datos, fecha=fecha)
    resultado['huecos'] += [{'bloque': 'titulares', 'causa': f'{e["tipo"]} {e["id"]}: {e["causa"]}'} for e in sin_nivel]
    return resultado


def _f002(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    datos = datos_f002(entrada['red'], entrada['fuente'], entrada.get('frecuencia_hz'))
    return celdas_de_formato(registro, 'F-002', datos, fecha=fecha)


def _f003(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    return celdas_de_formato(registro, 'F-003', datos_f003(entrada['red'], entrada['fuente']), fecha=fecha)


def _por_sistema(codigo: str, por_sistema: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    """Un formato que va una hoja por sistema eléctrico (F-106, F-108): el primero en su hoja y cada uno de los demás en
    una copia de ella («F-108 (2)»…), que el libro de la entrega tiene que crear antes de escribir (``hojas_a_copiar``)."""
    if not por_sistema:
        return {'codigo': codigo, 'celdas': [], 'huecos': [{'bloque': 'sistemas', 'causa': 'sin sistemas eléctricos en la '
                                                                                            'fuente'}],
                'filas_a_insertar': {}, 'insertar_en': [], 'grupos_a_insertar': {}, 'avisos': []}
    salida: dict[str, Any] = {'codigo': codigo, 'celdas': [], 'huecos': [], 'filas_a_insertar': {}, 'insertar_en': [],
                              'grupos_a_insertar': {}, 'avisos': [], 'hojas_a_copiar': []}
    for k, (sistema, r) in enumerate(por_sistema.items(), start=1):
        hoja = codigo if k == 1 else f'{codigo} ({k})'
        if k > 1:
            salida['hojas_a_copiar'].append({'de': codigo, 'a': hoja, 'sistema': sistema})
        for c in r['celdas']:
            salida['celdas'].append({**c, 'id': c['id'].replace(f'{codigo}!', f'{hoja}!', 1),
                                     'celda': c['celda'].replace(f'{codigo}!', f'{hoja}!', 1)})
        salida['huecos'] += [{**h, 'sistema': sistema} for h in r['huecos']]
        salida['avisos'] += r.get('avisos', [])
        for i in r.get('insertar_en') or ():
            bloque = f'{i["bloque"]}:{sistema}'
            salida['insertar_en'].append({**i, 'hoja': hoja, 'bloque': bloque})
            salida['filas_a_insertar'][bloque] = i['filas']
    if not salida['hojas_a_copiar']:
        del salida['hojas_a_copiar']
    return salida


def _demanda_3b(codigo: str) -> Mapeador:
    def llenar(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
        from .demanda_regulatoria import celdas_f101, celdas_f102_f103
        if codigo == 'F-101':
            return celdas_f101(registro, entrada['salida'], entrada['red'], entrada['fuente'])
        return celdas_f102_f103(registro, entrada['salida'], entrada['red'], entrada['fuente'])[codigo]
    return llenar


def _cadena(codigo: str) -> Mapeador:
    def llenar(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
        from .demanda_cadena import celdas_cadena
        from .demanda_resumen import HUECO_TOTALES
        celdas = celdas_cadena(registro, entrada['cadena'], entrada['fuente'], fecha)
        if codigo == 'F-108':
            return _por_sistema(codigo, celdas[codigo])
        resultado = celdas[codigo]
        resultado['huecos'].append({'bloque': 'totales', 'causa': HUECO_TOTALES})
        return resultado
    return llenar


def _historia(codigo: str) -> Mapeador:
    def llenar(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
        from .demanda_resumen import celdas_historia
        hecho = celdas_historia(registro, entrada['historia'], entrada['fuente'], fecha)
        if codigo in hecho:
            return hecho[codigo]
        vacio = celdas_de_formato(registro, codigo, {'fuente': entrada['fuente'], 'bloques': {}}, fecha=fecha)
        vacio['huecos'].append({'bloque': 'anios', 'causa': f'la historia entregada no trae los datos de {codigo}'})
        return vacio
    return llenar


def _f106(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    from .demanda_resumen import celdas_modelos
    return _por_sistema('F-106', {s: celdas_modelos(registro, 'F-106', s, m, entrada['fuente'], fecha)
                                  for s, m in (entrada.get('sistemas') or {}).items()})


def _f107(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    from .demanda_resumen import celdas_modelos
    return celdas_modelos(registro, 'F-107', str(entrada.get('area') or ''), entrada.get('modelos') or (),
                          entrada['fuente'], fecha)


def _resumen(codigo: str) -> Mapeador:
    def llenar(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
        from .demanda_resumen import celdas_resumen, resumen_demanda
        resumen = resumen_demanda(registro, entrada['cadena'], entrada.get('libres'), fecha)
        return celdas_resumen(registro, resumen, entrada.get('area'), entrada['fuente'], fecha)[codigo]
    return llenar


def _usuarios(codigo: str) -> Mapeador:
    """F-113 a F-118 (``usuarios``: ``{'fuente', 'proyeccion', 'area'}``; la proyección, de
    ``usuarios_libres.proyeccion_usuarios`` con el libro de cargas nuevas y ``pit.usuarios_libres`` del perfil)."""
    def llenar(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
        from .usuarios_libres import celdas_usuarios
        return celdas_usuarios(registro, entrada['proyeccion'], entrada.get('area'), entrada['fuente'], fecha)[codigo]
    return llenar


def _f123(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    """F-123, los mapas de densidad (``densidad``: ``{'fuente', 'mapas', 'area'}``; los mapas, de
    ``densidad.mapas_f123``)."""
    from .densidad import resultado_f123
    return resultado_f123(entrada['mapas'], entrada.get('area'))


def _f124(registro: RegistroNormativo, entrada: Mapping[str, Any], fecha: str | None) -> dict[str, Any]:
    """F-124 deducido de la medición de las centrales (``generacion``: ``{'fuente', 'centrales', 'curvas', 'area',
    'titular', 'tipo_sistema', 'huecos'}``; las curvas, de ``generacion.generacion_medida``)."""
    from .generacion import datos_f124
    datos = datos_f124(entrada.get('centrales') or {}, entrada.get('curvas') or {}, entrada['fuente'],
                       area=entrada.get('area'), titular=entrada.get('titular'),
                       tipo_sistema=entrada.get('tipo_sistema'), huecos=entrada.get('huecos') or ())
    resultado = celdas_de_formato(registro, 'F-124', datos, fecha=fecha)
    resultado['avisos'] = list(resultado.get('avisos') or []) + datos['avisos']
    return resultado


#: Formato → (clave de su fuente en ``fuentes``, función que lo llena). Crece formato a formato en 107-T19b. La red
#: del área (``red``: ``{'fuente', 'red', 'frecuencia_hz'}``) alimenta a F-001, F-002 y F-003. La demanda (107 T28 a
#: T30): ``demanda_3b`` (``{'fuente', 'salida', 'red'}``, salida de ``demanda_regulatoria``) a F-101 a F-103; ``cadena``
#: (``{'fuente', 'cadena'}``, de ``demanda_cadena.cadena_regulatoria``) a F-108 a F-112; ``historia`` (``{'fuente',
#: 'historia'}``) a F-104 y F-105; ``tendencias`` (``{'fuente', 'sistemas'}``) a F-106; ``econometrico`` (``{'fuente',
#: 'area', 'modelos'}``) a F-107; y ``resumen`` (``{'fuente', 'cadena', 'libres', 'area'}``) a F-119 a F-122.
MAPEADORES: dict[str, tuple[str, Mapeador]] = {
    'F-001': ('red', _f001), 'F-002': ('red', _f002), 'F-003': ('red', _f003), F208: (F208, _f208),
    **{c: ('demanda_3b', _demanda_3b(c)) for c in ('F-101', 'F-102', 'F-103')},
    **{c: ('historia', _historia(c)) for c in ('F-104', 'F-105')},
    'F-106': ('tendencias', _f106), 'F-107': ('econometrico', _f107),
    **{c: ('cadena', _cadena(c)) for c in ('F-108', 'F-109', 'F-110', 'F-111', 'F-112')},
    **{c: ('resumen', _resumen(c)) for c in ('F-119', 'F-120', 'F-121', 'F-122')},
    'F-124': ('generacion', _f124),
    'F-123': ('densidad', _f123),
    **{c: ('usuarios', _usuarios(c)) for c in ('F-113', 'F-114', 'F-115', 'F-116', 'F-117', 'F-118')}}

#: Formatos que aún no tienen fuente en el conversor, con su causa nombrada (107 T30): siguen en ``pendientes_de_mapeo``
#: y su plantilla dice esta causa, no la genérica. Desde PIT-F113-118, PIT-F123 y PIT-F124, ningún formato de demanda.
CAUSAS_DE_PENDIENTE: dict[str, str] = {}


def formatos_exigidos(registro: RegistroNormativo, fecha: str | None = None) -> list[str]:
    """Los códigos que exige el estudio del plan, de la regla citada del registro."""
    try:
        rv = registro.regla('pit.plan.formatos_exigidos', fecha)
    except RegistroError as exc:
        raise PitError('falta la regla pit.plan.formatos_exigidos en el registro normativo: no se supone qué formatos '
                       f'lleva el estudio ({exc})') from exc
    grupos = rv.regla.valor.get('grupos') if isinstance(rv.regla.valor, Mapping) else None
    if not grupos:
        raise PitError('la regla pit.plan.formatos_exigidos no trae sus «grupos»')
    return codigos_de_grupos(grupos)


def llenar_formatos(registro: RegistroNormativo, fuentes: Mapping[str, Mapping[str, Any]], fecha: str | None = None,
                    mapeadores: Mapping[str, tuple[str, Mapeador]] | None = None) -> dict[str, Any]:
    """Cada formato exigido, llenado o como plantilla con su causa, y las celdas de los llenados.

    ``fuentes``: clave de fuente (``red``, ``F-208``…) → la entrada de su mapeador, con su ``fuente`` y su huella.
    ``mapeadores`` sustituye a ``MAPEADORES`` (pruebas). ``resultados`` da el de cada formato llenado (con sus huecos
    y sus filas que insertar), que es lo que escribe el libro de la entrega (107-P10c).
    """
    tabla: Mapping[str, tuple[str, Mapeador]] = MAPEADORES if mapeadores is None else mapeadores
    aplicables = {f['codigo']: f for f in formatos_aplicables(registro, fecha)['formatos']}
    salida, celdas, pendientes, resultados = [], [], [], {}
    for codigo in formatos_exigidos(registro, fecha):
        f = aplicables.get(codigo)
        fila: dict[str, Any] = {'codigo': codigo, 'titulo': (f or {}).get('titulo') or codigo, 'huecos': []}
        if f is None:
            fila.update(estado='plantilla', causa='el estudio lo exige y la norma vigente no lo lista')
        elif not f['transcrito']:
            fila.update(estado='plantilla', causa='formato no transcrito en el registro normativo')
        elif codigo not in tabla:
            fila.update(estado='plantilla', causa=CAUSAS_DE_PENDIENTE.get(codigo)
                        or 'sin mapeo campo → celda todavía (107-T19b)')
            pendientes.append(codigo)
        elif tabla[codigo][0] not in fuentes:
            fila.update(estado='plantilla', causa=f'sin datos de origen: no se entregó la fuente '
                                                  f'«{tabla[codigo][0]}» de {codigo}')
        else:
            clave, funcion = tabla[codigo]
            resultado = funcion(registro, fuentes[clave], fecha)
            fila.update(estado='llenado', causa='', huecos=resultado.get('huecos', []))
            fila['avisos'] = resultado.get('avisos', [])  # valores de la fuente en celdas sombreadas (delta20)
            celdas += resultado['celdas']
            resultados[codigo] = resultado
        salida.append(fila)
    return {'formatos': salida, 'celdas': celdas, 'pendientes_de_mapeo': pendientes, 'resultados': resultados}
