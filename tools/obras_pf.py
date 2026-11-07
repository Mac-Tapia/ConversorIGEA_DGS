#!/usr/bin/env python
"""Obras de mejora de la spec 011 en un proyecto de DIgSILENT.

Con ``--bibliotecas`` solo lee lo que el formulario de la web ofrece para elegir:

- de cada alimentador marcado, su tensión, sus barras, sus tramos con su tipo y sus
  ternas, sus SED con el tipo de transformador, y sus condensadores y reguladores
  (RF-88);
- los tipos de la clase que pide cada obra (``TypLne``, ``TypTr2``, ``TypVoltreg``,
  ``TypRecl``) de la biblioteca del proyecto (RF-89), de la global de DIgSILENT (RF-90)
  y, si el plan lo pide, de otro proyecto (RF-91), cada uno con los datos que deciden
  la elección (RF-94).

El otro proyecto se lee sin activarlo: activarlo cerraría el del operador, y con él
el caso y las variaciones que tiene activos. Leer no escribe nada en ningún proyecto.

``copiar_tipo`` trae un tipo a la biblioteca del proyecto, de él mismo con datos nuevos
o de otra biblioteca (RF-60, RF-92, RF-93): nunca cambia el original (RF-59). Dentro
del proyecto copia con ``AddCopy``; desde la global o desde otro proyecto, con
``PasteCopy``, porque la referencia de Python de PF 2024 dice que ``AddCopy`` no sirve
entre proyectos distintos (plan, «Métodos de la API comprobados»).

Sin ``--bibliotecas`` aplica las obras del plan (``--simular``: dice lo que haría, sin
escribir nada, RF-69). Las reglas comunes a todas (RF-57 a RF-60, RF-64 a RF-67):

1. Lee la red y los tipos y planifica todas las obras con
   ``convertersmartgrid.obras_pf.plan_simulacion``: lo que se aplica es lo que se simuló. Cada
   alimentador se lee en el caso de sus obras («Con proyecto» si todas son de allí, si no
   «Sin proyecto»), con la troncal del camino más largo (spec 016).
2. Mide «Sin proyecto» antes de tocar nada: cabecera y tensión mínima por alimentador.
3. Por obra: una variación nueva, creada en el primero de sus casos; copia los tipos que
   pide y la construye (``CONSTRUCTORES``, uno por clase, tareas T13 a T15). Si algo
   falla al construirla, la variación se borra: nunca queda una obra a medias.
4. La activa solo en sus casos y la desactiva en los demás; en el «Caso base» nunca.
5. En cada caso donde está activa, un flujo de carga. Si no converge, la obra queda
   inactiva en ese caso, se conserva en el proyecto y el informe da el diagnóstico del
   ajuste (spec 006, RF-15), leído antes de desactivarla.
6. Vuelve a medir «Sin proyecto»: en los alimentadores sin obras activas allí, la
   cabecera y la tensión mínima tienen que ser las de antes. Si cambian, una obra tocó
   algo compartido, y el informe dice el alimentador y el valor.
7. Reabre el proyecto y relee (048:RF-9): cada obra sigue en su variación, graba algo y está
   activa solo donde quedó; el «Caso base», y «Sin proyecto» si ninguna obra es de allí,
   tienen la misma foto que antes de aplicar. Sin eso, ``persistencia.ok`` es falso y sale 2.

    python tools/obras_pf.py --bibliotecas --plan plan.json --output-json informe.json
    python tools/obras_pf.py --plan plan.json --output-json informe.json [--simular]
        [--cancel-file cancelar.flag]

El plan lleva ``project``, ``folder`` y ``feeders`` como el de los estudios; ``obras``
(como las guarda la web, ``Obra.a_dict``); y, si se quieren, ``clases`` (por defecto las
cuatro) y ``otro_proyecto`` (la ruta del proyecto en la carpeta). Se cancela entre obras,
nunca a mitad de una.

Códigos de salida: 0 hecho, 2 no se pudo (el informe dice por qué), 3 sin API.
"""

from __future__ import annotations

import argparse
import json
import os
import math
import re
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from ajuste_cabecera_pf import _clave_objeto_nativo, cargas_sed, diagnostico
from cargas_pf import (
    Alimentadores, activar_proyecto, adaptar_banco, cabecera_de, cifras_de_banco, clave_pf, crear_variacion,
    error_inesperado, es_cable, completar_diagrama, distancia_m, fases_de_barra, flujo_de_carga, gps_de,
    leer_cabecera, leer_red, medir_estado,
    nombre_libre, nombre_pf, partir_tramo, trazado_de,
)
from casos_pf import (
    NOMBRES, anio_del_plan, casos_del_proyecto, crear_con_proyecto, es_de_carga_nueva,
    nombre_caso, sin_a_con_proyecto,
)
from estudios_pf import medida

from convertersmartgrid.carpeta_pf import buscar_proyecto, nombre_de_perfil
from convertersmartgrid.instalacion_ternas import factor_de_capacidad, instalacion
from convertersmartgrid.perfil_empresa import datos_perfil
from convertersmartgrid.pf_arnes import proyecto_de as _proyecto_de
from convertersmartgrid import sitio_set
from convertersmartgrid.vias import ruta_por_vias
from convertersmartgrid.native_action import native_action_block_report
from convertersmartgrid.obras_pf import (
    ATRIBUTOS_TIPO, BANDA_TENSION_PU, ESTADO_SERVICIO, SOLO_CON_PROYECTO, Obra, ObrasError, RedAlimentador, Tipo,
    clasificar_restos, diferencias_sin_proyecto, escribir_aperturas, fichero_aperturas, foto_de_referencia,
    fuera_de_servicio, leer_aperturas, mismos_datos, misma_apertura, plan_simulacion, red_de_lectura, resolver_copia,
    resumen_tipo, tipo_de_ficha, validar_obra, veredicto_persistencia,
)
from convertersmartgrid.estudios_pf import EstudiosError, limites_de_perfil
from convertersmartgrid.naming import feeder_short_name
from convertersmartgrid.obras_pf import nombre_copia, punto_indicado
from convertersmartgrid.troncal import (Conexion, TroncalError, aguas_abajo, camino_y_ramales, extremos_del_enlace,
                              punto_en_troncal)
from convertersmartgrid.troncal import troncal as troncal_de

#: Las clases de tipo que piden las obras (RF-89), en el orden en que se listan.
CLASES_TIPO = tuple(ATRIBUTOS_TIPO)


# =========================================================================== tipos
def datos_tipo(obj) -> dict:
    """Los datos de ``ATRIBUTOS_TIPO`` que tiene el tipo; los que no tiene no se inventan."""
    datos = {}
    for atributo in ATRIBUTOS_TIPO.get(obj.GetClassName(), ()):
        valor = getattr(obj, atributo, None)
        if isinstance(valor, (bool, int, float, str)):
            datos[atributo] = valor
    return datos


def _tipos_en(carpeta, clase: str) -> list:
    """Los tipos de la clase en la carpeta y sus subcarpetas, por nombre."""
    if carpeta is None:
        return []
    return sorted(carpeta.GetContents(f'*.{clase}', 1) or [], key=lambda o: o.loc_name.lower())


def ficha(obj, origen: str, proyecto: str = '') -> dict:
    """Un tipo como lo lista el formulario (RF-94)."""
    datos = datos_tipo(obj)
    clase = obj.GetClassName()
    return {'nombre': obj.loc_name, 'clase': clase, 'origen': origen, 'proyecto': proyecto,
            'datos': datos, 'resumen': resumen_tipo(clase, datos)}


def biblioteca_de_otro(proyecto):
    """La biblioteca de tipos de un proyecto sin activarlo.

    ``app.GetLocalLibrary`` solo sirve para el activo. En un proyecto de DIgSILENT la
    biblioteca de equipos es la carpeta con ``iopt_typ='equip'``, dentro de la
    «Library» (``iopt_typ='lib'``); si el proyecto no la tiene así (uno hecho a mano), se
    usa la «Library» entera.
    """
    carpetas = [c for c in proyecto.GetContents('*.IntPrjfolder') or []]
    for c in carpetas:
        if getattr(c, 'iopt_typ', None) == 'equip':
            return c
    for lib in (c for c in carpetas if getattr(c, 'iopt_typ', None) == 'lib'):
        for c in lib.GetContents('*.IntPrjfolder') or []:
            if getattr(c, 'iopt_typ', None) == 'equip':
                return c
        return lib
    return None


def leer_tipos(app, clases, otro=None, nombre_otro: str = '') -> list[dict]:
    """Los tipos de las tres bibliotecas, ordenados por clase, origen y nombre.

    042:RF-46: los de ``otro`` llevan el nombre con que se pidió: el proyecto puede conservar su nombre anterior, y quien busca el
    tipo lo busca por el nombre que pidió (Pisco, 2026-11-04: el nombre anterior frente a `CSG_Biblioteca_tipos`).
    """
    out = []
    origenes = [('proyecto', '', lambda c: app.GetLocalLibrary(c)),
                ('global', '', lambda c: app.GetGlobalLibrary(c))]
    if otro is not None:
        lib = biblioteca_de_otro(otro)
        origenes.append(('otro', nombre_otro or otro.loc_name, lambda _c: lib))
    for clase in clases:
        for origen, proyecto, carpeta in origenes:
            out += [ficha(o, origen, proyecto) for o in _tipos_en(carpeta(clase), clase)]
    return out


def copiar_tipo(app, original, nombre: str, cambios: dict | None = None) -> tuple[object, bool, str]:
    """El tipo con los datos del original y ``cambios``, en la biblioteca del proyecto.

    Devuelve ``(tipo, reutiliza, aviso)``. Si ya hay uno con ese nombre y esos datos, es
    ese (RF-62, RF-93); si lo hay con otros datos, la copia toma otro nombre y el aviso lo
    dice (RF-63). El original no se toca (RF-59): los cambios se escriben en la copia.
    """
    clase = original.GetClassName()
    local = app.GetLocalLibrary(clase)
    if local is None:
        raise RuntimeError('el proyecto activo no tiene biblioteca de tipos')
    datos = {**datos_tipo(original), **(cambios or {})}
    existentes = _tipos_en(local, clase)
    final, reutiliza, aviso = resolver_copia(
        nombre, clase, datos, {o.loc_name: Tipo(o.loc_name, clase, datos_tipo(o)) for o in existentes})
    if reutiliza:
        return next(o for o in existentes if o.loc_name.lower() == final.lower()), True, aviso
    # La biblioteca global no está en ningún proyecto: sin la comprobación de None, con el
    # proyecto activo sin resolver se tomaba por «el mismo» y se copiaba con AddCopy.
    de = _proyecto_de(original)
    if de is not None and de is app.GetActiveProject():
        nuevo = local.AddCopy(original, final)
    else:
        error, nuevo = local.PasteCopy(original)
        if error or nuevo is None:
            # Desde el proyecto biblioteca de los reguladores (025:RF-59), sin activar,
            # PasteCopy daba código 1 (Pisco, 2026-10-24): AddCopy y, si tampoco, un tipo nuevo
            # de la clase con los datos del original, que se comprueban abajo.
            try:
                nuevo = local.AddCopy(original, final)
            except Exception:  # noqa: BLE001 - se prueba la siguiente forma
                nuevo = None
            if nuevo is None:
                nuevo = local.CreateObject(clase, final)
                if nuevo is not None:
                    for atributo, valor in datos_tipo(original).items():
                        setattr(nuevo, atributo, valor)
            if nuevo is None:
                raise RuntimeError(f'DIgSILENT no dejó copiar el tipo {original.loc_name!r} '
                                   f'al proyecto (código {error})')
        nuevo.loc_name = final
    for atributo, valor in (cambios or {}).items():
        setattr(nuevo, atributo, valor)
    leidos = datos_tipo(nuevo)
    if not mismos_datos(leidos, datos):
        raise RuntimeError(f'La copia {final!r} no quedó con los datos pedidos: {leidos} '
                           f'en vez de {datos}')
    return nuevo, False, aviso


# =========================================================================== red
def _tension_de_cabecera(elm, barras: list[dict]) -> float | None:
    """La tensión de la barra de la cabecera; sin cabecera, la mayor del alimentador.

    La mayor sirve porque en un alimentador de media las barras de baja de las SED
    tienen menos tensión; la cabecera es la que manda si el ``ElmFeeder`` la tiene.
    """
    kv = getattr(cabecera_de(elm), 'uknom', None)
    if isinstance(kv, (int, float)) and kv > 0:
        return float(kv)
    tensiones = [b['kv'] for b in barras if b['kv']]
    return max(tensiones) if tensiones else None


def leer_alimentador(elm) -> dict:
    """Lo del alimentador que ofrece el formulario (RF-88), cada lista por nombre."""
    def nombre(o):
        return o.loc_name

    def tipo(o):
        return getattr(getattr(o, 'typ_id', None), 'loc_name', None)

    terminales = list(elm.GetObjs('ElmTerm'))
    cabecera = cabecera_de(elm)
    if cabecera is not None and all(b is not cabecera for b in terminales):
        terminales.append(cabecera)       # la migración la cambia también (RF-86)
    barras = [{'nombre': b.loc_name, 'kv': getattr(b, 'uknom', None)}
              for b in sorted(terminales, key=nombre)]
    return {
        'kv': _tension_de_cabecera(elm, barras),
        'barras': barras,
        'tramos': [{'nombre': ln.loc_name, 'tipo': tipo(ln), 'nlnum': int(getattr(ln, 'nlnum', 1) or 1),
                    'cable': es_cable(ln), 'largo_m': float(getattr(ln, 'dline', 0.0) or 0.0) * 1000.0}
                   for ln in sorted(elm.GetObjs('ElmLne'), key=nombre)],
        # La barra de media de cada SED: la migración cambia las de la parte que pasa (016:RF-54).
        'trafos': [{'nombre': tr.loc_name, 'tipo': tipo(tr),
                    'barra': getattr(getattr(getattr(tr, 'bushv', None), 'cterm', None), 'loc_name', None)}
                   for tr in sorted(elm.GetObjs('ElmTr2'), key=nombre)],
        'condensadores': [{'nombre': o.loc_name, 'kv': getattr(o, 'ushnm', None),
                           'barra': getattr(getattr(getattr(o, 'bus1', None), 'cterm', None), 'loc_name', None)}
                          for o in sorted(elm.GetObjs('ElmShnt'), key=nombre)],
        'reguladores': [{'nombre': o.loc_name, 'tipo': tipo(o)}
                        for o in sorted(elm.GetObjs('ElmVoltreg'), key=nombre)],
    }


# =========================================================================== órdenes
def bibliotecas(app, plan: dict) -> tuple[dict, int]:
    """Alimentadores y tipos para el formulario. Devuelve (informe, código de salida)."""
    clases = list(plan.get('clases') or CLASES_TIPO)
    informe: dict[str, Any] = {'project': plan.get('project'), 'clases': clases,
                               'alimentadores': {}, 'tipos': [], 'avisos': []}
    malas = sorted(set(clases) - set(CLASES_TIPO))
    if malas:
        return {**informe, 'error': f'clases de tipo desconocidas: {", ".join(malas)}'}, 2
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2

    alims = Alimentadores(app, proyecto, plan.get('feeders') or [])
    for f in alims.elegidos:
        elm = alims.elm.get(f)
        if elm is None:
            informe['avisos'].append(f'El alimentador {f} no está en el proyecto.')
            continue
        informe['alimentadores'][f] = leer_alimentador(elm)

    # 042:RF-40: a la tensión que se lee de cada alimentador, para cualquier empresa.
    tensiones = sorted({float(a['kv']) for a in informe['alimentadores'].values() if a.get('kv')})
    if plan.get('secciones_nuevas') and tensiones:
        # 042:RF-30: los normalizados que no están en ninguna biblioteca, desde su ficha.
        from convertersmartgrid.catalog import filas_de_conductores, tipo_de_ficha
        from convertersmartgrid.reglas import catalogo_del_proyecto

        filas = filas_de_conductores(catalogo_del_proyecto())
        conductores = [t for c in plan['secciones_nuevas'] for kv in tensiones if (t := tipo_de_ficha(c, kv, filas)) is not None]
        informe['conductores_creados'] = crear_tipos_conductor(app, conductores, informe['avisos'])
        if app.GetActiveProject() is not proyecto:
            proyecto.Activate()
    if plan.get('crear_reguladores') and tensiones:
        # 042:RF-34: sin esto, todas las variantes con regulador fallaban por el tipo que faltaba.
        reguladores, _codigo = crear_tipos_regulador(app, {'tensiones_kv': tensiones})
        informe['avisos'] += list(reguladores.get('avisos') or []) + ([reguladores['error']] if reguladores.get('error') else [])
        informe['reguladores_creados'] = [r['nombre'] for r in reguladores.get('creados') or []]
        if app.GetActiveProject() is not proyecto:
            proyecto.Activate()
    otro = None
    ruta = plan.get('otro_proyecto')
    if ruta:
        otro = buscar_proyecto(app, ruta, plan.get('folder') or nombre_de_perfil())
        if otro is None:
            informe['avisos'].append(f'No existe el proyecto {ruta!r}: se listan solo los tipos '
                                     'del proyecto y de la biblioteca global.')
        elif otro is proyecto:
            informe['avisos'].append(f'{ruta!r} es el mismo proyecto: sus tipos ya están listados.')
            otro = None
        elif biblioteca_de_otro(otro) is None:
            informe['avisos'].append(f'El proyecto {ruta!r} no tiene biblioteca de tipos.')
            otro = None
    informe['tipos'] = leer_tipos(app, clases, otro, str(plan.get('otro_proyecto') or ''))
    return informe, 0


#: Proyecto de DIgSILENT, en la carpeta del usuario, con los tipos de catálogo (025:RF-59).
#: La biblioteca global no deja escribir al usuario (sonda del 2026-10-24: ``CreateObject``
#: en ``\Lib`` y sus carpetas devuelve nada); las obras lo leen como «otro proyecto».
BIBLIOTECA_TIPOS = 'CSG_Biblioteca_tipos'


def _proyecto_biblioteca(app, nombre: str, avisos: list[str]):
    """El proyecto biblioteca y su carpeta de tipos; se crean si faltan."""
    from convertersmartgrid.util import NOMBRES_ANTERIORES_PF

    usuario = app.GetCurrentUser()
    proyectos = usuario.GetContents('*.IntPrj') or []
    proyecto = next((p for p in proyectos if p.loc_name == nombre), None)
    if proyecto is None and nombre in NOMBRES_ANTERIORES_PF:
        # La biblioteca de antes del cambio de nombre, con los tipos que ya usan las obras.
        proyecto = next((p for p in proyectos if p.loc_name == NOMBRES_ANTERIORES_PF[nombre]), None)
    if proyecto is not None and biblioteca_de_otro(proyecto) is None and not proyecto.GetContents('*'):
        # Uno vacío, de un intento con ``CreateObject('IntPrj')``: DIgSILENT no deja crearle
        # carpetas así (2026-10-24), y vacío no guarda nada.
        proyecto.Delete()
        proyecto = None
    if proyecto is None:
        if hasattr(app, 'CreateProject'):
            proyecto = app.CreateProject(nombre, 'Red')
        else:
            proyecto = usuario.CreateObject('IntPrj', nombre)
            lib = proyecto.CreateObject('IntPrjfolder', 'Library')
            lib.iopt_typ = 'lib'
            lib.CreateObject('IntPrjfolder', 'Equipment Type Library').iopt_typ = 'equip'
        if proyecto is None:
            raise RuntimeError(f'DIgSILENT no dejó crear el proyecto {nombre!r} en la carpeta del usuario')
        avisos.append(f'Se creó el proyecto {nombre!r} en la carpeta del usuario para los tipos de catálogo.')
    equip = biblioteca_de_otro(proyecto)
    if equip is None:
        proyecto.Activate()
        equip = app.GetProjectFolder('equip', 1)
    if equip is None:
        raise RuntimeError(f'el proyecto {nombre!r} no tiene biblioteca de tipos')
    return proyecto, equip


def _iguales(leidos: dict, pedidos: dict) -> bool:
    """DIgSILENT guarda en coma flotante simple: 22,9/√3 vuelve como 13,2213…"""
    return all(isinstance(leidos.get(k), (int, float)) and math.isclose(float(leidos[k]), float(v), rel_tol=1e-5)
               for k, v in pedidos.items())


def crear_tipos_conductor(app, conductores: list[dict], avisos: list[str]) -> list[str]:
    """042:RF-30: un ``TypLne`` en el proyecto biblioteca por cada conductor que no tiene ningún tipo de su código a
    su tensión (±10 %) en el proyecto, la biblioteca global o la de tipos. Devuelve los nombres creados."""
    try:
        _p, equip = _proyecto_biblioteca(app, BIBLIOTECA_TIPOS, avisos)
    except RuntimeError as exc:
        avisos.append(f'No se crearon los conductores normalizados: {exc}')
        return []
    existentes = (_tipos_en(app.GetLocalLibrary('TypLne'), 'TypLne') + _tipos_en(app.GetGlobalLibrary('TypLne'), 'TypLne')
                  + _tipos_en(equip, 'TypLne'))

    def a_tension(o, kv) -> bool:
        return abs(float(getattr(o, 'uline', 0) or 0) - kv) <= 0.1 * kv

    creados = []
    for c in conductores:
        kv = float(c['kv'])
        if any(o.loc_name.upper().startswith(c['codigo'].upper()) and a_tension(o, kv) for o in existentes):
            continue
        # En la biblioteca del proyecto activo: en la del proyecto biblioteca, sin activarlo, DIgSILENT no deja
        # crear un TypLne (Pisco, 2026-11-03: CreateObject devolvió None para AA24003D).
        local = app.GetLocalLibrary('TypLne')
        tipo = (local.CreateObject('TypLne', c['nombre']) if local is not None else None) or equip.CreateObject('TypLne', c['nombre'])
        if tipo is None:
            avisos.append(f"DIgSILENT no dejó crear el tipo {c['nombre']!r} (042:RF-30).")
            continue
        ref = next((o for o in existentes if a_tension(o, kv)), None)
        if ref is not None and getattr(ref, 'frnom', None):
            tipo.frnom = ref.frnom                                   # la frecuencia de la red, no la de fábrica
        for atributo, valor in c['datos'].items():
            setattr(tipo, atributo, valor)
        leidos = {a: getattr(tipo, a, None) for a in c['datos']}
        if not _iguales(leidos, c['datos']):
            tipo.Delete()
            avisos.append(f"El tipo {c['nombre']!r} no quedó con los datos de su ficha: {leidos} (042:RF-30).")
            continue
        existentes.append(tipo)
        creados.append(c['nombre'])
        avisos.append(f"Se creó el tipo {c['nombre']} en la biblioteca del proyecto: {c['datos']['sline'] * 1000:.0f} A, "
                      f"R {c['datos']['rline']:.4f} Ω/km, de su ficha ({c.get('fuente') or 'catálogo'}) (042:RF-30).")
    return creados


def crear_tipos_regulador(app, plan: dict) -> tuple[dict, int]:
    """Los ``TypVoltreg`` del catálogo para cada tensión del plan, en el proyecto biblioteca
    (025:RF-59). Los que ya existen con ese nombre no se tocan ni se duplican."""
    from convertersmartgrid.catalogo_reguladores import CatalogoError, FABRICANTE, unidades_para

    nombre = plan.get('biblioteca') or BIBLIOTECA_TIPOS
    informe: dict[str, Any] = {'biblioteca': nombre, 'fabricante': FABRICANTE,
                               'creados': [], 'existentes': [], 'avisos': []}
    try:
        _proyecto, equip = _proyecto_biblioteca(app, nombre, informe['avisos'])
    except RuntimeError as exc:
        return {**informe, 'error': str(exc)}, 2
    existentes = {o.loc_name.lower() for o in _tipos_en(equip, 'TypVoltreg')}
    for kv in sorted({float(k) for k in plan.get('tensiones_kv') or []}):
        try:
            unidades = unidades_para(kv)
        except CatalogoError as exc:
            informe['avisos'].append(str(exc))
            continue
        for u in unidades:
            if u.nombre.lower() in existentes:
                informe['existentes'].append(u.nombre)
                continue
            tipo = equip.CreateObject('TypVoltreg', u.nombre)
            if tipo is None:
                # 042:RF-34: sin activar, DIgSILENT no deja escribir en el proyecto biblioteca (Pisco, 2026-11-03).
                _proyecto.Activate()
                equip = app.GetProjectFolder('equip', 1) or equip
                tipo = equip.CreateObject('TypVoltreg', u.nombre)
            if tipo is None:
                return {**informe, 'error': f'DIgSILENT no dejó crear el tipo {u.nombre!r}'}, 2
            for atributo, valor in u.datos_tipo().items():
                setattr(tipo, atributo, valor)
            try:
                tipo.desc = [u.descripcion()]
            except Exception:  # noqa: BLE001, S110 - la descripción no decide nada
                pass
            leidos = {a: getattr(tipo, a, None) for a in u.datos_tipo()}
            if not _iguales(leidos, u.datos_tipo()):
                tipo.Delete()
                return {**informe, 'error': f'el tipo {u.nombre!r} no quedó con los datos del catálogo: {leidos}'}, 2
            existentes.add(u.nombre.lower())
            informe['creados'].append({'nombre': u.nombre, 'kv': kv, 'corriente_a': u.corriente_a,
                                       'unidad_v': u.tension_unidad_v})
    print(f"Tipos de regulador: {len(informe['creados'])} creados, "
          f"{len(informe['existentes'])} ya estaban, en {nombre}.")
    return informe, 0


# =========================================================================== aplicar
class Contexto:
    """Lo que recibe el constructor de una obra, con su variación ya grabando.

    Clase normal y no ``dataclass``: las pruebas cargan este guion sin registrarlo en
    ``sys.modules``, y ``dataclasses`` lo busca ahí al resolver las anotaciones.
    """

    def __init__(self, app, proyecto, obra: Obra, fila: dict, red: RedAlimentador, elm, *,
                 alims=None, redes=None, plan=None):
        self.app, self.proyecto, self.obra, self.fila, self.red = app, proyecto, obra, fila, red
        self.elm = elm
        """El ``ElmFeeder`` del alimentador de la obra."""
        self.alims = alims
        self.redes = dict(redes or {})
        """Las redes leídas de todos los alimentadores: el enlace necesita la del que cede."""
        self.plan = dict(plan or {})
        self.casos: dict = {}
        """098:RF-34: los casos de la obra por su papel; el flujo que la obra ajusta es el de cada uno."""
        self.tipos: dict = {}
        """``(clase, nombre del original)`` → tipo copiado o reutilizado en el proyecto."""
        self.copias: dict = {}
        """Nombre que planificó la simulación → tipo copiado: si al copiar hubo que darle
        otro nombre (RF-63), el constructor sigue encontrándolo por el planificado."""

    def tipo(self, clase: str, nombre: str):
        """El tipo que la fila manda asignar: una copia de esta obra o uno del proyecto."""
        if nombre in self.copias:
            return self.copias[nombre]
        hallado = next((o for o in _tipos_en(self.app.GetLocalLibrary(clase), clase)
                        if o.loc_name.lower() == nombre.lower()), None)
        if hallado is None:
            raise RuntimeError(f'no está el tipo {nombre!r} ({clase}) en la biblioteca del proyecto')
        return hallado

    def objeto(self, clase: str, nombre: str):
        """El elemento del alimentador con ese nombre; error si no está."""
        candidatos = list(self.elm.GetObjs(clase))
        if clase == 'ElmTerm' and cabecera_de(self.elm) is not None:
            candidatos.append(cabecera_de(self.elm))
        hallado = next((o for o in candidatos if o.loc_name == nombre), None)
        if hallado is None:
            raise RuntimeError(f'no está {nombre!r} ({clase}) en el alimentador '
                               f'{self.obra.alimentador}')
        return hallado


#: Clase de obra → la función que la construye dentro de su variación (T13 a T15, abajo);
#: una clase sin constructor se rechaza al aplicar, no a medias.
CONSTRUCTORES: dict[str, Callable[[Contexto], None]] = {}

#: Nombre de caso → su rol en ``casos_pf``.
ROL_DE_CASO = {nombre: rol for rol, nombre in NOMBRES.items()}


# =========================================================================== constructores
#: ``ElmShnt.shtype``: 2 es «C», solo condensador (localización en-GB de PF 2024).
SHUNT_C = 2


def principio_del_tramo(elm, linea) -> tuple:
    """``(cubículo, barra)`` del extremo del tramo más cercano a la cabecera.

    Se recorre la red del alimentador desde la barra de su cabecera: el orden de los
    cubículos (``obj_bus``) dice cómo se dibujó el tramo en el export, no hacia dónde
    fluye la potencia, y un tramo dibujado al revés dejaría el reconectador o el
    regulador aguas abajo de lo que protege o regula.
    """
    cabecera = cabecera_de(elm)
    if cabecera is None:
        raise RuntimeError(f'el alimentador {elm.loc_name} no tiene cabecera: no se sabe dónde '
                           'empieza cada tramo')
    barras = list(elm.GetObjs('ElmTerm'))
    if all(clave_pf(b) != clave_pf(cabecera) for b in barras):
        barras.append(cabecera)
    extremos: dict[int, list] = {}
    cubiculos = {}
    for barra in barras:
        cubiculos[clave_pf(barra)] = list(barra.GetContents('*.StaCubic') or [])
        for cub in cubiculos[clave_pf(barra)]:
            elemento = getattr(cub, 'obj_id', None)
            if elemento is not None:
                extremos.setdefault(clave_pf(elemento), []).append((barra, cub))
    distancia = {clave_pf(cabecera): 0}
    cola = [cabecera]
    while cola:
        barra = cola.pop(0)
        for cub in cubiculos.get(clave_pf(barra), []):
            elemento = getattr(cub, 'obj_id', None)
            if elemento is None:                     # cubículo vacío: no lleva a ninguna barra
                continue
            for otra, _ in extremos.get(clave_pf(elemento), []):
                if clave_pf(otra) not in distancia:
                    distancia[clave_pf(otra)] = distancia[clave_pf(barra)] + 1
                    cola.append(otra)
    lados = [(distancia[clave_pf(b)], i, b, c) for i, (b, c) in enumerate(extremos.get(clave_pf(linea), []))
             if clave_pf(b) in distancia]
    if not lados:
        raise RuntimeError(f'el tramo {linea.loc_name} no tiene camino hasta la cabecera')
    _, _, barra, cub = min(lados)
    return cub, barra


def _aviso_del_flujo(ctx, atributo: str, que: str) -> None:
    """Avisa si el flujo de carga del caso no ajusta lo que la obra deja regulando."""
    ldf = ctx.app.GetFromStudyCase('ComLdf')
    if ldf is not None and not getattr(ldf, atributo, 0):
        ctx.fila['avisos'].append(
            f'El flujo de carga del caso no tiene activo el ajuste automático de {que} '
            f'(ComLdf.{atributo}): la obra queda con la consigna puesta, pero no regula en los '
            'estudios hasta que se active.')


def _ldf_del_caso(app, caso):
    """098:RF-34: el ``ComLdf`` de ``caso``, sin depender de cuál esté activo.

    La obra se construye con activo el primero de sus casos (``_aplicar_una``), que puede ser «Sin proyecto»: activar el
    ajuste en el flujo del caso activo no lo activaba en «Con proyecto», donde se mide. Las órdenes de cálculo cuelgan del
    caso; si no se encuentra la suya, el del caso activo solo si ``caso`` es el activo.
    """
    if caso is not None and hasattr(caso, 'GetContents'):
        propio = next(iter(caso.GetContents('*.ComLdf') or []), None)
        if propio is not None:
            return propio
    activo = app.GetActiveStudyCase()
    if caso is None or activo is caso or (activo is not None and _ruta_de(activo) == _ruta_de(caso)):
        return app.GetFromStudyCase('ComLdf')
    return None


def anotar_valor(ctx, clase: str, obj, atributo: str, nuevo, caso=None) -> None:
    """098:RF-34: como :func:`abrir`: anota el valor de ``atributo`` en la fila y en disco antes de cambiarlo, y lo cambia.

    Si la orden muere tras cambiarlo, la siguiente lo restituye (081:RF-82); al borrar la variante evaluada, también.
    """
    anotar_valores(ctx, [(clase, obj, atributo, nuevo, caso)])


def anotar_valores(ctx, cambios: list[tuple]) -> None:
    """098:RF-34: :func:`anotar_valor` de un lote ``(clase, objeto, atributo, nuevo, caso)``, con el registro de disco
    escrito una vez: con cientos de transformadores con toma, una escritura por cada uno tardaba más que la medida."""
    if not cambios:
        return
    entradas_nuevas = []
    for clase, obj, atributo, _nuevo, caso in cambios:
        caso = caso if caso is not None else ctx.app.GetActiveStudyCase()
        if clase == 'ComLdf' and not ctx.plan.get('evaluando'):
            _guardar_original(ctx.plan, caso, atributo, getattr(obj, atributo, 0))           # 098:RF-34
        e = {'clase': clase, 'nombre': getattr(obj, 'loc_name', '') or '', 'ruta': _ruta_de(obj), 'atributo': atributo,
             'valor': getattr(obj, atributo, 0), 'nuevo': _nuevo, 'caso': getattr(caso, 'loc_name', '') or '',
             'caso_ruta': _ruta_de(caso) if caso is not None else ''}
        ctx.fila.setdefault('valores', []).append(e)
        entradas_nuevas.append(e)
    if ctx.plan.get('project'):
        ruta = fichero_aperturas(ctx.plan)
        entradas = leer_aperturas(ruta)
        entradas += [{**e, 'proyecto': ctx.plan['project'], 'variacion': ctx.fila.get('variacion') or '',
                      'evaluando': bool(ctx.plan.get('evaluando')), 'fecha': time.strftime('%Y-%m-%dT%H:%M:%S'),
                      'accion': 'valor'} for e in entradas_nuevas]
        try:
            escribir_aperturas(ruta, entradas)
        except OSError as exc:
            ctx.fila.setdefault('avisos', []).append(f'No se pudo anotar en disco el cambio de {len(cambios)} valor(es): '
                                                     f'{exc}; si la orden muere, no se restituirán solos (098:RF-34).')
    for _clase, obj, atributo, nuevo, _caso in cambios:
        setattr(obj, atributo, nuevo)


def _activar_en_el_flujo(ctx, atributo: str, que: str, propios=()) -> None:
    """098:RF-34: el flujo de cada caso de la obra ajusta lo que la obra deja regulando; si no lo hacía, se activa y se anota.

    CHN102 (2026-11-07): con ``ComLdf.iopt_at = 0`` las variantes con «+ regulador 500 A» y «300 A» daban la misma
    tensión que sin él (0,956 frente a 0,956): el regulador se quedaba en su toma central. Al borrar la variante
    evaluada, el flujo vuelve a como estaba (como lo abierto, 081:RF-81); en la obra aplicada, se queda y se dice.
    """
    casos = list((getattr(ctx, 'casos', None) or {}).values()) or [ctx.app.GetActiveStudyCase()]
    activados = []
    for caso in casos:
        nombre = getattr(caso, 'loc_name', '') or ''
        ldf = _ldf_del_caso(ctx.app, caso)
        if ldf is None:
            ctx.fila['avisos'].append(f'No se encontró el flujo de carga de «{nombre}»: la obra no regula allí hasta que se '
                                      f'active su ajuste automático de {que} (ComLdf.{atributo}) (098:RF-34).')
            continue
        if getattr(ldf, atributo, 0):
            continue
        anotar_valor(ctx, 'ComLdf', ldf, atributo, 1, caso)
        activados.append(nombre)
        ctx.fila['avisos'].append(f'Se activa el ajuste automático de {que} del flujo de «{nombre}» (ComLdf.{atributo}): '
                                  'sin él la obra no regula (098:RF-34).')
    if activados and atributo == 'iopt_at':
        _otras_tomas(ctx, propios)


#: 098:RF-34, RF-36: anotaciones del registro que no son una apertura de una obra: el valor del flujo antes de la
#: primera obra con regulador, el diario de una sustitución y la obra apartada de la medida.
ACCIONES_ESPECIALES = ('original', 'sustitucion', 'apartada')


def _guardar_original(plan: dict, caso, atributo: str, valor) -> None:
    """098:RF-34: el ``ComLdf.<atributo>`` del caso antes de la primera obra aplicada que lo activó, por proyecto y caso.

    Con dos obras con regulador, la segunda ya lo encontraba activo y no anotaba nada: retiradas las dos, el flujo se
    quedaba con el ajuste de tomas que no había puesto el operador. Se guarda una vez y se restituye al retirar la última
    obra con regulador (:func:`restituir_flujo_original`)."""
    if not plan.get('project'):
        return
    ruta = fichero_aperturas(plan)
    entradas = leer_aperturas(ruta)
    clave = (plan['project'], _ruta_de(caso), atributo)
    if any(e.get('accion') == 'original' and (e.get('proyecto'), e.get('caso_ruta'), e.get('atributo')) == clave
           for e in entradas):
        return
    entradas.append({'accion': 'original', 'proyecto': plan['project'], 'caso': getattr(caso, 'loc_name', '') or '',
                     'caso_ruta': _ruta_de(caso), 'clase': 'ComLdf', 'atributo': atributo, 'valor': valor,
                     'fecha': time.strftime('%Y-%m-%dT%H:%M:%S')})
    try:
        escribir_aperturas(ruta, entradas)
    except OSError:
        pass


def restituir_flujo_original(app, plan: dict, casos: dict, avisos: list[str]) -> int:
    """098:RF-34: el ajuste del flujo como estaba antes de la primera obra con regulador, cuando ya no queda ninguna
    variación activa con regulador en ese caso; mientras quede, sigue y se dice."""
    if not plan.get('project'):
        return 0
    ruta = fichero_aperturas(plan)
    entradas = leer_aperturas(ruta)
    if not any(e.get('accion') == 'original' and e.get('proyecto') == plan['project'] for e in entradas):
        return 0
    por_ruta = {_ruta_de(c): c for c in casos.values()}
    por_nombre = {c.loc_name: c for c in casos.values()}
    inicial = app.GetActiveStudyCase()
    hechos, quedan = 0, []
    try:
        for e in entradas:
            if e.get('accion') != 'original' or e.get('proyecto') != plan['project']:
                quedan.append(e)
                continue
            caso = por_ruta.get(e.get('caso_ruta')) or por_nombre.get(e.get('caso'))
            if caso is None:
                quedan.append(e)
                continue
            caso.Activate()
            otros = _reguladores_activos(app)
            if otros:
                avisos.append(f"El ajuste de tomas del flujo de «{e.get('caso')}» sigue activo: lo necesitan "
                              + ', '.join(otros[:5]) + ' (098:RF-34).')
                quedan.append(e)
                continue
            ldf = _ldf_del_caso(app, caso)
            if ldf is not None and getattr(ldf, e['atributo'], None) != e.get('valor'):
                setattr(ldf, e['atributo'], e.get('valor'))
                hechos += 1
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    if len(quedan) != len(entradas):
        try:
            escribir_aperturas(ruta, quedan)
        except OSError:
            pass
    return hechos


#: 098:RF-34: los atributos de toma automática de cada clase con tomas (``ElmTr3``, uno por devanado).
TOMAS_AUTOMATICAS = {'ElmTr2': ('ntrcn',), 'ElmTr3': ('ntrcn', 'ntrcn_h', 'ntrcn_m', 'ntrcn_l'), 'ElmVoltreg': ('ntrcn',)}


def _otras_tomas(ctx, propios=()) -> None:
    """098:RF-34: con el ajuste de tomas activado por la obra, los equipos con toma automática también regulan: los
    transformadores de dos y tres devanados y los reguladores que no son de esta obra.

    Midiendo, se dejan fijos (anotados en un solo lote): la variante tiene que cumplir por su obra, no porque se movieron
    otras tomas que sin ella no se movían. Aplicada, se dice cuáles regulan ahora en «Con proyecto».
    """
    mios = {_ruta_de(o) for o in propios or ()}
    otras = []
    for clase, atributos in TOMAS_AUTOMATICAS.items():
        for t in ctx.app.GetCalcRelevantObjects(f'*.{clase}') or []:
            if _ruta_de(t) in mios:
                continue
            for a in atributos:
                try:
                    valor = getattr(t, a)
                except AttributeError:
                    continue
                if int(valor or 0):
                    otras.append((clase, t, a))
    if not otras:
        return
    nombres = sorted({str(t.loc_name) for _c, t, _a in otras})
    lista = ', '.join(nombres[:10]) + (f' y {len(nombres) - 10} más' if len(nombres) > 10 else '')
    otras_n = len(nombres)
    if ctx.plan.get('evaluando'):
        anotar_valores(ctx, [(c, t, a, 0, None) for c, t, a in otras])
        ctx.fila['avisos'].append(f'Mientras se mide, {otras_n} equipo(s) con toma automática quedan con la toma '
                                  f'fija ({lista}): la variante no cumple gracias a ellos; al borrarla vuelven (098:RF-34).')
    else:
        ctx.fila['avisos'].append(f'Con el ajuste de tomas activo, también regulan {otras_n} equipo(s) con toma '
                                  f'automática: {lista} (098:RF-34).')


def restituir_valores(app, casos: dict, valores: list[dict], avisos: list[str]) -> int:
    """098:RF-34: lo que :func:`anotar_valor` cambió, como estaba, en el caso donde se cambió (por su nombre completo).

    En orden inverso: si el mismo atributo se anotó dos veces, el primero es el original."""
    por_ruta = {_ruta_de(c): c for c in casos.values()}
    por_nombre = {c.loc_name: c for c in casos.values()}
    inicial = app.GetActiveStudyCase()
    hechos = 0
    try:
        for e in reversed(valores):
            caso = por_ruta.get(e.get('caso_ruta')) or por_nombre.get(e.get('caso'))
            if caso is None and e.get('caso'):
                avisos.append(f"No está el caso «{e['caso']}»: {e.get('clase')} {e.get('nombre')}.{e['atributo']} queda "
                              'como lo dejó la obra (098:RF-34).')
                continue
            if caso is not None:
                caso.Activate()
            objs = ([_ldf_del_caso(app, caso)] if e.get('clase') == 'ComLdf'
                    else _con_nombre(app, e['clase'], e['nombre'], e.get('ruta')))
            if e.get('clase') == 'ComLdf' and e['atributo'] == 'iopt_at' and not e.get('valor'):
                otros = _reguladores_activos(app)
                if otros:
                    # 2 obras con regulador comparten el flujo: apagarlo al retirar una dejaba la otra sin regular.
                    avisos.append(f"El ajuste de tomas del flujo de «{e.get('caso')}» sigue activo: lo necesitan "
                                  + ', '.join(otros[:5]) + ' (098:RF-34).')
                    continue
            for o in objs:
                if o is not None and getattr(o, e['atributo'], None) != e['valor']:
                    setattr(o, e['atributo'], e['valor'])
                    hechos += 1
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    return hechos


def _reguladores_activos(app) -> list[str]:
    """098:RF-34: las variaciones activas en el caso activo que graban un regulador (o lo tienen en sus etapas)."""
    out = []
    for v in app.GetActiveNetworkVariations() or []:
        try:
            etapas = v.GetContents('*.IntSstage') or []
            if any(e.GetContents('*.ElmVoltreg', 1) for e in etapas):
                out.append(v.loc_name)
        except AttributeError:
            continue
    return sorted(out)


def restituir_el_flujo(app, casos: dict, filas: list[dict], plan: dict | None = None) -> list[str]:
    """098:RF-34: lo que :func:`_activar_en_el_flujo` y :func:`_otras_tomas` cambiaron, como estaba; los avisos."""
    valores = [e for f in filas for e in f.get('valores') or []]
    # Las filas de antes de anotar en disco: ``[caso, atributo, valor]`` del flujo.
    valores += [{'clase': 'ComLdf', 'caso': x[0], 'atributo': x[1], 'valor': x[2]}
                for f in filas for x in f.get('flujo_activado') or []]
    avisos: list[str] = []
    if valores:
        restituir_valores(app, casos, valores, avisos)
        if plan is not None:
            quitar_aperturas(plan, filas)
    return avisos


def _barra_con_tres_fases(ctx, barra):
    """La barra de un banco trifásico nuevo: la pedida o la compatible más cercana (081:RF-8).

    Un banco trifásico en una barra de dos fases dejó sin flujo toda la calibración de un sistema. Sin ninguna
    barra compatible, queda en la pedida y se avisa (081:RF-9): nunca se rechaza por sus fases.
    """
    from convertersmartgrid.comprobacion_fases import Barra, ubicar_nuevo

    fases = fases_de_barra
    if fases(barra) >= 3:
        return barra
    def distancia(b) -> float:
        return math.hypot(float(getattr(b, 'GPSlat', 0) or 0) - float(getattr(barra, 'GPSlat', 0) or 0),
                          float(getattr(b, 'GPSlon', 0) or 0) - float(getattr(barra, 'GPSlon', 0) or 0)) * 111_000.0

    otras = {b.loc_name: b for b in ctx.elm.GetObjs('ElmTerm')
             if b is not barra and math.isclose(float(b.uknom), float(barra.uknom), rel_tol=1e-3)}
    ubicacion = ubicar_nuevo('banco', ctx.obra.barra, 3, Barra(barra.loc_name, fases(barra)),
                             [(Barra(n, fases(b)), distancia(b)) for n, b in otras.items()])
    if ubicacion.nota:
        ctx.fila.setdefault('avisos', []).append(ubicacion.nota)
    return otras.get(ubicacion.barra, barra)


def construir_condensador(ctx) -> None:
    """Banco de condensadores en la barra, fijo o regulando por escalones (RF-71, RF-72)."""
    o = ctx.obra
    barra = ctx.objeto('ElmTerm', o.barra)
    barra = _barra_con_tres_fases(ctx, barra)                                   # 081:RF-8, RF-9
    red = barra.GetParent()
    banco = red.CreateObject('ElmShnt', nombre_libre(red, 'ElmShnt', f'Banco_{o.barra}'))
    cub = barra.CreateObject('StaCubic', nombre_pf(f'Cub_{banco.loc_name}'))
    cub.obj_id, cub.obj_bus = banco, 0
    banco.shtype = SHUNT_C
    banco.ushnm = float(barra.uknom)
    # ``qcapn`` es la potencia de un escalón: la total es escalones × qcapn (spec 012,
    # ComCapo instala sus bancos igual en DIgSILENT real).
    banco.qcapn = o.q_kvar / 1000.0 / o.escalones
    banco.ncapx = banco.ncapa = o.escalones
    n_fases = fases_de_barra(barra)
    adaptar_banco(banco, n_fases)                          # 081:RF-68: queda como dice el aviso
    if n_fases < 3:
        ctx.fila.setdefault('avisos', []).append(f'{banco.loc_name}: {cifras_de_banco(o.q_kvar, float(barra.uknom), n_fases)}')
    banco.i_cont = 0                                       # escalones discretos
    if o.consigna_pu:                                      # RF-72
        banco.iswitch = 1
        banco.usetp_mn = o.consigna_pu - BANDA_TENSION_PU
        banco.usetp_mx = o.consigna_pu + BANDA_TENSION_PU
        _aviso_del_flujo(ctx, 'iopt_asht', 'los escalones de los condensadores')
    else:
        banco.iswitch = 0


def construir_reconectador(ctx) -> None:
    """Interruptor con protección y reenganche al principio del tramo, sin relé (RF-73).

    Lo que usan la confiabilidad y la ubicación de reconectadores de DIgSILENT son las
    marcas del interruptor (``rel_hasProt``, ``rel_hasRecl``; comprobado en DIgSILENT real
    con la spec 012). El relé con su bloque ``RelRecl`` no se crea: sin su ``TypRelay``,
    DIgSILENT no calcula el flujo («missing type», NA203, 2026-10-24), y ese tipo es de las
    protecciones (RF-73b).
    """
    o = ctx.obra
    cub, _barra = principio_del_tramo(ctx.elm, ctx.objeto('ElmLne', o.tramo))
    interruptor = next(iter(cub.GetContents('*.StaSwitch') or []), None)
    if interruptor is None:
        interruptor = cub.CreateObject('StaSwitch', nombre_pf(f'Reconectador_{o.tramo}'))
    else:
        # Un cubículo admite un solo interruptor: el que ya tenía pasa a reconectador.
        ctx.fila['avisos'].append(f'El principio del tramo {o.tramo} ya tenía el interruptor '
                                  f'{interruptor.loc_name}: pasa a ser el reconectador.')
    interruptor.aUsage, interruptor.on_off = 'cbk', 1
    interruptor.rel_hasProt, interruptor.rel_hasRecl = 1, 1


def construir_regulador(ctx) -> None:
    """Regulador intercalado al principio del tramo, con una barra nueva (RF-75, RF-76).

    El cubículo del tramo pasa de su barra a la nueva y el regulador queda entre las
    dos: partir la línea cambiaría su longitud y su trazado GPS (spec 010).
    """
    o = ctx.obra
    cub, origen = principio_del_tramo(ctx.elm, ctx.objeto('ElmLne', o.tramo))
    red = origen.GetParent()
    nueva = red.CreateObject('ElmTerm', nombre_libre(red, 'ElmTerm', f'{o.tramo}_REG'))
    nueva.uknom = origen.uknom
    for atributo in ('iUsage', 'GPSlat', 'GPSlon'):
        if getattr(origen, atributo, None) is not None:
            setattr(nueva, atributo, getattr(origen, atributo))
    if nueva.Move(cub) != 0:
        # 025:RF-76: grabando en una variación DIgSILENT no deja mover el cubículo (PN107 y
        # SI213, 2026-10-24); el tramo pasa a un cubículo nuevo de la barra nueva, por el
        # mismo lado, como conecta la línea la obra de enlace.
        # La API da un envoltorio nuevo en cada acceso: se compara por nombre completo.
        cabeza = getattr(ctx.elm, 'obj_id', None)
        if cabeza is not None and clave_pf(cabeza) == clave_pf(cub):
            # Vaciar el cubículo de la cabecera dejaría el alimentador sin su principio.
            raise RuntimeError(f'el tramo {o.tramo} sale de la cabecera: el regulador va en uno '
                               'posterior de la troncal')
        linea = ctx.objeto('ElmLne', o.tramo)
        lado = int(getattr(cub, 'obj_bus', 0) or 0)
        cub.obj_id = None
        nuevo = nueva.CreateObject('StaCubic', nombre_pf(f'Cub_{o.tramo}_REG'))
        nuevo.obj_id, nuevo.obj_bus = linea, lado
        conectado = getattr(nuevo, 'obj_id', None)
        if conectado is None or clave_pf(conectado) != clave_pf(linea):
            raise RuntimeError(f'DIgSILENT no dejó pasar el tramo {o.tramo} a la barra nueva')
    regulador = red.CreateObject('ElmVoltreg', nombre_libre(red, 'ElmVoltreg', f'Regulador_{o.tramo}'))
    regulador.typ_id = ctx.tipo('TypVoltreg', ctx.fila['tipo'])
    # Lado S en la barra de origen (la fuente), lado L en la nueva (el tramo).
    for barra, lado, nombre in ((origen, 0, 'CubS'), (nueva, 1, 'CubL')):
        c = barra.CreateObject('StaCubic', nombre_pf(f'{nombre}_{regulador.loc_name}'))
        c.obj_id, c.obj_bus = regulador, lado
    regulador.usetp = o.consigna_pu
    regulador.usp_low = o.consigna_pu - BANDA_TENSION_PU
    regulador.usp_up = o.consigna_pu + BANDA_TENSION_PU
    regulador.ntrcn, regulador.i_cont, regulador.nntap1 = 1, 0, 0
    _activar_en_el_flujo(ctx, 'iopt_at', 'las tomas', propios=(regulador,))


def construir_seccion(ctx) -> None:
    """El tipo de línea de la obra en cada tramo que lista la fila (RF-77, RF-78).

    Los tramos y el tipo (copiado a la tensión del alimentador si hacía falta, RF-79) los
    decidió la simulación; los que ya lo tenían no están en la fila.
    """
    for e in ctx.fila['elementos']:
        # Con toda la troncal, los tramos de cable llevan su propio tipo (016:RF-7).
        ctx.objeto('ElmLne', e['elemento']).typ_id = ctx.tipo('TypLne', e.get('tipo') or ctx.fila['tipo'])


def construir_terna(ctx) -> None:
    """Una terna más en cada tramo de la fila, con el mismo tipo (RF-80) o con el de la obra (042:RF-98).

    Se suma a lo que el tramo tiene en el caso donde se crea la obra, que ya incluye las
    obras anteriores activas allí (dos obras sobre el mismo tramo se suman, casos límite).
    Si la simulación decidió que el conductor cambia, la fila trae su tipo: el tramo pasa a él
    antes de sumar la terna, para que los dos circuitos sean iguales (usuario, 2026-11-07).
    """
    for e in ctx.fila['elementos']:
        linea = ctx.objeto('ElmLne', e['elemento'])
        if e.get('tipo'):
            linea.typ_id = ctx.tipo('TypLne', e['tipo'])
        linea.nlnum = int(getattr(linea, 'nlnum', 1) or 1) + 1
        _instalar_ternas(ctx.fila, linea, getattr(ctx.obra, 'configuracion', ''))


def _instalar_ternas(fila: dict, linea, configuracion: str = '') -> None:
    """Las ternas subterráneas de un tramo: su configuración y su capacidad (084:RF-12 a RF-15).

    ``fline`` es el factor de reducción del ``ElmLne``: el tipo sigue siendo el del catálogo y es la
    línea la que lleva la capacidad para esa instalación. Sin el dato del fabricante no se toca.
    """
    tipo = getattr(linea, 'typ_id', None)
    inst = instalacion(tipo=getattr(tipo, 'loc_name', '') or '', ternas=int(getattr(linea, 'nlnum', 1) or 1),
                       cable=bool(es_cable(linea)), perfil=datos_perfil(), configuracion=configuracion)
    if inst is None:
        return
    factor = factor_de_capacidad(inst, float(getattr(tipo, 'sline', 0) or 0) * 1000)
    if factor is not None:
        linea.fline = factor
    fila.setdefault('instalaciones', []).append({**inst, 'tramo': linea.loc_name, 'factor': factor})
    fila['avisos'] += [a for a in inst['avisos'] if a not in fila['avisos']]


def _trazados_de_la_red(app) -> list:
    """El trazado de cada línea calculable: la red de la que la SET nueva se aparta (084:RF-9)."""
    out = []
    for ln in app.GetCalcRelevantObjects('*.ElmLne') or []:
        puntos = trazado_de(ln) or tuple(p for p in (gps_de(getattr(getattr(ln, c, None), 'cterm', None))
                                                     for c in ('bus1', 'bus2')) if p is not None)
        if puntos:
            out.append((ln.loc_name, puntos))
    return out


def _ambos_flujos(app) -> dict:
    """El flujo equilibrado y el desequilibrado en el punto final; deja el modo y los resultados (084:RF-8).

    Una SET reubicada a mano solo quedó aceptada con los dos (2026-11-02). Con líneas de menos de tres
    fases ``flujo_de_carga`` obliga al desequilibrado (054:RF-7): se dice el modo que corrió de verdad.
    """
    ldf = app.GetFromStudyCase('ComLdf')
    inicial = getattr(ldf, 'iopt_net', 0)
    out = {}
    try:
        for nombre, modo in (('equilibrado', 0), ('desequilibrado', 1)):
            ldf.iopt_net = modo
            f = flujo_de_carga(app)
            out[nombre] = {'converge': f['converged'], 'vmin': f.get('vm_min'), 'vmax': f.get('vm_max'),
                           'modo': int(getattr(ldf, 'iopt_net', modo) or 0)}
    finally:
        ldf.iopt_net = inicial
    flujo_de_carga(app)
    return out


#: Clase de elemento → clase de su tipo, para los cambios de tipo de la migración.
TIPO_DE_ELEMENTO = {'ElmLne': 'TypLne', 'ElmTr2': 'TypTr2', 'ElmVoltreg': 'TypVoltreg'}


def _fuentes_en(barra) -> list:
    """Las redes externas (``ElmXnet``) conectadas a la barra."""
    return [c.obj_id for c in barra.GetContents('*.StaCubic') or []
            if getattr(c, 'obj_id', None) is not None and c.obj_id.GetClassName() == 'ElmXnet']


def construir_tension(ctx) -> None:
    """El alimentador entero a la tensión nueva, elemento a elemento (RF-81 a RF-86, RF-96
    a RF-103).

    Aplica exactamente lo que listó la simulación: ``uknom`` de las barras de media y de
    la cabecera, una copia de tipo a la tensión nueva para cada tipo de línea, de SED
    (solo la alta) y de regulador, y ``ushnm`` de los condensadores de media. No crea
    barras ni transformadores (RF-96) y solo toca lo del alimentador (RF-97). La fuente
    queda en su barra con su consigna en p.u. (RF-100, RF-101).

    No se usa ``ComFeedertool`` (plan, T15): con su tolerancia de tensión del 30 % no
    cambia el tipo de una línea si la tensión nueva está cerca, sus tipos nuevos no llevan
    el sufijo del conversor y el objeto de enlace que exige no es ``ComLink``.
    """
    destino = ctx.obra.kv_destino
    for e in ctx.fila['elementos']:
        elemento = ctx.objeto(e['clase'], e['elemento'])
        if e['clase'] == 'ElmTerm':
            elemento.uknom = destino
        elif e['clase'] == 'ElmShnt':
            elemento.ushnm = destino
        else:
            elemento.typ_id = ctx.tipo(TIPO_DE_ELEMENTO[e['clase']], e['tipo'])
    cabecera = cabecera_de(ctx.elm)
    fuentes = _fuentes_en(cabecera) if cabecera is not None else []
    if not fuentes:
        ctx.fila['avisos'].append('No hay ninguna red externa en la barra de cabecera: '
                                  'compruebe en DIgSILENT de dónde se alimenta.')
    for fuente in fuentes:                                              # RF-101
        pu = float(getattr(fuente, 'usetp', 1.0) or 1.0)
        ctx.fila['avisos'].append(
            f'La fuente {fuente.loc_name} queda en {cabecera.loc_name} con su consigna de '
            f'{pu:g} p.u., que a {destino:g} kV son {pu * destino:.3f} kV.')


def _limites(plan: dict):
    """Los de los estudios (011:RF-35): del perfil de empresa, con los que cambie el plan."""
    try:
        return limites_de_perfil().con(**{k: v for k, v in (plan.get('limites') or {}).items()
                                          if k in ('tension_min_pu', 'tension_max_pu',
                                                   'cargabilidad_max_pct')})
    except EstudiosError as exc:
        raise RuntimeError(str(exc)) from None


def _dentro(red, medida_flujo: dict, limites) -> tuple[list[str], dict]:
    """Tramos de la troncal con sus dos barras dentro de tensión y su carga bajo el límite (016:RF-26).

    Devuelve los tramos y, para avisar (RF-30, RF-32), la tensión mínima y la cargabilidad
    máxima de la troncal con su barra y su tramo.
    """
    u = dict(medida_flujo['barras'])
    carga = {n: c for n, _clase, c in medida_flujo['elementos']}
    por_nombre = red.topologia.por_nombre()
    dentro, peor_u, peor_c = [], None, None
    for nombre in red.troncal:
        tramo = por_nombre[nombre]
        tensiones = [(u[b], b) for b in (tramo.desde, tramo.hasta) if u.get(b) is not None]
        for v in tensiones:
            peor_u = v if peor_u is None or v[0] < peor_u[0] else peor_u
        c = carga.get(nombre)
        if c is not None:
            peor_c = (c, nombre) if peor_c is None or c > peor_c[0] else peor_c
        ok_u = len(tensiones) == 2 and all(limites.tension_min_pu <= v <= limites.tension_max_pu
                                           for v, _ in tensiones)
        if ok_u and (c is None or c < limites.cargabilidad_max_pct):
            dentro.append(nombre)
    return dentro, {'u': peor_u, 'carga': peor_c}


def _conexion_indicada(texto: str, red, tramos, minima, quien: str) -> Conexion:
    """La barra o el punto que indica el operador (016:RF-31): un punto, sobre su troncal."""
    punto = punto_indicado(texto)
    if punto is None:
        barra = red.topologia.barras.get(texto)
        if barra is None:
            raise RuntimeError(f'la barra {texto} no es del alimentador {quien}')
        return Conexion('', 0.0, barra.gps or (0.0, 0.0), 0.0, barra=texto)
    conexion = punto_en_troncal(red.topologia, tramos, punto, minima)
    if conexion is None:
        raise RuntimeError(f'ningún tramo de la troncal de {quien} tiene coordenadas')
    return conexion


def _barra_de(ctx, conexion: Conexion, f: str, lado: str):
    """La barra donde se engancha el enlace: la indicada, o la que deja partir el tramo (RF-29)."""
    elm = ctx.alims.elm[f]
    if not conexion.parte:
        barras = list(elm.GetObjs('ElmTerm'))
        cabecera = cabecera_de(elm)
        if cabecera is not None:
            barras.append(cabecera)
        hallada = next((b for b in barras if b.loc_name == conexion.barra), None)
        if hallada is None:
            raise RuntimeError(f'no está la barra {conexion.barra} en el alimentador {f}')
        return hallada
    linea = next((ln for ln in elm.GetObjs('ElmLne') if ln.loc_name == conexion.tramo), None)
    if linea is None:
        raise RuntimeError(f'no está el tramo {conexion.tramo} en el alimentador {f}')
    nombre = nombre_libre(linea.GetParent(), 'ElmTerm', f'ENLACE_{lado}_{feeder_short_name(f)}')
    barra, _ = partir_tramo(ctx.app, linea, conexion.fraccion, nombre, gps=conexion.gps)
    return barra


def _describir(conexion: Conexion) -> dict:
    return {'tramo': conexion.tramo, 'barra': conexion.barra, 'parte': conexion.parte,
            'fraccion': round(conexion.fraccion, 4), 'gps': list(conexion.gps)}


def construir_enlace(ctx) -> None:
    """Línea nueva entre dos alimentadores, abierta del lado del que cede (016:RF-26 a RF-43).

    El caso es «Con proyecto» y la variación de la obra ya graba. El flujo de antes del
    enlace decide los tramos de la troncal del que recibe donde puede engancharse (RF-26);
    los dos puntos los da ``troncal.extremos_del_enlace`` (RF-27, RF-28) o el operador
    (RF-31). Cada punto parte su tramo dentro de la variación, o usa la barra si está a
    menos de la distancia mínima (RF-20). La línea va en recta, con el trazado de sus dos
    extremos, y el seccionador del lado del que cede queda abierto: IN111 es de 10 kV y
    TA225 de 22,9 kV, y cerrado el flujo no converge (usuario, 2026-10-14). Nunca se cierra
    aquí (RF-62).
    """
    o, app, fila = ctx.obra, ctx.app, ctx.fila
    recibe, cede = ctx.red, ctx.redes.get(o.cede)
    if cede is None or cede.topologia is None or recibe.topologia is None:
        raise RuntimeError(f'no se leyó la red de {o.alimentador} o de {o.cede}')
    limites = _limites(ctx.plan)
    flujo = flujo_de_carga(app)
    candidatos, peor, medido = list(recibe.troncal), {}, None
    if flujo['converged']:
        medido = medida(ctx.elm)
        candidatos, peor = _dentro(recibe, medido, limites)
    elif not o.origen:
        raise RuntimeError(f'el flujo de «Con proyecto» no converge antes del enlace: no se sabe '
                           f'qué tramos de {o.alimentador} están dentro de los límites; indique '
                           f'el punto de origen')
    if not o.origen and not candidatos:                                    # RF-30
        u = peor.get('u') or (None, '?')
        c = peor.get('carga') or (None, '?')
        raise RuntimeError(
            f'ningún tramo de la troncal de {o.alimentador} está dentro de los límites '
            f'({limites.tension_min_pu:g} a {limites.tension_max_pu:g} p.u., '
            f'{limites.cargabilidad_max_pct:g} %): tensión mínima {u[0]} p.u. en {u[1]}, '
            f'cargabilidad máxima {c[0]} % en {c[1]}')
    minima = o.minima_m
    try:
        if o.origen:
            salida = _conexion_indicada(o.origen, recibe, recibe.troncal, minima, o.alimentador)
        if o.destino:
            llegada = _conexion_indicada(o.destino, cede, cede.troncal, minima, o.cede)
        if not o.origen and not o.destino:
            salida, llegada = extremos_del_enlace(recibe.topologia, candidatos, cede.topologia,
                                                  cede.troncal, minima)
        elif not o.destino:
            llegada = punto_en_troncal(cede.topologia, cede.troncal, salida.gps, minima)
        elif not o.origen:
            salida = punto_en_troncal(recibe.topologia, candidatos, llegada.gps, minima)
    except TroncalError as exc:                                                       # RF-33
        raise RuntimeError(f'{exc}: no se crea el enlace; indique los dos puntos') from None
    if salida is None or llegada is None:
        raise RuntimeError('ningún tramo de las troncales tiene coordenadas: no se crea el '
                           'enlace; indique los dos puntos')
    if o.origen and medido is not None:                                           # RF-32
        por_nombre = recibe.topologia.por_nombre()
        if salida.parte:
            fuera, donde = salida.tramo not in candidatos, f'el tramo {salida.tramo}'
            barras_punto = (por_nombre[salida.tramo].desde, por_nombre[salida.tramo].hasta)
        else:
            fuera = not any(salida.barra in (por_nombre[n].desde, por_nombre[n].hasta)
                            for n in candidatos)
            donde, barras_punto = f'la barra {salida.barra}', (salida.barra,)
        if fuera:
            u = dict(medido['barras'])
            carga = {n: c for n, _clase, c in medido['elementos']}
            tensiones = ', '.join(f'{b} {u[b]:.3f} p.u.' for b in barras_punto if u.get(b) is not None)
            cargabilidad = carga.get(salida.tramo) if salida.parte else None
            fila['avisos'].append(
                f'El origen que indica el operador, {donde}, está fuera de los límites '
                f'({tensiones or "sin tensión"}'
                f'{f", cargabilidad {cargabilidad:.1f} %" if cargabilidad is not None else ""}): '
                f'se usa igual.')

    origen = _barra_de(ctx, salida, o.alimentador, 'R')
    destino = _barra_de(ctx, llegada, o.cede, 'C')
    a = gps_de(origen) or salida.gps
    b = gps_de(destino) or llegada.gps
    # RF-81 a RF-87: por la vía, con sus curvas, si el perfil habilita un enrutador.
    ruta = ruta_por_vias(tuple(a), tuple(b), datos_perfil().get('vias'))
    fila['avisos'] += ruta.avisos
    largo_m = ruta.largo_m
    red = origen.GetParent()
    linea = red.CreateObject('ElmLne', nombre_libre(red, 'ElmLne', f'Enlace_{o.alimentador}_{o.cede}'))
    linea.typ_id = ctx.tipo('TypLne', fila['tipo'])                                  # RF-38
    linea.dline = max(largo_m / 1000.0, 1e-6)                                         # RF-34
    # Entre tensiones distintas DIgSILENT no calcula con la línea en servicio, aunque el
    # seccionador esté abierto («Line is connected between different voltage levels»,
    # IN111 + TA225, 2026-10-15): queda fuera de servicio hasta que una migración iguale
    # las tensiones y la ponga en servicio (RF-76).
    distinta = not math.isclose(float(getattr(origen, 'uknom', 0) or 0),
                                float(getattr(destino, 'uknom', 0) or 0), rel_tol=1e-3)
    linea.nlnum, linea.outserv = 1, int(distinta)
    if distinta:
        fila['avisos'].append(
            f'{origen.loc_name} ({origen.uknom:g} kV) y {destino.loc_name} ({destino.uknom:g} kV) '
            f'tienen tensiones distintas: la línea {linea.loc_name} queda fuera de servicio '
            f'hasta migrar la parte de {o.cede} que pasa.')
    linea.SetAttribute('GPScoords', [list(p) for p in ruta.puntos])                  # RF-35
    cubiculos = []
    for lado, (barra, cola) in enumerate(((origen, o.alimentador), (destino, o.cede))):
        cub = barra.CreateObject('StaCubic', nombre_pf(f'Cub_{linea.loc_name}_{cola}'))
        cub.obj_id, cub.obj_bus = linea, lado
        cubiculos.append(cub)
    seccionador = cubiculos[1].CreateObject('StaSwitch', nombre_pf(f'SECC_{linea.loc_name}'))
    seccionador.aUsage, seccionador.on_off = 'dct', 0                                # RF-36
    if int(getattr(seccionador, 'on_off', 1)) != 0:                                   # RF-43
        raise RuntimeError(f'el seccionador {seccionador.loc_name} no quedó abierto')
    fila['enlace'] = {**fila.get('enlace', {}), 'linea': linea.loc_name,
                      'seccionador': seccionador.loc_name, 'largo_m': round(largo_m, 1),
                      'trazado': ruta.resumen(),
                      'origen': {**_describir(salida), 'barra_final': origen.loc_name},
                      'destino': {**_describir(llegada), 'barra_final': destino.loc_name},
                      'candidatos': len(candidatos)}


def _tipo_a_tension(ctx, objeto, clase: str, campo: str, origen: float, destino: float):
    """La copia a la tensión de destino del tipo de ``objeto`` (011:RF-82, RF-83, RF-99).

    La que copió la obra por la simulación si está; si no (una mitad que dejó un enlace de
    la misma tanda, que la simulación no conocía), se copia aquí con el mismo nombre y las
    mismas reglas, una vez por tipo original.
    """
    base = getattr(objeto, 'typ_id', None)
    if base is None:
        raise RuntimeError(f'{objeto.loc_name} no tiene tipo: no se sabe a qué copiarlo')
    hecho = ctx.tipos.get((clase, base.loc_name))
    if hecho is not None:
        return hecho
    datos = datos_tipo(base)
    if datos.get(campo) is not None and math.isclose(float(datos[campo]), destino):
        return base
    copia, _reutiliza, aviso = copiar_tipo(
        ctx.app, base, nombre_copia(base.loc_name, kv=destino, kv_origen=origen),
        {**datos, campo: destino})
    if aviso:
        ctx.fila['avisos'].append(aviso)
    ctx.tipos[(clase, base.loc_name)] = copia
    return copia


def _cubiculos(app, linea) -> list:
    """Los cubículos de los extremos de ``linea``: ``bus1``/``bus2`` en DIgSILENT; sin ellos
    (el doble de las pruebas), los del proyecto que la apuntan."""
    if hasattr(linea, 'bus1'):
        return [c for c in (linea.bus1, getattr(linea, 'bus2', None)) if c is not None]
    proyecto = app.GetActiveProject()
    return [c for c in (proyecto.GetContents('*.StaCubic', 1) if proyecto else [])
            if getattr(c, 'obj_id', None) is linea]


def _barras_de(app, linea) -> set[str]:
    return {c.cterm.loc_name for c in _cubiculos(app, linea)
            if getattr(c, 'cterm', None) is not None}


def _kw_sin_alimentar(ctx, fuera: set[str]) -> float:
    """La demanda escrita de las barras que dejan de alimentarse y de la baja de sus SED (017:RF-42f)."""
    barras = set(fuera)
    for trafo in ctx.elm.GetObjs('ElmTr2'):
        if getattr(getattr(getattr(trafo, 'bushv', None), 'cterm', None), 'loc_name', None) in fuera:
            baja = getattr(getattr(getattr(trafo, 'buslv', None), 'cterm', None), 'loc_name', None)
            if baja:
                barras.add(baja)
    return sum(float(getattr(c, 'plini', 0.0) or 0.0) * float(getattr(c, 'scale0', 1.0) or 1.0) * 1000.0
               for c in ctx.elm.GetObjs('ElmLod')
               if getattr(getattr(getattr(c, 'bus1', None), 'cterm', None), 'loc_name', None) in barras)


def construir_migracion_camino(ctx) -> None:
    """Solo el camino a la SED y las SED de sus barras, a la tensión de destino; se abren los ramales (017:RF-42, RF-42d).

    Se recalcula con la red de ahora, como la migración desde un nodo. Todo se comprueba antes de la primera escritura y
    se relee después: lo que lance una excepción aquí lo borra ``_grabar_una`` con su variación (RF-42e).
    """
    o, fila = ctx.obra, ctx.fila
    origen, destino = float(fila['kv_origen']), float(o.kv_destino)
    flujo_de_carga(ctx.app)
    cabecera = cabecera_de(ctx.elm)
    if cabecera is None:
        raise RuntimeError(f'el alimentador {o.alimentador} no dice su cabecera')
    try:
        camino = camino_y_ramales(leer_red(ctx.elm, cabecera), cabecera.loc_name, fila['hasta']['barra'])
    except TroncalError as exc:
        raise RuntimeError(str(exc)) from None
    dentro = set(camino.barras)
    barras = {b.loc_name: b for b in ctx.elm.GetObjs('ElmTerm')}
    barras[cabecera.loc_name] = cabecera
    lineas = {ln.loc_name: ln for ln in ctx.elm.GetObjs('ElmLne')}
    acopladores = {c.loc_name: c for c in ctx.elm.GetObjs('ElmCoup')}
    faltan = [n for n in camino.barras if n not in barras] + [n for n in camino.ramales if n not in lineas and n not in acopladores]
    if faltan:
        raise RuntimeError(f'la red leída nombra elementos que el alimentador no devuelve: {", ".join(sorted(faltan))}')
    # Las copias de tipo antes de escribir: una que falte para aquí, sin haber cambiado ninguna tensión.
    tipos_lineas = [(lineas[n], _tipo_a_tension(ctx, lineas[n], 'TypLne', 'uline', origen, destino))
                    for n in camino.tramos if n in lineas]
    trafos = [tr for tr in ctx.elm.GetObjs('ElmTr2')
              if getattr(getattr(getattr(tr, 'bushv', None), 'cterm', None), 'loc_name', None) in dentro]
    tipos_trafos = [(tr, _tipo_a_tension(ctx, tr, 'TypTr2', 'utrn_h', origen, destino)) for tr in trafos]
    kw_fuera = _kw_sin_alimentar(ctx, set(camino.fuera))
    a_cambiar = [barras[n] for n in camino.barras if math.isclose(float(getattr(barras[n], 'uknom', 0) or 0), origen)]
    for barra in a_cambiar:
        barra.uknom = destino
    for objeto, tipo in tipos_lineas + tipos_trafos:
        objeto.typ_id = tipo
    for banco in ctx.elm.GetObjs('ElmShnt'):
        donde = getattr(getattr(getattr(banco, 'bus1', None), 'cterm', None), 'loc_name', None)
        if donde in dentro and math.isclose(float(getattr(banco, 'ushnm', 0) or 0), origen):
            banco.ushnm = destino
    for ramal in camino.ramales:
        # 042:RF-19, 081:RF-80: anotado antes de abrirlo, para volver a cerrarlo si la obra no llega a quedar.
        if ramal in lineas:
            abrir(ctx, 'ElmLne', lineas[ramal])
        else:
            abrir(ctx, 'ElmCoup', acopladores[ramal])
    a_medias = ([b.loc_name for b in a_cambiar if not math.isclose(float(b.uknom), destino)]
                + [n for n in camino.ramales if (n in lineas and not int(lineas[n].outserv))
                   or (n in acopladores and int(acopladores[n].on_off))])
    if a_medias:
        raise RuntimeError(f'la migración no quedó entera, no se aplica: {", ".join(sorted(a_medias))}')
    reguladores = [r.loc_name for r in ctx.elm.GetObjs('ElmVoltreg')
                   if getattr(getattr(getattr(r, 'bus1', None), 'cterm', None), 'loc_name', None) in dentro]
    if reguladores:
        fila['avisos'].append(f'Los reguladores de la troncal no se cambian: {", ".join(sorted(reguladores))}; '
                              f'revíselos a {destino:g} kV.')
    parte = {'barras': len(camino.barras), 'tramos': len(tipos_lineas), 'seds': len(trafos), 'entrada': None,
             'ramales': list(camino.ramales), 'sin_alimentar': {**fila.get('parte', {}).get('sin_alimentar', {}),
                                                                'barras': len(camino.fuera), 'kw': round(kw_fuera, 1)}}
    fila['parte'] = parte
    if camino.ramales:
        fila['avisos'].append(f'Con los ramales abiertos salen del flujo {kw_fuera:.1f} kW de demanda escrita: la mejora de '
                              f'«Con proyecto» incluye esa baja, no es solo efecto de la migración.')


def _celda_nueva(ctx, nodo, nombre_salida: str, kv: float) -> None:
    """La salida nueva en la barra de la tensión de destino de la SET, y el alimentador sale por ella (042:RF-51).

    Con la barra de 10 kV compartida, cambiar su tensión pasaría también a los demás alimentadores; por eso una celda
    en la barra de 22,9 kV y no un cambio de la cabecera. El ``ElmFeeder`` conserva su nombre y queda en la celda nueva.
    """
    salida = next((b for b in ctx.app.GetCalcRelevantObjects('*.ElmTerm') if b.loc_name == nombre_salida), None)
    if salida is None or nodo is None:
        raise RuntimeError(f'sin la barra {nombre_salida} o sin el nodo para la celda nueva de {ctx.obra.alimentador}')
    red = salida.GetParent()
    celda = red.CreateObject('ElmCoup', nombre_libre(red, 'ElmCoup', nombre_pf(f'CELDA_{ctx.obra.alimentador}_{kv:g}kV')))
    celda.aUsage, celda.on_off = 'cbk', 1
    cubiculo = None
    for barra, lado in ((salida, 0), (nodo, 1)):
        c = barra.CreateObject('StaCubic', nombre_pf(f'Cub_{celda.loc_name}_{lado}'))
        c.obj_id, c.obj_bus = celda, lado
        cubiculo = cubiculo or c
    ctx.elm.obj_id = cubiculo
    ctx.fila['salida_nueva'] = {'celda': celda.loc_name, 'barra': salida.loc_name, 'nodo': nodo.loc_name}


#: IEC 60076-5, tabla 1, si el perfil no da la suya: hasta tantos MVA, tanta uk en %.
UK_IEC_HASTA_MVA = ((0.63, 4.0), (1.25, 5.0), (2.5, 6.0), (6.3, 7.0), (25.0, 10.0))


def _elevador_dedicado(ctx, cabecera, nodo, origen: float, destino: float) -> None:
    """El transformador solo para esta salida, de la barra compartida al primer nodo (042:RF-61).

    La barra sigue a su tensión para los demás alimentadores. El ``ElmFeeder`` sale por el lado de baja, en esa barra:
    orientado desde ahí, sigue viendo aguas abajo lo que pasó de tensión, con su nombre.
    """
    if cabecera is None or nodo is None:
        raise RuntimeError(f'sin cabecera o sin el nodo para el elevador de {ctx.obra.alimentador}')
    mva = float(ctx.obra.elevador_mva)
    cfg = (datos_perfil().get('planificacion') or {}).get('transformador_set') or {}
    equip = ctx.app.GetProjectFolder('equip') or ctx.proyecto
    tipo = equip.CreateObject('TypTr2', nombre_libre(equip, 'TypTr2', nombre_pf(f'TR_ELEVADOR_{mva:g}MVA_{origen:g}-{destino:g}kV')))
    tipo.strn, tipo.utrn_h, tipo.utrn_l = mva, destino, origen
    tipo.uktr = next((uk for hasta, uk in sorted(cfg.get('uk_pct_hasta_mva') or UK_IEC_HASTA_MVA) if mva <= float(hasta)),
                     UK_IEC_HASTA_MVA[-1][1])
    red = cabecera.GetParent()
    tr = red.CreateObject('ElmTr2', nombre_libre(red, 'ElmTr2', nombre_pf(f'TR_ELEVADOR_{ctx.obra.alimentador}')))
    tr.typ_id, tr.ntnum, tr.outserv, tr.nntap = tipo, 1, 0, 0
    alta = nodo.CreateObject('StaCubic', nombre_pf(f'Cub_{tr.loc_name}_alta'))
    alta.obj_id, alta.obj_bus = tr, 0
    baja = cabecera.CreateObject('StaCubic', nombre_pf(f'Cub_{tr.loc_name}_baja'))
    baja.obj_id, baja.obj_bus = tr, 1
    ctx.elm.obj_id = baja
    ctx.fila['elevador'] = {'transformador': tr.loc_name, 'mva': mva, 'barra': cabecera.loc_name, 'nodo': nodo.loc_name}


def barra_de_destino(app, cabecera, kv: float, radio_m: float = 500.0):
    """La barra principal a ``kv`` de la misma SET: la más cercana a la cabecera, por GPS (042:RF-51).

    Por posición y no por nombre: cada empresa llama a sus barras a su manera, y de la SET no hay otro dato común.
    """
    origen = gps_de(cabecera)
    if not origen:
        return None
    mejor, mejor_m = None, radio_m
    for barra in app.GetCalcRelevantObjects('*.ElmTerm'):
        if (int(getattr(barra, 'iUsage', 1) or 0) == 0 and abs(float(getattr(barra, 'uknom', 0) or 0) - kv) < 0.05 * kv
                and (punto := gps_de(barra))):
            metros = 111320.0 * math.hypot(punto[0] - origen[0], (punto[1] - origen[1]) * math.cos(math.radians(origen[0])))
            if metros <= mejor_m:
                mejor, mejor_m = barra, metros
    return mejor


def construir_migracion(ctx) -> None:
    """Lo que queda aguas abajo del nodo, a la tensión de destino (016:RF-54 a RF-58).

    El caso es «Con proyecto» y la variación de la obra ya graba. La parte que pasa se
    vuelve a calcular aquí, con la red de ahora: un enlace de la misma tanda pudo partir un
    tramo de esa parte, y la mitad nueva no estaba en la simulación (IN111 cede a TA225 y
    el enlace llega a su troncal, 2026-10-15). Cambian las barras de media, los tipos de
    las líneas y de las SED (solo la alta) y se abre el tramo que entra al nodo; nada más
    del alimentador (RF-57).
    """
    if ctx.obra.hasta:
        construir_migracion_camino(ctx)
        return
    o, fila = ctx.obra, ctx.fila
    origen, destino = float(fila['kv_origen']), float(o.kv_destino)
    # Un flujo antes de leer, como el enlace: sin él, el ElmFeeder no daba el nodo que
    # partió el enlace de la misma variación activa («no tiene camino cerrado desde su
    # cabecera»; IN111 + TA225, 2026-10-15, la simulación sí lo encontraba).
    flujo_de_carga(ctx.app)
    cabecera = cabecera_de(ctx.elm)
    if cabecera is None:
        raise RuntimeError(f'el alimentador {o.alimentador} no dice su cabecera')
    try:
        parte = aguas_abajo(leer_red(ctx.elm, cabecera), cabecera.loc_name, o.nodo)
    except TroncalError as exc:
        raise RuntimeError(str(exc)) from None
    dentro = set(parte.barras)
    planificados = {e['elemento'] for e in fila['elementos']}
    barras = {b.loc_name: b for b in ctx.elm.GetObjs('ElmTerm')}
    for nombre in parte.barras:                                                     # RF-55
        barra = barras.get(nombre)
        if barra is not None and math.isclose(float(getattr(barra, 'uknom', 0) or 0), origen):
            barra.uknom = destino
    lineas = {ln.loc_name: ln for ln in ctx.elm.GetObjs('ElmLne')}
    # Toda línea con sus dos barras en la parte que pasa, no solo los tramos del árbol:
    # los que cierran un anillo quedaban a 10 kV entre barras de 22,9 y el flujo no se
    # ejecutaba (IN111, SEC_1091_1059394 y SEC_1091_1059767, 2026-10-15).
    anillo = [n for n, ln in lineas.items() if n not in set(parte.tramos)
              and len(_barras_de(ctx.app, ln)) == 2 and _barras_de(ctx.app, ln) <= dentro]
    nuevos = []
    # 087:RF-32, RF-33: a un vecino de la misma tensión la parte solo cambia de alimentador: ni tipos ni tensiones.
    misma = math.isclose(origen, destino, rel_tol=1e-3)
    for nombre in list(parte.tramos) + anillo:                                      # RF-56
        linea = lineas.get(nombre)
        if linea is None or misma:
            continue                                     # un seccionador: no tiene tensión
        linea.typ_id = _tipo_a_tension(ctx, linea, 'TypLne', 'uline', origen, destino)
        if nombre not in planificados:
            nuevos.append(nombre)
    for trafo in ([] if misma else ctx.elm.GetObjs('ElmTr2')):                       # RF-54
        alta = getattr(getattr(getattr(trafo, 'bushv', None), 'cterm', None), 'loc_name', None)
        if alta in dentro:
            trafo.typ_id = _tipo_a_tension(ctx, trafo, 'TypTr2', 'utrn_h', origen, destino)
    entrada = parte.entrada                                                          # RF-58
    acopladores = {c.loc_name: c for c in ctx.elm.GetObjs('ElmCoup')}
    if o.salida or o.elevador_mva:
        bancos = [s for s in ctx.elm.GetObjs('ElmShnt')
                  if getattr(getattr(getattr(s, 'bus1', None), 'cterm', None), 'loc_name', None) in dentro]
        if o.salida:
            _celda_nueva(ctx, barras.get(o.nodo), o.salida, destino)                 # 042:RF-51
        else:
            _elevador_dedicado(ctx, cabecera, barras.get(o.nodo), origen, destino)   # 042:RF-61
        for banco in bancos:
            banco.ushnm = destino
    # 081:RF-80: la transferencia y el traslado (087:RF-31) abrían la entrada sin anotarla: al cortarse la escalera en
    # Pisco (2026-11-07), nada la volvió a cerrar y «Con proyecto» quedó con 724 barras de media sin tensión.
    if entrada in lineas:
        # 098:RF-12: se abre la maniobra que ya tiene el tramo, como hace el operador (CA101 a CHN102, 2026-11-07);
        # solo un tramo sin ella (una migración pedida a mano, 016) sale de servicio, y se dice.
        cub = next((c for c in (getattr(lineas[entrada], 'bus1', None), getattr(lineas[entrada], 'bus2', None))
                    if c is not None and (c.GetContents('*.StaSwitch') or [])), None)
        if cub is not None:
            abrir(ctx, 'StaSwitch', (cub.GetContents('*.StaSwitch') or [])[0])
        else:
            abrir(ctx, 'ElmLne', lineas[entrada])
            fila['avisos'].append(f'{entrada} no tiene interruptor ni seccionador: sale de servicio para separar la parte '
                                  'que pasa (098:RF-12).')
    elif entrada in acopladores:
        abrir(ctx, 'ElmCoup', acopladores[entrada])
    if nuevos:
        fila['avisos'].append(f'La parte que pasa tiene tramos que no estaban en la simulación '
                              f'(los que partió un enlace o cierran un anillo): '
                              f'{", ".join(nuevos)}; pasan también a {destino:g} kV.')
    # RF-76, RF-80: el enlace que llega a la parte que pasa ya une barras de la misma
    # tensión; se pone en servicio y se cierra, porque esa parte solo se alimenta por él.
    # Fuera de servicio no la da GetCalcRelevantObjects: se busca en los datos de red, o en
    # el proyecto si no hay esa carpeta.
    donde = ctx.app.GetProjectFolder('netdat') or ctx.app.GetActiveProject()
    for linea in (donde.GetContents('Enlace_*.ElmLne', 1) if donde else []):
        cubiculos = _cubiculos(ctx.app, linea)
        barras = [getattr(c, 'cterm', None) for c in cubiculos]
        abierto = any(int(getattr(sw, 'on_off', 1)) == 0 for cub in cubiculos for sw in (cub.GetContents('*.StaSwitch') or []))
        # 087:RF-32: el de la misma tensión quedó en servicio con su seccionador abierto (016:RF-36): también se cierra.
        if (int(getattr(linea, 'outserv', 0)) or abierto) and any(b is not None and b.loc_name in dentro
                                                                   for b in barras)                 and all(b is not None and math.isclose(float(b.uknom), destino, rel_tol=1e-3) for b in barras):
            linea.outserv = 0
            # RF-80: la parte que pasa ya no cuelga de su alimentador (se abrió el tramo de
            # entrada) y sin el enlace cerrado quedaba sin servicio: 142 SED de IN111 en
            # «Con proyecto», y la transferencia no hallaba camino (2026-10-15).
            cerrados = []
            for cub in cubiculos:
                for sw in (cub.GetContents('*.StaSwitch') or []):
                    if int(getattr(sw, 'on_off', 1)) == 0:
                        sw.on_off = 1
                        cerrados.append(sw.loc_name)
            cuales = ', '.join(cerrados) or 'sin seccionador'
            fila['avisos'].append(f'El enlace {linea.loc_name} ya une barras de {destino:g} kV: '
                                  f'queda en servicio y cerrado ({cuales}); la parte que pasa '
                                  f'se alimenta por él.')
    otros = [] if o.salida or o.elevador_mva else [
        s.loc_name for s in ctx.elm.GetObjs('ElmShnt') + ctx.elm.GetObjs('ElmVoltreg')
        if getattr(getattr(getattr(s, 'bus1', None), 'cterm', None), 'loc_name', None) in dentro]
    if otros:
        fila['avisos'].append(f'Los bancos y reguladores de la parte que pasa no se cambian: '
                              f'{", ".join(sorted(otros))}; revíselos a {destino:g} kV.')
    fila['parte'] = {**fila.get('parte', {}), 'barras': len(parte.barras),
                     'tramos': len([n for n in parte.tramos if n in lineas]),
                     'entrada': entrada}


def construir_consigna(ctx) -> None:
    """Consigna de la red externa de la cabecera (019:RF-12).

    Es dato de operación: queda en el escenario del caso activo al construir, que es
    «Con proyecto» porque la obra solo va allí; «Sin proyecto» conserva la suya.
    """
    cabecera = cabecera_de(ctx.elm)
    fuentes = _fuentes_en(cabecera) if cabecera is not None else []
    if not fuentes:
        raise RuntimeError(f'no hay red externa en la cabecera de {ctx.obra.alimentador}')
    for fuente in fuentes:
        fuente.usetp = float(ctx.obra.consigna_pu)


#: Atributos de la red externa de cabecera que se copian a la de la SET nueva (042:RF-5).
ATRIBUTOS_RED_EXTERNA = ('usetp', 'phiini', 'snss', 'snssmin', 'rntxn', 'rntxnmin', 'z2tz1', 'x0tx1',
                         'r0tx0', 'cmax', 'cmin')
#: Cuánto se acerca la SET nueva a la barra que peor queda en cada intento, y cuántos (042:RF-10).
ACERCAR = 0.35
INTENTOS_SET = 6


def _uk_del_perfil(mva: float, cfg: dict) -> float:
    """La uk de la tabla del perfil para esa potencia (IEC 60076-5, tabla 1)."""
    for hasta, uk in sorted(cfg.get('uk_pct_hasta_mva') or []):
        if mva <= float(hasta):
            return float(uk)
    raise RuntimeError(f'el perfil no da la uk de un transformador de {mva:g} MVA '
                       '(planificacion.transformador_set.uk_pct_hasta_mva)')


def _hacia(a: tuple[float, float], b: tuple[float, float], f: float) -> tuple[float, float]:
    return a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])


def validar_salida_set_existente(proyecto, origen, destino, tipo, nombre, circuitos, ruta) -> dict:
    """063:RF-36, RF-38: preflight de solo lectura, sin exigir etapa o escenario.

    Valida los objetos ya resueltos y la polilínea explícita antes de abrir cualquier
    etapa de obra. Devuelve metadatos JSON, con rutas completas; no devuelve objetos
    nativos ni consulta servicios de mapas. El caller verifica además las colisiones
    entre salidas del mismo lote, todavía no creadas.
    """
    if proyecto is None or proyecto.GetClassName() != 'IntPrj':
        raise ValueError('La salida requiere el objeto nativo del proyecto vinculado.')
    identidad = clave_pf(proyecto)
    for etiqueta, obj, clase in (('origen', origen, 'ElmTerm'), ('destino', destino, 'ElmTerm'),
                                 ('tipo', tipo, 'TypLne')):
        if obj is None or obj.GetClassName() != clase:
            raise ValueError(f'{etiqueta}: se requiere un objeto {clase} resuelto, no un nombre.')
        propietario = _proyecto_de(obj)
        if propietario is None or clave_pf(propietario) != identidad:
            raise ValueError(f'{etiqueta}: el objeto no pertenece al proyecto vinculado.')
    if clave_pf(origen) == clave_pf(destino):
        raise ValueError('Los terminales de origen y destino deben ser distintos.')
    tensiones = [float(getattr(obj, attr, 0) or 0) for obj, attr in
                 ((origen, 'uknom'), (destino, 'uknom'), (tipo, 'uline'))]
    if (any(not math.isfinite(kv) or kv < 1 for kv in tensiones)
            or any(not math.isclose(kv, tensiones[0], rel_tol=1e-4, abs_tol=.001) for kv in tensiones[1:])):
        raise ValueError('Las barras de media tensión y el tipo propio deben tener la misma tensión nominal.')
    if type(circuitos) is not int or circuitos < 1:
        raise ValueError('El número de circuitos requiere un entero positivo.')
    if not isinstance(nombre, str) or not nombre or nombre_pf(nombre) != nombre:
        raise ValueError('El nombre explícito de la salida debe cumplir el formato nativo de 40 caracteres.')
    if not isinstance(ruta, (list, tuple)) or len(ruta) < 2:
        raise ValueError('La salida necesita una ruta GPS explícita con al menos dos puntos.')
    puntos = []
    for p in ruta:
        if (not isinstance(p, (list, tuple)) or len(p) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in p)
                or not -90 <= p[0] <= 90 or not -180 <= p[1] <= 180):
            raise ValueError('La ruta contiene coordenadas GPS incompletas o no válidas.')
        puntos.append([float(p[0]), float(p[1])])
    gps_origen, gps_destino = gps_de(origen), gps_de(destino)
    if gps_origen is None or gps_destino is None:
        raise ValueError('Los dos terminales necesitan coordenadas nativas verificables.')
    errores_extremos = [distancia_m(gps_origen, puntos[0]), distancia_m(gps_destino, puntos[-1])]
    # Un metro cubre la serialización decimal del trazado; no desplaza ningún terminal.
    if any(e > 1. for e in errores_extremos):
        raise ValueError('Los extremos de la ruta explícita no coinciden con el GPS nativo de los terminales.')
    largo_m = sum(distancia_m(a, b) for a, b in zip(puntos, puntos[1:]))
    if not math.isfinite(largo_m) or largo_m <= 0:
        raise ValueError('La ruta no tiene longitud física positiva.')
    red = origen.GetParent()
    while red is not None and red.GetClassName() != 'ElmNet':
        red = red.GetParent()
    if red is None:
        raise ValueError('El terminal de origen no pertenece a una red ElmNet del proyecto.')
    for clase in ('ElmLne', 'ElmFeeder'):
        if any(obj.loc_name == nombre for obj in proyecto.GetContents(f'*.{clase}', 1)):
            raise ValueError(f'Ya existe {nombre}.{clase}; no se renombra ni reutiliza una salida anterior.')
    nombres_cubiculos = [nombre_pf(f'Cub_{i}_{nombre}') for i in (0, 1)]
    for barra, n in zip((origen, destino), nombres_cubiculos):
        if any(c.loc_name == n for c in barra.GetContents('*.StaCubic')):
            raise ValueError(f'Ya existe el cubículo {n}; no se modifica una conexión anterior.')
    return {'red': clave_pf(red), 'origen': clave_pf(origen), 'destino': clave_pf(destino),
            'tipo': clave_pf(tipo), 'tipo_nombre': tipo.loc_name, 'nombre': nombre,
            'circuitos': circuitos, 'kv': tensiones[0], 'GPScoords': puntos,
            'largo_m': largo_m, 'longitud_km': largo_m / 1000.,
            'GPS_origen': list(gps_origen), 'GPS_destino': list(gps_destino),
            'error_extremos_m': errores_extremos, 'nombres_cubiculos': nombres_cubiculos}


def construir_salida_set_existente(app, proyecto, origen, destino, tipo, nombre, circuitos, ruta) -> dict:
    """063:RF-36, RF-38: crea cuatro objetos en la etapa que ya abrió el caller.

    El caller mantiene la responsabilidad de revertir su etapa si falla la API.
    El constructor no activa nada ni toca la SET, sus coordenadas o sus tipos;
    repite el preflight para detectar colisiones aparecidas después de validar el lote.
    """
    if proyecto is None or proyecto.GetClassName() != 'IntPrj':
        raise ValueError('La salida requiere el objeto nativo del proyecto vinculado.')
    identidad = clave_pf(proyecto)
    activo = app.GetActiveProject()
    if activo is None or clave_pf(activo) != identidad:
        raise ValueError('El proyecto vinculado no es el proyecto activo.')
    etapa = app.GetRecordingStage()
    if etapa is None or _proyecto_de(etapa) is None or clave_pf(_proyecto_de(etapa)) != identidad:
        raise ValueError('El caller debe abrir una etapa propia del proyecto antes de construir la salida.')
    if app.GetActiveScenario() is not None:
        raise ValueError('El escenario debe estar inactivo para registrar la salida en su etapa propia.')
    datos = validar_salida_set_existente(proyecto, origen, destino, tipo, nombre, circuitos, ruta)
    red = origen.GetParent()
    while red.GetClassName() != 'ElmNet':
        red = red.GetParent()
    puntos, largo_m = datos['GPScoords'], datos['largo_m']

    linea = red.CreateObject('ElmLne', nombre)
    if linea is None:
        raise RuntimeError('La API no creó la línea de la salida.')
    linea.typ_id, linea.nlnum, linea.outserv = tipo, circuitos, 0
    linea.dline = largo_m / 1000.
    linea.SetAttribute('GPScoords', puntos)
    # 084:RF-12: una salida de dos o más ternas es una instalación como las demás.
    instalada: dict = {'avisos': []}
    _instalar_ternas(instalada, linea)
    cubiculos = []
    for lado, (barra, n) in enumerate(zip((origen, destino), datos['nombres_cubiculos'])):
        cub = barra.CreateObject('StaCubic', n)
        if cub is None:
            raise RuntimeError('La API no creó uno de los cubículos de la salida.')
        cub.obj_id, cub.obj_bus = linea, lado
        cubiculos.append(cub)
    feeder = red.CreateObject('ElmFeeder', nombre)
    if feeder is None:
        raise RuntimeError('La API no creó el alimentador de la salida.')
    feeder.obj_id, feeder.iorient = cubiculos[0], 0
    if (clave_pf(linea.typ_id) != clave_pf(tipo) or linea.nlnum != circuitos or linea.outserv != 0
            or not math.isclose(float(linea.dline), largo_m / 1000., rel_tol=1e-6)
            or linea.GetAttribute('GPScoords') != puntos
            or any(clave_pf(c.obj_id) != clave_pf(linea) or c.obj_bus != i
                   or clave_pf(c.cterm) != clave_pf(b)
                   for i, (c, b) in enumerate(zip(cubiculos, (origen, destino))))
            or clave_pf(feeder.obj_id) != clave_pf(cubiculos[0]) or feeder.iorient != 0):
        raise RuntimeError('La relectura inmediata de la salida no conserva sus datos y conexiones.')
    return {'linea': clave_pf(linea), 'nombre': linea.loc_name, 'feeder': clave_pf(feeder),
            'feeder_nombre': feeder.loc_name, 'cubiculos': [clave_pf(c) for c in cubiculos],
            'origen': clave_pf(origen), 'destino': clave_pf(destino), 'tipo': clave_pf(tipo),
            'tipo_nombre': tipo.loc_name, 'kv': datos['kv'], 'circuitos': circuitos,
            'instalaciones': instalada.get('instalaciones', []), 'avisos_ternas': instalada['avisos'],
            'longitud_km': float(linea.dline), 'largo_m': largo_m, 'GPScoords': puntos,
            'GPS_origen': datos['GPS_origen'], 'GPS_destino': datos['GPS_destino'],
            'error_extremos_m': datos['error_extremos_m'], 'etapa': clave_pf(etapa),
            'objetos_creados': [clave_pf(o) for o in (linea, *cubiculos, feeder)]}


def construir_set_nueva(ctx) -> None:
    """SET nueva con su transformador y las ramas que pasan a ella (042:RF-5, RF-6, RF-10, RF-11).

    Barras de alta y de media en el punto, red externa con los datos de la de cabecera
    (usuario, 2026-10-31: «red externa con datos de la SET actual»), transformador del módulo
    PIT con la uk de la norma, y por rama una línea desde la barra de media hasta su nodo, su
    tramo de entrada abierto y un ``ElmFeeder`` nuevo. Después, mientras alguna barra de media
    quede fuera de los límites, la SET se acerca a la que peor queda y se recalculan las líneas.
    """
    o, app, fila = ctx.obra, ctx.app, ctx.fila
    punto = punto_indicado(o.destino)
    cabecera = cabecera_de(ctx.elm)
    fuentes = _fuentes_en(cabecera) if cabecera is not None else []
    if not fuentes:
        raise RuntimeError(f'no hay red externa en la cabecera de {o.alimentador}: no se sabe con qué '
                           'datos alimentar la SET nueva')
    cfg = (datos_perfil().get('planificacion') or {}).get('transformador_set') or {}
    # 084:RF-9: antes de crear nada, para que la SET no se aparte de sus propias salidas.
    cfg_sitio = sitio_set.parametros(datos_perfil())
    trazados = _trazados_de_la_red(app)
    punto_inicial = punto
    red = cabecera.GetParent()
    kv_mt = float(cabecera.uknom)
    # 052:RF-19: con el nombre que da el operador («SET COPARA» → SET_COPARA_AT, TR_SET_COPARA…).
    base = nombre_pf(getattr(o, 'nombre_set', '') or 'SET_NUEVA')
    at = red.CreateObject('ElmTerm', nombre_libre(red, 'ElmTerm', f'{base}_AT'))
    mt = red.CreateObject('ElmTerm', nombre_libre(red, 'ElmTerm', f'{base}_MT'))
    at.uknom, at.iUsage, mt.uknom, mt.iUsage = float(o.kv_alta), 0, kv_mt, 0
    xnet = red.CreateObject('ElmXnet', nombre_libre(red, 'ElmXnet', f'Red_{base}'))
    copiados = []
    for a in ATRIBUTOS_RED_EXTERNA:
        valor = getattr(fuentes[0], a, None)
        if valor is not None:
            try:
                setattr(xnet, a, valor)
                copiados.append(a)
            except Exception:  # noqa: BLE001, S110 - un atributo que no tiene esta versión
                pass
    xnet.bustp = 'SL'
    cub = at.CreateObject('StaCubic', nombre_pf('Cub_Red_SET_NUEVA'))
    cub.obj_id, cub.obj_bus = xnet, 0
    equip = app.GetProjectFolder('equip') or ctx.proyecto
    tipo_tr = equip.CreateObject('TypTr2', nombre_libre(
        equip, 'TypTr2', nombre_pf(f'TR_SET_NUEVA_{o.mva:g}MVA_{o.kv_alta:g}-{kv_mt:g}kV')))
    tipo_tr.strn, tipo_tr.utrn_h, tipo_tr.utrn_l = float(o.mva), float(o.kv_alta), kv_mt
    tipo_tr.uktr = _uk_del_perfil(float(o.mva), cfg)
    frecuencia = float(getattr(red, 'frnom', 0) or 0)
    if frecuencia:
        tipo_tr.frnom = frecuencia
    tipo_tr.itapch, tipo_tr.tap_side = 1, 0
    tipo_tr.dutap = float(cfg.get('toma_paso_pct') or 0.0)
    tipo_tr.ntpmn, tipo_tr.ntpmx, tipo_tr.nntap0 = -int(cfg.get('tomas') or 0), int(cfg.get('tomas') or 0), 0
    tr = red.CreateObject('ElmTr2', nombre_libre(red, 'ElmTr2', f'TR_{base}'))
    # 042:RF-14: n transformadores iguales en paralelo son un ElmTr2 con ntnum = n (cada uno con
    # la uk de su potencia); NA203 + NA205 pedían 45,5 MVA y el mayor módulo era de 40.
    tr.typ_id, tr.ntnum, tr.outserv, tr.nntap = tipo_tr, int(getattr(o, 'unidades', None) or 1), 0, 0
    # 042:RF-16: la media de la SET nueva a la consigna de la cabecera actual, con el cambiador en
    # carga regulando y, para el flujo del caso aunque no ajuste tomas, en la toma que la deja ahí.
    # Sin regular, la red externa en 60 kV con la consigna copiada dejaba la media baja y 15 barras
    # de NA203 + NA205 bajo 0,95 p.u. con la SET COPARA en su mejor punto (2026-11-01).
    consigna = float(getattr(fuentes[0], 'usetp', 0) or 1.0)
    regula = {}
    for atributo, valor in (('ntrcn', 1), ('usetp', consigna)):
        try:
            setattr(tr, atributo, valor)
            regula[atributo] = valor
        except Exception:  # noqa: BLE001, S110 - un atributo que no tiene esta versión
            pass
    _aviso_del_flujo(ctx, 'iopt_at', 'las tomas')
    for barra, lado, nombre in ((at, 0, 'Cub1_TR_SET_NUEVA'), (mt, 1, 'Cub2_TR_SET_NUEVA')):
        c = barra.CreateObject('StaCubic', nombre_pf(nombre))
        c.obj_id, c.obj_bus = tr, lado
    # 042:RF-20: una barra de media por tensión, cada una con su transformador desde la alta.
    medias = {round(kv_mt, 1): mt}
    niveles = [{'kv': kv_mt, 'barra': mt.loc_name, 'transformador': tr.loc_name}]

    def media_de(kv: float):
        if round(kv, 1) in medias:
            return medias[round(kv, 1)]
        barra = red.CreateObject('ElmTerm', nombre_libre(red, 'ElmTerm', nombre_pf(f'{base}_MT_{kv:g}kV')))
        barra.uknom, barra.iUsage = kv, 0
        tipo = equip.CreateObject('TypTr2', nombre_libre(
            equip, 'TypTr2', nombre_pf(f'TR_SET_NUEVA_{o.mva:g}MVA_{o.kv_alta:g}-{kv:g}kV')))
        tipo.strn, tipo.utrn_h, tipo.utrn_l, tipo.uktr = float(o.mva), float(o.kv_alta), kv, tipo_tr.uktr
        if frecuencia:
            tipo.frnom = frecuencia
        tipo.itapch, tipo.tap_side, tipo.dutap = 1, 0, tipo_tr.dutap
        tipo.ntpmn, tipo.ntpmx, tipo.nntap0 = tipo_tr.ntpmn, tipo_tr.ntpmx, 0
        otro = red.CreateObject('ElmTr2', nombre_libre(red, 'ElmTr2', nombre_pf(f'TR_{base}_{kv:g}kV')))
        otro.typ_id, otro.ntnum, otro.outserv, otro.nntap = tipo, tr.ntnum, 0, 0
        for atributo, valor in regula.items():
            setattr(otro, atributo, valor)
        for b, lado in ((at, 0), (barra, 1)):
            c = b.CreateObject('StaCubic', nombre_pf(f'Cub{lado + 1}_{otro.loc_name}'))
            c.obj_id, c.obj_bus = otro, lado
        medias[round(kv, 1)] = barra
        niveles.append({'kv': kv, 'barra': barra.loc_name, 'transformador': otro.loc_name})
        return barra

    lineas = []
    for texto in o.ramas:
        alim, _, nodo = texto.partition('/')
        elm = ctx.alims.elm.get(alim) if ctx.alims is not None else None
        rama_red = ctx.redes.get(alim)
        if elm is None or rama_red is None or rama_red.topologia is None:
            raise RuntimeError(f'no se leyó el alimentador {alim} de la rama {texto}')
        barras = {b.loc_name: b for b in elm.GetObjs('ElmTerm')}
        if nodo not in barras:
            raise RuntimeError(f'el nodo {nodo} no está en {alim}')
        parte = aguas_abajo(rama_red.topologia, rama_red.cabecera, nodo)
        lineas_f = {ln.loc_name: ln for ln in elm.GetObjs('ElmLne')}
        acopladores = {c.loc_name: c for c in elm.GetObjs('ElmCoup')}
        if parte.entrada in lineas_f:
            abrir(ctx, 'ElmLne', lineas_f[parte.entrada])                               # 042:RF-19, 081:RF-80
        elif parte.entrada in acopladores:
            abrir(ctx, 'ElmCoup', acopladores[parte.entrada])
        tipo = (ctx.tipo('TypLne', o.tipo.nombre) if o.tipo is not None else
                getattr(lineas_f.get((rama_red.troncal or ('',))[0]), 'typ_id', None))
        if tipo is None:
            raise RuntimeError(f'sin tipo de línea para el alimentador nuevo hasta {nodo}: indíquelo')
        linea = red.CreateObject('ElmLne', nombre_libre(red, 'ElmLne', nombre_pf(f'SETN_{alim}_{nodo}')))
        linea.typ_id, linea.nlnum, linea.outserv = tipo, 1, 0
        salida_mt = media_de(float(getattr(barras[nodo], 'uknom', 0) or kv_mt))         # 042:RF-20
        for barra, lado in ((salida_mt, 0), (barras[nodo], 1)):
            c = barra.CreateObject('StaCubic', nombre_pf(f'Cub_{linea.loc_name}_{lado}'))
            c.obj_id, c.obj_bus = linea, lado
            if lado == 0:
                salida = c
        nuevo = red.CreateObject('ElmFeeder', nombre_libre(red, 'ElmFeeder', nombre_pf(f'SETN_{alim}_{nodo}')))
        nuevo.obj_id, nuevo.iorient = salida, 0
        lineas.append({'linea': linea, 'nodo': barras[nodo], 'alimentador': alim, 'entrada': parte.entrada,
                       'feeder': nuevo.loc_name})

    def situar(p: tuple[float, float]) -> None:
        for b in (at, *medias.values()):
            b.GPSlat, b.GPSlon = p
        for x in lineas:
            fin = gps_de(x['nodo']) or p
            ruta = ruta_por_vias(tuple(p), tuple(fin), datos_perfil().get('vias'))
            x['linea'].dline = max(ruta.largo_m / 1000.0, 1e-6)
            x['linea'].SetAttribute('GPScoords', [list(q) for q in ruta.puntos])
            x['largo_m'] = ruta.largo_m

    limites = _limites(ctx.plan)
    tomas = int(cfg.get('tomas') or 0)

    def medir() -> tuple[dict, list]:
        flujo = flujo_de_carga(app)
        fuera = []
        if flujo['converged']:
            for b in app.GetCalcRelevantObjects('*.ElmTerm'):
                u = _resultado(b, 'm:u') if float(getattr(b, 'uknom', 0) or 0) >= 1.0 else None
                if u is not None and not limites.tension_min_pu <= u <= limites.tension_max_pu:
                    fuera.append((u, b))
        return flujo, fuera

    def u_media() -> float | None:
        return _resultado(mt, 'm:u')

    def ajustar_toma() -> None:
        """RF-16: la toma fija que deja la media más cerca de la consigna, con la pendiente medida."""
        tr.nntap = 0
        if not tomas or not medir()[0]['converged'] or (u0 := u_media()) is None:
            return
        tr.nntap = 1
        u1 = u_media() if medir()[0]['converged'] else None
        tr.nntap = 0
        if u1 is None or abs(u1 - u0) < 1e-6:
            return
        tr.nntap = max(-tomas, min(tomas, round((consigna - u0) / (u1 - u0))))

    def clave(x: dict) -> tuple:
        return (bool(x['converge']), -int(x['fuera']), float(x['vmin'] or 0.0))

    intentos, mejor, paso = [], None, ACERCAR
    for _n in range(INTENTOS_SET):                                                    # RF-10
        # 084:RF-9: acercarse a la barra que cae es acercarse a la red: cada punto se aparta antes de medirlo.
        if cfg_sitio.retiro_m is not None:
            punto = sitio_set.apartar(punto, trazados, cfg_sitio.calles, cfg_sitio.retiro_m) or punto
        situar(punto)
        ajustar_toma()
        flujo, fuera = medir()
        intento = {'lat': punto[0], 'lon': punto[1], 'converge': flujo['converged'], 'fuera': len(fuera),
                   'vmin': flujo.get('vm_min'), 'vmin_barra': flujo.get('vm_min_bus'),
                   'toma': int(getattr(tr, 'nntap', 0) or 0), 'u_media': u_media()}
        intentos.append(intento)
        peor = min(fuera, key=lambda x: x[0])[1] if fuera else None
        if mejor is None or clave(intento) > clave(mejor['intento']):
            mejor = {'intento': intento, 'punto': punto, 'peor': peor}
        else:
            paso /= 2                  # empeoró: se vuelve al mejor y se acerca la mitad (2026-11-01)
        if flujo['converged'] and not fuera:
            break
        destino = gps_de(mejor['peor']) if mejor['peor'] is not None else None
        if destino is None:
            break
        punto = _hacia(mejor['punto'], destino, paso)
    # El punto que queda es el mejor probado: antes quedaba el último, sin medir, y en NA203 +
    # NA205 la SET COPARA acabó a 18 km de las cargas con 460 barras fuera (2026-11-01).
    punto, elegido = mejor['punto'], mejor['intento']
    if elegido is not intentos[-1]:
        situar(punto)
        tr.nntap = elegido['toma']
        flujo_de_carga(app)
    flujos_finales = _ambos_flujos(app)                                               # 084:RF-8
    sitio = sitio_set.revisar(punto, trazados, cfg_sitio)
    sitio.update(movido=not sitio_set.mismo_punto(punto, punto_inicial),
                 original={'lat': punto_inicial[0], 'lon': punto_inicial[1]})
    sitio['frase'] = sitio_set.frase(sitio)
    fila['avisos'] += [a for a in sitio['avisos'] if a not in fila['avisos']]
    no_convergen = [k for k, v in flujos_finales.items() if not v['converge']]
    if no_convergen:
        fila['avisos'].append(f'En el punto final no converge el flujo {" ni el ".join(no_convergen)} (084:RF-8).')
    cumple = bool(elegido['converge'] and not elegido['fuera'] and not no_convergen)
    if not cumple:
        fila['avisos'].append(f'Ningún punto de los {len(intentos)} probados deja todas las barras de media '
                              f'entre {limites.tension_min_pu:g} y {limites.tension_max_pu:g} p.u.; queda el '
                              f'mejor, con {elegido["fuera"]} fuera (042:RF-10).')
    fila['set_nueva'] = {**fila.get('set_nueva', {}), 'lat': punto[0], 'lon': punto[1], 'cumple': cumple,
                         'toma': elegido['toma'], 'u_media': elegido['u_media'], 'consigna_pu': consigna,
                         'regula': regula, 'sitio': sitio,
                         'flujos_en_punto': {'lat': punto[0], 'lon': punto[1], **flujos_finales},
                         'intentos': intentos, 'transformador': tr.loc_name, 'tipo_transformador': tipo_tr.loc_name,
                         'uk_pct': tipo_tr.uktr, 'red_externa': xnet.loc_name, 'copiado_de': fuentes[0].loc_name,
                         'niveles': niveles,
                         'atributos_copiados': copiados,
                         'alimentadores_nuevos': [{k: x[k] for k in ('alimentador', 'entrada', 'feeder', 'largo_m')}
                                                  | {'linea': x['linea'].loc_name, 'nodo': x['nodo'].loc_name}
                                                  for x in lineas]}


def construir_expreso(ctx) -> None:
    """Alimentador expreso desde la barra de media de la SET del alimentador (042:RF-22).

    Por rama: una línea de la cabecera hasta el nodo, por las vías, con el tipo de la troncal (o el de la obra),
    su tramo de entrada abierto y un ``ElmFeeder`` nuevo. La zona no justifica una SET nueva.
    """
    hechos = []
    for texto in ctx.obra.ramas:
        alim, _, nodo = texto.partition('/')
        elm = ctx.alims.elm.get(alim) if ctx.alims is not None else None
        rama_red = ctx.redes.get(alim)
        if elm is None or rama_red is None or rama_red.topologia is None:
            raise RuntimeError(f'no se leyó el alimentador {alim} de la rama {texto}')
        cabecera = cabecera_de(elm)
        barras = {b.loc_name: b for b in elm.GetObjs('ElmTerm')}
        if cabecera is None or nodo not in barras:
            raise RuntimeError(f'{alim}: sin cabecera o sin el nodo {nodo}')
        parte = aguas_abajo(rama_red.topologia, rama_red.cabecera, nodo)
        lineas_f = {ln.loc_name: ln for ln in elm.GetObjs('ElmLne')}
        acopladores = {c.loc_name: c for c in elm.GetObjs('ElmCoup')}
        if parte.entrada in lineas_f:
            abrir(ctx, 'ElmLne', lineas_f[parte.entrada])                               # 042:RF-19, 081:RF-80
        elif parte.entrada in acopladores:
            abrir(ctx, 'ElmCoup', acopladores[parte.entrada])
        tipo = (ctx.tipo('TypLne', ctx.obra.tipo.nombre) if ctx.obra.tipo is not None else
                getattr(lineas_f.get((rama_red.troncal or ('',))[0]), 'typ_id', None))
        if tipo is None:
            raise RuntimeError(f'sin tipo de línea para el alimentador expreso hasta {nodo}: indíquelo')
        red = cabecera.GetParent()
        linea = red.CreateObject('ElmLne', nombre_libre(red, 'ElmLne', nombre_pf(f'EXP_{alim}_{nodo}')))
        linea.typ_id, linea.nlnum, linea.outserv = tipo, 1, 0
        for barra, lado in ((cabecera, 0), (barras[nodo], 1)):
            c = barra.CreateObject('StaCubic', nombre_pf(f'Cub_{linea.loc_name}_{lado}'))
            c.obj_id, c.obj_bus = linea, lado
            if lado == 0:
                salida = c
        # 087:RF-35: la salida nueva es una celda: su interruptor en el cubículo de la barra de la SET.
        interruptor = salida.CreateObject('StaSwitch', nombre_pf(f'CB_{linea.loc_name}'))
        interruptor.aUsage, interruptor.on_off = 'cbk', 1
        inicio, fin = gps_de(cabecera), gps_de(barras[nodo])
        largo_m = 0.0
        if inicio and fin:
            ruta = ruta_por_vias(tuple(inicio), tuple(fin), datos_perfil().get('vias'))
            largo_m = ruta.largo_m
            linea.SetAttribute('GPScoords', [list(q) for q in ruta.puntos])
        linea.dline = max(largo_m / 1000.0, 1e-3)
        nuevo = red.CreateObject('ElmFeeder', nombre_libre(red, 'ElmFeeder', nombre_pf(f'EXP_{alim}_{nodo}')))
        nuevo.obj_id, nuevo.iorient = salida, 0
        # 087:RF-34: la salida, el trazado y la llegada, georreferenciados.
        hechos.append({'alimentador': alim, 'nodo': nodo, 'entrada': parte.entrada, 'linea': linea.loc_name,
                       'feeder': nuevo.loc_name, 'largo_m': largo_m, 'desde': cabecera.loc_name,
                       'celda': {'barra': cabecera.loc_name, 'interruptor': interruptor.loc_name},
                       'salida_gps': list(inicio) if inicio else None, 'llegada_gps': list(fin) if fin else None,
                       'trazado': [list(q) for q in ruta.puntos] if inicio and fin else []})
    ctx.fila['expreso'] = {'alimentadores_nuevos': hechos}


def _estado_de(elm) -> dict:
    """Tensión mínima de media y carga máxima de los tramos de un alimentador con el último flujo (098:RF-24)."""
    us = [_resultado(b, 'm:u') for b in elm.GetObjs('ElmTerm') if float(getattr(b, 'uknom', 0) or 0) > 1.0]
    cs = [_resultado(ln, 'c:loading') for ln in elm.GetObjs('ElmLne')]
    us, cs = [u for u in us if u is not None], [c for c in cs if c is not None]
    return {'u_min': round(min(us), 4) if us else None, 'carga_max_pct': round(max(cs), 1) if cs else None}


def construir_maniobra(ctx) -> None:
    """098:RF-21, RF-24: la transferencia por un enlace que ya existe, sin construir nada.

    Se cierra el enlace si estaba abierto y se abre la maniobra, las dos anotadas (081:RF-80) para que la variante
    evaluada se restituya; después dice qué SED pasaron, con cuántos kW, y la tensión mínima y la carga máxima de los dos
    alimentadores antes y después. CA101 y CHN102 (2026-11-07): el enlace ya existía y no se probaba.
    """
    from cargas_pf import potencia

    o, fila, app = ctx.obra, ctx.fila, ctx.app
    maniobra = next(iter(_con_nombre(app, o.maniobra_clase, o.maniobra, o.maniobra_ruta or None)), None)
    enlace = next(iter(_con_nombre(app, o.enlace_clase, o.enlace, o.enlace_ruta or None)), None)
    if maniobra is None or enlace is None:
        raise RuntimeError(f'no está {o.maniobra if maniobra is None else o.enlace} en el proyecto: la transferencia '
                           'por el enlace existente no se puede hacer')
    vecino = (ctx.alims.elm.get(o.vecino) if ctx.alims is not None else None)
    if vecino is None:
        raise RuntimeError(f'el alimentador {o.vecino} que recibe no está en el proyecto')
    flujo_de_carga(app)
    cargas = {c.loc_name: c for c in ctx.elm.GetObjs('ElmLod')}
    antes = {o.alimentador: _estado_de(ctx.elm), o.vecino: _estado_de(vecino)}
    cerrado = (not int(getattr(enlace, 'outserv', 0) or 0)
               and (o.enlace_clase not in ('ElmCoup', 'StaSwitch') or int(getattr(enlace, 'on_off', 1) or 0)))
    if not cerrado:
        cerrar_anotado(ctx, o.enlace_clase, enlace)
    abrir(ctx, o.maniobra_clase, maniobra)
    flujo = flujo_de_carga(app)
    del_vecino = {c.loc_name for c in vecino.GetObjs('ElmLod')}
    pasan = sorted(n for n in cargas if n in del_vecino)
    fila['transferencia'] = {
        'enlace': o.enlace, 'enlace_cerrado_antes': bool(cerrado), 'maniobra': o.maniobra, 'vecino': o.vecino,
        'sed': pasan, 'kw': round(sum(potencia(cargas[n])[0] for n in pasan), 1),
        'antes': antes, 'despues': {o.alimentador: _estado_de(ctx.elm), o.vecino: _estado_de(vecino)},
        'converge': bool(flujo.get('converged'))}
    escenario = app.GetActiveScenario()
    if escenario is not None and not ctx.plan.get('evaluando'):
        escenario.Save()                     # 042:RF-19: abrir y cerrar son del escenario; la obra aplicada queda en él
    fila.setdefault('avisos', []).append(
        f"Transferencia de {o.alimentador} a {o.vecino} por {o.enlace}"
        + ('' if cerrado else ' (se cierra)') + f', abriendo {o.maniobra}: pasan {len(pasan)} SED, '
        f"{fila['transferencia']['kw']:,.1f} kW (098:RF-24).")


CONSTRUCTORES.update(set_nueva=construir_set_nueva, expreso=construir_expreso, maniobra=construir_maniobra)
CONSTRUCTORES.update(condensador=construir_condensador, reconectador=construir_reconectador,
                     regulador=construir_regulador, seccion=construir_seccion,
                     terna=construir_terna, tension=construir_tension, enlace=construir_enlace,
                     migracion=construir_migracion, consigna=construir_consigna)

#: Obras que necesitan la troncal o la red: sin tramos indicados, la sección y la terna
#: van a la troncal (RF-77, RF-80); el enlace se apoya en las dos troncales y la migración
#: toma lo que queda aguas abajo de un nodo (spec 016).
CON_TRONCAL = ('seccion', 'terna', 'enlace', 'migracion', 'set_nueva', 'expreso')


def leer_troncal(elm, f: str) -> tuple[tuple[str, ...], object, str, list[str]]:
    """(troncal, red, cabecera, avisos) del alimentador en el caso activo (016:RF-1, RF-2).

    Es la troncal del camino más largo de ``convertersmartgrid.troncal``, no la de ``ComBbone``:
    DIgSILENT solo dibuja troncales entre alimentadores con un enlace, e IN111 no tenía
    ninguno (2026-10-14). El N-1 y la transferencia siguen con ``ComBbone`` (016:RF-10).
    Solo cuentan las líneas: un seccionador del camino une, pero no se le cambia el tipo.
    """
    cabecera = cabecera_de(elm)
    if cabecera is None:
        return (), None, '', [f'{f}: el ElmFeeder no dice su cabecera; sin troncal, la sección y '
                              'la terna necesitan los tramos indicados.']
    red = leer_red(elm, cabecera)
    t = troncal_de(red, cabecera.loc_name)
    lineas = {ln.loc_name for ln in elm.GetObjs('ElmLne')}
    avisos = []
    if t.mallas:
        avisos.append(f'{f}: hay anillos cerrados; para la troncal cada barra cuelga de su camino '
                      f'más corto y se dejan fuera {", ".join(t.mallas)}.')
    return tuple(n for n in t.tramos if n in lineas), red, cabecera.loc_name, avisos


def _fuente_de_tipo(app, tipo: dict, plan: dict):
    """El tipo original que la fila del plan manda copiar, en su biblioteca."""
    clase, origen = tipo['clase'], tipo['origen']
    if origen == 'proyecto':
        carpeta = app.GetLocalLibrary(clase)
    elif origen == 'global':
        carpeta = app.GetGlobalLibrary(clase)
    else:
        otro = buscar_proyecto(app, plan.get('otro_proyecto') or '',
                               plan.get('folder') or nombre_de_perfil())
        carpeta = biblioteca_de_otro(otro) if otro is not None else None
    hallado = next((o for o in _tipos_en(carpeta, clase)
                    if o.loc_name.lower() == tipo['desde'].lower()), None)
    if hallado is None:
        raise RuntimeError(f"no está el tipo {tipo['desde']!r} ({clase}) en la biblioteca {origen}")
    return hallado


def _leer(app, plan, alims, feeders, obras, casos) -> tuple[dict, list, list[str]]:
    """Redes, tipos y avisos de la lectura, cada alimentador en el caso de sus obras.

    En «Sin proyecto», salvo los alimentadores cuyas obras son todas de «Con proyecto»
    (el enlace y la migración), que se leen allí: la red sobre la que se hace la obra
    (016:RF-2), con lo que ya tenga «Con proyecto», como un enlace abierto anterior.
    """
    redes, avisos = {}, []
    toca: dict[str, set[str]] = {}
    solo_con: dict[str, bool] = {}
    for o in obras:
        # 042:RF-6: la SET nueva toca también los alimentadores de sus ramas.
        for g in (o.alimentador, o.cede, *(r.partition('/')[0] for r in o.ramas)):
            if g:
                toca.setdefault(g, set()).add(o.clase)
                solo_con[g] = solo_con.get(g, True) and NOMBRES['sin'] not in o.casos
    con_troncal = {f for f, clases in toca.items() if clases & set(CON_TRONCAL)}
    # También las obras que el operador pone solo en «Con proyecto»: tras una migración,
    # la parte que pasó cuelga de otro alimentador allí (SEC_1091_307903 de IN111 lo
    # alimenta TA225), y leída en «Sin proyecto» la terna se rechazaba (2026-10-15).
    en_con = {f for f, clases in toca.items()
              if clases <= set(SOLO_CON_PROYECTO) or solo_con.get(f)}
    for rol, grupo in (('con', [f for f in feeders if f in en_con]),
                       ('sin', [f for f in feeders if f not in en_con])):
        if not grupo:
            continue
        # Sin «Con proyecto» todavía (se crea después de las obras de «Sin proyecto»,
        # 016:RF-12), su red es la de «Sin proyecto».
        (casos.get(rol) or casos['sin']).Activate()
        # La obra se graba con las cargas nuevas apartadas (ver _apartar_cargas_nuevas): se
        # lee la misma red sobre la que se escribe, sin sus barras de la troncal partida.
        apartadas = _apartar_cargas_nuevas(app) if rol in casos and rol == 'con' else []
        try:
            # El ElmFeeder da sus objetos según la última topología calculada: sin un flujo
            # después de cambiar las variaciones activas, el nodo que creó el enlace unas
            # veces estaba en IN111 y otras no (2026-10-15).
            flujo_de_carga(app)
            _leer_grupo(grupo, alims, con_troncal, redes, avisos)
        finally:
            for v in apartadas:
                v.Activate()
    casos['sin'].Activate()
    otro = None
    if plan.get('otro_proyecto'):
        otro = buscar_proyecto(app, plan['otro_proyecto'], plan.get('folder') or nombre_de_perfil())
        if otro is None or biblioteca_de_otro(otro) is None:
            avisos.append(f"No se pudo leer el proyecto {plan['otro_proyecto']!r}.")
            otro = None
    tipos = [tipo_de_ficha(t) for t in leer_tipos(app, CLASES_TIPO, otro, str(plan.get('otro_proyecto') or ''))]
    return redes, tipos, avisos


def _apartar_cargas_nuevas(app) -> list:
    """Desactiva las variaciones de cargas nuevas (007) del caso activo y las devuelve.

    DIgSILENT no deja grabar una etapa nueva con tres o más etapas activas de la misma
    fecha, ni con ``Activate(1)`` ni cambiando el orden de reactivación: IN111 + TA225
    (2026-10-15, sonda en el proyecto), con las nueve cargas nuevas de TA225 activas en
    «Con proyecto», el enlace no grababa; con dos, sí. La 007 ya crea cada carga con las
    demás apartadas; la obra hace lo mismo y se devuelven antes de su flujo.
    """
    apartadas = [v for v in (app.GetActiveNetworkVariations() or []) if es_de_carga_nueva(v)]
    for v in apartadas:
        v.Deactivate()
    return apartadas


def _leer_grupo(grupo, alims, con_troncal, redes, avisos) -> None:
    """Lee la red de cada alimentador del grupo en el caso activo."""
    for f in grupo:
        elm = alims.elm.get(f)
        if elm is None:
            avisos.append(f'El alimentador {f} no está en el proyecto.')
            continue
        leido = leer_alimentador(elm)
        # RF-102: si otro alimentador sale de la misma barra, comparte barra y fuente, y
        # migrar esa barra lo cambiaría también a él. Por su clave y no con ``is``: la API da
        # un objeto nuevo en cada acceso, y la barra de la SET 51 de Nasca, de la que salen
        # NA203, NA205 y los demás, no se veía compartida (2026-10-24).
        cabecera = cabecera_de(elm)
        propia = clave_pf(cabecera) if cabecera is not None else None
        leido['cabecera_compartida_con'] = sorted(
            g for g, otro in alims.elm.items()
            if g != f and propia is not None and (c := cabecera_de(otro)) is not None
            and clave_pf(c) == propia)
        troncal, topologia, nombre_cabecera = (), None, ''
        if f in con_troncal:
            troncal, topologia, nombre_cabecera, avisos_troncal = leer_troncal(elm, f)
            avisos += avisos_troncal
        try:
            redes[f] = red_de_lectura(f, leido, troncal=troncal, topologia=topologia,
                                      cabecera=nombre_cabecera)
        except ObrasError as exc:
            avisos.append(str(exc))


def _aplicar_una(app, plan, proyecto, casos, alims, obra: Obra, fila: dict, red,
                 redes=None, conjunto: bool = False) -> None:
    """Una obra en su variación y en sus casos. Deja en ``fila`` lo que pasó.

    Solo en los casos que ya existen: si falta «Con proyecto», ``aplicar`` lo crea después
    como copia de «Sin proyecto» y la obra pasa a él con la copia (016:RF-12).
    """
    roles = [ROL_DE_CASO[c] for c in obra.casos if ROL_DE_CASO[c] in casos]
    casos[roles[0]].Activate()
    apartadas = _apartar_cargas_nuevas(app) if roles[0] == 'con' else []
    try:
        _grabar_una(app, plan, proyecto, casos, alims, obra, fila, red, redes)
    finally:
        if apartadas:
            casos['con'].Activate()
            for v in apartadas:
                v.Activate()
    if apartadas and fila['variacion']:
        # Una obra y una carga que graban el mismo objeto (p. ej. el mismo tramo de la
        # troncal partido) se pisarían: se avisa, no se decide cuál manda.
        # Por la ruta dentro de la etapa: «Cub_0» o «Terminal» se repiten en cada tramo.
        propios = _grabados(_variacion(app, fila['variacion']))
        comunes = sorted(n for n in set().union(*(_grabados(v) for v in apartadas)) & propios
                         # SplitLine llama «Terminal» y «Cub_0/1» a lo que crea en cada etapa:
                         # objetos distintos con el mismo nombre, no el mismo objeto.
                         if not re.fullmatch(r'Terminal\.ElmTerm|Cub_\d+\.StaCubic', n.lstrip('\\')))
        if comunes:
            fila['avisos'].append('La obra y alguna carga nueva graban los mismos objetos: '
                                  + ', '.join(comunes[:10]))
    if not fila['variacion']:
        return
    variacion = _variacion(app, fila['variacion'])
    # Activa solo en sus casos (RF-57); en el «Caso base», nunca (RF-58).
    for rol in NOMBRES:
        if rol not in casos:
            continue
        casos[rol].Activate()
        if rol in roles:
            variacion.Activate()
        else:
            variacion.Deactivate()

    fila['casos_activos'], fila['flujo'] = [], {}
    if conjunto:
        return                    # 042:RF-23: el flujo es del plan completo, después de crearlas todas
    for rol in roles:                                                     # RF-66
        _flujo_con_la_obra(app, proyecto, casos, obra, fila, variacion, rol, plan=plan)


def flujo_del_plan(app, proyecto, casos, filas: list[dict], plan: dict | None = None) -> dict:
    """042:RF-23: un solo flujo de «Con proyecto» con todas las obras del plan; si no converge, se apagan todas."""
    con = [f for f in filas if f.get('variacion') and not f.get('error')]
    if not con or 'con' not in casos:
        return {'obras': 0}
    nombre = NOMBRES['con']
    casos['con'].Activate()
    flujo = flujo_de_carga(app)
    for f in con:
        f['flujo'][nombre] = {'converge': flujo['converged'], 'en_conjunto': True}
        if flujo['converged']:
            f['casos_activos'].append(nombre)
    if flujo['converged']:
        return {'obras': len(con), 'converge': True, 'vm_min': flujo.get('vm_min')}
    diag = diagnostico(Alimentadores(app, proyecto, sorted({f['alimentador'] for f in con})),
                       con[0]['alimentador'], {}, {})
    for f in con:
        _variacion(app, f['variacion']).Deactivate()
        cerrar_lo_abierto(app, f, plan)                                       # 042:RF-19
        f['flujo'][nombre]['diagnostico'] = diag
        f['avisos'].append(f'Con el plan completo ({len(con)} obras), el flujo de «{nombre}» no converge: '
                           'quedan inactivas y se conservan en el proyecto (042:RF-23).')
    return {'obras': len(con), 'converge': False}


def _grabados(variacion) -> set[str]:
    """Lo que graban las etapas de la variación, por su ruta relativa a la etapa."""
    out = set()
    for etapa in variacion.GetContents('*.IntSstage'):
        raiz = etapa.GetFullName()
        out |= {o.GetFullName().replace(raiz, '', 1) for o in etapa.GetContents('*', 1)}
    return out


def _variacion(app, nombre: str):
    carpeta = app.GetProjectFolder('scheme')
    return next(v for v in carpeta.GetContents('*.IntScheme', 1) if v.loc_name == nombre)


def _grabar_una(app, plan, proyecto, casos, alims, obra: Obra, fila: dict, red,
                redes) -> None:
    """Crea la variación de la obra y graba en ella; si falla, la borra y deja el error."""
    try:
        variacion, _etapa = crear_variacion(app, fila['variacion'], fila['variacion'])
    except RuntimeError as exc:
        fila.update(variacion='', error=f'no se pudo crear la obra: {exc}')
        return
    fila['variacion'] = variacion.loc_name
    try:
        ctx = Contexto(app, proyecto, obra, fila, red, alims.elm[obra.alimentador], alims=alims,
                       redes=redes, plan=plan)
        ctx.casos = {r: casos[r] for r in (ROL_DE_CASO.get(c) for c in obra.casos) if r in casos}
        for t in fila['tipos']:                                            # RF-60
            copia, reutiliza, aviso = copiar_tipo(app, _fuente_de_tipo(app, t, plan),
                                                  t['nombre'], t['datos'])
            ctx.copias[t['nombre']] = copia
            t.update(nombre=copia.loc_name, reutiliza=reutiliza)
            if aviso:
                fila['avisos'].append(aviso)
            ctx.tipos[(t['clase'], t['desde'])] = copia
        CONSTRUCTORES[obra.clase](ctx)
    except Exception as exc:  # noqa: BLE001 - la obra no queda a medias; las demás siguen
        # Activa y grabando, DIgSILENT no la borra y se quedaba con lo escrito a medias
        # (una Obra_migracion_IN111 inactiva con 1457 objetos, 2026-10-15).
        variacion.Deactivate()
        variacion.Delete()
        cerrar_lo_abierto(app, fila, plan)                                    # 042:RF-19
        fila.update(variacion='', error=f'no se pudo crear la obra: {exc}')
        return



def _flujo_con_la_obra(app, proyecto, casos, obra: Obra, fila: dict, variacion, rol: str,
                       plan: dict | None = None) -> None:
    """El flujo del caso con la obra activa; si no converge, la obra queda inactiva allí."""
    nombre = NOMBRES[rol]
    casos[rol].Activate()
    flujo = flujo_de_carga(app)
    fila['flujo'][nombre] = {'converge': flujo['converged']}
    if flujo['converged']:
        fila['casos_activos'].append(nombre)
        return
    # RF-67: el diagnóstico se lee antes de desactivarla, con lo que dejó este flujo.
    fila['flujo'][nombre]['diagnostico'] = diagnostico(
        Alimentadores(app, proyecto, [obra.alimentador]), obra.alimentador, {}, {})
    variacion.Deactivate()
    cerrar_lo_abierto(app, fila, plan)                                        # 042:RF-19
    fila['avisos'].append(f'Con la obra, el flujo de «{nombre}» no converge: queda inactiva '
                          'en ese caso y se conserva en el proyecto.')


def cerrar_lo_abierto(app, fila: dict, plan: dict | None = None) -> list[str]:
    """042:RF-19: abrir es dato del escenario; con la obra inactiva, lo abierto se vuelve a cerrar en el caso activo.

    081:RF-81: también lo que quedó fuera de servicio, que ``GetCalcRelevantObjects`` no devuelve; y sale del registro.
    """
    cerrados = []
    for entrada in fila.get('abiertos') or []:
        clase, nombre = entrada[0], entrada[1]
        for obj in _con_nombre(app, clase, nombre, entrada[3] if len(entrada) > 3 else None):
            _cerrar(clase, obj)
            cerrados.append(nombre)
    reabiertos = []
    for entrada in fila.get('cerrados') or []:                                   # 098:RF-21
        for obj in _con_nombre(app, entrada[0], entrada[1], entrada[3] if len(entrada) > 3 else None):
            _reabrir(entrada[0], obj)
            reabiertos.append(entrada[1])
    if cerrados:
        fila.setdefault('avisos', []).append('La obra quedó inactiva: se vuelven a cerrar ' + ', '.join(cerrados)
                                             + ', que había abierto (042:RF-19).')
    if reabiertos:
        fila.setdefault('avisos', []).append('La obra quedó inactiva: se vuelven a abrir ' + ', '.join(reabiertos)
                                             + ', que había cerrado (098:RF-21).')
    if plan is not None:
        quitar_aperturas(plan, [fila])
    return cerrados


# =========================================================================== aperturas (081:RF-80 a RF-85)
# Abrir un tramo o una llave es dato de operación: con el escenario del caso activo, DIgSILENT lo guarda en el escenario y
# no en la etapa de la variación que graba (042:RF-19; referencia de Python de PF 2024, IntScenario: «Saves the current
# active value of all operational attributes», y el escenario manda sobre la red). Borrar la variación de una variante no
# lo deshace. Pisco (2026-11-07): la escalera se cortó mientras medía una transferencia (087:RF-31) y «Con proyecto» se
# quedó con SEC_1091_1055499 y SEC_1091_957116 fuera de servicio, 724 barras de media sin tensión y la confirmación
# conjunta rehaciendo obras sobre una red rota. Por eso cada apertura se anota antes de hacerla, en la fila y en disco, y
# se restituye al borrar la variante o al empezar la orden siguiente.

def _con_nombre(app, clase: str, nombre: str, ruta: str | None = None) -> list:
    """Los elementos con ese nombre, también fuera de servicio: ``GetCalcRelevantObjects`` no devuelve esos (RF-81).

    098:RF-12: con ``ruta`` (el nombre completo), solo ese. Un interruptor de cubículo no tiene nombre único («Switch»
    en cada tramo que parte ``SplitLine``): sin ella se habrían cerrado todos los del mismo nombre."""
    # Por el nombre también aquí: el doble filtra el patrón solo por la clase.
    vivos = [o for o in (app.GetCalcRelevantObjects(f'{nombre}.{clase}') or []) if getattr(o, 'loc_name', nombre) == nombre]
    if not vivos and hasattr(app, 'GetProjectFolder'):
        donde = app.GetProjectFolder('netdat') or app.GetActiveProject()
        vivos = [o for o in ((donde.GetContents(f'{nombre}.{clase}', 1) if donde is not None else None) or [])
                 if o.loc_name == nombre and o.GetClassName() == clase]
    return [o for o in vivos if o.GetFullName() == ruta] if ruta else vivos


def _reabrir(clase: str, obj) -> None:
    """098:RF-21: lo que una obra cerró (el enlace existente), otra vez abierto."""
    if clase in ('ElmCoup', 'StaSwitch'):
        obj.on_off = 0
    else:
        obj.outserv = 1


def cerrar_anotado(ctx, clase: str, obj) -> None:
    """098:RF-21: como :func:`abrir`, pero al revés: anota que se cierra, en la fila y en disco, y después cierra.

    El enlace existente de una transferencia se cierra en «Con proyecto»; al borrar la variante evaluada o si la orden
    muere, se vuelve a abrir (081:RF-81, RF-82). Por su nombre completo (098:RF-19)."""
    caso = getattr(ctx.app.GetActiveStudyCase(), 'loc_name', '') or ''
    completo = obj.GetFullName()
    ctx.fila.setdefault('cerrados', []).append([clase, obj.loc_name, caso, completo])
    if ctx.plan.get('project'):
        ruta = fichero_aperturas(ctx.plan)
        entradas = leer_aperturas(ruta)
        entradas.append({'proyecto': ctx.plan['project'], 'caso': caso, 'clase': clase, 'nombre': obj.loc_name,
                         'variacion': ctx.fila.get('variacion') or '', 'evaluando': bool(ctx.plan.get('evaluando')),
                         'fecha': time.strftime('%Y-%m-%dT%H:%M:%S'), 'ruta': completo, 'accion': 'cerrar'})
        try:
            escribir_aperturas(ruta, entradas)
        except OSError as exc:
            ctx.fila.setdefault('avisos', []).append(f'No se pudo anotar en disco el cierre de {obj.loc_name}: {exc} '
                                                     '(098:RF-21).')
    _cerrar(clase, obj)


def _cerrar(clase: str, obj) -> None:
    if clase in ('ElmCoup', 'StaSwitch'):
        obj.on_off = 1
    if clase != 'StaSwitch':
        obj.outserv = 0


def abrir(ctx, clase: str, obj) -> None:
    """081:RF-80: anota la apertura en la fila y en el registro de disco, y después abre."""
    caso = getattr(ctx.app.GetActiveStudyCase(), 'loc_name', '') or ''
    # 098:RF-12: un interruptor de cubículo va con su nombre completo; su nombre no es único.
    completo = obj.GetFullName() if clase == 'StaSwitch' else None
    ctx.fila.setdefault('abiertos', []).append([clase, obj.loc_name, caso] + ([completo] if completo else []))  # 042:RF-19
    if ctx.plan.get('project'):
        ruta = fichero_aperturas(ctx.plan)
        entradas = leer_aperturas(ruta)
        entradas.append({'proyecto': ctx.plan['project'], 'caso': caso, 'clase': clase, 'nombre': obj.loc_name,
                         'variacion': ctx.fila.get('variacion') or '', 'evaluando': bool(ctx.plan.get('evaluando')),
                         'fecha': time.strftime('%Y-%m-%dT%H:%M:%S'), **({'ruta': completo} if completo else {})})
        try:
            escribir_aperturas(ruta, entradas)
        except OSError as exc:
            ctx.fila.setdefault('avisos', []).append(f'No se pudo anotar en disco la apertura de {obj.loc_name}: {exc}; '
                                                     'si la orden muere, no se restituirá sola (081:RF-80).')
    if clase in ('ElmCoup', 'StaSwitch'):
        obj.on_off = 0
    else:
        obj.outserv = 1


def quitar_aperturas(plan: dict, filas: list[dict]) -> None:
    """Saca del registro las aperturas de ``filas``: ya restituidas, o de una obra que queda aplicada (RF-81)."""
    if not plan.get('project'):
        return
    propias = [{'caso': (e[2] if len(e) > 2 else ''), 'clase': e[0], 'nombre': e[1]}
               for f in filas for e in list(f.get('abiertos') or []) + list(f.get('cerrados') or [])]
    propias += [{'caso': e.get('caso') or '', 'clase': e.get('clase'), 'nombre': e.get('nombre')}      # 098:RF-34
                for f in filas for e in f.get('valores') or []]
    if not propias:
        return
    ruta = fichero_aperturas(plan)
    entradas = leer_aperturas(ruta)
    # Sin la variación en la comparación: al fallar una obra, su fila pierde el nombre de la variación (``_grabar_una``).
    quedan = [e for e in entradas if e.get('accion') in ACCIONES_ESPECIALES
              or not any(misma_apertura({**e, 'variacion': None}, {**p, 'variacion': None}) for p in propias)]
    if len(quedan) != len(entradas):
        try:
            escribir_aperturas(ruta, quedan)
        except OSError:
            pass


def restituir_lo_abierto(app, casos: dict, filas: list[dict], plan: dict) -> list[str]:
    """081:RF-81: lo que abrieron las obras de una variante, otra vez cerrado en el caso donde se abrió.

    Al borrar la variante se borra lo que grabó su variación, pero no lo que el escenario guardó al abrir."""
    por_caso: dict[str, list] = {}
    for f in filas:
        for accion in ('abiertos', 'cerrados'):                                  # 098:RF-21: también lo cerrado
            for e in f.get(accion) or []:
                por_caso.setdefault(e[2] if len(e) > 2 else '', []).append((accion, e))
    if not por_caso:
        return []
    por_nombre = {c.loc_name: c for c in casos.values()}
    cerrados = []
    for caso, entradas in por_caso.items():
        if por_nombre.get(caso) is not None:
            por_nombre[caso].Activate()
        for accion, e in entradas:
            for obj in _con_nombre(app, e[0], e[1], e[3] if len(e) > 3 else None):
                (_reabrir if accion == 'cerrados' else _cerrar)(e[0], obj)
                cerrados.append(e[1])
    quitar_aperturas(plan, filas)
    return cerrados


def restituir_pendientes(app, plan: dict, casos: dict, informe: dict) -> list[dict]:
    """081:RF-82: al empezar una orden, lo que dejó abierto una orden de obras que no terminó, otra vez cerrado.

    Lo de una obra aplicada (no evaluada) cuya variación sigue activa en su caso es la obra: se respeta. Lo restituido se
    guarda en el escenario del caso y el informe lo dice con su lista."""
    if not plan.get('project'):
        return []
    ruta = fichero_aperturas(plan)
    todas = [e for e in leer_aperturas(ruta) if e.get('proyecto') in (None, plan['project'])]
    especiales = [e for e in todas if e.get('accion') in ACCIONES_ESPECIALES]
    recuperadas = _recuperar_especiales(app, plan, casos, especiales, informe)            # 098:RF-36
    entradas = [e for e in todas if e.get('accion') not in ACCIONES_ESPECIALES]
    if not entradas:
        return recuperadas
    por_nombre = {c.loc_name: c for c in casos.values()}
    carpeta = app.GetProjectFolder('scheme')
    existen = {v.loc_name for v in ((carpeta.GetContents('*.IntScheme', 1) if carpeta else None) or [])}
    inicial = app.GetActiveStudyCase()
    restituidas: list[dict] = []
    respetadas: list[dict] = []
    quedan: list[dict] = []
    try:
        for caso in dict.fromkeys(e.get('caso') or '' for e in entradas):
            objeto_caso = por_nombre.get(caso)
            grupo = [e for e in entradas if (e.get('caso') or '') == caso]
            if objeto_caso is None:
                quedan += grupo          # de otro año o de un caso que no se ha abierto: espera a su orden
                continue
            objeto_caso.Activate()
            activas = {v.loc_name for v in app.GetActiveNetworkVariations() or []}
            hechas = 0
            for e in grupo:
                if not e.get('evaluando') and e.get('variacion') and e['variacion'] in activas:
                    respetadas.append(e)
                    continue
                if e.get('accion') == 'valor':                                  # 098:RF-34
                    objs = ([_ldf_del_caso(app, objeto_caso)] if e.get('clase') == 'ComLdf'
                            else _con_nombre(app, e['clase'], e['nombre'], e.get('ruta')))
                    for obj in objs:
                        if obj is not None:
                            setattr(obj, e['atributo'], e.get('valor'))
                            hechas += 1
                    restituidas.append(e)
                    continue
                for obj in _con_nombre(app, e['clase'], e['nombre'], e.get('ruta')):
                    (_reabrir if e.get('accion') == 'cerrar' else _cerrar)(e['clase'], obj)       # 098:RF-21
                    hechas += 1
                restituidas.append(e)
            escenario = app.GetActiveScenario()
            if hechas and escenario is not None:
                escenario.Save()
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    try:
        # Lo especial que sigue vigente (el valor original del flujo, la sustitución en curso de esta orden) se queda.
        vigentes = [e for e in leer_aperturas(ruta) if e.get('accion') in ACCIONES_ESPECIALES]
        escribir_aperturas(ruta, quedan + vigentes)
    except OSError:
        pass
    if restituidas:
        nombres = ', '.join(sorted({f"{e['nombre']} en «{e.get('caso')}»" for e in restituidas}))
        informe.setdefault('avisos', []).append(
            f'Una orden de obras anterior no terminó y dejó abierto {nombres}: se vuelve a cerrar, como estaba (081:RF-82).')
        sueltas = sorted({e['variacion'] for e in restituidas if e.get('evaluando') and e.get('variacion') in existen})
        if sueltas:
            informe['avisos'].append('Quedan en el proyecto las variaciones de la evaluación cortada: '
                                     + ', '.join(sueltas) + '; retírelas con las obras del alimentador (042:RF-60).')
    informe['aperturas_restituidas'] = [{k: e.get(k) for k in ('caso', 'clase', 'nombre', 'variacion')} for e in restituidas]
    return restituidas


def _esquemas(app) -> dict:
    carpeta = app.GetProjectFolder('scheme')
    return {v.loc_name: v for v in ((carpeta.GetContents('*.IntScheme', 1) if carpeta is not None else None) or [])}


def _diario(plan: dict, entrada: dict) -> None:
    """098:RF-36: el paso de una sustitución en el registro de disco, para completarla o deshacerla si la orden muere."""
    ruta = fichero_aperturas(plan)
    entradas = [e for e in leer_aperturas(ruta) if not (e.get('accion') == entrada.get('accion')
                                                         and e.get('id') == entrada.get('id'))]
    escribir_aperturas(ruta, entradas + [entrada])


def _quitar_diario(plan: dict, accion: str, ident: str) -> None:
    ruta = fichero_aperturas(plan)
    entradas = leer_aperturas(ruta)
    quedan = [e for e in entradas if not (e.get('accion') == accion and e.get('id') == ident)]
    if len(quedan) != len(entradas):
        escribir_aperturas(ruta, quedan)


def anotar_apartadas(plan: dict, caso, nombres: list[str]) -> str | None:
    """098:RF-36: la obra que se aparta de la medida por su nombre, anotada antes: si la orden muere con ella apartada,
    la siguiente la vuelve a activar (:func:`restituir_pendientes`)."""
    if not nombres or not plan.get('project'):
        return None
    ident = f'{time.time_ns():x}'
    try:
        _diario(plan, {'accion': 'apartada', 'id': ident, 'proyecto': plan['project'],
                       'caso': getattr(caso, 'loc_name', '') or '', 'variaciones': list(nombres),
                       'fecha': time.strftime('%Y-%m-%dT%H:%M:%S')})
    except OSError:
        return None
    return ident


def _reactivar(app, caso, nombres) -> list[str]:
    if caso is not None:
        caso.Activate()
    activas = {v.loc_name for v in app.GetActiveNetworkVariations() or []}
    esquemas = _esquemas(app)
    hechas = []
    for n in nombres or ():
        v = esquemas.get(n)
        if v is not None and n not in activas:
            v.Activate()
            hechas.append(n)
    return hechas


def _borrar_variaciones(app, casos: dict, nombres) -> tuple[list[str], list[str]]:
    """Las variaciones nombradas, desactivadas en cada caso y borradas; las que siguen después, aparte (098:RF-36)."""
    esquemas = _esquemas(app)
    borradas = []
    for n in nombres or ():
        v = esquemas.get(n)
        if v is None:
            continue
        for rol in ('sin', 'con'):
            if rol in casos:
                casos[rol].Activate()
                v.Deactivate()
        v.Delete()
        borradas.append(n)
    quedan = sorted(set(nombres or ()) & set(_esquemas(app)))
    return [n for n in borradas if n not in quedan], quedan


def deshacer_operacion(app, plan: dict, casos: dict, filas: list[dict], avisos: list[str]) -> set[str]:
    """098:RF-34, RF-36: lo que hicieron en la operación las obras de ``filas`` (lo abierto, lo cerrado, las tomas), como
    estaba; el ajuste de tomas del flujo, como antes de la primera obra con regulador si ya no queda ninguna. Devuelve
    los casos donde algo cambió."""
    cambiados: set[str] = set()
    for f in filas:
        for accion in ('abiertos', 'cerrados'):
            for e in f.get(accion) or []:
                caso = e[2] if len(e) > 2 else ''
                if restituir_lo_abierto(app, casos, [{accion: [e]}], plan):
                    cambiados.add(caso)
    valores = [e for f in filas for e in f.get('valores') or []
               if not (e.get('clase') == 'ComLdf' and e.get('atributo') == 'iopt_at')]
    for e in valores:
        if restituir_valores(app, casos, [e], avisos):
            cambiados.add(e.get('caso') or '')
    if restituir_flujo_original(app, plan, casos, avisos):
        cambiados |= {c.loc_name for c in casos.values()}
    return cambiados


def rehacer_operacion(app, casos: dict, filas: list[dict]) -> set[str]:
    """098:RF-36: la operación de las obras de ``filas`` otra vez como la dejaron: lo abierto, abierto; lo cerrado,
    cerrado; los valores, el que pusieron (el ajuste de tomas, activo)."""
    por_nombre = {c.loc_name: c for c in casos.values()}
    cambiados: set[str] = set()
    for f in filas:
        for accion in ('abiertos', 'cerrados'):
            for e in f.get(accion) or []:
                caso = e[2] if len(e) > 2 else ''
                if por_nombre.get(caso) is not None:
                    por_nombre[caso].Activate()
                for obj in _con_nombre(app, e[0], e[1], e[3] if len(e) > 3 else None):
                    (_reabrir if accion == 'abiertos' else _cerrar)(e[0], obj)
                    cambiados.add(caso)
        for e in f.get('valores') or []:
            nuevo = e.get('nuevo', 1 if e.get('clase') == 'ComLdf' else None)
            if nuevo is None:
                continue
            caso = por_nombre.get(e.get('caso'))
            if caso is not None:
                caso.Activate()
            objs = ([_ldf_del_caso(app, caso)] if e.get('clase') == 'ComLdf'
                    else _con_nombre(app, e['clase'], e['nombre'], e.get('ruta')))
            for o in objs:
                if o is not None:
                    setattr(o, e['atributo'], nuevo)
                    cambiados.add(e.get('caso') or '')
    return cambiados


def _guardar_escenarios(app, casos: dict, nombres: set[str]) -> None:
    """Guarda el escenario solo de los casos donde algo cambió: guardar otro guardaba lo ajeno (098:RF-36)."""
    if not nombres:
        return
    for c in casos.values():
        if c.loc_name in nombres:
            c.Activate()
            escenario = app.GetActiveScenario() if hasattr(app, 'GetActiveScenario') else None
            if escenario is not None:
                escenario.Save()


def deshacer_sustitucion(app, plan: dict, casos: dict, creadas, viejas, operacion, filas_nuevas,
                         operacion_deshecha: bool, avisos: list[str]) -> None:
    """098:RF-36: la nueva, fuera (lo que creó y lo que hizo en la operación); la vieja, otra vez activa con su operación.
    La vieja no se recrea: nunca se borró. Cada paso en su ``try``, para que uno que falle no impida los demás."""
    cambiados: set[str] = set()
    try:
        cambiados |= deshacer_operacion(app, plan, casos, list(filas_nuevas or []), avisos)
    finally:
        try:
            _borrar_variaciones(app, casos, creadas)
        finally:
            try:
                _reactivar(app, casos.get('con'), viejas)
            finally:
                try:
                    if operacion_deshecha:
                        cambiados |= rehacer_operacion(app, casos, list(operacion or []))
                finally:
                    _guardar_escenarios(app, casos, cambiados | ({casos['con'].loc_name} if 'con' in casos else set()))


class _Deshacer(Exception):
    """La obra nueva de una sustitución no quedó como debía: se deshace (098:RF-36)."""


def _por_que_no_queda(hecho: dict, caso_con: str) -> str | None:
    if hecho.get('error'):
        return str(hecho['error'])
    filas = hecho.get('obras') or []
    if not filas:
        return 'no se creó ninguna obra'
    for f in filas:
        if f.get('error'):
            return f"{f.get('variacion') or f.get('clase')}: {f['error']}"
        if not f.get('variacion'):
            return f"{f.get('clase')}: no se creó su variación"
        if caso_con not in (f.get('casos_activos') or []):
            return f"{f['variacion']} no quedó activa en «{caso_con}»"
        if not all(x.get('converge') for x in (f.get('flujo') or {}).values()):
            return f"con {f['variacion']} el flujo no converge"
    return None


def sustituir(app, plan: dict) -> tuple[dict, int]:
    """098:RF-36: la obra nueva en lugar de la vieja de la escalera, sin quedarse nunca sin obra.

    Con la vieja desactivada por su nombre en «Con proyecto» y su operación deshecha, se aplica la nueva; si queda
    activa y su flujo converge, se borra la vieja y se comprueba que no queda ninguna; si algo falla (también una
    excepción o la orden cortada), se borra lo creado de la nueva y la vieja vuelve, activa y con su operación. Cada paso
    va al registro de disco: si el proceso muere, :func:`restituir_pendientes` completa o deshace.
    """
    s = dict(plan.get('sustituir') or {})
    viejas = [str(x) for x in s.get('variaciones') or []]
    operacion = list(s.get('operacion') or [])
    base: dict[str, Any] = {'project': plan.get('project'), 'modo': 'sustituir', 'obras': [], 'avisos': []}
    if not viejas:
        return {**base, 'error': 'sin las variaciones de la obra que se sustituye (098:RF-36)'}, 2
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**base, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    casos = casos_del_proyecto(app, anio_del_plan(plan))
    if 'con' not in casos:
        return {**base, 'error': 'falta «Con proyecto»'}, 2
    antes = sorted(_esquemas(app))
    ident = f'{time.time_ns():x}'
    entrada = {'accion': 'sustitucion', 'id': ident, 'proyecto': plan['project'], 'caso': casos['con'].loc_name,
               'paso': 'inicio', 'viejas': viejas, 'antes': antes, 'operacion': operacion, 'apartadas': [],
               'fecha': time.strftime('%Y-%m-%dT%H:%M:%S')}
    _diario(plan, entrada)
    inicial = app.GetActiveStudyCase()
    hecho: dict = {}
    apartadas: list[str] = []
    deshecha = False
    try:
        casos['con'].Activate()
        activas = {v.loc_name for v in app.GetActiveNetworkVariations() or []}
        esquemas = _esquemas(app)
        apartadas = [n for n in viejas if n in activas]
        entrada.update(paso='vieja_apartada', apartadas=apartadas)
        _diario(plan, entrada)
        for n in apartadas:
            esquemas[n].Deactivate()
        entrada['paso'] = 'operacion_deshecha'
        _diario(plan, entrada)
        deshecha = True
        deshacer_operacion(app, plan, casos, operacion, base['avisos'])
        hecho, _rc = aplicar(app, {**plan, 'sustituir': None, 'sustitucion_en_curso': ident})
        entrada.update(paso='nueva_creada', creadas=sorted(set(_esquemas(app)) - set(antes)))
        _diario(plan, entrada)
        motivo = _por_que_no_queda(hecho, casos['con'].loc_name)
        if motivo:
            raise _Deshacer(motivo)
        entrada['paso'] = 'nueva_verificada'
        _diario(plan, entrada)
        borradas, sin_borrar = _borrar_variaciones(app, casos, viejas)
        hecho['sustitucion'] = {'hecha': True, 'retiradas': borradas, 'sin_borrar': sin_borrar}
        hecho['avisos'] = list(hecho.get('avisos') or []) + base['avisos']
        if sin_borrar:
            hecho['avisos'].append('La obra vieja no se borró entera: quedan ' + ', '.join(sin_borrar)
                                   + ', desactivadas en «Con proyecto»; retírelas a mano (098:RF-36).')
        _quitar_diario(plan, 'sustitucion', ident)
        return hecho, 0 if not sin_borrar else 2
    except BaseException as exc:
        creadas = sorted(set(_esquemas(app)) - set(antes))
        try:
            deshacer_sustitucion(app, plan, casos, creadas, apartadas, operacion, (hecho or {}).get('obras'), deshecha,
                                 base['avisos'])
        finally:
            _quitar_diario(plan, 'sustitucion', ident)
        informe = {**base, **(hecho or {})}
        motivo = str(exc) or type(exc).__name__
        for f in informe.get('obras') or []:
            f['error'] = f'deshecha: {motivo}'
        informe['sustitucion'] = {'hecha': False, 'motivo': motivo, 'deshechas': creadas}
        informe['avisos'] = list(informe.get('avisos') or []) + base['avisos'] + [
            f'La obra nueva no queda ({motivo}): se deshace lo creado y vuelve la vieja, activa (098:RF-36).']
        if isinstance(exc, _Deshacer):
            return informe, 2
        raise
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()


def _recuperar_especiales(app, plan: dict, casos: dict, especiales: list[dict], informe: dict) -> list[dict]:
    """098:RF-36: lo que dejó a medias una orden que murió: la sustitución se completa si la nueva ya quedó comprobada y
    se deshace si no; la obra apartada de la medida vuelve a estar activa."""
    hechas = []
    en_curso = plan.get('sustitucion_en_curso')
    for e in especiales:
        if e.get('accion') == 'sustitucion' and e.get('id') != en_curso:
            avisos = informe.setdefault('avisos', [])
            if e.get('paso') == 'nueva_verificada':
                borradas, quedan = _borrar_variaciones(app, casos, e.get('viejas') or [])
                avisos.append('Una sustitución quedó a medias con la obra nueva ya comprobada: se borra la vieja, '
                              + ', '.join(borradas or quedan) + ' (098:RF-36).')
            else:
                creadas = sorted(n for n in set(_esquemas(app)) - set(e.get('antes') or []) if n.startswith('Obra_'))
                deshacer_sustitucion(app, plan, casos, creadas, e.get('apartadas') or [], e.get('operacion') or [], None,
                                     e.get('paso') in ('operacion_deshecha', 'nueva_creada'), avisos)
                avisos.append('Una sustitución quedó a medias: se deshace la obra nueva (' + (', '.join(creadas) or 'nada')
                              + ') y la vieja vuelve, activa (098:RF-36).')
            _quitar_diario(plan, 'sustitucion', e['id'])
            hechas.append(e)
        elif e.get('accion') == 'apartada':
            por_nombre = {c.loc_name: c for c in casos.values()}
            vueltas = _reactivar(app, por_nombre.get(e.get('caso')), e.get('variaciones') or [])
            if vueltas:
                informe.setdefault('avisos', []).append('Una medida que se cortó dejó apartada ' + ', '.join(vueltas)
                                                        + ': vuelve a estar activa (098:RF-36).')
            _quitar_diario(plan, 'apartada', e['id'])
            hechas.append(e)
    if hechas:
        informe['especiales_recuperadas'] = [{k: e.get(k) for k in ('accion', 'paso', 'viejas', 'variaciones')}
                                             for e in hechas]
    return hechas


def _barras_de_elemento(clase: str, obj) -> list:
    """Las barras que une un elemento de :data:`ESTADO_SERVICIO`; de una llave, las de su cubículo y su elemento."""
    if clase == 'StaSwitch':
        cub = obj.GetParent()
        barras = [getattr(cub, 'cterm', None)]
        elem = getattr(cub, 'obj_id', None)
        if elem is not None:
            barras += [getattr(getattr(elem, a, None), 'cterm', None) for a in ('bus1', 'bus2', 'bushv', 'buslv')]
        return [b for b in barras if b is not None]
    return [b for b in (getattr(getattr(obj, a, None), 'cterm', None) for a in ('bus1', 'bus2', 'bushv', 'buslv'))
            if b is not None]


def _estado_servicio(app) -> dict[str, tuple]:
    """Por nombre completo, de cada elemento que corta un camino: ``(clase, objeto, fuera, valores)``. Una pasada por
    clase sobre los datos de red, que traen también lo fuera de servicio (P2: nunca una por alimentador)."""
    donde = app.GetProjectFolder('netdat') or app.GetActiveProject()
    out = {}
    for clase, atributos in ESTADO_SERVICIO.items():
        for o in ((donde.GetContents(f'*.{clase}', 1) if donde is not None else None) or []):
            valores = {a: getattr(o, a, None) for a in atributos}
            out[o.GetFullName()] = (clase, o, fuera_de_servicio(clase, valores), valores)
    return out


def _sin_tension(app) -> set[str] | None:
    """Las barras sin tensión tras un flujo (``ElmTerm.IsEnergized`` a 0); ``None`` si DIgSILENT no lo sabe."""
    flujo_de_carga(app)
    out, sabe = set(), False
    for b in app.GetCalcRelevantObjects('*.ElmTerm') or []:
        try:
            estado = int(b.IsEnergized())
        except Exception:  # noqa: BLE001 - sin el dato, no cuenta
            continue
        if estado in (0, 1):
            sabe = True
        if estado == 0:
            out.add(b.loc_name)
    return out if sabe else None


def comprobar_servicio_con_proyecto(app, plan: dict, casos: dict, informe: dict) -> dict:
    """081:RF-83 a RF-85: lo que está fuera de servicio o abierto en «Con proyecto» y en servicio en «Sin proyecto», sin
    variación activa que lo explique, vuelve a como está en «Sin proyecto» si es un resto; si puede ser del operador, se
    avisa sin tocarlo.

    Explica una diferencia la variación activa de «Con proyecto» (de obra o de carga nueva) que graba el elemento o una
    de sus barras. Es un resto lo anotado en el registro de aperturas y lo que deja sin tensión barras que en «Sin
    proyecto» la tienen.
    """
    resultado: dict[str, Any] = {'restituidos': [], 'respetados': [], 'explicados': []}
    if 'sin' not in casos or 'con' not in casos:
        return resultado
    inicial = app.GetActiveStudyCase()
    try:
        casos['sin'].Activate()
        sin = _estado_servicio(app)
        casos['con'].Activate()
        con = _estado_servicio(app)
        candidatos = [{'clave': k, 'nombre': f'{v[1].loc_name} ({v[0]})', 'clase': v[0], 'objeto': v[1]}
                      for k, v in con.items() if v[2] and k in sin and not sin[k][2]]
        if not candidatos:
            return resultado
        grabados = set()
        for v in app.GetActiveNetworkVariations() or []:
            grabados |= {r.rsplit('\\', 1)[-1] for r in _grabados(v)}
        explicados = {c['clave'] for c in candidatos
                      if f"{c['objeto'].loc_name}.{c['clase']}" in grabados
                      or any(f'{b.loc_name}.ElmTerm' in grabados for b in _barras_de_elemento(c['clase'], c['objeto']))}
        anotadas = {(e.get('clase'), e.get('nombre')) for e in leer_aperturas(fichero_aperturas(plan))
                    if plan.get('project') and e.get('caso') in (None, '', casos['con'].loc_name)}
        anotados = {c['clave'] for c in candidatos if (c['clase'], c['objeto'].loc_name) in anotadas}
        dudosos = [c for c in candidatos if c['clave'] not in explicados and c['clave'] not in anotados]
        cortan: set[str] = set()
        if dudosos:
            muertas_con = _sin_tension(app)
            casos['sin'].Activate()
            muertas_sin = _sin_tension(app)
            casos['con'].Activate()
            if muertas_con is not None and muertas_sin is not None:
                nuevas = muertas_con - muertas_sin
                cortan = {c['clave'] for c in dudosos
                          if any(b.loc_name in nuevas for b in _barras_de_elemento(c['clase'], c['objeto']))}
        clasificado = clasificar_restos(candidatos, explicados=explicados, cortan=cortan, anotados=anotados)
        resultado['explicados'] = clasificado['explicados']
        resultado['respetados'] = clasificado['respetar']
        a_restituir = [c for c in candidatos if c['clave'] not in explicados and c['clave'] in anotados | cortan]
        nombre_con = casos['con'].loc_name
        if a_restituir:
            escenario = app.GetActiveScenario()
            if escenario is None:
                # RF-85: sin escenario, escribir el servicio cambiaría la red de todos los casos, no solo «Con proyecto».
                resultado['sin_escenario'] = sorted(c['nombre'] for c in a_restituir)
                informe.setdefault('avisos', []).append(
                    f'«{nombre_con}» no tiene escenario de operación: no se restituyen '
                    + ', '.join(resultado['sin_escenario']) + ', fuera de servicio o abiertos sin variación que lo '
                    'explique (081:RF-85).')
            else:
                for c in a_restituir:
                    for a, v in sin[c['clave']][3].items():          # los valores leídos en «Sin proyecto»
                        if v is not None:
                            setattr(c['objeto'], a, v)
                    resultado['restituidos'].append(c['nombre'])
                escenario.Save()
                informe.setdefault('avisos', []).append(
                    f'«{nombre_con}» tenía fuera de servicio o abiertos, sin ninguna variación que lo explique, '
                    + ', '.join(resultado['restituidos']) + f', que en «{casos["sin"].loc_name}» están en servicio: '
                    'se vuelven a poner como allí en el escenario de «' + nombre_con + '» (081:RF-83).')
                restantes = [e for e in leer_aperturas(fichero_aperturas(plan))
                             if (e.get('clase'), e.get('nombre')) not in {(c['clase'], c['objeto'].loc_name)
                                                                          for c in a_restituir}]
                try:
                    escribir_aperturas(fichero_aperturas(plan), restantes)
                except OSError:
                    pass
        if resultado['respetados']:
            informe.setdefault('avisos', []).append(
                f'«{nombre_con}» tiene fuera de servicio o abiertos ' + ', '.join(resultado['respetados'])
                + f', en servicio en «{casos["sin"].loc_name}», sin variación que lo explique; no dejan barras sin tensión '
                'y pueden ser un cambio del operador: no se tocan (081:RF-84).')
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    informe['servicio_con_proyecto'] = resultado
    return resultado


def _crear_con_proyecto(app, proyecto, casos, aplicadas, informe, plan: dict | None = None) -> None:
    """«Con proyecto» como copia de «Sin proyecto» con sus obras ya hechas (016:RF-11, RF-12).

    Usuario, 2026-10-14: «lo que se modifica en Sin proyecto debe pasar a Con proyecto y la
    copia se hace una vez modificado el Sin proyecto». La copia lleva las variaciones
    activas de «Sin proyecto», y con ellas las obras; aquí se comprueba que están activas
    y se ejecuta el flujo de «Con proyecto» con cada una.
    """
    anio = informe.get('anio_casos')                                    # 025:RF-41
    casos['con'] = crear_con_proyecto(app, casos['sin'], anio)
    informe['avisos'].append(f"El proyecto no tenía «{nombre_caso('con', anio)}»: se creó como "
                             f"copia de «{nombre_caso('sin', anio)}» después de aplicar sus obras.")
    carpeta = app.GetProjectFolder('scheme')
    por_nombre = {v.loc_name: v for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])}
    for obra, fila in aplicadas:
        variacion = por_nombre.get(fila.get('variacion'))
        if fila['error'] or variacion is None or NOMBRES['sin'] not in fila['casos_activos']:
            continue
        casos['con'].Activate()
        if variacion.loc_name not in {v.loc_name for v in (app.GetActiveNetworkVariations() or [])}:
            variacion.Activate()
        _flujo_con_la_obra(app, proyecto, casos, obra, fila, variacion, 'con', plan=plan)


def _comprobar_sin_proyecto(app, casos, alims, feeders, antes, informe) -> None:
    """RF-64 y RF-65: «Sin proyecto» igual que antes donde no hay obras activas."""
    casos['sin'].Activate()
    con_obras = {f['alimentador'] for f in informe['obras']
                 if NOMBRES['sin'] in f.get('casos_activos', [])}
    libres = [f for f in feeders if f not in con_obras]
    despues = medir_estado(app, alims, feeders)
    diferencias = diferencias_sin_proyecto(antes['feeders'], despues['feeders'], libres)
    informe['comprobacion'] = {'alimentadores': libres, 'diferencias': diferencias}
    for d in diferencias:
        informe['avisos'].append(
            f"En «Sin proyecto», {d['alimentador']} no tiene obras y su {d['medida']} pasó "
            f"de {d['antes']} a {d['despues']}: una obra tocó algo compartido.")


# =========================================================================== persistencia (048:RF-9)
#: Lo que se fotografía de cada clase en el caso de referencia: lo que una obra escribe (tipo, ternas, servicio,
#: estado de los interruptores, escalones, tomas, demanda). Sin flujo: dos flujos de la misma red no dan las mismas
#: cifras al decimal, y la cabecera de los alimentadores sin obras ya la compara RF-64.
ATRIBUTOS_FOTO = {
    'ElmLne': ('typ_id', 'nlnum', 'outserv', 'dline'),
    'ElmTr2': ('typ_id', 'outserv', 'nntap'),
    'ElmShnt': ('outserv', 'ncapx', 'ncapa', 'qcapn'),
    'ElmVoltreg': ('typ_id', 'outserv', 'usetp'),
    'ElmTerm': ('outserv', 'uknom'),
    'ElmCoup': ('on_off', 'outserv'),
    'StaSwitch': ('on_off',),
    'ElmLod': ('plini', 'qlini', 'scale0', 'outserv'),
}


def leer_foto(app, caso) -> dict:
    """La foto del caso (048:RF-9): una pasada por clase sobre toda la red, nunca una por alimentador (P2).

    Toda la red y no solo la de las obras: lo que una obra no debe tocar es justamente lo que no es suyo (un
    tipo compartido, la carga de otro alimentador).
    """
    caso.Activate()
    filas = []
    for clase, atributos in ATRIBUTOS_FOTO.items():
        for o in app.GetCalcRelevantObjects(f'*.{clase}') or []:
            filas.append({'nombre': o.GetFullName(), 'clase': clase,
                          'datos': {a: getattr(o, a, None) for a in atributos}})
    return foto_de_referencia(filas)


def roles_de_referencia(obras: list[Obra]) -> list[str]:
    """Los casos que las obras no deben cambiar: el «Caso base» siempre (011:RF-58); «Sin proyecto» si ninguna es de allí."""
    return ['base'] + ([] if any(NOMBRES['sin'] in o.casos for o in obras) else ['sin'])


def releer_obras(app, filas: list[dict], casos: dict) -> dict[str, dict]:
    """De cada variación de las obras, leída de nuevo del proyecto: si está, cuánto graba y en qué casos está activa.

    Lo activo se lee una vez por caso, no una por obra.
    """
    carpeta = app.GetProjectFolder('scheme')
    por_nombre = {v.loc_name: v for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else []) or []}
    activas, sin_vigor = {}, {}
    for rol in NOMBRES:
        if rol in casos:
            casos[rol].Activate()
            hora = int(getattr(casos[rol], 'iStudyTime', 0) or 0)
            vivas = list(app.GetActiveNetworkVariations() or [])
            activas[NOMBRES[rol]] = {v.loc_name for v in vivas}
            # 081:RF-78: una etapa posterior a la hora del caso no se aplica aunque su variación esté activa.
            sin_vigor[NOMBRES[rol]] = {v.loc_name for v in vivas if (etapas := v.GetContents('*.IntSstage') or [])
                                       and all(int(getattr(s, 'tAcTime', 0) or 0) > hora for s in etapas)}
    out = {}
    for fila in filas:
        nombre = fila.get('variacion')
        if not nombre:
            continue
        v = por_nombre.get(nombre)
        out[nombre] = {'existe': v is not None, 'objetos': len(_grabados(v)) if v is not None else 0,
                       'activa_en': [c for c, nombres in activas.items() if nombre in nombres],
                       'sin_vigor_en': [c for c, nombres in sin_vigor.items() if nombre in nombres]}
    return out


def comprobar_persistencia(app, plan: dict, filas: list[dict], fotos_antes: dict[str, dict],
                           anio: int | None) -> dict:
    """048:RF-9: reabre el proyecto y relee las obras y la foto de los casos de referencia.

    Reabrir es desactivar y volver a activar el proyecto, como la lectura del gemelo (024:RF-27): lo que cuenta es
    lo guardado en la base de DIgSILENT, no lo que el proceso tenía en memoria al escribirlo. Deja activo el caso
    que DIgSILENT activa al reabrir, que es el último que tenía el proyecto (el del operador, que ``aplicar`` ya
    devolvió).
    """
    proyecto = app.GetActiveProject()
    if proyecto is not None:
        proyecto.Deactivate()
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {'ok': False, 'reabierto': False, 'obras': [], 'referencias': {},
                'error': 'el proyecto no se pudo volver a activar para releer las obras'}
    casos = casos_del_proyecto(app, anio)
    inicial = app.GetActiveStudyCase()
    try:
        relectura = releer_obras(app, filas, casos)
        referencias = {NOMBRES[rol]: {'antes': foto, 'despues': leer_foto(app, casos[rol]) if rol in casos else None}
                       for rol, foto in fotos_antes.items()}
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    return {**veredicto_persistencia(filas, relectura, referencias), 'reabierto': True}


def _avisos_de_persistencia(persistencia: dict, avisos: list[str]) -> None:
    for o in persistencia.get('obras') or []:
        if not o['ok']:
            avisos.append(f"La obra {o['variacion']} no persiste como se aplicó: {o['motivo']} (048:RF-9).")
    for caso, ref in (persistencia.get('referencias') or {}).items():
        if not ref['igual']:
            avisos.append(f"Las obras cambiaron «{caso}», que es la referencia: {'; '.join(ref['cambios'][:5])}"
                          f"{' …' if ref['total_cambios'] > 5 else ''} (048:RF-9).")
    if persistencia.get('error'):
        avisos.append(f"No se pudo comprobar que las obras persisten: {persistencia['error']} (048:RF-9).")


#: Elementos con sitio en la red, y los atributos con sus barras (042:RF-36).
CLASES_CON_SITIO = ('ElmLne', 'ElmShnt', 'ElmVoltreg', 'ElmTerm', 'ElmTr2')


def _extremos_de(objeto) -> list:
    """Las barras de un elemento: él mismo si es barra; si no, las de sus conexiones."""
    if objeto.GetClassName() == 'ElmTerm':
        return [objeto]
    return [t for t in (getattr(getattr(objeto, a, None), 'cterm', None) for a in ('bus1', 'bus2', 'bushv', 'buslv'))
            if t is not None]


def _punto_de(barra, transformar, crs) -> dict | None:
    gps = gps_de(barra)
    if not gps:
        return None
    punto = {'barra': barra.loc_name, 'lat': gps[0], 'lon': gps[1]}
    if transformar is not None:
        este, norte = transformar.transform(gps[1], gps[0])
        punto.update(crs=crs, este=round(este, 1), norte=round(norte, 1))
    return punto


def georreferenciar_obras(app, filas: list[dict]) -> None:
    """042:RF-36: ``ubicacion`` de cada obra con su variación, con «Con proyecto» activo.

    Se lee de lo que grabó su etapa, sin saber de cada clase de obra: la que venga mañana también queda situada.
    """
    from convertersmartgrid.geography import make_transformer

    crs = datos_perfil().get('crs_origen')
    try:
        transformar = make_transformer('EPSG:4326', crs) if crs else None
    except (ImportError, ValueError):
        transformar = None
    vivos = {(clase, o.loc_name): o for clase in CLASES_CON_SITIO for o in app.GetCalcRelevantObjects(f'*.{clase}') or []}
    carpeta = app.GetProjectFolder('scheme')
    variaciones = {v.loc_name: v for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta is not None else []) or []}
    for fila in filas:
        v = variaciones.get(fila.get('variacion'))
        if v is None:
            continue
        ubicacion = []
        for etapa in v.GetContents('*.IntSstage') or []:
            for o in etapa.GetContents('*', 1) or []:
                vivo = vivos.get((o.GetClassName(), o.loc_name))
                if vivo is None:
                    continue
                puntos = [p for p in (_punto_de(b, transformar, crs) for b in _extremos_de(vivo)) if p]
                ubicacion.append({'elemento': vivo.loc_name, 'clase': vivo.GetClassName(), 'puntos': puntos})
        fila['ubicacion'] = ubicacion
        if any(not u['puntos'] for u in ubicacion):
            fila.setdefault('avisos', []).append('Hay elementos de esta obra sin coordenadas en sus barras (042:RF-36).')


def aplicar(app, plan: dict, *, simular: bool = False,
            cancelado=lambda: False) -> tuple[dict, int]:
    """Simula o aplica las obras del plan. Devuelve (informe, código de salida)."""
    informe: dict[str, Any] = {'project': plan.get('project'),
                               'modo': 'simular' if simular else 'aplicar', 'obras': [],
                               'avisos': [], 'cancelado': False, 'comprobacion': None}
    try:
        obras = [validar_obra(o) for o in plan.get('obras') or []]
    except ObrasError as exc:
        return {**informe, 'error': f'obra no válida: {exc}'}, 2
    if not obras:
        return {**informe, 'error': 'el plan no trae obras'}, 2
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    # 025:RF-41: con ``anio_casos``, las obras van a los casos de ese año; los de otro año
    # no se tocan. Las obras siguen nombrando su caso por su papel («Sin/Con proyecto»).
    anio = informe['anio_casos'] = anio_del_plan(plan)
    casos = casos_del_proyecto(app, anio)
    if 'base' not in casos or 'sin' not in casos:
        return {**informe, 'error': f"el proyecto no tiene los casos «Caso base» y "
                                    f"«{nombre_caso('sin', anio)}»: prepare los casos primero"}, 2

    feeders = sorted({o.alimentador for o in obras} | {o.cede for o in obras if o.cede} | {o.vecino for o in obras if o.vecino}
                     | set(plan.get('feeders') or []))
    evaluando = bool(plan.get('evaluando'))
    if not evaluando:
        restituir_pendientes(app, plan, casos, informe)                           # 081:RF-82
    alims = Alimentadores(app, proyecto, feeders)
    inicial = app.GetActiveStudyCase()
    # 025:RF-69: la obra elegida por la escalera se comprueba con las cargas nuevas de los
    # alimentadores sin resolver apartadas, como se evaluó; vuelven al terminar.
    ajenas = []
    if 'con' in casos and (plan.get('apartar_cargas_de') or plan.get('apartar_variaciones')):
        casos['con'].Activate()
        ajenas = _apartar_cargas_de(app, list(plan.get('apartar_cargas_de') or []),
                                    plan.get('apartar_variaciones'))                  # 042:RF-2
    try:
        casos['sin'].Activate()
        redes, tipos, avisos = _leer(app, plan, alims, feeders, obras, casos)
        informe['avisos'] += avisos
        carpeta = app.GetProjectFolder('scheme')
        ocupadas = [v.loc_name for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])]
        filas = plan_simulacion(obras, redes, tipos, variaciones=ocupadas)
        if simular:                                                       # RF-69
            informe['obras'] = filas
            return informe, 2 if any(f['error'] for f in filas) else 0
        # 025:RF-49: al evaluar variantes de la escalera, sus obras se miden y se borran: ni
        # sincronizar, ni comprobar «Sin proyecto», que no tocan, ni dibujarlas.
        if not evaluando:
            # 048:RF-9: la foto de los casos de referencia antes de escribir nada, también de la sincronización.
            fotos_antes = {rol: leer_foto(app, casos[rol]) for rol in roles_de_referencia(obras) if rol in casos}
            casos['sin'].Activate()
        if 'con' in casos and not evaluando:                     # 014:RF-31 a RF-34
            informe['sin_a_con'] = sin_a_con_proyecto(app, casos)
            informe['avisos'] += informe['sin_a_con']['avisos']
        for fila in filas:
            if not fila['error'] and fila['clase'] not in CONSTRUCTORES:
                fila['error'] = f"las obras de clase {fila['clase']} todavía no se pueden aplicar"

        antes = {'converged': False} if evaluando else medir_estado(app, alims, feeders)  # RF-64
        if not antes['converged'] and not evaluando:
            informe['avisos'].append('«Sin proyecto» no converge antes de las obras: no se puede '
                                     'comprobar después que no cambió.')
        # Sin «Con proyecto», primero las obras de «Sin proyecto»; después se crea «Con
        # proyecto» como su copia, y luego van las que son solo de «Con proyecto» (016:RF-12).
        pares = list(enumerate(zip(obras, filas)))
        if 'con' not in casos:
            pares.sort(key=lambda p: NOMBRES['sin'] not in p[1][0].casos)
        hechas: list[tuple[int, tuple]] = []
        for i, (obra, fila) in pares:
            if cancelado():
                informe['cancelado'] = True
                break
            if 'con' not in casos and NOMBRES['sin'] not in obra.casos:
                _crear_con_proyecto(app, proyecto, casos, [p for _, p in hechas], informe, plan)
            if not fila['error']:
                _aplicar_una(app, plan, proyecto, casos, alims, obra, fila, redes[obra.alimentador],
                             redes, conjunto=bool(plan.get('en_conjunto')))
            hechas.append((i, (obra, fila)))
        if plan.get('en_conjunto') and not informe['cancelado']:
            informe['plan_completo'] = flujo_del_plan(app, proyecto, casos, [f for _, (_, f) in hechas], plan)
        if 'con' not in casos and not informe['cancelado']:
            _crear_con_proyecto(app, proyecto, casos, [p for _, p in hechas], informe, plan)
        informe['obras'] = [fila for _, (_, fila) in sorted(hechas, key=lambda h: h[0])]
        if not evaluando:
            # 081:RF-81: lo que abrieron las obras que quedan aplicadas es parte de ellas: sale del registro. Lo de una
            # variante evaluada lo restituye ``evaluar`` al borrarla.
            quitar_aperturas(plan, informe['obras'])
        if antes['converged']:
            _comprobar_sin_proyecto(app, casos, alims, feeders, antes, informe)
        if 'con' in casos and not evaluando and any(f.get('variacion') for f in informe['obras']):
            # 016:RF-89: el enlace y las mitades de un tramo partido, en el diagrama; en
            # «Con proyecto», que tiene también las obras de «Sin proyecto».
            casos['con'].Activate()
            try:
                georreferenciar_obras(app, informe['obras'])             # 042:RF-36
            except Exception as exc:  # noqa: BLE001 - situarlas no puede perder las obras ya aplicadas
                informe['avisos'].append(f'No se pudieron leer las coordenadas de las obras: {exc} (042:RF-36).')
            informe['dibujo'] = completar_diagrama(app, proyecto)
    finally:
        if ajenas:
            casos['con'].Activate()
            for v in ajenas:
                v.Activate()
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()

    if not evaluando:
        try:
            informe['persistencia'] = comprobar_persistencia(app, plan, informe['obras'], fotos_antes, anio)
        except Exception as exc:  # noqa: BLE001 - releer no puede perder las obras ya aplicadas
            informe['persistencia'] = {'ok': False, 'reabierto': False, 'obras': [], 'referencias': {},
                                       'error': f'{type(exc).__name__}: {exc}'}
        _avisos_de_persistencia(informe['persistencia'], informe['avisos'])
    fallos = any(f['error'] or not all(x['converge'] for x in f.get('flujo', {}).values())
                 for f in informe['obras'])
    diferencias = bool((informe['comprobacion'] or {}).get('diferencias'))
    sin_persistir = not evaluando and not informe['persistencia']['ok']
    return informe, 2 if fallos or diferencias or sin_persistir or informe['cancelado'] else 0


# =========================================================================== escalera optimizada
def _resultado(obj, atributo: str) -> float | None:
    try:
        v = obj.GetAttribute(atributo)
    except Exception:  # noqa: BLE001 - sin resultado del flujo
        return None
    return float(v) if isinstance(v, (int, float)) and math.isfinite(float(v)) else None


def reponer_cargas(app, plan: dict) -> tuple[dict, int]:
    """042:RF-32: activa en «Con proyecto» las variaciones de ``variaciones`` que estén desactivadas."""
    informe: dict[str, Any] = {'project': plan.get('project'), 'modo': 'reponer_cargas', 'repuestas': [], 'avisos': []}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    anio = anio_del_plan(plan)
    casos = casos_del_proyecto(app, anio)
    if 'con' not in casos:
        return {**informe, 'error': f"falta «{nombre_caso('con', anio)}»"}, 2
    inicial = app.GetActiveStudyCase()
    nombres = set(plan.get('variaciones') or ())
    try:
        casos['con'].Activate()
        activas = {v.loc_name for v in app.GetActiveNetworkVariations() or []}
        carpeta = app.GetProjectFolder('scheme')
        for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta is not None else []) or []:
            if v.loc_name in nombres and v.loc_name not in activas:
                v.Activate()
                informe['repuestas'].append(v.loc_name)
        ahora = {v.loc_name for v in app.GetActiveNetworkVariations() or []}
        if faltan := sorted(nombres - ahora):
            informe['avisos'].append(f"No se pudieron activar: {', '.join(faltan)} (042:RF-32).")
    finally:
        if inicial is not None:
            inicial.Activate()
    return informe, 0


def es_obra_de(nombre: str, alimentador: str) -> bool:
    """``Obra_<clase>_<alimentador>`` con su número si se repite; otro alimentador no entra por parecerse (042:RF-60)."""
    return bool(re.fullmatch(rf'Obra_[A-Za-z_]+?_{re.escape(alimentador)}(_\d+)?', nombre))


def retirar_obras(app, plan: dict) -> tuple[dict, int]:
    """042:RF-60: borra las variaciones de obra ``variaciones`` de ``feeders``, por su nombre exacto; las de carga, las de
    otros alimentadores y las que no se nombran no se tocan.

    098:RF-36: la web nombra solo las que aplicó la escalera. Por el patrón ``Obra_<clase>_<alim>`` se borraban también
    las que el operador hizo desde la pestaña de obras (040:RF-8, 014:RF-3: un cambio manual se respeta y se avisa)."""
    informe: dict[str, Any] = {'project': plan.get('project'), 'modo': 'retirar_obras', 'retiradas': [], 'avisos': []}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    anio = anio_del_plan(plan)
    casos = casos_del_proyecto(app, anio)
    if 'con' not in casos:
        return {**informe, 'error': f"falta «{nombre_caso('con', anio)}»"}, 2
    inicial = app.GetActiveStudyCase()
    feeders = [str(f) for f in plan.get('feeders') or ()]
    pedidas = set(plan.get('variaciones') or ())
    if not pedidas:
        informe['avisos'].append('Sin los nombres exactos de las obras a retirar no se borra ninguna (098:RF-36).')
        return informe, 0
    try:
        casos['con'].Activate()
        carpeta = app.GetProjectFolder('scheme')
        for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta is not None else []) or []:
            if v.loc_name in pedidas and any(es_obra_de(v.loc_name, f) for f in feeders):
                nombre = v.loc_name
                v.Deactivate()                      # activa y grabando, DIgSILENT no la borra (2026-10-15)
                v.Delete()
                informe['retiradas'].append(nombre)
        sin_borrar = sorted(pedidas - set(informe['retiradas']))
        if sin_borrar:
            informe['avisos'].append('No se retiran, por no estar en el proyecto o no ser obra de los alimentadores '
                                     'pedidos: ' + ', '.join(sin_borrar) + ' (098:RF-36).')
        # 098:RF-36: lo que la obra retirada abrió, cerró o cambió en el flujo es del escenario y del caso, no de su
        # variación: sin esto, CHN102 se quedaba con el ajuste de tomas y lo abierto de la obra que ya no está.
        filas = [f for f in plan.get('operacion_de_obras') or [] if f.get('variacion') in informe['retiradas']]
        cambiados = deshacer_operacion(app, plan, casos, filas, informe['avisos']) if filas else set()
        if not filas:
            # 098:RF-34: el ajuste de tomas, como antes de la primera obra con regulador, si ya no queda ninguna.
            cambiados = {c.loc_name for c in casos.values()} if restituir_flujo_original(
                app, plan, casos, informe['avisos']) else set()
        # Solo el escenario de los casos donde algo cambió: guardar otro guardaba lo ajeno.
        _guardar_escenarios(app, casos, cambiados)
        if filas:
            quitar_aperturas(plan, filas)
            informe['operacion_restituida'] = sorted(f['variacion'] for f in filas)
    finally:
        if inicial is not None:
            inicial.Activate()
    return informe, 0


#: Lo que une dos barras en serie sin ser una línea: el camino eléctrico pasa por ello (042:RF-44).
EQUIPOS_EN_SERIE = ('ElmCoup', 'ElmVoltreg', 'ElmTr2', 'ElmZpu', 'ElmSind')


def _ruta_de(obj) -> str:
    """098:RF-19: el nombre completo con que se encuentra de nuevo el mismo elemento; su nombre si no lo da."""
    try:
        return str(obj.GetFullName())
    except AttributeError:
        return str(getattr(obj, 'loc_name', ''))


def puentes_de_la_red(app) -> list[dict]:
    """042:RF-44: los equipos en serie en servicio, como tramos de largo 0 que no llevan obra; un acoplador abierto no une nada."""
    out = []
    for clase in EQUIPOS_EN_SERIE:
        for o in app.GetCalcRelevantObjects(f'*.{clase}') or []:
            if int(getattr(o, 'outserv', 0) or 0) or (clase == 'ElmCoup' and not int(getattr(o, 'on_off', 1) or 0)):
                continue
            barras = [t for t in (getattr(getattr(o, a, None), 'cterm', None) for a in ('bus1', 'bus2', 'bushv', 'buslv')) if t is not None]
            if len(barras) == 2:
                out.append({'nombre': o.loc_name, 'desde': barras[0].loc_name, 'hasta': barras[1].loc_name, 'largo_m': 0.0, 'puente': True,
                            # 098:RF-11: un acoplador es una maniobra; un transformador o un regulador no se abren.
                            'maniobra': ({'nombre': o.loc_name, 'clase': 'ElmCoup', 'ruta': _ruta_de(o)}
                                         if clase == 'ElmCoup' else None)})
    return out


def maniobra_del_tramo(linea) -> dict | None:
    """098:RF-11: el interruptor o seccionador de un cubículo del tramo, el de su ``bus1`` primero; ``None`` sin él."""
    for lado in ('bus1', 'bus2'):
        cub = getattr(linea, lado, None)
        for sw in ((cub.GetContents('*.StaSwitch') if cub is not None else None) or []):
            # 098:RF-19: con su nombre completo: los de cubículo se llaman casi siempre igual («Switch»).
            return {'nombre': sw.loc_name, 'clase': 'StaSwitch', 'ruta': _ruta_de(sw)}
    return None


#: 098:RF-29: barras bajo el límite que da la lectura por alimentador, de la más baja a la menos.
MAX_BAJAS = 10


def enlaces_existentes(app, alims, feeders, tramos_red: list[dict], margen: dict) -> dict[str, list[dict]]:
    """098:RF-21, RF-22, RF-27: por cada alimentador de ``feeders``, lo que ya une una barra suya con una de otro
    alimentador del proyecto, abierto o cerrado.

    Acopladores, tramos y equipos en serie, con sus interruptores, en una pasada por clase para todos (nada de recorrer
    la red una vez por alimentador). De cada uno, su barra en el alimentador y las maniobras del camino eléctrico de la
    cabecera hasta ella (los tramos con su interruptor y los acopladores, 098:RF-11), en orden; y el margen del vecino
    con el flujo de ahora (087:RF-32). CA101 y CHN102 (2026-11-07): el enlace con CHN102 ya existía y la escalera no lo
    veía.
    """
    from convertersmartgrid.escalera_optima import camino_electrico

    pedidos = set(feeders)
    out: dict[str, list[dict]] = {f: [] for f in feeders}
    de_barra: dict[str, str] = {}
    for g, elm in alims.elm.items():
        cab_g = cabecera_de(elm)
        for b in elm.GetObjs('ElmTerm'):
            if cab_g is not None and b.loc_name == cab_g.loc_name:
                continue                                  # la barra de la SET la comparten: no es un enlace
            de_barra.setdefault(b.loc_name, g)
    for clase in ('ElmCoup', 'ElmLne') + tuple(c for c in EQUIPOS_EN_SERIE if c not in ('ElmCoup',)):
        for o in app.GetCalcRelevantObjects(f'*.{clase}') or []:
            lados = [getattr(o, a, None) for a in (('bushv', 'buslv') if clase == 'ElmTr2' else ('bus1', 'bus2'))]
            barras = [getattr(c, 'cterm', None) for c in lados]
            if any(b is None for b in barras):
                continue
            duenos = [de_barra.get(b.loc_name) for b in barras]
            if None in duenos or duenos[0] == duenos[1] or not pedidos & set(duenos):
                continue
            cerrado = (not int(getattr(o, 'outserv', 0) or 0)
                       and not (clase == 'ElmCoup' and not int(getattr(o, 'on_off', 1) or 0))
                       and all(int(getattr(s, 'on_off', 1) or 0) for c in lados if c is not None
                               for s in (c.GetContents('*.StaSwitch') or [])))
            for lado, f in enumerate(duenos):
                if f not in pedidos:
                    continue
                propia, vecino = barras[lado], duenos[1 - lado]
                cab = cabecera_de(alims.elm[f])
                camino = camino_electrico(tramos_red, cab.loc_name, propia.loc_name) if cab is not None else []
                puntos = [{'rama': t['nombre'], 'barra': t.get('hasta'), 'maniobra': t['maniobra']} for t in camino
                          if t.get('maniobra') and t['maniobra'].get('nombre') != o.loc_name]
                out[f].append({'enlace': o.loc_name, 'clase': clase, 'ruta': o.GetFullName(), 'cerrado': bool(cerrado),
                               'vecino': vecino, 'barra': propia.loc_name, 'puntos': puntos,
                               **(margen.get(vecino) or {})})
    return {f: sorted(x, key=lambda e: (e['vecino'], e['enlace'])) for f, x in out.items()}


#: 098:RF-32: lo que se compara de cada objeto que graban las variaciones activas.
ATRIBUTOS_DE_HUELLA = ('outserv', 'on_off', 'plini', 'qlini', 'scale0', 'dline', 'nlnum', 'ncapa', 'ncapx', 'usetp',
                       'ntrcn', 'nntap', 'qcapn', 'uknom')


def _atributos(o, nombres) -> dict:
    out = {}
    for a in nombres:
        try:
            out[a] = getattr(o, a)
        except AttributeError:
            continue
    return out


def _de_tipo(o):
    """098:RF-32: del tipo, su nombre y lo eléctrico: un tipo de igual nombre con otra sección es otra red."""
    tipo = getattr(o, 'typ_id', None)
    if tipo is None:
        return None
    return [getattr(tipo, 'loc_name', None), _atributos(tipo, ('sline', 'rline', 'xline', 'uline'))]


def huella_de_la_red(app, alims, feeders) -> str | None:
    """098:RF-32: la huella de lo que se mide, con el contenido de las variaciones y no solo sus nombres.

    Dos variaciones con el mismo nombre y otra potencia (una carga nueva con otros kW, una obra rehecha) daban la misma
    huella con solo los nombres, y la escalera reutilizaba una medida de otra red. Lleva lo que graba cada etapa activa
    (cada objeto, con :data:`ATRIBUTOS_DE_HUELLA` y su tipo) y la suma de la demanda de cada alimentador. Sin poder
    leerla, ``None``: no se reutiliza nada."""
    import hashlib

    try:
        partes = []
        for v in sorted(app.GetActiveNetworkVariations() or [], key=lambda x: x.loc_name):
            for etapa in v.GetContents('*.IntSstage') or []:
                raiz = etapa.GetFullName()
                for o in etapa.GetContents('*', 1) or []:
                    partes.append([v.loc_name, o.GetFullName().replace(raiz, '', 1), _atributos(o, ATRIBUTOS_DE_HUELLA),
                                   _de_tipo(o)])
        # El estado de operación lo guarda el escenario, no la etapa (042:RF-19): lo abierto y lo fuera de servicio. Solo
        # de los alimentadores en estudio (el plan trae también sus vecinos): toda la red tardaba en una de 200.
        escenario = app.GetActiveScenario() if hasattr(app, 'GetActiveScenario') else None
        partes.append(['escenario', getattr(escenario, 'loc_name', None)])
        for f in sorted(feeders):
            elm = alims.elm.get(f)
            if elm is None:
                continue
            for clase in ('ElmLne', 'ElmCoup', 'ElmTr2', 'ElmLod', 'ElmShnt', 'ElmVoltreg'):
                objs = list(elm.GetObjs(clase) or [])
                partes.append([f, clase, sorted([_ruta_de(o), _atributos(o, ('outserv', 'on_off')), _de_tipo(o)]
                                                for o in objs)])
                if clase == 'ElmLne':
                    llaves = [sw for ln in objs for lado in ('bus1', 'bus2')
                              for sw in ((getattr(ln, lado, None).GetContents('*.StaSwitch') or [])
                                         if getattr(ln, lado, None) is not None else [])]
                    partes.append([f, 'StaSwitch', sorted([_ruta_de(sw), _atributos(sw, ('on_off',))] for sw in llaves)])
        for f in sorted(feeders):
            elm = alims.elm.get(f)
            cargas = list(elm.GetObjs('ElmLod')) if elm is not None else []
            partes.append([f, round(sum(float(getattr(c, 'plini', 0) or 0) * float(getattr(c, 'scale0', 1) or 1)
                                        for c in cargas if not int(getattr(c, 'outserv', 0) or 0)), 3),
                           round(sum(float(getattr(c, 'qlini', 0) or 0) * float(getattr(c, 'scale0', 1) or 1)
                                     for c in cargas if not int(getattr(c, 'outserv', 0) or 0)), 3), len(cargas)])
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return None
    datos = json.dumps(partes, sort_keys=True, ensure_ascii=False, default=str)
    if not datos:
        return None
    return hashlib.sha256(datos.encode('utf-8')).hexdigest()


def datos_escalera(app, plan: dict) -> tuple[dict, int]:
    """Lo que necesita armar las variantes de la escalera, en «Con proyecto <año>» (025:RF-49,
    RF-60): la troncal de cada alimentador desde la cabecera, leída sin las cargas nuevas
    (sobre esa red graban las obras), con el largo de cada tramo; su corriente y su tensión con
    todas las cargas; el primer tramo que queda bajo ``tension_min_pu``, en qué tramo de la
    troncal cae cada barra de ``barras`` (por su posición GPS) y cuáles de ellas existen sin las
    cargas nuevas (``existen``): un banco en el nodo que crea la variación de una carga
    dependería de ella (Pisco, 2026-10-23: NODE_T_PI_1 y NODE_T_PI_11; 025:RF-44).
    """
    informe: dict[str, Any] = {'project': plan.get('project'), 'modo': 'datos_escalera',
                               'alimentadores': {}, 'avisos': []}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    anio = informe['anio_casos'] = anio_del_plan(plan)
    casos = casos_del_proyecto(app, anio)
    if 'con' not in casos:
        return {**informe, 'error': f"falta «{nombre_caso('con', anio)}»"}, 2
    feeders = list(plan.get('feeders') or [])
    alims = Alimentadores(app, proyecto, feeders)
    vmin = float(plan.get('tension_min_pu') or 0)
    inicial = app.GetActiveStudyCase()
    troncales: dict[str, list[dict]] = {}
    extremos: dict[str, list[tuple]] = {}             # nombres de las dos barras de cada tramo
    posiciones: dict[str, list[list]] = {}            # y su posición GPS
    existen: dict[str, list[str]] = {}                # barras pedidas que no crea ninguna carga
    sin_cargas_de: dict[str, set[str]] = {}
    media_de: dict[str, list[str]] = {}               # barras de media del alimentador (087:RF-55)
    ajenas: list = []
    diario_apartadas = None
    try:
        # 081:RF-82, RF-83: antes de leer la escalera, «Con proyecto» sin restos de una orden cortada. Pisco (2026-11-07):
        # leída con dos tramos abiertos de una transferencia a medias, toda la escalera se rehízo sobre una red rota.
        restituir_pendientes(app, plan, casos, informe)
        comprobar_servicio_con_proyecto(app, plan, casos, informe)
        casos['con'].Activate()
        # 025:RF-73: el estado de «Con proyecto» con el que se medirá; una evaluación anterior
        # solo se reutiliza si es el mismo.
        informe['variaciones_activas'] = sorted(v.loc_name for v in app.GetActiveNetworkVariations() or [])
        diario_apartadas = anotar_apartadas(plan, casos['con'], list(plan.get('apartar_obras') or []))   # 098:RF-36
        ajenas = _apartar_cargas_de(app, list(plan.get('apartar_cargas_de') or []),
                                    plan.get('apartar_variaciones'), plan.get('apartar_obras'))   # RF-69, 042:RF-2
        # 098:RF-32: la red tal como se mide, sin lo apartado (también la obra que se compara, 098:RF-36).
        informe['huella_red'] = huella_de_la_red(app, alims, feeders)
        apartadas = _apartar_cargas_nuevas(app)
        try:
            flujo_de_carga(app)          # el ElmFeeder da sus objetos según la última topología
            for f in feeders:
                elm = alims.elm.get(f)
                if elm is None:
                    informe['avisos'].append(f'{f}: no está en el proyecto.')
                    continue
                tramos, red, _cab, av = leer_troncal(elm, f)
                informe['avisos'] += av
                por = red.por_nombre() if red is not None else {}
                troncales[f] = [{'nombre': n, 'largo_m': float(por[n].largo_m) if n in por else 0.0}
                                for n in tramos]
                extremos[f] = [((por[n].desde, por[n].hasta) if n in por else ()) for n in tramos]
                posiciones[f] = [[red.barras[b].gps for b in ext if b in red.barras and red.barras[b].gps]
                                 for ext in extremos[f]]
                sin_cargas = sin_cargas_de[f] = {b.loc_name for b in elm.GetObjs('ElmTerm')}
                # 087:RF-55: donde la búsqueda puede poner bancos, en todo el alimentador y sin las cargas nuevas.
                media_de[f] = sorted(b.loc_name for b in elm.GetObjs('ElmTerm')
                                     if float(getattr(b, 'uknom', 0) or 0) >= 1.0)
                existen[f] = [b for b in (plan.get('barras') or {}).get(f, []) if b in sin_cargas]
        finally:
            for v in apartadas:
                v.Activate()
        flujo = flujo_de_carga(app)                                   # con todas las cargas
        informe['converge'] = bool(flujo['converged'])
        # 042: una ampliación (040:RF-4) cuelga de la barra de baja de su SED; lo que mide la
        # escalera es la de media (025:RF-50). Con la de baja, en NA203 + NA205 (2026-10-31) todas
        # las variantes salían «la carga nueva en SE50150_BT queda a ? p.u.».
        terminales = {b.loc_name: b for b in app.GetCalcRelevantObjects('*.ElmTerm')}
        media: dict[str, str] = {}
        for f in troncales:
            for nombre in (plan.get('barras') or {}).get(f, []):
                m = _media_de(terminales.get(nombre))
                media[nombre] = m.loc_name if m is not None else nombre
            existen[f] = list(dict.fromkeys(
                [media.get(b, b) for b in existen.get(f, [])]
                + [media[b] for b in (plan.get('barras') or {}).get(f, [])
                   if media.get(b, b) != b and media[b] in sin_cargas_de.get(f, set())]))
        # 063:RF-32: el camino eléctrico de la cabecera a cada carga, con todas las cargas y el
        # flujo que convergió; sobre él van sección y terna, y el banco en su barra de aguas arriba.
        from convertersmartgrid.escalera_optima import camino_electrico
        from convertersmartgrid.obras_integrales import con_maniobras
        tramos_red = []
        for ln in app.GetCalcRelevantObjects('*.ElmLne') or []:
            a = getattr(getattr(ln, 'bus1', None), 'cterm', None)
            b = getattr(getattr(ln, 'bus2', None), 'cterm', None)
            if a is None or b is None or int(getattr(ln, 'outserv', 0) or 0):
                continue
            tipo = getattr(ln, 'typ_id', None)
            i = _resultado(ln, 'm:I:bus1') if flujo['converged'] else None
            tramos_red.append({'nombre': ln.loc_name, 'desde': a.loc_name, 'hasta': b.loc_name,
                               'u': ({a.loc_name: _resultado(a, 'm:u'), b.loc_name: _resultado(b, 'm:u')}
                                     if flujo['converged'] else {}),                  # 042:RF-47
                               'largo_m': float(getattr(ln, 'dline', 0) or 0) * 1000,
                               'corriente_a': i * 1000 if i is not None else None,
                               'tipo': tipo.loc_name if tipo is not None else None,
                               'cable': bool(es_cable(ln)),                # 084:RF-16
                               'inom_a': (float(getattr(tipo, 'sline', 0) or 0) * 1000
                                          if tipo is not None else None),
                               'maniobra': maniobra_del_tramo(ln)})                      # 098:RF-11
        tramos_red += puentes_de_la_red(app)                                  # 042:RF-44
        margen = None                  # 098:RF-21: el de cada vecino, una vez para todos
        for f, troncal in troncales.items():
            elm = alims.elm[f]
            lineas = {ln.loc_name: ln for ln in elm.GetObjs('ElmLne')}
            barras = {b.loc_name: b for b in elm.GetObjs('ElmTerm')}
            # 098:RF-29: las barras de media del alimentador bajo el límite con «Con proyecto» como está (todas las cargas):
            # un alimentador sin cargas nuevas que viola límites también lleva su escalera. CHN102 (2026-11-07) quedó
            # en 0,73 p.u. en la zona que recibió y la escalera solo trabajó CA101.
            bajas = sorted((u, n) for n, b in barras.items() if float(getattr(b, 'uknom', 0) or 0) > 1.0
                           and flujo['converged'] and vmin and (u := _resultado(b, 'm:u')) is not None and u < vmin)
            corriente, fuera = None, None
            for i, (t, ext) in enumerate(zip(troncal, extremos[f])):
                ln = lineas.get(t['nombre'])
                c = _resultado(ln, 'm:I:bus1') if ln is not None and flujo['converged'] else None
                corriente = c * 1000 if c is not None else corriente  # partido por una carga: el anterior
                t['corriente_a'] = corriente
                # 063:RF-30: el conductor de cada tramo, para que el cambio de sección solo suba de
                # sección (SM218, 2026-11-01: «sección CU 50 mm²» bajaba casi toda la troncal).
                tipo = getattr(ln, 'typ_id', None) if ln is not None else None
                if tipo is not None:
                    t['tipo'] = tipo.loc_name
                    t['inom_a'] = float(getattr(tipo, 'sline', 0) or 0) * 1000
                    t['cable'] = bool(es_cable(ln))                        # 084:RF-16
                # 063:RF-31: los nodos de inicio y fin de cada tramo, para decir dónde va la obra.
                if len(ext) == 2:
                    t['desde'], t['hasta'] = ext
                us = [u for u in (_resultado(barras[b], 'm:u') for b in ext if b in barras) if u]
                if fuera is None and vmin and us and min(us) < vmin:
                    fuera = i
            puntos = posiciones[f]
            indices = {}
            for nombre in dict.fromkeys(media.get(b, b) for b in (plan.get('barras') or {}).get(f, [])):
                barra = barras.get(nombre) or terminales.get(nombre)
                g = gps_de(barra) if barra is not None else None
                candidatos = [(distancia_m(g, q), i) for i, ps in enumerate(puntos) for q in ps if q] if g else []
                if candidatos:
                    indices[nombre] = min(candidatos)[1]
                else:
                    informe['avisos'].append(f'{f}: la barra {nombre} no tiene posición GPS; sin tramo de '
                                             'la troncal para su terna o su sección.')
            # 063:RF-25: la barra de una carga que crea su propia variación (NODE_T_ al partir un
            # tramo) no existe sin ella; su banco va en la barra existente de ese tramo de la
            # troncal, la de aguas arriba. SM218 (2026-11-01): INKA quedaba sin escalón de bancos.
            sin_ellas = sin_cargas_de.get(f, set())
            banco_en = {}
            for nombre, i in indices.items():
                if nombre in sin_ellas or i >= len(extremos[f]):
                    continue
                existente = next((b for b in extremos[f][i] if b in sin_ellas), None)
                if existente is not None:
                    banco_en[nombre] = existente
            cab = cabecera_de(elm)
            caminos = {}
            for nombre in dict.fromkeys(media.get(b, b) for b in (plan.get('barras') or {}).get(f, [])):
                c = con_maniobras(camino_electrico(tramos_red, cab.loc_name, nombre)) if cab is not None else []  # 098:RF-11
                if c:
                    caminos[nombre] = c
                    if nombre not in sin_ellas and c[-1]['desde'] in sin_ellas:
                        banco_en[nombre] = c[-1]['desde']        # aguas arriba, por el camino real
                else:
                    informe['avisos'].append(f'{f}: sin camino eléctrico hasta {nombre}: sus obras se colocan por cercanía GPS (042:RF-45).')
            # 042:RF-43: los tramos de cualquier ramal que pasan del límite con las cargas nuevas.
            limite = float(plan.get('cargabilidad_max_pct') or 0)
            por_nombre = {t['nombre']: t for t in tramos_red}
            sobrecargados = []
            for ln in (lineas.values() if limite and flujo['converged'] else ()):
                carga = _resultado(ln, 'c:loading')
                if carga is not None and carga > limite:
                    sobrecargados.append({**por_nombre.get(ln.loc_name, {}), 'nombre': ln.loc_name, 'carga_pct': float(carga),
                                          'largo_m': float(getattr(ln, 'dline', 0) or 0) * 1000,
                                          'nlnum': int(getattr(ln, 'nlnum', 1) or 1)})
            nivel = None
            if plan.get('migrar_a_kv') and cab is not None:                    # 042:RF-50 a RF-53
                salida = barra_de_destino(app, cab, float(plan['migrar_a_kv']))
                con_cabecera = [t for t in tramos_red if cab.loc_name in (t['desde'], t['hasta'])
                                and t['nombre'] in {x.loc_name for x in list(elm.GetObjs('ElmLne')) + list(elm.GetObjs('ElmCoup'))}]
                primero = (con_cabecera[0]['hasta'] if con_cabecera and con_cabecera[0]['desde'] == cab.loc_name
                           else con_cabecera[0]['desde'] if con_cabecera else '')
                nivel = {'salida': salida.loc_name if salida is not None else '', 'nodo': primero,
                         'km': sum(float(getattr(ln, 'dline', 0) or 0) for ln in elm.GetObjs('ElmLne')),
                         'seds': len(elm.GetObjs('ElmTr2')),
                         'compartida': any(g != f and (c := cabecera_de(otro)) is not None and clave_pf(c) == clave_pf(cab)
                                           for g, otro in alims.elm.items())}
            # 098:RF-21: los enlaces que ya existen con los vecinos, para transferir sin construir nada.
            if margen is None:
                margen = {}
                for g, otro in alims.elm.items():
                    us = [_resultado(b, 'm:u') for b in otro.GetObjs('ElmTerm') if flujo['converged']
                          and float(getattr(b, 'uknom', 0) or 0) > 1.0]
                    cs = [_resultado(ln, 'c:loading') for ln in otro.GetObjs('ElmLne') if flujo['converged']]
                    us, cs = [u for u in us if u is not None], [c for c in cs if c is not None]
                    margen[g] = {'u_min': min(us) if us else None, 'carga_max_pct': max(cs) if cs else None}
                enlaces = enlaces_existentes(app, alims, list(troncales), tramos_red, margen)
            informe['alimentadores'][f] = {'troncal': troncal, 'fuera_desde': fuera, 'indices': indices, 'nivel': nivel,
                                           'enlaces': enlaces.get(f, []),
                                           'bajas': [{'barra': n, 'u': round(u, 4)} for u, n in bajas[:MAX_BAJAS]],
                                           'banco_en': banco_en, 'caminos': caminos, 'sobrecargados': sobrecargados,
                                           'existen': existen.get(f, []), 'barras_media': media_de.get(f, []),
                                           'media': {b: media.get(b, b) for b in (plan.get('barras') or {}).get(f, [])}}
    finally:
        if ajenas:
            casos['con'].Activate()
            for v in ajenas:
                v.Activate()
        if diario_apartadas:
            _quitar_diario(plan, 'apartada', diario_apartadas)
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    return informe, 0


def datos_oraculo(app, plan: dict) -> tuple[dict, int]:
    """Lo de ``datos_escalera`` y, en la misma lectura, el grafo eléctrico de «Con proyecto» con
    todas las cargas nuevas del plan activas y, por cada una, su nodo, su P y su Q (052:RF-1).

    Una sola lectura por optimización: el oráculo calcula después cada variante sin volver a
    DIgSILENT. La carga nueva se busca por el nombre con que la crea la 007 (``nombre_pf`` de
    su SED); su variación se activa solo para leerla y se deja como estaba.
    """
    import sys

    aqui = str(Path(__file__).resolve().parent)
    if aqui not in sys.path:                  # cargado como módulo suelto (pruebas, servidor)
        sys.path.insert(0, aqui)
    import digital_twin_snapshot_pf as snap

    informe, codigo = datos_escalera(app, plan)
    informe['modo'] = 'datos_oraculo'
    if codigo:
        return informe, codigo
    proyecto = app.GetActiveProject()
    casos = casos_del_proyecto(app, anio_del_plan(plan))
    inicial = app.GetActiveStudyCase()
    pedidas = {str(c.get('variacion')) for c in plan.get('nuevas') or []}
    activadas: list = []
    try:
        casos['con'].Activate()
        activas = {v.loc_name for v in app.GetActiveNetworkVariations() or []}
        carpeta = app.GetProjectFolder('scheme')
        for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta is not None else []):
            if v.loc_name in pedidas and v.loc_name not in activas:
                v.Activate()
                activadas.append(v)
        raiz = snap.clave_pf(proyecto)
        grafo = snap.grafo(app, proyecto, raiz, list(plan.get('feeders') or []))
        # El largo de cada tramo, para el cambio de sección (052:RF-2).
        largos = {snap._id(ln, raiz): float(getattr(ln, 'dline', 0.0) or 0.0)
                  for ln in app.GetCalcRelevantObjects('*.ElmLne')}
        for r in grafo.get('ramas') or []:
            if r.get('id') in largos:
                r['largo_km'] = largos[r['id']]
        # Lo que pone cada variación, por diferencia: la red con ella activa y sin ella. Una carga
        # nueva aparece; una ampliación de un cliente existente (040) cambia su P y su Q. Por el
        # nombre, en NA203 + NA205 (2026-11-01) solo se hallaban 3 de 35.
        def foto() -> dict:
            out = {}
            for c in app.GetCalcRelevantObjects('*.ElmLod'):
                if int(getattr(c, 'outserv', 0) or 0):
                    continue
                escala = float(getattr(c, 'scale0', 1.0) or 1.0)
                out[c.GetFullName()] = (c, float(getattr(c, 'plini', 0.0) or 0.0) * escala,
                                        float(getattr(c, 'qlini', 0.0) or 0.0) * escala)
            return out

        variaciones = {v.loc_name: v for v in (app.GetActiveNetworkVariations() or [])}
        con_todas = foto()
        nuevas = []
        for c in plan.get('nuevas') or []:
            v = variaciones.get(str(c.get('variacion')))
            if v is None:
                informe['avisos'].append(f"la variación {c.get('variacion')} de {c.get('sed')} no está activa "
                                         'en «Con proyecto»')
                continue
            v.Deactivate()
            try:
                sin_ella = foto()
            finally:
                v.Activate()
            cambios = []
            for clave, (obj, pc, qc) in con_todas.items():
                ps, qs = sin_ella.get(clave, (None, 0.0, 0.0))[1:]
                if abs(pc - ps) > 1e-9 or abs(qc - qs) > 1e-9:
                    cambios.append((obj, pc - ps, qc - qs))
            if not cambios:
                informe['avisos'].append(f"la variación {c.get('variacion')} de {c.get('sed')} no cambia ninguna "
                                         'carga en «Con proyecto»')
                continue
            obj, dp, dq = max(cambios, key=lambda t: abs(t[1]))
            # Su cubículo: el ``bus1`` o, si aún no lo da, el que la apunta (como la conecta la 007).
            cub = getattr(obj, 'bus1', None) or next(
                (k for k in app.GetCalcRelevantObjects('*.StaCubic') if getattr(k, 'obj_id', None) is obj), None)
            nuevas.append({**c, 'nodo': snap._barra(cub, raiz), 'p_mw': sum(t[1] for t in cambios),
                           'q_mvar': sum(t[2] for t in cambios), 'objeto': obj.loc_name})
        informe['grafo'] = grafo
        informe['nuevas'] = nuevas
    finally:
        for v in activadas:
            v.Deactivate()
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    return informe, 0


def _cargas_de(alims, feeder: str) -> list:
    """Las cargas en servicio del alimentador, en todas sus troncales (063:RF-39).

    ``ElmFeeder.GetObjs`` solo ve lo que cuelga de su cubículo: en SM218 (2026-11-02), 242 de 306
    cargas; las 64 de la segunda troncal (1,698 MW) no se escalaban en los sorteos y las pérdidas
    salían en 2 126 kW en vez de 428 kW. ``cargas_sed`` une la topología y ``p:alimentador``, como la
    calibración (CA101: 95 de 168).
    """
    cargas = {_clave_objeto_nativo(c): c for c in cargas_sed(alims, feeder)[0].values()}
    # La lista de ``alims`` se guardó en «Sin proyecto»: la carga nueva de «Con proyecto» solo la ve
    # el ElmFeeder en el caso activo. Sin esto, INKA (1 100 kW) salía como pérdidas.
    elm = alims.elm.get(feeder)
    for c in (elm.GetObjs('ElmLod') if elm is not None else []):
        if not getattr(c, 'outserv', 0):
            cargas.setdefault(_clave_objeto_nativo(c), c)
    return list(cargas.values())


#: 042:RF-89: lo que tarda cada parte de las medidas ligeras, para saber dónde se va el tiempo.
TIEMPOS = {'flujos': 0, 'flujo_s': 0.0, 'lectura_s': 0.0}
#: 042:RF-89: las fases se miran una vez por caso: una obra de la escalera no las cambia.
_MONOFASICOS: dict[str, bool] = {}


def _monofasicos_del_caso(app) -> bool:
    caso = getattr(app.GetActiveStudyCase(), 'loc_name', '')
    if caso not in _MONOFASICOS:
        from convertersmartgrid.dgs import red_con_monofasicos

        _MONOFASICOS[caso] = red_con_monofasicos(app)
    return _MONOFASICOS[caso]


#: 087:RF-51: las obras que cambian qué alimenta a qué: tras borrarlas, un flujo para que el ElmFeeder lo vea.
TOPOLOGIA = frozenset({'enlace', 'migracion', 'tension', 'expreso', 'set_nueva'})


def medida_para_criterio(app, alims, feeders: list[str], *, ligera: bool = False) -> dict[str, Any]:
    """Lo que juzga ``escalera_optima.cumple``: si converge, la tensión de cada barra de media
    y la carga de cada tramo de los alimentadores, y sus pérdidas (025:RF-50, RF-53)."""
    inicio = time.perf_counter()
    flujo = flujo_de_carga(app, extremos=False, monofasicos=_monofasicos_del_caso(app)) if ligera else flujo_de_carga(app)
    medio = time.perf_counter()
    out: dict[str, Any] = {'converge': bool(flujo['converged']), 'u': {}, 'carga': {}, 'perdidas_kw': None}
    if ligera:
        TIEMPOS['flujos'] += 1
        TIEMPOS['flujo_s'] += medio - inicio
    if not out['converge']:
        return out

    def objetos(f, clase):
        # 025:RF-75: los del alimentador en este caso y con esta variante; la lista guardada de
        # ``alims`` es la de «Sin proyecto», sin la barra de la carga nueva (NODE_T_CH_9 de
        # PN107 salía «a ? p.u.», 2026-10-24).
        elm = alims.elm.get(f)
        if elm is None:
            return alims.objetos(f, clase)
        try:
            return list(elm.GetObjs(clase))
        except Exception:  # noqa: BLE001 - se usa la lista guardada
            return alims.objetos(f, clase)

    for f in feeders:
        for b in objetos(f, 'ElmTerm'):
            try:
                if float(getattr(b, 'uknom', 0) or 0) >= 1.0 and b.HasResults():
                    out['u'][b.loc_name] = float(b.GetAttribute('m:u'))
            except Exception:  # noqa: BLE001, S110 - sin resultado, no cuenta
                pass
        for ln in objetos(f, 'ElmLne'):
            try:
                out['carga'][ln.loc_name] = float(ln.GetAttribute('c:loading'))
            except Exception:  # noqa: BLE001, S110
                pass
        # 042:RF-28: los transformadores de la SET que alimenta al alimentador, con el mismo límite.
        elm = alims.elm.get(f)
        cab = cabecera_de(elm) if elm is not None else None
        for c in (cab.GetContents('*.StaCubic') if cab is not None else []) or []:
            e = getattr(c, 'obj_id', None)
            if e is not None and e.GetClassName() in ('ElmTr2', 'ElmTr3'):
                try:
                    out['carga'][e.loc_name] = float(e.GetAttribute('c:loading'))
                except Exception:  # noqa: BLE001, S110
                    pass
    if ligera:                                                                  # 042:RF-89: el criterio no usa pérdidas
        TIEMPOS['lectura_s'] += time.perf_counter() - medio
        return out
    # 087:RF-42: las barras de media sin servicio de toda la red, no solo de estos alimentadores: una parte que una
    # transferencia o un traslado deja colgando sale de su ElmFeeder y, sin resultado, no la veía el criterio.
    # Solo con la máxima: escalar la demanda en los sorteos no cambia la topología.
    relevantes = getattr(app, 'GetCalcRelevantObjects', None)
    if relevantes is not None:
        aisladas = []
        for b in relevantes('*.ElmTerm') or []:
            try:
                if float(getattr(b, 'uknom', 0) or 0) >= 1.0 and int(b.IsEnergized()) == 0:
                    aisladas.append(b.loc_name)
            except Exception:  # noqa: BLE001, S110 - sin el dato, no cuenta
                pass
        out['aisladas'] = sorted(aisladas)
    # 025:RF-70: lo que entra por la cabecera menos lo que consumen las cargas en el flujo; con
    # su potencia nominal, a 0,88 p.u. las pérdidas de SI213 salían −2044 kW (2026-10-24).
    # 087:RF-51: lo que entra por todas las cabeceras menos lo que consumen todas sus cargas, cada una una vez. Con una
    # transferencia, la parte que pasa sigue en la lista de su alimentador de antes y en el ElmFeeder del que la recibe;
    # por alimentador se contaba dos veces y las pérdidas salían negativas (CHI201 a SC215, Pisco, 2026-11-04).
    entra, consumo, vistas = 0.0, 0.0, set()
    for f in feeders:
        elm = alims.elm.get(f)
        cab = leer_cabecera(elm) if elm is not None else None
        if cab is None or not cab.converge or cab.kw is None:
            out['perdidas_kw'] = None
            return out
        entra += cab.kw
        for c in _cargas_de(alims, f):                                           # 063:RF-39
            clave = c.GetFullName() if hasattr(c, 'GetFullName') else id(c)
            if clave in vistas:
                continue
            vistas.add(clave)
            x = _resultado(c, 'm:Psum:bus1')
            if x is None:
                out['perdidas_kw'] = None
                return out
            consumo += x
    out['perdidas_kw'] = entra - 1000 * consumo if feeders else None
    return out


def _apartar_cargas_de(app, feeders: list[str], variaciones=(), obras=()) -> list:
    """Desactiva en el caso activo las variaciones de cargas nuevas de ``feeders`` y las
    devuelve, para volver a activarlas (025:RF-69). Una carga es ``Carga_<SED>_<alim>_…``.

    042:RF-1 a RF-3: también las de ``variaciones``, por su nombre: la escalera carga a carga
    mide las k mayores del alimentador con las demás suyas apartadas.
    """
    tokens = [f'_{nombre_pf(f)}_' for f in feeders]
    nombres = set(variaciones or ())
    # 098:RF-36: la obra que se compara con la de corto plazo se mide fuera, por su nombre exacto, y vuelve después.
    de_obra = set(obras or ())
    apartadas = [v for v in (app.GetActiveNetworkVariations() or [])
                 if v.loc_name in de_obra
                 or (es_de_carga_nueva(v) and (v.loc_name in nombres
                                               or any(t in v.loc_name[len('Carga_'):] for t in tokens)))]
    for v in apartadas:
        v.Deactivate()
    return apartadas


def base_guardada(ruta: str | None, sorteos: int, valle: int) -> tuple[list, list] | None:
    """087:RF-28: los sorteos base ya medidos en este trabajo; ``None`` si no están o no son de estos sorteos.

    Con las etapas de 042:RF-87 puede haber solo los primeros: valen, y los que faltan se miden al necesitarlos.
    """
    if not ruta:
        return None
    try:
        datos = json.loads(Path(ruta).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not datos.get('sorteos') or len(datos['sorteos']) > sorteos or len(datos.get('valle') or []) != valle:
        return None
    return datos['sorteos'], datos['valle']


def guardar_base(ruta: str | None, sin_sorteos: list, sin_valle: list) -> None:
    """Si no se puede escribir, se medirá otra vez: no es razón para fallar la evaluación."""
    if not ruta:
        return
    try:
        temporal = Path(f'{ruta}.tmp')
        temporal.write_text(json.dumps({'sorteos': sin_sorteos, 'valle': sin_valle}), encoding='utf-8')
        os.replace(temporal, ruta)
    except OSError:
        pass


class _Sorteo:
    """Escenario temporal, copia del del caso, donde se escalan las cargas existentes por el
    factor de su alimentador; se borra al salir y vuelve el escenario del caso (025:RF-51).

    073:RF-25, RF-39: en valle, las cargas nuevas también: apagadas o a su potencia.
    """

    def __init__(self, app, alims, feeders, existentes: set[str]):
        self.app, self.alims, self.feeders, self.existentes = app, alims, feeders, existentes

    def __enter__(self):
        app = self.app
        self.original = app.GetActiveScenario()
        if self.original is None:
            # Sin escenario, escribir la demanda cambiaría la red del caso, no un escenario.
            raise RuntimeError(f'«{app.GetActiveStudyCase().loc_name}» no tiene escenario de '
                               'operación: no se sortea sobre él (025:RF-51)')
        carpeta = app.GetProjectFolder('scen', 1)
        nombre = nombre_libre(carpeta, 'IntScenario', 'CSG_sorteo_escalera')
        self.temporal = carpeta.AddCopy(self.original, nombre)
        self.original.Deactivate(0)
        self.temporal.Activate()
        # 063:RF-28: se escala ``scale0``, no ``plini``/``qlini``. Sonda en una copia de SM218
        # (2026-11-02): las existentes daban 7,2 MW; tras escribir ``plini × 0,35`` en el
        # escenario, 9,1 MW, y lo mismo con cualquier factor (en PC escribir la Q mueve el cos φ
        # y la calibración vive en ``scale0``). Todos los sorteos medían la misma red: INKA a
        # 0,938 p.u. con factores de 0,35 a 0,74, y las variantes salían al 94,5 %. Con
        # ``scale0 × 0,35`` la demanda bajó a 3,2 MW e INKA subió a 0,960 p.u.
        self.base = {}
        self.nuevas = {}
        for f in self.feeders:
            for c in _cargas_de(self.alims, f):                              # 063:RF-39
                destino = self.base if c.loc_name in self.existentes else self.nuevas
                destino[id(c)] = (c, f, float(getattr(c, 'scale0', 1.0) or 0.0))
        return self

    def escalar(self, factores: dict[str, float], factor_nuevas: float | None = None) -> None:
        for c, f, s0 in self.base.values():
            c.scale0 = s0 * float(factores.get(f, 1.0))
        if factor_nuevas is not None:
            for c, _f, s0 in self.nuevas.values():
                c.scale0 = s0 * float(factor_nuevas)

    def __exit__(self, *exc):
        try:
            for c, _f, s0 in (*self.base.values(), *self.nuevas.values()):      # todavía en el temporal
                c.scale0 = s0
            self.temporal.Deactivate(0)
        finally:
            self.original.Activate()
            self.temporal.Delete()
        return False


#: 098:RF-28: lo que dice la evaluación de una variante que no quedó aplicada donde se mide.
NO_APLICADA = 'no aplicada'


def _clave_obras(obras) -> str:
    return json.dumps(sorted(json.dumps(o, sort_keys=True, ensure_ascii=False) for o in obras), ensure_ascii=False)


def _sin_regulador(v: dict) -> str:
    """098:RF-34: la clave de las obras de la variante sin sus reguladores."""
    return _clave_obras([o for o in v.get('obras') or [] if o.get('clase') != 'regulador'])


def sin_cambio(antes: dict, despues: dict, tol_u: float = 1e-6, tol_carga: float = 1e-4) -> bool:
    """098:RF-28: si dos medidas convergidas dan las mismas tensiones y cargas, barra por barra y tramo por tramo."""
    if not (antes.get('converge') and despues.get('converge')):
        return False
    ua, ud = antes.get('u') or {}, despues.get('u') or {}
    ca, cd = antes.get('carga') or {}, despues.get('carga') or {}
    if not ud or set(ua) != set(ud) or set(ca) != set(cd):
        return False
    return (all(abs(float(ua[b] or 0) - float(ud[b] or 0)) <= tol_u for b in ud)
            and all(abs(float(ca[e] or 0) - float(cd[e] or 0)) <= tol_carga for e in cd))


def evaluar(app, plan: dict, *, cancelado=lambda: False) -> tuple[dict, int]:
    """Cada variante de la escalera en «Con proyecto <año>»: con la máxima y, si cumple, en los
    sorteos; sin dejar ninguna obra ni el escenario temporal (025:RF-50 a RF-52b, RF-44b).

    ``plan``: ``project``, ``anio_casos``, ``feeders``, ``variantes`` (``nombre`` y ``obras``),
    ``barras_cargas`` (las barras de media de las cargas nuevas), ``sorteos`` (``factores``
    por alimentador), ``parametros`` (el perfil con ``escalera``, ``planificacion`` y
    ``estudios``) y ``valle`` (sus ``puntos``, 073:RF-25). Devuelve por variante si cumple con la
    máxima, la fracción de sorteos que cumplen, sus pérdidas con la máxima y lo medido en valle.
    """
    from convertersmartgrid.escalera_optima import (cumple, cumple_en_valle, definitiva, grupo_economico,
                                                    hace_falta_seguir, parametros, plan_de_horizonte)
    from convertersmartgrid.informes import clasificar_bajo_limite
    from convertersmartgrid.valle import CASOS_CARGAS, anotar_punto, sin_comprobar

    informe: dict[str, Any] = {'project': plan.get('project'), 'modo': 'evaluar', 'variantes': [],
                               'avisos': [], 'cancelado': False}
    try:
        p = parametros(plan.get('parametros') or {}, plan.get('tipo_cambio'))       # 025:RF-67
    except ValueError as exc:
        return {**informe, 'error': str(exc)}, 2
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    anio = informe['anio_casos'] = anio_del_plan(plan)
    casos = casos_del_proyecto(app, anio)
    if 'sin' not in casos or 'con' not in casos:
        return {**informe, 'error': f"faltan «{nombre_caso('sin', anio)}» o «{nombre_caso('con', anio)}»"}, 2
    feeders = list(plan.get('feeders') or [])
    restituir_pendientes(app, plan, casos, informe)                               # 081:RF-82
    alims = Alimentadores(app, proyecto, feeders)
    barras = list(plan.get('barras_cargas') or [])
    sorteos = list(plan.get('sorteos') or [])
    # 073:RF-25: los puntos de valle de la medición. ``scale0`` lleva P y Q juntas: aquí la Q va con
    # el factor de la P, y lo exacto es la calibración a valle en su caso (T8).
    puntos_valle = list((plan.get('valle') or {}).get('puntos') or [])
    if puntos_valle:
        informe['avisos'].append('En valle, la Q se escala con el factor de la P (scale0): la Q medida entra con '
                                 'la calibración a valle (073 T8).')
    inicial = app.GetActiveStudyCase()
    casos['con'].Activate()
    ajenas: list = []
    diario_apartadas = None
    try:
        # 098:RF-36: dentro del ``try``: lo apartado vuelve aunque falle a mitad; la obra apartada, anotada en disco.
        diario_apartadas = anotar_apartadas(plan, casos['con'], list(plan.get('apartar_obras') or []))
        ajenas = _apartar_cargas_de(app, list(plan.get('apartar_cargas_de') or []),
                                    plan.get('apartar_variaciones'), plan.get('apartar_obras'))   # RF-69, 098:RF-36
        # «Sin proyecto» con la máxima y con cada sorteo, una sola vez (RF-50).
        casos['sin'].Activate()
        existentes = {c.loc_name for f in feeders for c in _cargas_de(alims, f)}   # 063:RF-39
        for f in feeders:
            # 063:RF-40: una troncal fuera del ElmFeeder entra en la evaluación, y se dice.
            elm = alims.elm.get(f)
            crudo = getattr(elm, 'crudo', elm)
            vistas = {c.loc_name for c in (crudo.GetObjs('ElmLod') if crudo is not None else [])}
            fuera = [c.loc_name for c in _cargas_de(alims, f) if c.loc_name not in vistas]
            if fuera:
                informe['avisos'].append(f'{f}: {len(fuera)} cargas de otra troncal, fuera de su ElmFeeder, entran '
                                         'en los sorteos, las pérdidas y el criterio (063:RF-40).')
        sin_max = medida_para_criterio(app, alims, feeders)
        informe['sin_proyecto'] = {'converge': sin_max['converge'], 'perdidas_kw': sin_max['perdidas_kw']}
        # 087:RF-28: la referencia sin obra se mide una vez por trabajo y se guarda; 042:RF-87 y RF-88: solo
        # la de los sorteos que van a usarse. Juntas: lo guardado puede ser solo la primera etapa.
        base = base_guardada(plan.get('base_sin_fichero'), len(sorteos), len(puntos_valle))
        sin_sorteos, sin_valle = (list(base[0]), list(base[1])) if base is not None else ([], [])
        # 042:RF-87: en la primera etapa, y sin etapas (0) o con pocos sorteos, todos.
        en_primera = len(sorteos) if not 0 < p.sorteos_etapa < len(sorteos) else p.sorteos_etapa

        def referencia_hasta(n: int) -> bool:
            """042:RF-88: la referencia sin obra de los sorteos que van a usarse; ``False`` si se cancela."""
            if n <= len(sin_sorteos):
                return True
            with _Sorteo(app, alims, feeders, existentes) as s:
                for i in range(len(sin_sorteos), n):
                    if i % 10 == 0 and cancelado():
                        informe['cancelado'] = True
                        return False
                    s.escalar(sorteos[i]['factores'])
                    sin_sorteos.append(medida_para_criterio(app, alims, feeders, ligera=True))
            if base is not None or puntos_valle_listos():
                guardar_base(plan.get('base_sin_fichero'), sin_sorteos, sin_valle)
            return True

        def puntos_valle_listos() -> bool:
            return len(sin_valle) == len(puntos_valle)

        if puntos_valle and not puntos_valle_listos():
            with _Sorteo(app, alims, feeders, existentes) as s:
                for pt in puntos_valle:
                    s.escalar(pt['factores'], 0.0)
                    sin_valle.append(medida_para_criterio(app, alims, feeders, ligera=True))
        if not referencia_hasta(en_primera):
            return informe, 2
        guardar_base(plan.get('base_sin_fichero'), sin_sorteos, sin_valle)

        def medir_valle() -> dict[str, Any]:
            """Lo que está activo en cada punto de valle, sin las cargas nuevas y con ellas, en un
            escenario temporal (073:RF-17, RF-25, RF-39)."""
            fila = sin_comprobar()
            casos_valle = CASOS_CARGAS if barras else CASOS_CARGAS[:1]
            with _Sorteo(app, alims, feeders, existentes) as s:
                for pt, sin_i in zip(puntos_valle, sin_valle):
                    for caso, factor_nuevas in casos_valle:
                        s.escalar(pt['factores'], factor_nuevas)
                        con = medida_para_criterio(app, alims, feeders, ligera=True)
                        bien, motivos = cumple_en_valle(sin_i, con, barras if factor_nuevas else [], p)    # 042:RF-85
                        anotar_punto(fila, pt, caso, bien, motivos, con.get('u') or {})
            return fila

        def con_variante(v, medir):
            """Crea las obras de ``v``, mide con ``medir()`` y las borra (RF-54); ``None`` y el
            error si no se pudieron crear."""
            # 098:RF-34: ``aplicar`` dentro del ``try``: si se corta a mitad, lo que alcanzó a cambiar (variaciones,
            # aperturas, el flujo y las tomas) se deshace igual, con lo anotado en disco de esta variante.
            hecho: dict = {}
            try:
                hecho, _rc = aplicar(app, {**plan, 'obras': v['obras'], 'evaluando': True})
                errores = [o['error'] for o in hecho.get('obras') or [] if o.get('error')] + (
                    [hecho['error']] if hecho.get('error') else [])
                # 098:RF-28: una obra que quedó inactiva en «Con proyecto» (su flujo no convergió, 011:RF-66) no se mide
                # como si estuviera: CA101 (2026-11-07) dio «cambio a 22.9 kV» con las tensiones de sin obra.
                inactivas = [o for o in hecho.get('obras') or [] if o.get('variacion') and not o.get('error')
                             and NOMBRES['con'] in (o.get('casos') or [])
                             and NOMBRES['con'] not in (o.get('casos_activos') or [])]
                if inactivas and not errores:
                    errores = [f"{NO_APLICADA}: {o['variacion']} quedó inactiva en «{NOMBRES['con']}»: "
                               + '; '.join(a for a in o.get('avisos') or [] if 'no converge' in a)[:300] for o in inactivas]
                if errores:
                    return None, '; '.join(errores)
                casos['con'].Activate()
                return medir(), None
            finally:
                filas_v = list(hecho.get('obras') or [])
                creadas = [o['variacion'] for o in filas_v if o.get('variacion')]
                # 098:RF-34: cada restitución en su ``try``: si una falla, las otras se hacen igual.
                try:
                    carpeta = app.GetProjectFolder('scheme')
                    por_nombre = {x.loc_name: x for x in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])}
                    for n in creadas:
                        var = por_nombre.get(n)
                        if var is not None:
                            for rol in ('sin', 'con'):
                                casos[rol].Activate()
                                var.Deactivate()
                            var.Delete()
                finally:
                    try:
                        # 081:RF-81: lo abierto es dato del escenario y sobrevive a la variación borrada (Pisco, 2026-11-07).
                        restituir_lo_abierto(app, casos, filas_v, plan)
                    finally:
                        try:
                            informe['avisos'] += restituir_el_flujo(app, casos, filas_v, plan)       # 098:RF-34
                        finally:
                            if not filas_v:
                                # ``aplicar`` no llegó a devolver sus filas: lo anotado en disco de esta evaluación.
                                restos = restituir_pendientes(app, plan, casos, {})
                                if restos:
                                    informe['avisos'].append(
                                        f"«{v['nombre']}» se cortó al crearse: se restituye lo que anotó, "
                                        + ', '.join(sorted({str(e.get('nombre')) for e in restos})) + ' (098:RF-34).')
                # 087:RF-51: una obra que cambia la topología (enlace, migración) deja el ElmFeeder con la red de la variante
                # hasta otro flujo; sin él, la siguiente creación de la misma obra no hallaba su nodo («no tiene camino
                # cerrado desde su cabecera», CHI201, Pisco, 2026-11-04) y sus sorteos y su alcance salían vacíos.
                if creadas and any(o.get('clase') in TOPOLOGIA for o in v['obras']):
                    casos['con'].Activate()
                    flujo_de_carga(app)

        def bajas(con: dict[str, Any]) -> dict[str, Any]:
            """086:RF-48: de cada barra, solo las que quedan bajo el límite con la máxima; las dos medidas ya están
            hechas, y guardar la ``u`` entera por variante pesaría sin que nadie la use (SI112, 2026-11-04)."""
            return clasificar_bajo_limite(sin_max.get('u') or {}, con.get('u') or {}, barras, p.tension_min_pu, p.tolerancia_pu)

        fallidos: list[dict] = []        # 063:RF-28: qué sorteos fallan y por qué, de la última variante
        certeza: dict = {}               # 087:RF-9: sorteos usados y probabilidad de cumplir, de la última variante

        def sortear(desde=0, hasta=None, fallos_antes=0):
            """Fracción de sorteos que cumplen; deja de sortear en cuanto ya no puede llegar a la
            del perfil (RF-72). Anota en ``fallidos`` el instante, el factor y el motivo de cada
            sorteo que falla: en SM218 (2026-11-01) tres variantes se quedaban en el 94,5 % y no se
            sabía si era por la máxima o por el valle."""
            # 087:RF-8: con la marca del plan se para también a favor, en cuanto la certeza lo permite; sigue
            # contando lo de la etapa anterior (042:RF-87), para no empezar de cero la posterior.
            from convertersmartgrid.seleccion_bayesiana import Seguimiento

            hasta = len(sorteos) if hasta is None else hasta
            seg = Seguimiento(len(sorteos), p.cumplimiento, bayesiana=bool(plan.get('parada_bayesiana')),
                              cumplen=desde - fallos_antes, fallan=fallos_antes)
            admite = int((1 - p.cumplimiento) * len(sorteos) + 1e-9)
            if not desde:
                fallidos.clear()
            with _Sorteo(app, alims, feeders, existentes) as s:
                for i, (sorteo, sin_i) in enumerate(zip(sorteos[desde:hasta], sin_sorteos[desde:hasta]), desde):
                    if i % 10 == 0 and cancelado():          # una variante puede llevar minutos
                        informe['cancelado'] = True
                        return None
                    s.escalar(sorteo['factores'])
                    bien, motivos = cumple(sin_i, medida_para_criterio(app, alims, feeders, ligera=True), barras, p)
                    if not bien:
                        fallidos.append({'instante': sorteo.get('instante'), 'factores': sorteo.get('factores'),
                                         'motivos': list(motivos)[:3]})
                    if seg.anota(bien):
                        break
            certeza.clear()
            certeza.update(seg.resumen())                                    # 087:RF-9
            if seg.bayesiana:
                return seg.fraccion()
            fallos = seg.fallan
            if fallos > admite:
                # En la primera etapa, sobre lo medido: con más fallos de los que caben no hay que seguir.
                return (len(sorteos) - fallos) / len(sorteos) if hasta == len(sorteos) else seg.cumplen / seg.medidos
            return (hasta - fallos) / hasta

        def por_etapas(v=None):
            """042:RF-87: la primera etapa y, si queda cerca del criterio, el resto; ``(fracción, error, medidos)``.
            Con la parada bayesiana (087:RF-8), el resto solo si la posterior aún no ha decidido."""
            medir = (lambda f: con_variante(v, f)) if v is not None else (lambda f: (f(), None))
            n = len(sorteos)
            fraccion, error = medir(lambda: sortear(0, en_primera))
            decidida = bool(certeza.get('parada')) if plan.get('parada_bayesiana') else False
            if error or fraccion is None or decidida or not hace_falta_seguir(fraccion, en_primera, n, p):
                return fraccion, error, certeza.get('sorteos_usados') or en_primera
            fallos = round((1 - fraccion) * en_primera)
            casos['sin'].Activate()
            listo = referencia_hasta(n)
            casos['con'].Activate()
            if not listo:
                return None, None, en_primera
            fraccion, error = medir(lambda: sortear(en_primera, n, fallos))
            return fraccion, error, certeza.get('sorteos_usados') or n

        def de_cada_alimentador() -> dict[str, set[str]]:
            """Los nombres de barras y tramos de cada alimentador, para saber a quién culpar de un motivo."""
            out: dict[str, set[str]] = {}
            for f in feeders:
                elm = alims.elm.get(f)
                try:
                    objs = list(elm.GetObjs('ElmTerm')) + list(elm.GetObjs('ElmLne')) if elm is not None else []
                except Exception:  # noqa: BLE001 - sin el alimentador, sin nombres
                    objs = []
                out[f] = {o.loc_name for o in objs}
            return out

        def confirmar_conjunto(con: dict[str, Any]) -> dict[str, Any]:
            """087:RF-45, RF-46: el sistema entero con todas sus obras y sus cargas nuevas, en un solo flujo por instante.

            Pisco (2026-11-04, el usuario): «¿por qué DIgSILENT corre alimentador por alimentador y no todo el sistema?».
            Cada escalón se elige con los otros apartados (025:RF-69); juntos pueden pesar en la SET o el vecino que
            comparten. Aquí se mide todo junto y se dice de qué alimentadores son los motivos.
            """
            bien, motivos = cumple(sin_max, con, barras, p)
            fila: dict[str, Any] = {'maxima': bien, 'motivos': list(motivos), 'fraccion': None, 'perdidas_kw': con.get('perdidas_kw'),
                                    'aisladas': sorted(set(con.get('aisladas') or []) - set(sin_max.get('aisladas') or [])),
                                    'bajo_limite': bajas(con)}
            textos = list(motivos)
            # Todos los motivos de cada alimentador, no solo los 5 primeros: con sus barras y tramos.
            nombres = de_cada_alimentador()
            por_alimentador: dict[str, list[str]] = {}
            for f, propios in nombres.items():
                sin_f = {**sin_max, 'u': {b: x for b, x in (sin_max.get('u') or {}).items() if b in propios},
                         'carga': {e: x for e, x in (sin_max.get('carga') or {}).items() if e in propios}}
                con_f = {**con, 'u': {b: x for b, x in (con.get('u') or {}).items() if b in propios},
                         'carga': {e: x for e, x in (con.get('carga') or {}).items() if e in propios}}
                ok_f, motivos_f = cumple(sin_f, con_f, [b for b in barras if b in propios], p)
                if not ok_f:
                    por_alimentador[f] = list(motivos_f)
            if bien and sorteos:
                fila['fraccion'], error, fila['sorteos_medidos'] = por_etapas()
                fila['error'] = error
                fila['certeza'] = dict(certeza)
                textos += [m for x in fallidos for m in x.get('motivos') or []]
            if bien and puntos_valle:
                fila.update(medir_valle())
                textos += list(fila.get('valle_motivos') or [])
            for f, propios in nombres.items():
                if f not in por_alimentador and any(n in t for t in textos[len(motivos):] for n in propios if len(n) > 3):
                    por_alimentador[f] = [t for t in textos[len(motivos):] if any(n in t for n in propios if len(n) > 3)][:5]
            fila['cumple'] = bool(bien and (fila['fraccion'] is None or fila['fraccion'] >= p.cumplimiento)
                                  and fila.get('valle') is not False)
            fila['por_alimentador'] = por_alimentador
            return fila

        # RF-74: con lo que ya tiene «Con proyecto» (una obra de una escalera anterior), si
        # cumple no se prueba ninguna variante.
        casos['con'].Activate()
        con_actual = medida_para_criterio(app, alims, feeders)
        if plan.get('solo_confirmar'):
            informe['conjunto'] = confirmar_conjunto(con_actual)                 # 087:RF-45
            return informe, 0
        # 087:RF-44: al aplicar la obra ya elegida no hay sorteos (042:RF-59) y sin ellos «ya cumple» con la máxima
        # salía al 100 %: CHI201 (Pisco, 2026-11-04) se dio por resuelto con su sección elegida y sin aplicarla.
        if not plan.get('aplicando_elegida') and cumple(sin_max, con_actual, barras, p)[0]:
            fraccion = por_etapas()[0] if sorteos else 1.0
            if fraccion is None:
                return informe, 2
            if fraccion >= p.cumplimiento:
                informe['ya_cumple'] = {'fraccion': fraccion, 'perdidas_kw': con_actual['perdidas_kw'],
                                        'bajo_limite': bajas(con_actual)}              # 086:RF-48
                if puntos_valle:                                                       # 073:RF-26
                    informe['ya_cumple'].update(medir_valle())
                print(f'  «Con proyecto» ya cumple: sorteos {100 * fraccion:.0f} %', flush=True)
                return informe, 0

        # Fase 1: todas con la máxima (RF-52b); con eso ya se sabe su costo anual entero.
        variantes = list(plan.get('variantes') or [])
        filas = []
        clases_que_cumplen: set = set()                                     # 042:RF-55
        primera_que_cumple = None                                           # 042:RF-90
        # 042:RF-91: los años los pone el perfil aquí: el plan solo trae la tasa.
        horizonte = plan.get('horizonte')
        if horizonte and feeders:
            horizonte = plan_de_horizonte(feeders[0], horizonte.get('tasa'), p)
        hay_definitiva = False

        def alcance():
            primeros: list[str] = []
            with _Sorteo(app, alims, feeders, existentes) as s:
                for anios in horizonte['anios']:
                    s.escalar(horizonte['factores'][str(anios)])
                    bien, motivos = definitiva(medida_para_criterio(app, alims, feeders, ligera=True), p)
                    if bien:
                        return {'definitiva': anios == horizonte['anios'][0], 'aguanta_anios': anios, 'motivos': primeros,
                                'mas_corto': min(horizonte['anios']), 'probados': sorted(horizonte['anios'])}
                    primeros = primeros or list(motivos)
            # 098:RF-35: 0 es medido y sin llegar ni al horizonte más corto; sin medir, la fila no lleva horizonte.
            return {'definitiva': False, 'aguanta_anios': 0, 'motivos': primeros, 'mas_corto': min(horizonte['anios']),
                    'probados': sorted(horizonte['anios'])}

        medidas_sin_regulador: dict[str, tuple[str, dict]] = {}                       # 098:RF-34
        # 098:RF-32: las ya medidas con la misma huella (la web las da): no se miden, pero cuentan para parar.
        conocidas = {str(x.get('nombre')): x for x in plan.get('ya_medidas') or [] if x.get('nombre')}
        for v in variantes:
            if cancelado():
                informe['cancelado'] = True
                break
            if primera_que_cumple is not None and len(filas) - primera_que_cumple >= p.variantes_tras_cumplir:
                informe['avisos'].append(f'Se paró tras {p.variantes_tras_cumplir} variantes más desde la primera que '
                                         f'cumple, con {len(clases_que_cumplen)} alternativa(s) (042:RF-90).')
                break
            if v['nombre'] in conocidas:
                fila = {**conocidas[v['nombre']], 'reutilizada': True}
                filas.append((v, fila))
                print(f"  {v['nombre']}: ya medida con la misma red (098:RF-32)", flush=True)
                cumple_aqui = bool(fila.get('maxima')) and v.get('costo_base') is not None and fila.get('valle') is not False
                if plan.get('alternativas') and cumple_aqui:                            # 042:RF-55
                    primera_que_cumple = len(filas) if primera_que_cumple is None else primera_que_cumple
                    if horizonte and not fila.get('horizonte'):                     # 098:RF-37
                        fila['horizonte'], error = con_variante(v, alcance)
                        fila['error'] = fila['error'] or error
                    hay_definitiva = hay_definitiva or bool((fila.get('horizonte') or {}).get('definitiva'))
                    clases_que_cumplen.add(frozenset(v.get('escalones') or ()))
                    if len(clases_que_cumplen) >= int(plan['alternativas']) and (hay_definitiva or not horizonte):
                        break
                elif plan.get('basta_una') and cumple_aqui and (fila.get('fraccion') or 0) >= p.cumplimiento:   # 073:RF-18
                    informe['basta_una'] = fila['nombre']
                    break
                continue
            fila = {'nombre': v['nombre'], 'maxima': False, 'motivos': [], 'fraccion': None,
                    'perdidas_kw': None, 'error': None, 'sin_sortear': None}
            def medir_todo():
                # 073:RF-30: con la obra ya creada, también en valle: crearla otra vez cuesta minutos.
                con = medida_para_criterio(app, alims, feeders)
                return con, (medir_valle() if puntos_valle and con.get('converge') else None)

            medido, fila['error'] = con_variante(v, medir_todo)
            con_max, en_valle = medido if medido is not None else (None, None)
            if fila['error'] and fila['error'].startswith(NO_APLICADA):
                fila['no_aplicada'] = fila['error']                                     # 098:RF-28
            elif con_max is not None and (base := medidas_sin_regulador.get(_sin_regulador(v))) is not None \
                    and _sin_regulador(v) != _clave_obras(v['obras']) and sin_cambio(base[1], con_max):
                # 098:RF-34: el regulador no cambia nada: sin él la variante es otra que ya se midió.
                fila['no_aplicada'] = fila['error'] = (f'{NO_APLICADA}: el regulador no cambia ninguna tensión ni corriente '
                                                       f'respecto de «{base[0]}»')
                con_max, en_valle = None, None
            elif con_max is not None and sin_cambio(con_actual, con_max):
                # 098:RF-28: ni una tensión ni una corriente cambió: la variante no se aplicó donde se mide.
                fila['no_aplicada'] = fila['error'] = (f'{NO_APLICADA}: con ella no cambia ninguna tensión ni corriente '
                                                       f"de «{NOMBRES['con']}» respecto de sin obra")
                con_max, en_valle = None, None
            if con_max is not None:
                medidas_sin_regulador.setdefault(_clave_obras(v['obras']), (v['nombre'], con_max))
            fila.update(en_valle or {})
            mejora = ''
            if con_max is not None:
                fila['perdidas_kw'] = con_max['perdidas_kw']
                fila['maxima'], fila['motivos'] = cumple(sin_max, con_max, barras, p)
                # 063:RF-28: cuánto deja cada escalón, también cuando no basta: la tensión de cada
                # barra de carga nueva y la mínima de media (SM218: «primero debiste probar con
                # bancos, ver cuánto mejora»).
                u = con_max.get('u') or {}
                fila['u_cargas'] = {b: u.get(b) for b in barras}
                fila['u_min_mt'] = min(u.values()) if u else None
                fila['bajo_limite'] = bajas(con_max)                                   # 086:RF-48
                cargas_max = [float(c) for c in (con_max.get('carga') or {}).values() if c is not None]
                fila['carga_max_pct'] = max(cargas_max) if cargas_max else None      # 087:RF-22
                partes = [f'{b} a {x:.3f} p.u.' for b, x in fila['u_cargas'].items() if x is not None]
                if fila['u_min_mt'] is not None:
                    partes.append(f"mínima de media {fila['u_min_mt']:.3f} p.u.")
                mejora = f" ({'; '.join(partes)})" if partes else ''
            print(f"  {v['nombre']}: " + (fila['no_aplicada'] if fila.get('no_aplicada') else
                                          f"máxima {'cumple' if fila['maxima'] else 'no cumple'}{mejora}"), flush=True)
            filas.append((v, fila))
            # 042:RF-2: para saber si las cargas caben basta una variante con costo que cumpla;
            # la más barata solo hace falta al aplicar. Se sortea en cuanto cumple la máxima y,
            # si también cumple en los sorteos, no se prueba ninguna más (NA203 + NA205,
            # 2026-11-01: cada prueba recorría las 20 y las 40 variantes, unos 60 min).
            if (plan.get('alternativas') and fila['maxima'] and v.get('costo_base') is not None
                    and fila.get('valle') is not False):                                # 042:RF-55
                clase = frozenset(v.get('escalones') or ())
                primera_que_cumple = len(filas) if primera_que_cumple is None else primera_que_cumple
                # 098:RF-37: el alcance de cada una que cumple, no solo de la primera de su clase: la de largo plazo es
                # la más barata que aguanta el horizonte, y sin medirlas no se sabe cuál es.
                if horizonte:                                                  # 042:RF-92
                    fila['horizonte'], error = con_variante(v, alcance)
                    fila['error'] = fila['error'] or error
                    hay_definitiva = hay_definitiva or bool((fila['horizonte'] or {}).get('definitiva'))
                    print(f"  {v['nombre']}: alcance {fila['horizonte']}", flush=True)
                clases_que_cumplen.add(clase)
                if len(clases_que_cumplen) >= int(plan['alternativas']) and (hay_definitiva or not horizonte):
                    break
            elif (plan.get('basta_una') and fila['maxima'] and v.get('costo_base') is not None
                    and fila.get('valle') is not False):                                # 073:RF-18
                if sorteos:
                    fila['fraccion'], error, fila['sorteos_medidos'] = por_etapas(v)         # 042:RF-88
                    fila['error'] = fila['error'] or error
                    fila['sorteos_fallidos'] = list(fallidos)
                    fila['certeza'] = dict(certeza)
                else:
                    fila['fraccion'] = 1.0
                print(f"  {v['nombre']}: sorteos {100 * (fila['fraccion'] or 0):.0f} %", flush=True)
                if (fila['fraccion'] or 0) >= p.cumplimiento:
                    informe['basta_una'] = fila['nombre']
                    break
        if informe.get('basta_una') or (plan.get('basta_una') and not plan.get('alternativas')):
            informe['variantes'] = [f for _v, f in filas]
            return informe, 0
        # Fase 2 (RF-71): de la más barata a la más cara, hasta la primera que cumple en los sorteos.
        k = float(plan.get('costo_por_kw_perdido') or 0.0)

        def costo(v, fila):
            return float(v['costo_base']) + k * float(fila['perdidas_kw'] or 0.0)

        candidatas = sorted(((v, f) for v, f in filas if f['maxima'] and v.get('costo_base') is not None
                             and f.get('valle') is not False),
                            key=lambda vf: (grupo_economico(vf[0].get('escalones')), costo(*vf), vf[1]['nombre']))   # 042:RF-56
        for v, fila in filas:
            if fila['maxima'] and v.get('costo_base') is None:
                fila['sin_sortear'] = 'sin costo: no se puede elegir, no se sortea'
            elif fila['maxima'] and fila.get('valle') is False:                        # 073:RF-18
                fila['sin_sortear'] = 'no cumple en valle: los sorteos no lo compensan, no se sortea'
        ganadora = None
        for v, fila in candidatas:
            if informe['cancelado'] or cancelado():
                informe['cancelado'] = True
                break
            if ganadora is not None:
                fila['sin_sortear'] = f"no se sortea: «{ganadora}» cuesta menos y ya cumple"
                continue
            if fila.get('reutilizada') and fila.get('fraccion') is not None:
                pass                                       # 098:RF-32: sus sorteos ya se hicieron con la misma red
            elif not sorteos:
                fila['fraccion'] = 1.0
            else:
                fila['fraccion'], error, fila['sorteos_medidos'] = por_etapas(v)             # 042:RF-88
                fila['error'] = fila['error'] or error
                fila['sorteos_fallidos'] = list(fallidos)                     # 063:RF-28
            print(f"  {v['nombre']}: sorteos {100 * (fila['fraccion'] or 0):.0f} %", flush=True)
            if (fila['fraccion'] or 0) >= p.cumplimiento:
                ganadora = fila['nombre']
        informe['tiempos_medida'] = TIEMPOS                                     # 042:RF-89
        if horizonte and not hay_definitiva and clases_que_cumplen:
            informe['avisos'].append('Ninguna alternativa es definitiva a la vida útil dentro del tope de variantes (042:RF-92).')
        informe['variantes'] = [f for _v, f in filas]
        print(f"  Tiempos de las medidas ligeras: {TIEMPOS['flujos']} flujos, {TIEMPOS['flujo_s']:.1f} s de flujo y "
              f"{TIEMPOS['lectura_s']:.1f} s de lectura (042:RF-89).", flush=True)
    finally:
        if ajenas:
            casos['con'].Activate()
            for v in ajenas:
                v.Activate()
        if diario_apartadas:
            _quitar_diario(plan, 'apartada', diario_apartadas)
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    return informe, 0


def _media_de(barra):
    """La barra de media de una barra de baja: la de alta de su transformador; si ya es de media
    o no tiene transformador, ella misma."""
    if barra is None or float(getattr(barra, 'uknom', 0) or 0) >= 1.0:
        return barra
    for e in barra.GetConnectedElements():
        if e.GetClassName() == 'ElmTr2':
            alta = getattr(getattr(e, 'bushv', None), 'cterm', None)
            if alta is not None and alta is not barra:
                return alta
    return barra


def _barra_de_media(carga):
    """La barra de media de la SED de una carga."""
    return _media_de(getattr(getattr(carga, 'bus1', None), 'cterm', None))


def datos_set_nueva(app, plan: dict) -> tuple[dict, int]:
    """La red de cada alimentador en «Con proyecto <año>» para la SET nueva (042:RF-6, RF-7, RF-9).

    Cabecera y tensión, barras con su GPS, tramos con su largo y si están cerrados, y cada carga
    con su barra de media y lo que consume (lo escrito por su factor de escala, 015:RF-44). Con
    las cargas nuevas activas: sus barras son las que pasan a la SET nueva. No cambia nada.
    """
    from ajuste_cabecera_pf import potencia_efectiva

    informe: dict[str, Any] = {'project': plan.get('project'), 'modo': 'datos_set_nueva',
                               'alimentadores': {}, 'avisos': []}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    anio = anio_del_plan(plan)
    casos = casos_del_proyecto(app, anio)
    if 'con' not in casos:
        return {**informe, 'error': f"falta «{nombre_caso('con', anio)}»"}, 2
    feeders = list(plan.get('feeders') or [])
    alims = Alimentadores(app, proyecto, feeders)
    inicial = app.GetActiveStudyCase()
    try:
        casos['con'].Activate()
        # 042:RF-15: las barras de la red sin las cargas nuevas, que es como la obra lee y graba;
        # la rama que pasa a la SET nueva se abre en una de ellas.
        existentes: dict[str, list[str]] = {}
        apartadas = _apartar_cargas_nuevas(app)
        try:
            flujo_de_carga(app)
            for f in feeders:
                elm = alims.elm.get(f)
                if elm is not None:
                    existentes[f] = sorted({b.loc_name for b in elm.GetObjs('ElmTerm')})
        finally:
            for v in apartadas:
                v.Activate()
        flujo_de_carga(app)              # el ElmFeeder da sus objetos según la última topología
        for f in feeders:
            elm = alims.elm.get(f)
            cabecera = cabecera_de(elm) if elm is not None else None
            if cabecera is None:
                informe['avisos'].append(f'{f}: no está en el proyecto o no dice su cabecera.')
                continue
            red = leer_red(elm, cabecera)
            cargas = []
            for c in elm.GetObjs('ElmLod'):
                barra = _barra_de_media(c)
                if barra is None or int(getattr(c, 'outserv', 0) or 0):
                    continue
                p, q = potencia_efectiva(c)
                cargas.append({'nombre': c.loc_name, 'barra': barra.loc_name, 'kw': p, 'kvar': q})
            # 042: las cargas que pasan a la SET nueva son justo las que la escalera apartó, así
            # que en «Con proyecto» no están activas y no se encuentran por su nombre: se llega a
            # su barra de media desde la barra que dio la escalera (NA203 + NA205, 2026-10-31:
            # 29 de 32 quedaban fuera de la SET nueva con «no está activa»).
            terminales = {b.loc_name: b for b in app.GetCalcRelevantObjects('*.ElmTerm')}
            media = {}
            for nombre in (plan.get('barras') or {}).get(f, []):
                m = _media_de(terminales.get(nombre))
                if m is not None:
                    media[nombre] = m.loc_name
            informe['alimentadores'][f] = {
                'media': media, 'existentes': existentes.get(f),
                'cabecera': cabecera.loc_name, 'kv': float(getattr(cabecera, 'uknom', 0) or 0),
                'barras': [{'nombre': b.nombre, 'kv': b.kv, 'gps': list(b.gps) if b.gps else None}
                           for b in red.barras.values()],
                'tramos': [{'nombre': t.nombre, 'desde': t.desde, 'hasta': t.hasta, 'largo_m': t.largo_m,
                            'cerrado': t.cerrado,
                            # 084:RF-1: el trazado real, no la recta entre barras.
                            **({'puntos': [list(q) for q in t.trazado]} if t.trazado else {})}
                           for t in red.tramos],
                'cargas': cargas}
    finally:
        if inicial is not None:
            inicial.Activate()
    return informe, 0


def _gps_por_la_red(barra, con_gps: dict, max_barras: int = 500) -> tuple[Any, str | None]:
    """098:RF-20: las coordenadas de la barra con GPS más cercana a ``barra`` por la red, en número de ramas, y su
    nombre; ``(None, None)`` si no hay ninguna a ``max_barras`` barras. Solo lee."""
    if barra is None:
        return None, None
    vistas, frente = {barra.loc_name}, [barra]
    while frente and len(vistas) <= max_barras:
        siguiente = []
        for t in frente:
            for e in t.GetConnectedElements() or []:
                for c in ('bus1', 'bus2', 'bushv', 'buslv'):
                    o = getattr(getattr(e, c, None), 'cterm', None)
                    if o is None or o.loc_name in vistas:
                        continue
                    vistas.add(o.loc_name)
                    g = con_gps.get(o.loc_name) or gps_de(o)
                    if g:
                        return g, o.loc_name
                    siguiente.append(o)
        frente = siguiente
    return None, None


def datos_vecinos(app, plan: dict) -> tuple[dict, int]:
    """087:RF-32, RF-33: los alimentadores vecinos de cada nodo, con su margen en «Con proyecto <año>».

    De cada otro ``ElmFeeder`` del proyecto: su barra de media más cercana al nodo, la distancia en recta, su tensión,
    su tensión mínima y su carga máxima con el flujo de ahora. Solo los que quedan a menos de ``radio_km`` (15 si el
    plan no lo da): uno más lejos no es una transferencia sino un alimentador nuevo. No cambia nada.
    """
    informe: dict[str, Any] = {'project': plan.get('project'), 'modo': 'datos_vecinos', 'vecinos': {}, 'avisos': []}
    proyecto = activar_proyecto(app, plan['project'], plan.get('folder'))
    if proyecto is None:
        return {**informe, 'error': f"no existe el proyecto {plan['project']!r} en DIgSILENT"}, 2
    anio = anio_del_plan(plan)
    casos = casos_del_proyecto(app, anio)
    if 'con' not in casos:
        return {**informe, 'error': f"falta «{nombre_caso('con', anio)}»"}, 2
    radio_m = float(plan.get('radio_km') or 15.0) * 1000.0
    inicial = app.GetActiveStudyCase()
    try:
        casos['con'].Activate()
        flujo = flujo_de_carga(app)
        if not flujo['converged']:
            informe['avisos'].append('El flujo de «Con proyecto» no converge: sin margen de los vecinos (087:RF-32).')
        todos = {f.loc_name: f for f in app.GetCalcRelevantObjects('*.ElmFeeder')}
        # Una pasada por alimentador, no una por nodo: sus barras de media con GPS, tensión y resultado.
        resumen: dict[str, dict[str, Any]] = {}
        for nombre, elm in todos.items():
            barras = [b for b in elm.GetObjs('ElmTerm') if float(getattr(b, 'uknom', 0) or 0) > 1.0]
            u = [b.GetAttribute('m:u') for b in barras if flujo['converged'] and b.HasResults(0)]
            carga = [ln.GetAttribute('c:loading') for ln in elm.GetObjs('ElmLne') if flujo['converged'] and ln.HasResults(0)]
            cabecera = cabecera_de(elm)
            resumen[nombre] = {'gps': [(b.loc_name, g) for b in barras for g in [gps_de(b)] if g],
                               'kv': float(getattr(cabecera, 'uknom', 0) or 0) if cabecera is not None else None,
                               'u_min': min(u) if u else None, 'carga_max_pct': max(carga) if carga else None}
        for f, nodos in (plan.get('nodos') or {}).items():
            propio = dict((resumen.get(f) or {}).get('gps', []))
            barras_f = {b.loc_name: b for b in todos[f].GetObjs('ElmTerm')} if f in todos else {}
            for nodo in nodos:
                punto = propio.get(nodo)
                if punto is None:
                    # 098:RF-20: sin GPS propio, el de la barra con GPS más cercana por la red. CA101 + CHN102
                    # (2026-11-07): 12333, 11969 y la barra nueva de CH_10 no tenían coordenadas, la búsqueda de vecinos
                    # salía vacía y la escalera daba la transferencia por imposible sin haberla probado.
                    punto, desde = _gps_por_la_red(barras_f.get(nodo), propio)
                    if punto is None:
                        informe['avisos'].append(f'{f}: la barra {nodo} no tiene coordenadas ni las tiene ninguna barra '
                                                 'cercana por la red: sin vecinos para ella (087:RF-32, 098:RF-20).')
                        continue
                    informe['avisos'].append(f'{f}: la barra {nodo} no tiene coordenadas: se toman las de {desde}, la '
                                             'más cercana por la red (098:RF-20).')
                filas = []
                for nombre, r in resumen.items():
                    if nombre == f or not r['gps']:
                        continue
                    barra, g = min(r['gps'], key=lambda par: distancia_m(tuple(punto), tuple(par[1])))
                    d = distancia_m(tuple(punto), tuple(g))
                    if d <= radio_m:
                        filas.append({'alimentador': nombre, 'barra': barra, 'distancia_m': round(d, 1), 'kv': r['kv'],
                                      'u_min': r['u_min'], 'carga_max_pct': r['carga_max_pct']})
                informe['vecinos'].setdefault(f, {})[nodo] = sorted(filas, key=lambda x: x['distancia_m'])
    finally:
        if inicial is not None:
            inicial.Activate()
    return informe, 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Obras de mejora de la spec 011 en DIgSILENT')
    p.add_argument('--plan', required=True, help='Plan JSON preparado por la web')
    p.add_argument('--output-json', required=True, help='Dónde dejar el informe')
    p.add_argument('--bibliotecas', action='store_true',
                   help='Solo leer alimentadores y tipos de las bibliotecas para el formulario')
    p.add_argument('--simular', action='store_true',
                   help='Decir lo que haría cada obra sin escribir en el proyecto')
    p.add_argument('--cancel-file', help='Si este fichero aparece, para entre obras')
    p.add_argument('--tipos-regulador', action='store_true',
                   help='Crear los reguladores del catálogo en el proyecto biblioteca (025:RF-59)')
    p.add_argument('--evaluar', action='store_true',
                   help='Medir las variantes de la escalera con la máxima y los sorteos, sin dejarlas (025:RF-50)')
    p.add_argument('--retirar-obras', action='store_true',
                   help='borra las variaciones de obra de los alimentadores del plan (042:RF-60)')
    p.add_argument('--reponer-cargas', action='store_true',
                   help='Activa en «Con proyecto» las cargas nuevas del plan que estén desactivadas (042:RF-32)')
    p.add_argument('--escalera-datos', action='store_true',
                   help='Troncal, corrientes y tramo de cada carga nueva para la escalera (025:RF-49)')
    p.add_argument('--oraculo-datos', action='store_true',
                   help='Grafo de «Con proyecto» y nodo de cada carga nueva para el oráculo (052:RF-1)')
    p.add_argument('--set-nueva-datos', action='store_true',
                   help='Red y cargas de cada alimentador en «Con proyecto» para la SET nueva (042:RF-6)')
    p.add_argument('--vecinos', action='store_true',
                   help='Alimentadores vecinos de cada nodo y su margen, para transferir o trasladar (087:RF-32)')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    # Crear tipos de catálogo no toca ninguna red convertida: no lleva contexto de acción.
    blocked = None if args.tipos_regulador else native_action_block_report(plan, ('obras', 'obras_bibliotecas'))
    if blocked:
        Path(args.output_json).write_text(
            json.dumps(blocked, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(blocked['error'])
        return 2
    # 019:RF-1 a RF-6: turno del motor de la máquina, reintento con el motor ocupado y
    # primera línea al responder, comunes a todos los guiones.
    from convertersmartgrid.pf_arnes import PFNoDisponible, conectar

    try:
        app = conectar('obras_pf.py')
    except PFNoDisponible as exc:
        print(f'ERROR: {exc}')
        return 3

    def cancelado() -> bool:
        return bool(args.cancel_file) and Path(args.cancel_file).exists()

    try:
        if args.tipos_regulador:
            informe, codigo = crear_tipos_regulador(app, plan)
        elif args.evaluar:
            informe, codigo = evaluar(app, plan, cancelado=cancelado)
        elif args.reponer_cargas:
            informe, codigo = reponer_cargas(app, plan)
        elif args.retirar_obras:
            informe, codigo = retirar_obras(app, plan)
        elif args.escalera_datos:
            informe, codigo = datos_escalera(app, plan)
        elif args.oraculo_datos:
            informe, codigo = datos_oraculo(app, plan)
        elif args.set_nueva_datos:
            informe, codigo = datos_set_nueva(app, plan)
        elif args.vecinos:
            informe, codigo = datos_vecinos(app, plan)
        elif args.bibliotecas:
            informe, codigo = bibliotecas(app, plan)
        elif plan.get('sustituir') and not args.simular:
            informe, codigo = sustituir(app, plan)                                   # 098:RF-36
        else:
            informe, codigo = aplicar(app, plan, simular=args.simular, cancelado=cancelado)
    except Exception as exc:  # noqa: BLE001 - el informe dice el error en vez de perderse
        traceback.print_exc()
        informe, codigo = error_inesperado(plan, args.simular, exc), 1
    Path(args.output_json).write_text(
        json.dumps(informe, indent=2, ensure_ascii=False, default=str) + '\n', encoding='utf-8')
    print(f'Informe: {args.output_json}')
    return codigo


if __name__ == '__main__':
    raise SystemExit(main())
