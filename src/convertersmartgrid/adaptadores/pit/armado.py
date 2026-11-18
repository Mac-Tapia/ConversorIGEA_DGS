"""Armado del expediente del PIT de punta a punta, también desde la web (107-P10c; RF-1 a RF-9, RF-13, RF-14).

Une lo que ya existe, en este orden:
1. el ámbito del área (``ambito.reunir``) y su red (``red_area``);
2. el diagnóstico (``diagnostico``);
3. las alternativas, si las hay, con sus costos (``alternativas.evaluar``) y el programa de la elegida (``programa``);
4. los cuadros (``cuadros``);
5. F-001 a F-003 desde la red (``llenado`` y ``formatos_red``);
6. el libro de Información General, el «F-000» (``expediente.escribir_informacion_general``);
7. la emisión (``expediente.emitir``).
No inventa ningún dato que falte: lo nombra.

**Alternativas** (aclaración de 107:RF-5): un JSON del espacio de trabajo,
``{"alternativas": [{"nombre": str, "cambios": [cambio, …]}, …]}``. Cada cambio lleva:

- ``accion``: ``alta`` o ``baja``;
- ``elemento``: en un alta, el elemento nuevo como en el libro de la red (objeto con ``id`` y ``tipo``); en una baja,
  el ``id`` del que sale;
- ``costo`` (solo en un alta): ``codigo``, ``cantidad`` (número > 0) y ``unidad`` del módulo estándar;
- ``anio`` (entero), ``titular``, ``instalacion`` y ``descripcion`` (texto).

Del mismo JSON sale el programa de la alternativa elegida, sin un segundo fichero. Un JSON mal formado es un error que
nombra el campo (``alternativas[0].cambios[1].costo.cantidad``).

**Costos** (``pit.costos`` del perfil): por ámbito (``transmision``), una lista de fuentes con su vigencia, según la regla
de los ficheros reemplazables por periodo, nunca con una versión fija. Cada fuente lleva:

- ``lector``: ``modulos_transmision`` o ``sicodi``;
- ``fichero``: ruta relativa al espacio de trabajo;
- ``sha256``, ``vigencia_desde`` y, si la tiene, ``vigencia_hasta``;
- ``resolucion``, ``anio``, ``moneda``, ``url`` y ``fecha_descarga``;
- para los módulos, ``columnas`` y, si hace falta, ``hoja`` y ``unidad``.

Vale la vigente en la fecha de apertura. Sin una vigente, la comparación queda como hueco nombrado.

**Sin alternativas** (o sin costos), el expediente es de diagnóstico: ``emitir`` lo rotula «DE DIAGNÓSTICO, no
presentable a Osinergmin» y nunca lo da por completo.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ...aplicacion.costos_fuentes import CostosError, TablaCostos, leer_modulos_transmision, leer_sicodi
from ...dominio.registro_normativo import RegistroNormativo
from ...dominio.pit import PitError
from .alternativas import evaluar
from ...dominio.pit.norma import factor_potencia
from ...dominio.pit.ambito import areas_del_perfil, reunir
from .cuadros import celdas_de_cuadros, definiciones, formatos_aplicables
from .diagnostico import agregar_demanda, diagnosticar, limites_de_tension, limites_del_estudio
from .expediente import F000, abrir, emitir, escribir_informacion_general, filas_del_programa
from .llenado import llenar_formatos
from .plantillas import cargar_mapeo
from ...dominio.pit.programa import programar
from ...aplicacion.pit.red_area import desde_ambito, leer_libro_red

__all__ = ['LECTORES_DE_COSTOS', 'VARIABLE_FUENTES_NORMATIVAS', 'armar_expediente', 'carpeta_de_fuentes',
           'leer_alternativas', 'tablas_de_costos']

#: Lectores de una fuente de costos de ``pit.costos``.
LECTORES_DE_COSTOS = ('modulos_transmision', 'sicodi')
_ACCIONES = ('alta', 'baja')
#: La carpeta de fuentes normativas de la máquina (los libros oficiales con su SHA256SUMS.txt): la lee la web y la
#: comprueba el doctor. No va en el perfil, que es de la empresa; fijarla desde la web es de 107-P10d.
VARIABLE_FUENTES_NORMATIVAS = 'CSG_FUENTES_NORMATIVAS'


def carpeta_de_fuentes(entorno: Mapping[str, str] | None = None) -> Path | None:
    """La carpeta de ``CSG_FUENTES_NORMATIVAS``, o ``None`` si no está puesta."""
    valor = str((os.environ if entorno is None else entorno).get(VARIABLE_FUENTES_NORMATIVAS) or '').strip()
    return Path(valor) if valor else None


def _texto(c: Mapping[str, Any], campo: str, donde: str) -> str:
    v = c.get(campo)
    if not isinstance(v, str) or not v.strip():
        raise PitError(f'{donde}.{campo}: falta o no es un texto')
    return v


def leer_alternativas(datos: Any) -> list[dict[str, Any]]:
    """Las alternativas del JSON del espacio, validadas campo a campo; la primera falta es un error que la nombra."""
    lista = datos.get('alternativas') if isinstance(datos, Mapping) else None
    if not isinstance(lista, list) or not lista:
        raise PitError('alternativas: falta la lista «alternativas» (al menos una)')
    nombres, salida = set(), []
    for i, a in enumerate(lista):
        donde = f'alternativas[{i}]'
        if not isinstance(a, Mapping):
            raise PitError(f'{donde}: tiene que ser un objeto')
        nombre = _texto(a, 'nombre', donde)
        if nombre in nombres:
            raise PitError(f'{donde}.nombre: «{nombre}» está repetido')
        nombres.add(nombre)
        cambios = a.get('cambios')
        if not isinstance(cambios, list) or not cambios:
            raise PitError(f'{donde}.cambios: falta la lista de cambios (al menos uno)')
        validos = []
        for j, c in enumerate(cambios):
            dc = f'{donde}.cambios[{j}]'
            if not isinstance(c, Mapping):
                raise PitError(f'{dc}: tiene que ser un objeto')
            accion = c.get('accion')
            if accion not in _ACCIONES:
                raise PitError(f'{dc}.accion: tiene que ser una de {list(_ACCIONES)}, no {accion!r}')
            elemento = c.get('elemento')
            if accion == 'alta':
                if not isinstance(elemento, Mapping):
                    raise PitError(f'{dc}.elemento: un alta trae el elemento nuevo (objeto con «id» y «tipo»)')
                _texto(elemento, 'id', f'{dc}.elemento')
                _texto(elemento, 'tipo', f'{dc}.elemento')
                costo = c.get('costo')
                if not isinstance(costo, Mapping):
                    raise PitError(f'{dc}.costo: un alta trae su costo (código, cantidad y unidad)')
                _texto(costo, 'codigo', f'{dc}.costo')
                _texto(costo, 'unidad', f'{dc}.costo')
                cantidad = costo.get('cantidad')
                if isinstance(cantidad, bool) or not isinstance(cantidad, (int, float)) or cantidad <= 0:
                    raise PitError(f'{dc}.costo.cantidad: tiene que ser un número mayor que cero')
            elif not isinstance(elemento, str) or not elemento.strip():
                raise PitError(f'{dc}.elemento: una baja trae el «id» del elemento que sale')
            anio = c.get('anio')
            if isinstance(anio, bool) or not isinstance(anio, int):
                raise PitError(f'{dc}.anio: tiene que ser un año entero')
            for campo in ('titular', 'instalacion', 'descripcion'):
                _texto(c, campo, dc)
            validos.append(dict(c))
        salida.append({'nombre': nombre, 'cambios': validos})
    return salida


def _vigente(fuente: Mapping[str, Any], fecha: str) -> bool:
    desde, hasta = str(fuente.get('vigencia_desde') or ''), fuente.get('vigencia_hasta')
    return bool(desde) and desde <= fecha and (not hasta or fecha <= str(hasta))


def tablas_de_costos(perfil: Mapping[str, Any], raiz: Path, fecha: str) -> tuple[dict[str, TablaCostos], list[str]]:
    """Las tablas de costos vigentes en ``fecha`` (``pit.costos``), cada fichero comprobado por su sha256 antes de
    leerlo, y lo que falta como pendiente nombrado."""
    declaradas = ((perfil.get('pit') or {}).get('costos') or {}) if isinstance(perfil, Mapping) else {}
    tablas, pendientes = {}, []
    if not declaradas:
        return {}, ['sin pit.costos en el perfil: no hay costos con que comparar las alternativas']
    for ambito, fuentes in sorted(declaradas.items()):
        vigentes = [f for f in (fuentes or ()) if isinstance(f, Mapping) and _vigente(f, fecha)]
        if not vigentes:
            pendientes.append(f'pit.costos.{ambito}: ninguna fuente vigente el {fecha}')
            continue
        f = max(vigentes, key=lambda x: str(x.get('vigencia_desde')))
        donde = f'pit.costos.{ambito}'
        if f.get('lector') not in LECTORES_DE_COSTOS:
            raise PitError(f'{donde}.lector: tiene que ser uno de {list(LECTORES_DE_COSTOS)}')
        ruta = (Path(raiz) / str(f.get('fichero') or '')).resolve()
        if not f.get('fichero') or not ruta.is_relative_to(Path(raiz).resolve()) or not ruta.is_file():
            raise PitError(f'{donde}.fichero: {f.get("fichero")!r} no es un fichero del espacio de trabajo')
        real = hashlib.sha256(ruta.read_bytes()).hexdigest()
        if real != str(f.get('sha256') or '').lower():
            raise PitError(f'{donde}: {ruta.name} tiene sha256 {real} y el perfil declara {f.get("sha256")!r}; '
                           'no se lee')
        comunes = {k: f.get(k) for k in ('resolucion', 'anio', 'moneda', 'url', 'fecha_descarga')}
        try:
            if f['lector'] == 'sicodi':
                tablas[ambito] = leer_sicodi(ruta, **comunes)
            else:
                tablas[ambito] = leer_modulos_transmision(ruta, columnas=f.get('columnas') or {}, hoja=f.get('hoja'),
                                                          unidad=f.get('unidad'), **comunes)
        except (CostosError, TypeError) as exc:
            raise PitError(f'{donde}: {exc}') from exc
    return tablas, pendientes


def _para_programa(c: Mapping[str, Any]) -> dict[str, Any]:
    e = c['elemento']
    return {'accion': c['accion'], 'elemento': e['id'] if isinstance(e, Mapping) else e,
            'tipo': e.get('tipo', '') if isinstance(e, Mapping) else '', 'anio': c['anio'], 'titular': c['titular'],
            'instalacion': c['instalacion'], 'descripcion': c['descripcion']}


def armar_expediente(raiz: Path | str, perfil: Mapping[str, Any], registro: RegistroNormativo, *, area: str,
                     periodo: str, anios: Sequence[int], libro_red: Path | str, proyeccion: Sequence[Mapping[str, Any]],
                     fecha_apertura: str, alternativas: Any = None, alternativa_elegida: str | None = None,
                     fuentes: Path | str | None = None, motor: str = 'abierto', ejecutar: Any = None,
                     mapeo: Mapping[str, Any] | None = None,
                     cancel: threading.Event | None = None,
                     on_progress: Callable[[int, int, str], None] | None = None) -> dict[str, Any]:
    """Arma y emite el expediente del área en ``raiz`` (el espacio de trabajo) y devuelve lo que salió.

    ``alternativas`` es el contenido del JSON de alternativas; sin él, el expediente es de diagnóstico. ``fuentes``
    es la carpeta de fuentes normativas: sin ella no sale el libro F-000 y se dice por qué. ``ejecutar`` sustituye
    a Excel en las pruebas, y ``mapeo`` al de ``config/pit_mapeo_formatos.json``.
    """
    raiz = Path(raiz)
    pasos = 6
    avance = on_progress or (lambda i, n, texto: None)
    datos_area = areas_del_perfil(perfil, area)[0]
    cfg = (perfil.get('pit') or {}).get('libro_red')
    if not cfg:
        raise PitError('pit.libro_red: el perfil no describe el libro de la red')
    elegidas = leer_alternativas(alternativas) if alternativas is not None else None
    if elegidas is not None and alternativa_elegida not in {a['nombre'] for a in elegidas}:
        raise PitError(f'alternativa_elegida: {alternativa_elegida!r} no está en las alternativas '
                       f'({[a["nombre"] for a in elegidas]})')
    avance(1, pasos, 'red del área')
    libro_red = Path(libro_red)
    elementos = leer_libro_red(libro_red, cfg)
    red = desde_ambito(reunir(datos_area, elementos))
    red.avisos.extend(elementos.avisos)
    avance(2, pasos, 'diagnóstico')
    # La tensión, por barra desde la norma (107 T7, PIT-TEN); pit.limites del perfil queda como respaldo explícito.
    diag = diagnosticar(datos_area, red, proyeccion, anios, limites_del_estudio(registro, perfil), motor=motor,
                        cancel=cancel, tension=limites_de_tension(red, datos_area, registro, perfil), registro=registro)
    pendientes: list[str] = []
    comparacion = programa = None
    celdas: list[dict[str, Any]] = []
    avance(3, pasos, 'alternativas')
    if elegidas is None:
        pendientes.append('sin alternativas: no hay comparación ni programa')
    else:
        tablas, faltan = tablas_de_costos(perfil, raiz, fecha_apertura)
        pendientes += faltan
        if tablas:
            comparacion = evaluar(red, elegidas, agregar_demanda(datos_area, red, proyeccion,
                                                                  factor_potencia=factor_potencia(registro)),
                                  [a.anio for a in diag.anios] or anios, registro,
                                  tablas, motor=motor, cancel=cancel, ubicacion=datos_area.ubicacion)
            evaluada = next(a for a in comparacion.alternativas if a.nombre == alternativa_elegida)
            if evaluada.completa:
                elegida = next(a for a in elegidas if a['nombre'] == alternativa_elegida)
                programa = programar(datos_area, [_para_programa(c) for c in elegida['cambios']])
                celdas = celdas_de_cuadros(definiciones(registro), filas_del_programa(programa, comparacion,
                                                                                      str(alternativa_elegida)))
            else:
                # Sin la elegida completa no hay programa: el expediente sigue de diagnóstico y dice por qué.
                pendientes.append(f'la alternativa elegida {alternativa_elegida!r} está incompleta: '
                                  f'{"; ".join(evaluada.motivos)}')
    avance(4, pasos, 'formatos de información general')
    huella = hashlib.sha256(libro_red.read_bytes()).hexdigest()
    frecuencia = (perfil.get('pit') or {}).get('frecuencia_hz')
    llenado = llenar_formatos(registro, {'red': {'fuente': {'nombre': libro_red.name, 'huella': huella}, 'red': red,
                                                 'frecuencia_hz': frecuencia}})
    carpeta = abrir(raiz, datos_area.codigo, periodo, registro, fecha_apertura=fecha_apertura)
    avance(5, pasos, 'libro F-000')
    mapeo = cargar_mapeo() if mapeo is None else mapeo
    grupo = (mapeo.get('alias') or {}).get(F000, {}).get('equivale_a') or ()
    resultados = [llenado['resultados'][c] for c in grupo if c in llenado['resultados']]
    if fuentes is None:
        libro = {'libro': None, 'motivo': 'falta la carpeta de fuentes normativas (CSG_FUENTES_NORMATIVAS): sin la '
                                          'plantilla oficial no se escribe el libro F-000'}
    else:
        libro = escribir_informacion_general(carpeta, resultados, Path(fuentes), ejecutar=ejecutar, mapeo=mapeo)
    avance(6, pasos, 'emisión')
    salidas = emitir(carpeta, registro, celdas=[*celdas, *llenado['celdas']], diagnostico=diag,
                     comparacion=comparacion, programa=programa,
                     alternativa_elegida=alternativa_elegida if programa is not None else None,
                     formatos=formatos_aplicables(registro))
    resumen = json.loads(salidas['resumen'].read_text(encoding='utf-8'))
    return {'carpeta': str(carpeta), 'salidas': {k: str(v) for k, v in sorted(salidas.items())},
            'tipo': resumen['tipo'], 'estado': resumen['estado'], 'pendientes': resumen['pendientes'],
            'pendientes_del_armado': pendientes, 'avisos': list(diag.avisos),
            'libro_f000': {'nombre': libro.get('nombre'), 'libro': str(libro['libro']) if libro.get('libro') else None,
                           'motivo': libro.get('motivo', '')}}
