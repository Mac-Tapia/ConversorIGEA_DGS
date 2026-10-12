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

1. Lee la red y los tipos en «Sin proyecto» y planifica todas las obras con
   ``igea_dgs.obras_pf.plan_simulacion``: lo que se aplica es lo que se simuló.
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
import traceback
from pathlib import Path
from typing import Any, Callable

from ajuste_cabecera_pf import diagnostico
from cargas_pf import (
    Alimentadores, activar_proyecto, crear_variacion, error_inesperado, flujo_de_carga,
    medir_estado, nombre_libre, nombre_pf,
)
from casos_pf import NOMBRES, tres_casos
from estudios_pf import tramos_troncales

from igea_dgs.carpeta_pf import buscar_proyecto, nombre_de_perfil
from igea_dgs.obras_pf import (
    ATRIBUTOS_TIPO, BANDA_TENSION_PU, Obra, ObrasError, RedAlimentador, Tipo, diferencias_sin_proyecto,
    mismos_datos, plan_simulacion, red_de_lectura, resolver_copia, resumen_tipo,
    tipo_de_ficha, validar_obra,
)

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
def cabecera_de(elm):
    """La barra de la cabecera: la del cubículo con que se define el ``ElmFeeder``."""
    cubiculo = getattr(elm, 'obj_id', None)
    return getattr(cubiculo, 'cterm', None) if cubiculo is not None else None


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
        'tramos': [{'nombre': ln.loc_name, 'tipo': tipo(ln), 'nlnum': int(getattr(ln, 'nlnum', 1) or 1)}
                   for ln in sorted(elm.GetObjs('ElmLne'), key=nombre)],
        'trafos': [{'nombre': tr.loc_name, 'tipo': tipo(tr)}
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


# =========================================================================== aplicar
class Contexto:
    """Lo que recibe el constructor de una obra, con su variación ya grabando.

    Clase normal y no ``dataclass``: las pruebas cargan este guion sin registrarlo en
    ``sys.modules``, y ``dataclasses`` lo busca ahí al resolver las anotaciones.
    """

    def __init__(self, app, proyecto, obra: Obra, fila: dict, red: RedAlimentador, elm):
        self.app, self.proyecto, self.obra, self.fila, self.red = app, proyecto, obra, fila, red
        self.elm = elm
        """El ``ElmFeeder`` del alimentador de la obra."""
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
    if all(b is not cabecera for b in barras):
        barras.append(cabecera)
    extremos: dict[int, list] = {}
    cubiculos = {}
    for barra in barras:
        cubiculos[id(barra)] = list(barra.GetContents('*.StaCubic') or [])
        for cub in cubiculos[id(barra)]:
            elemento = getattr(cub, 'obj_id', None)
            if elemento is not None:
                extremos.setdefault(id(elemento), []).append((barra, cub))
    distancia = {id(cabecera): 0}
    cola = [cabecera]
    while cola:
        barra = cola.pop(0)
        for cub in cubiculos.get(id(barra), []):
            for otra, _ in extremos.get(id(getattr(cub, 'obj_id', None)), []):
                if id(otra) not in distancia:
                    distancia[id(otra)] = distancia[id(barra)] + 1
                    cola.append(otra)
    lados = [(distancia[id(b)], i, b, c) for i, (b, c) in enumerate(extremos.get(id(linea), []))
             if id(b) in distancia]
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
    tipo = ctx.tipo('TypLne', ctx.fila['tipo'])
    for e in ctx.fila['elementos']:
        ctx.objeto('ElmLne', e['elemento']).typ_id = tipo


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


CONSTRUCTORES.update(condensador=construir_condensador, reconectador=construir_reconectador,
                     regulador=construir_regulador, seccion=construir_seccion,
                     terna=construir_terna, tension=construir_tension)

#: Obras que necesitan la troncal: sin tramos indicados, son los de la troncal (RF-77,
#: RF-80), y la sección avisa de los que no son de ella (RF-87).
CON_TRONCAL = ('seccion', 'terna')


def leer_troncales(app, feeders: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Tramos de la troncal de cada alimentador, con el estudio de troncal (RF-44).

    Es la misma lectura que el N-1 de ``estudios_pf``. Las troncales que crea
    ``ComBbone`` son el resultado de un cálculo, no red: se borran después de leerlas
    para que leer no deje objetos nuevos; las que ya había (de un estudio de troncal del
    operador) se quedan.
    """
    bbone = app.GetFromStudyCase('ComBbone')
    if bbone is None:
        return {}, ['El caso no admite la orden ComBbone: sin troncal, la sección y la terna '
                    'necesitan los tramos indicados.']
    previas = {id(b) for b in app.GetCalcRelevantObjects('*.ElmBbone')}
    try:
        bbone.Execute()
        tramos, sin_troncal = tramos_troncales(app, feeders)
    finally:
        for b in app.GetCalcRelevantObjects('*.ElmBbone'):
            if id(b) not in previas:
                b.Delete()
    avisos = [f'{f}: sin troncal calculada.' for f in sin_troncal]
    return {f: [ln.loc_name for ln in lineas] for f, lineas in tramos.items()}, avisos


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


def _leer(app, plan, alims, feeders, obras) -> tuple[dict, list, list[str]]:
    """Redes, tipos y avisos de la lectura, en el caso activo («Sin proyecto»)."""
    redes, avisos = {}, []
    troncales: dict[str, list[str]] = {}
    con_troncal = sorted({o.alimentador for o in obras if o.clase in CON_TRONCAL})
    if con_troncal:
        troncales, avisos_troncal = leer_troncales(app, con_troncal)
        avisos += avisos_troncal
    for f in feeders:
        elm = alims.elm.get(f)
        if elm is None:
            avisos.append(f'El alimentador {f} no está en el proyecto.')
            continue
        leido = leer_alimentador(elm)
        # RF-102: si otro alimentador sale de la misma barra, comparte barra y fuente, y
        # migrar esa barra lo cambiaría también a él.
        cabecera = cabecera_de(elm)
        leido['cabecera_compartida_con'] = sorted(
            g for g, otro in alims.elm.items()
            if g != f and cabecera is not None and cabecera_de(otro) is cabecera)
        try:
            redes[f] = red_de_lectura(f, leido, troncal=troncales.get(f, ()))
        except ObrasError as exc:
            avisos.append(str(exc))
    otro = None
    if plan.get('otro_proyecto'):
        otro = buscar_proyecto(app, plan['otro_proyecto'], plan.get('folder') or nombre_de_perfil())
        if otro is None or biblioteca_de_otro(otro) is None:
            avisos.append(f"No se pudo leer el proyecto {plan['otro_proyecto']!r}.")
            otro = None
    tipos = [tipo_de_ficha(t) for t in leer_tipos(app, CLASES_TIPO, otro)]
    return redes, tipos, avisos


def _aplicar_una(app, plan, proyecto, casos, alims, obra: Obra, fila: dict, red) -> None:
    """Una obra en su variación y en sus casos. Deja en ``fila`` lo que pasó."""
    roles = [ROL_DE_CASO[c] for c in obra.casos]
    casos[roles[0]].Activate()
    variacion, _etapa = crear_variacion(app, fila['variacion'], fila['variacion'])
    fila['variacion'] = variacion.loc_name
    try:
        ctx = Contexto(app, proyecto, obra, fila, red, alims.elm[obra.alimentador])
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
        variacion.Delete()
        fila.update(variacion='', error=f'no se pudo crear la obra: {exc}')
        return

    # Activa solo en sus casos (RF-57); en el «Caso base», nunca (RF-58).
    for rol in NOMBRES:
        casos[rol].Activate()
        if rol in roles:
            variacion.Activate()
        else:
            variacion.Deactivate()

    fila['casos_activos'], fila['flujo'] = [], {}
    for rol in roles:                                                     # RF-66
        nombre = NOMBRES[rol]
        casos[rol].Activate()
        flujo = flujo_de_carga(app)
        fila['flujo'][nombre] = {'converge': flujo['converged']}
        if flujo['converged']:
            fila['casos_activos'].append(nombre)
            continue
        # RF-67: el diagnóstico se lee antes de desactivarla, con lo que dejó este flujo.
        fila['flujo'][nombre]['diagnostico'] = diagnostico(
            Alimentadores(app, proyecto, [obra.alimentador]), obra.alimentador, {}, {})
        variacion.Deactivate()
        fila['avisos'].append(f'Con la obra, el flujo de «{nombre}» no converge: queda inactiva '
                              'en ese caso y se conserva en el proyecto.')


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
    casos = tres_casos(app)
    if not casos:
        return {**informe, 'error': 'el proyecto no tiene los casos «Caso base», «Sin proyecto» '
                                    'y «Con proyecto»: prepare los casos primero'}, 2

    feeders = sorted({o.alimentador for o in obras} | set(plan.get('feeders') or []))
    alims = Alimentadores(app, proyecto, feeders)
    inicial = app.GetActiveStudyCase()
    try:
        casos['sin'].Activate()
        redes, tipos, avisos = _leer(app, plan, alims, feeders, obras)
        informe['avisos'] += avisos
        carpeta = app.GetProjectFolder('scheme')
        ocupadas = [v.loc_name for v in (carpeta.GetContents('*.IntScheme', 1) if carpeta else [])]
        filas = plan_simulacion(obras, redes, tipos, variaciones=ocupadas)
        if simular:                                                       # RF-69
            informe['obras'] = filas
            return informe, 2 if any(f['error'] for f in filas) else 0
        for fila in filas:
            if not fila['error'] and fila['clase'] not in CONSTRUCTORES:
                fila['error'] = f"las obras de clase {fila['clase']} todavía no se pueden aplicar"

        antes = medir_estado(app, alims, feeders)                         # RF-64
        if not antes['converged']:
            informe['avisos'].append('«Sin proyecto» no converge antes de las obras: no se puede '
                                     'comprobar después que no cambió.')
        for obra, fila in zip(obras, filas):
            if cancelado():
                informe['cancelado'] = True
                break
            if not fila['error']:
                _aplicar_una(app, plan, proyecto, casos, alims, obra, fila, redes[obra.alimentador])
            informe['obras'].append(fila)
        if antes['converged']:
            _comprobar_sin_proyecto(app, casos, alims, feeders, antes, informe)
    finally:
        if inicial is not None and app.GetActiveStudyCase() is not inicial:
            inicial.Activate()

    fallos = any(f['error'] or not all(x['converge'] for x in f.get('flujo', {}).values())
                 for f in informe['obras'])
    diferencias = bool((informe['comprobacion'] or {}).get('diferencias'))
    return informe, 2 if fallos or diferencias or informe['cancelado'] else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Obras de mejora de la spec 011 en DIgSILENT')
    p.add_argument('--plan', required=True, help='Plan JSON preparado por la web')
    p.add_argument('--output-json', required=True, help='Dónde dejar el informe')
    p.add_argument('--bibliotecas', action='store_true',
                   help='Solo leer alimentadores y tipos de las bibliotecas para el formulario')
    p.add_argument('--simular', action='store_true',
                   help='Decir lo que haría cada obra sin escribir en el proyecto')
    p.add_argument('--cancel-file', help='Si este fichero aparece, para entre obras')
    args = p.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
    try:
        import powerfactory
    except ImportError as exc:
        print(f'ERROR: API de DIgSILENT no disponible ({exc}).')
        return 3
    try:
        app = powerfactory.GetApplicationExt()
    except Exception as exc:  # noqa: BLE001
        print(f'ERROR: no se pudo conectar a DIgSILENT: {exc}')
        return 3

    def cancelado() -> bool:
        return bool(args.cancel_file) and Path(args.cancel_file).exists()

    try:
        if args.bibliotecas:
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
