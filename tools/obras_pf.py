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
   ``igea_dgs.obras_pf.plan_simulacion``: lo que se aplica es lo que se simuló. Cada
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
import math
import re
import traceback
from pathlib import Path
from typing import Any, Callable

from ajuste_cabecera_pf import diagnostico
from cargas_pf import (
    Alimentadores, activar_proyecto, cabecera_de, clave_pf, crear_variacion, error_inesperado, es_cable,
    completar_diagrama, distancia_m, flujo_de_carga, gps_de, leer_cabecera, leer_red, medir_estado,
    nombre_libre, nombre_pf, partir_tramo,
)
from casos_pf import (
    NOMBRES, anio_del_plan, casos_del_proyecto, crear_con_proyecto, es_de_carga_nueva,
    nombre_caso, sin_a_con_proyecto,
)
from estudios_pf import medida

from igea_dgs.carpeta_pf import buscar_proyecto, nombre_de_perfil
from igea_dgs.perfil_empresa import datos_perfil
from igea_dgs.vias import ruta_por_vias
from igea_dgs.native_action import native_action_block_report
from igea_dgs.obras_pf import (
    ATRIBUTOS_TIPO, BANDA_TENSION_PU, SOLO_CON_PROYECTO, Obra, ObrasError, RedAlimentador, Tipo,
    diferencias_sin_proyecto, mismos_datos, plan_simulacion, red_de_lectura, resolver_copia,
    resumen_tipo, tipo_de_ficha, validar_obra,
)
from igea_dgs.estudios_pf import EstudiosError, limites_de_perfil
from igea_dgs.naming import feeder_short_name
from igea_dgs.obras_pf import nombre_copia, punto_indicado
from igea_dgs.troncal import (Conexion, TroncalError, aguas_abajo, extremos_del_enlace,
                              punto_en_troncal)
from igea_dgs.troncal import troncal as troncal_de

#: Las clases de tipo que piden las obras (RF-89), en el orden en que se listan.
CLASES_TIPO = tuple(ATRIBUTOS_TIPO)


# =========================================================================== tipos
def _proyecto_de(obj):
    """El ``IntPrj`` que contiene el objeto, o None si está fuera de todo proyecto."""
    actual = obj
    while actual is not None:
        if actual.GetClassName() == 'IntPrj':
            return actual
        actual = actual.GetParent()
    return None


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


def leer_tipos(app, clases, otro=None) -> list[dict]:
    """Los tipos de las tres bibliotecas, ordenados por clase, origen y nombre."""
    out = []
    origenes = [('proyecto', '', lambda c: app.GetLocalLibrary(c)),
                ('global', '', lambda c: app.GetGlobalLibrary(c))]
    if otro is not None:
        lib = biblioteca_de_otro(otro)
        origenes.append(('otro', otro.loc_name, lambda _c: lib))
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
        'condensadores': [{'nombre': o.loc_name, 'kv': getattr(o, 'ushnm', None)}
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
    informe['tipos'] = leer_tipos(app, clases, otro)
    return informe, 0


#: Proyecto de DIgSILENT, en la carpeta del usuario, con los tipos de catálogo (025:RF-59).
#: La biblioteca global no deja escribir al usuario (sonda del 2026-10-24: ``CreateObject``
#: en ``\Lib`` y sus carpetas devuelve nada); las obras lo leen como «otro proyecto».
BIBLIOTECA_TIPOS = 'IGEA_Biblioteca_tipos'


def _proyecto_biblioteca(app, nombre: str, avisos: list[str]):
    """El proyecto biblioteca y su carpeta de tipos; se crean si faltan."""
    usuario = app.GetCurrentUser()
    proyecto = next((p for p in usuario.GetContents('*.IntPrj') or [] if p.loc_name == nombre), None)
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


def crear_tipos_regulador(app, plan: dict) -> tuple[dict, int]:
    """Los ``TypVoltreg`` del catálogo para cada tensión del plan, en el proyecto biblioteca
    (025:RF-59). Los que ya existen con ese nombre no se tocan ni se duplican."""
    from igea_dgs.catalogo_reguladores import CatalogoError, FABRICANTE, unidades_para

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
            for otra, _ in extremos.get(clave_pf(getattr(cub, 'obj_id', None)), []):
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


def construir_condensador(ctx) -> None:
    """Banco de condensadores en la barra, fijo o regulando por escalones (RF-71, RF-72)."""
    o = ctx.obra
    barra = ctx.objeto('ElmTerm', o.barra)
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
    banco.i_cont = 0                                       # escalones discretos
    if o.consigna_pu:                                      # RF-72
        banco.iswitch = 1
        banco.usetp_mn = o.consigna_pu - BANDA_TENSION_PU
        banco.usetp_mx = o.consigna_pu + BANDA_TENSION_PU
        _aviso_del_flujo(ctx, 'iopt_asht', 'los escalones de los condensadores')
    else:
        banco.iswitch = 0


def construir_reconectador(ctx) -> None:
    """Interruptor con protección y reenganche al principio del tramo, y su relé (RF-73).

    Lo que usan la confiabilidad y la ubicación de reconectadores de DIgSILENT son las
    marcas del interruptor (``rel_hasProt``, ``rel_hasRecl``; comprobado en DIgSILENT real
    con la spec 012). El relé lleva un bloque de reenganche ``RelRecl``, que es el que
    tiene tipo ``TypRecl``; los ajustes y curvas de protección quedan fuera (spec 011).
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
    rele = cub.CreateObject('ElmRelay', nombre_pf(f'Rele_{o.tramo}'))
    bloque = rele.CreateObject('RelRecl', 'Reenganche')
    if ctx.fila.get('tipo'):
        bloque.typ_id = ctx.tipo('TypRecl', ctx.fila['tipo'])


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
        raise RuntimeError(f'DIgSILENT no dejó pasar el cubículo del tramo {o.tramo} a la barra nueva')
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
    _aviso_del_flujo(ctx, 'iopt_at', 'las tomas')


def construir_seccion(ctx) -> None:
    """El tipo de línea de la obra en cada tramo que lista la fila (RF-77, RF-78).

    Los tramos y el tipo (copiado a la tensión del alimentador si hacía falta, RF-79) los
    decidió la simulación; los que ya lo tenían no están en la fila.
    """
    for e in ctx.fila['elementos']:
        # Con toda la troncal, los tramos de cable llevan su propio tipo (016:RF-7).
        ctx.objeto('ElmLne', e['elemento']).typ_id = ctx.tipo('TypLne', e.get('tipo') or ctx.fila['tipo'])


def construir_terna(ctx) -> None:
    """Una terna más en cada tramo de la fila, con el mismo tipo (RF-80).

    Se suma a lo que el tramo tiene en el caso donde se crea la obra, que ya incluye las
    obras anteriores activas allí (dos obras sobre el mismo tramo se suman, casos límite).
    """
    for e in ctx.fila['elementos']:
        linea = ctx.objeto('ElmLne', e['elemento'])
        linea.nlnum = int(getattr(linea, 'nlnum', 1) or 1) + 1


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


def construir_migracion(ctx) -> None:
    """Lo que queda aguas abajo del nodo, a la tensión de destino (016:RF-54 a RF-58).

    El caso es «Con proyecto» y la variación de la obra ya graba. La parte que pasa se
    vuelve a calcular aquí, con la red de ahora: un enlace de la misma tanda pudo partir un
    tramo de esa parte, y la mitad nueva no estaba en la simulación (IN111 cede a TA225 y
    el enlace llega a su troncal, 2026-10-15). Cambian las barras de media, los tipos de
    las líneas y de las SED (solo la alta) y se abre el tramo que entra al nodo; nada más
    del alimentador (RF-57).
    """
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
    for nombre in list(parte.tramos) + anillo:                                      # RF-56
        linea = lineas.get(nombre)
        if linea is None:
            continue                                     # un seccionador: no tiene tensión
        linea.typ_id = _tipo_a_tension(ctx, linea, 'TypLne', 'uline', origen, destino)
        if nombre not in planificados:
            nuevos.append(nombre)
    for trafo in ctx.elm.GetObjs('ElmTr2'):                                          # RF-54
        alta = getattr(getattr(getattr(trafo, 'bushv', None), 'cterm', None), 'loc_name', None)
        if alta in dentro:
            trafo.typ_id = _tipo_a_tension(ctx, trafo, 'TypTr2', 'utrn_h', origen, destino)
    entrada = parte.entrada                                                          # RF-58
    acopladores = {c.loc_name: c for c in ctx.elm.GetObjs('ElmCoup')}
    if entrada in lineas:
        lineas[entrada].outserv = 1
    elif entrada in acopladores:
        acopladores[entrada].on_off = 0
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
        if int(getattr(linea, 'outserv', 0)) and any(b is not None and b.loc_name in dentro
                                                     for b in barras)                 and all(b is not None and math.isclose(float(b.uknom), destino, rel_tol=1e-3)
                        for b in barras):
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
    otros = [s.loc_name for s in ctx.elm.GetObjs('ElmShnt') + ctx.elm.GetObjs('ElmVoltreg')
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


CONSTRUCTORES.update(condensador=construir_condensador, reconectador=construir_reconectador,
                     regulador=construir_regulador, seccion=construir_seccion,
                     terna=construir_terna, tension=construir_tension, enlace=construir_enlace,
                     migracion=construir_migracion, consigna=construir_consigna)

#: Obras que necesitan la troncal o la red: sin tramos indicados, la sección y la terna
#: van a la troncal (RF-77, RF-80); el enlace se apoya en las dos troncales y la migración
#: toma lo que queda aguas abajo de un nodo (spec 016).
CON_TRONCAL = ('seccion', 'terna', 'enlace', 'migracion')


def leer_troncal(elm, f: str) -> tuple[tuple[str, ...], object, str, list[str]]:
    """(troncal, red, cabecera, avisos) del alimentador en el caso activo (016:RF-1, RF-2).

    Es la troncal del camino más largo de ``igea_dgs.troncal``, no la de ``ComBbone``:
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
        for g in (o.alimentador, o.cede):
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
    tipos = [tipo_de_ficha(t) for t in leer_tipos(app, CLASES_TIPO, otro)]
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
                 redes=None) -> None:
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
    for rol in roles:                                                     # RF-66
        _flujo_con_la_obra(app, proyecto, casos, obra, fila, variacion, rol)


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
        fila.update(variacion='', error=f'no se pudo crear la obra: {exc}')
        return



def _flujo_con_la_obra(app, proyecto, casos, obra: Obra, fila: dict, variacion, rol: str) -> None:
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
    fila['avisos'].append(f'Con la obra, el flujo de «{nombre}» no converge: queda inactiva '
                          'en ese caso y se conserva en el proyecto.')


def _crear_con_proyecto(app, proyecto, casos, aplicadas, informe) -> None:
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
        _flujo_con_la_obra(app, proyecto, casos, obra, fila, variacion, 'con')


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

    feeders = sorted({o.alimentador for o in obras} | {o.cede for o in obras if o.cede}
                     | set(plan.get('feeders') or []))
    alims = Alimentadores(app, proyecto, feeders)
    inicial = app.GetActiveStudyCase()
    # 025:RF-69: la obra elegida por la escalera se comprueba con las cargas nuevas de los
    # alimentadores sin resolver apartadas, como se evaluó; vuelven al terminar.
    ajenas = []
    if 'con' in casos and plan.get('apartar_cargas_de'):
        casos['con'].Activate()
        ajenas = _apartar_cargas_de(app, list(plan['apartar_cargas_de']))
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
        evaluando = bool(plan.get('evaluando'))
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
                _crear_con_proyecto(app, proyecto, casos, [p for _, p in hechas], informe)
            if not fila['error']:
                _aplicar_una(app, plan, proyecto, casos, alims, obra, fila, redes[obra.alimentador],
                             redes)
            hechas.append((i, (obra, fila)))
        if 'con' not in casos and not informe['cancelado']:
            _crear_con_proyecto(app, proyecto, casos, [p for _, p in hechas], informe)
        informe['obras'] = [fila for _, (_, fila) in sorted(hechas, key=lambda h: h[0])]
        if antes['converged']:
            _comprobar_sin_proyecto(app, casos, alims, feeders, antes, informe)
        if 'con' in casos and not evaluando and any(f.get('variacion') for f in informe['obras']):
            # 016:RF-89: el enlace y las mitades de un tramo partido, en el diagrama; en
            # «Con proyecto», que tiene también las obras de «Sin proyecto».
            casos['con'].Activate()
            informe['dibujo'] = completar_diagrama(app, proyecto)
    finally:
        if ajenas:
            casos['con'].Activate()
            for v in ajenas:
                v.Activate()
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()

    fallos = any(f['error'] or not all(x['converge'] for x in f.get('flujo', {}).values())
                 for f in informe['obras'])
    diferencias = bool((informe['comprobacion'] or {}).get('diferencias'))
    return informe, 2 if fallos or diferencias or informe['cancelado'] else 0


# =========================================================================== escalera optimizada
def _resultado(obj, atributo: str) -> float | None:
    try:
        v = obj.GetAttribute(atributo)
    except Exception:  # noqa: BLE001 - sin resultado del flujo
        return None
    return float(v) if isinstance(v, (int, float)) and math.isfinite(float(v)) else None


def datos_escalera(app, plan: dict) -> tuple[dict, int]:
    """Lo que necesita armar las variantes de la escalera, en «Con proyecto <año>» (025:RF-49,
    RF-60): la troncal de cada alimentador desde la cabecera, leída sin las cargas nuevas
    (sobre esa red graban las obras), con el largo de cada tramo; su corriente y su tensión con
    todas las cargas; el primer tramo que queda bajo ``tension_min_pu``, y en qué tramo de la
    troncal cae cada barra de ``barras`` (por su posición GPS).
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
    ajenas: list = []
    try:
        casos['con'].Activate()
        # 025:RF-73: el estado de «Con proyecto» con el que se medirá; una evaluación anterior
        # solo se reutiliza si es el mismo.
        informe['variaciones_activas'] = sorted(v.loc_name for v in app.GetActiveNetworkVariations() or [])
        ajenas = _apartar_cargas_de(app, list(plan.get('apartar_cargas_de') or []))   # RF-69
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
        finally:
            for v in apartadas:
                v.Activate()
        flujo = flujo_de_carga(app)                                   # con todas las cargas
        informe['converge'] = bool(flujo['converged'])
        for f, troncal in troncales.items():
            elm = alims.elm[f]
            lineas = {ln.loc_name: ln for ln in elm.GetObjs('ElmLne')}
            barras = {b.loc_name: b for b in elm.GetObjs('ElmTerm')}
            corriente, fuera = None, None
            for i, (t, ext) in enumerate(zip(troncal, extremos[f])):
                ln = lineas.get(t['nombre'])
                c = _resultado(ln, 'm:I:bus1') if ln is not None and flujo['converged'] else None
                corriente = c * 1000 if c is not None else corriente  # partido por una carga: el anterior
                t['corriente_a'] = corriente
                us = [u for u in (_resultado(barras[b], 'm:u') for b in ext if b in barras) if u]
                if fuera is None and vmin and us and min(us) < vmin:
                    fuera = i
            puntos = posiciones[f]
            indices = {}
            for nombre in (plan.get('barras') or {}).get(f, []):
                barra = barras.get(nombre)
                g = gps_de(barra) if barra is not None else None
                candidatos = [(distancia_m(g, q), i) for i, ps in enumerate(puntos) for q in ps if q] if g else []
                if candidatos:
                    indices[nombre] = min(candidatos)[1]
                else:
                    informe['avisos'].append(f'{f}: la barra {nombre} no tiene posición GPS; sin tramo de '
                                             'la troncal para su terna o su sección.')
            informe['alimentadores'][f] = {'troncal': troncal, 'fuera_desde': fuera, 'indices': indices}
    finally:
        if ajenas:
            casos['con'].Activate()
            for v in ajenas:
                v.Activate()
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()
    return informe, 0


def medida_para_criterio(app, alims, feeders: list[str]) -> dict[str, Any]:
    """Lo que juzga ``escalera_optima.cumple``: si converge, la tensión de cada barra de media
    y la carga de cada tramo de los alimentadores, y sus pérdidas (025:RF-50, RF-53)."""
    flujo = flujo_de_carga(app)
    out: dict[str, Any] = {'converge': bool(flujo['converged']), 'u': {}, 'carga': {}, 'perdidas_kw': None}
    if not out['converge']:
        return out
    for f in feeders:
        for b in alims.objetos(f, 'ElmTerm'):
            try:
                if float(getattr(b, 'uknom', 0) or 0) >= 1.0 and b.HasResults():
                    out['u'][b.loc_name] = float(b.GetAttribute('m:u'))
            except Exception:  # noqa: BLE001, S110 - sin resultado, no cuenta
                pass
        for ln in alims.objetos(f, 'ElmLne'):
            try:
                out['carga'][ln.loc_name] = float(ln.GetAttribute('c:loading'))
            except Exception:  # noqa: BLE001, S110
                pass
    # 025:RF-70: lo que entra por la cabecera menos lo que consumen las cargas en el flujo; con
    # su potencia nominal, a 0,88 p.u. las pérdidas de SI213 salían −2044 kW (2026-10-24).
    perdidas = []
    for f in feeders:
        elm = alims.elm.get(f)
        cab = leer_cabecera(elm) if elm is not None else None
        if cab is None or not cab.converge or cab.kw is None:
            continue
        consumo = [_resultado(c, 'm:Psum:bus1') for c in elm.GetObjs('ElmLod') if not getattr(c, 'outserv', 0)]
        if any(x is None for x in consumo):
            continue
        perdidas.append(cab.kw - 1000 * sum(consumo))
    out['perdidas_kw'] = sum(perdidas) if perdidas else None
    return out


def _apartar_cargas_de(app, feeders: list[str]) -> list:
    """Desactiva en el caso activo las variaciones de cargas nuevas de ``feeders`` y las
    devuelve, para volver a activarlas (025:RF-69). Una carga es ``Carga_<SED>_<alim>_…``."""
    tokens = [f'_{nombre_pf(f)}_' for f in feeders]
    apartadas = [v for v in (app.GetActiveNetworkVariations() or [])
                 if es_de_carga_nueva(v) and any(t in v.loc_name[len('Carga_'):] for t in tokens)]
    for v in apartadas:
        v.Deactivate()
    return apartadas


class _Sorteo:
    """Escenario temporal, copia del del caso, donde se escalan las cargas existentes por el
    factor de su alimentador; se borra al salir y vuelve el escenario del caso (025:RF-51)."""

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
        nombre = nombre_libre(carpeta, 'IntScenario', 'IGEA_sorteo_escalera')
        self.temporal = carpeta.AddCopy(self.original, nombre)
        self.original.Deactivate(0)
        self.temporal.Activate()
        self.base = {}
        for f in self.feeders:
            for c in self.alims.objetos(f, 'ElmLod'):
                if c.loc_name in self.existentes:
                    self.base[id(c)] = (c, f, float(c.plini or 0.0), float(c.qlini or 0.0))
        return self

    def escalar(self, factores: dict[str, float]) -> None:
        for c, f, p, q in self.base.values():
            k = float(factores.get(f, 1.0))
            c.plini, c.qlini = p * k, q * k

    def __exit__(self, *exc):
        try:
            for c, _f, p, q in self.base.values():                  # todavía en el temporal
                c.plini, c.qlini = p, q
            self.temporal.Deactivate(0)
        finally:
            self.original.Activate()
            self.temporal.Delete()
        return False


def evaluar(app, plan: dict, *, cancelado=lambda: False) -> tuple[dict, int]:
    """Cada variante de la escalera en «Con proyecto <año>»: con la máxima y, si cumple, en los
    sorteos; sin dejar ninguna obra ni el escenario temporal (025:RF-50 a RF-52b, RF-44b).

    ``plan``: ``project``, ``anio_casos``, ``feeders``, ``variantes`` (``nombre`` y ``obras``),
    ``barras_cargas`` (las barras de media de las cargas nuevas), ``sorteos`` (``factores``
    por alimentador) y ``parametros`` (el perfil con ``escalera``, ``planificacion`` y
    ``estudios``). Devuelve por variante si cumple con la máxima, la fracción de sorteos que
    cumplen y sus pérdidas con la máxima.
    """
    from igea_dgs.escalera_optima import cumple, parametros

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
    alims = Alimentadores(app, proyecto, feeders)
    barras = list(plan.get('barras_cargas') or [])
    sorteos = list(plan.get('sorteos') or [])
    inicial = app.GetActiveStudyCase()
    casos['con'].Activate()
    ajenas = _apartar_cargas_de(app, list(plan.get('apartar_cargas_de') or []))         # RF-69
    try:
        # «Sin proyecto» con la máxima y con cada sorteo, una sola vez (RF-50).
        casos['sin'].Activate()
        existentes = {c.loc_name for f in feeders for c in alims.objetos(f, 'ElmLod')}
        sin_max = medida_para_criterio(app, alims, feeders)
        informe['sin_proyecto'] = {'converge': sin_max['converge'], 'perdidas_kw': sin_max['perdidas_kw']}
        sin_sorteos = []
        with _Sorteo(app, alims, feeders, existentes) as s:
            for i, sorteo in enumerate(sorteos):
                if i % 10 == 0 and cancelado():
                    informe['cancelado'] = True
                    return informe, 2
                s.escalar(sorteo['factores'])
                sin_sorteos.append(medida_para_criterio(app, alims, feeders))
        def con_variante(v, medir):
            """Crea las obras de ``v``, mide con ``medir()`` y las borra (RF-54); ``None`` y el
            error si no se pudieron crear."""
            hecho, _rc = aplicar(app, {**plan, 'obras': v['obras'], 'evaluando': True})
            creadas = [o['variacion'] for o in hecho.get('obras') or [] if o.get('variacion')]
            errores = [o['error'] for o in hecho.get('obras') or [] if o.get('error')] + (
                [hecho['error']] if hecho.get('error') else [])
            try:
                if errores:
                    return None, '; '.join(errores)
                casos['con'].Activate()
                return medir(), None
            finally:
                carpeta = app.GetProjectFolder('scheme')
                por_nombre = {x.loc_name: x for x in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])}
                for n in creadas:
                    var = por_nombre.get(n)
                    if var is not None:
                        for rol in ('sin', 'con'):
                            casos[rol].Activate()
                            var.Deactivate()
                        var.Delete()

        def sortear():
            """Fracción de sorteos que cumplen; deja de sortear en cuanto ya no puede llegar a la
            del perfil (RF-72)."""
            admite = int((1 - p.cumplimiento) * len(sorteos) + 1e-9)
            fallos = 0
            with _Sorteo(app, alims, feeders, existentes) as s:
                for i, (sorteo, sin_i) in enumerate(zip(sorteos, sin_sorteos)):
                    if i % 10 == 0 and cancelado():          # una variante puede llevar minutos
                        informe['cancelado'] = True
                        return None
                    s.escalar(sorteo['factores'])
                    fallos += not cumple(sin_i, medida_para_criterio(app, alims, feeders), barras, p)[0]
                    if fallos > admite:
                        break
            return (len(sorteos) - fallos) / len(sorteos)

        # RF-74: con lo que ya tiene «Con proyecto» (una obra de una escalera anterior), si
        # cumple no se prueba ninguna variante.
        casos['con'].Activate()
        con_actual = medida_para_criterio(app, alims, feeders)
        if cumple(sin_max, con_actual, barras, p)[0]:
            fraccion = sortear() if sorteos else 1.0
            if fraccion is None:
                return informe, 2
            if fraccion >= p.cumplimiento:
                informe['ya_cumple'] = {'fraccion': fraccion, 'perdidas_kw': con_actual['perdidas_kw']}
                print(f'  «Con proyecto» ya cumple: sorteos {100 * fraccion:.0f} %', flush=True)
                return informe, 0

        # Fase 1: todas con la máxima (RF-52b); con eso ya se sabe su costo anual entero.
        variantes = list(plan.get('variantes') or [])
        filas = []
        for v in variantes:
            if cancelado():
                informe['cancelado'] = True
                break
            fila = {'nombre': v['nombre'], 'maxima': False, 'motivos': [], 'fraccion': None,
                    'perdidas_kw': None, 'error': None, 'sin_sortear': None}
            con_max, fila['error'] = con_variante(v, lambda: medida_para_criterio(app, alims, feeders))
            if con_max is not None:
                fila['perdidas_kw'] = con_max['perdidas_kw']
                fila['maxima'], fila['motivos'] = cumple(sin_max, con_max, barras, p)
            print(f"  {v['nombre']}: máxima {'cumple' if fila['maxima'] else 'no cumple'}", flush=True)
            filas.append((v, fila))
        # Fase 2 (RF-71): de la más barata a la más cara, hasta la primera que cumple en los sorteos.
        k = float(plan.get('costo_por_kw_perdido') or 0.0)

        def costo(v, fila):
            return float(v['costo_base']) + k * float(fila['perdidas_kw'] or 0.0)

        candidatas = sorted(((v, f) for v, f in filas if f['maxima'] and v.get('costo_base') is not None),
                            key=lambda vf: (costo(*vf), vf[1]['nombre']))
        for v, fila in filas:
            if fila['maxima'] and v.get('costo_base') is None:
                fila['sin_sortear'] = 'sin costo: no se puede elegir, no se sortea'
        ganadora = None
        for v, fila in candidatas:
            if informe['cancelado'] or cancelado():
                informe['cancelado'] = True
                break
            if ganadora is not None:
                fila['sin_sortear'] = f"no se sortea: «{ganadora}» cuesta menos y ya cumple"
                continue
            if not sorteos:
                fila['fraccion'] = 1.0
            else:
                fila['fraccion'], error = con_variante(v, sortear)
                fila['error'] = fila['error'] or error
            print(f"  {v['nombre']}: sorteos {100 * (fila['fraccion'] or 0):.0f} %", flush=True)
            if (fila['fraccion'] or 0) >= p.cumplimiento:
                ganadora = fila['nombre']
        informe['variantes'] = [f for _v, f in filas]
    finally:
        if ajenas:
            casos['con'].Activate()
            for v in ajenas:
                v.Activate()
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
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
    p.add_argument('--escalera-datos', action='store_true',
                   help='Troncal, corrientes y tramo de cada carga nueva para la escalera (025:RF-49)')
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
    from igea_dgs.pf_arnes import PFNoDisponible, conectar

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
        elif args.escalera_datos:
            informe, codigo = datos_escalera(app, plan)
        elif args.bibliotecas:
            informe, codigo = bibliotecas(app, plan)
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
