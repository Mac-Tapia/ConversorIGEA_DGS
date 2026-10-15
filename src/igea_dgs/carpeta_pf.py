"""Carpeta de DIgSILENT donde quedan los proyectos importados desde DGS (spec 005).

Cada DGS importado creaba un proyecto suelto en la raíz del usuario, junto a los hechos a
mano, y «Leer proyectos» tenía que abrirlos todos: en la prueba del 2026-10-09 seguía a
los seis minutos con 3,7 GB de memoria. Los proyectos del conversor van ahora a una
carpeta propia, y la lectura solo mira esa carpeta.

El nombre de la carpeta es una convención de cada empresa (constitución P13): sale de
``config/perfil_empresa.json``, local y fuera de git, como ``demanda_medida_alias.json``.
Sin perfil, la carpeta se llama :data:`NOMBRE_POR_DEFECTO`.

Este módulo no importa ``powerfactory``: la web valida el nombre antes de abrir
DIgSILENT (RF-4), y los guiones de ``tools/`` lo usan con el Python de la API.
"""
from __future__ import annotations

import json
from pathlib import Path

NOMBRE_POR_DEFECTO = 'Conversor IGEA-DGS'
#: Clave del perfil de empresa. Cuando exista el perfil de la spec 002 (RF-31), la
#: clave pasa a él con el mismo nombre.
CLAVE_PERFIL = 'carpeta_proyectos_pf'
#: DIgSILENT corta ``loc_name`` a 40 caracteres; un nombre más largo dejaría la carpeta
#: con otro nombre y la siguiente lectura no la encontraría.
LARGO_MAXIMO = 40
#: Los que Windows no admite en un nombre de fichero, más el punto, que DIgSILENT usa
#: para separar el nombre de la clase («SI213.IntPrj»). Por comprobar en PF 2024 (T12).
NO_ADMITIDOS = frozenset('\\/:*?"<>|.')


class CarpetaError(ValueError):
    """El nombre de la carpeta o el perfil de empresa no son válidos."""


def ruta_perfil() -> Path:
    from .perfil_empresa import ruta_perfil_activo

    return ruta_perfil_activo()


def validar_nombre(nombre: object) -> str:
    """El nombre limpio de espacios en los extremos, o :class:`CarpetaError` que lo nombra."""
    if not isinstance(nombre, str):
        raise CarpetaError(f'El nombre de la carpeta de DIgSILENT debe ser un texto, no {nombre!r}.')
    limpio = nombre.strip()
    if not limpio:
        raise CarpetaError(f'El nombre de la carpeta de DIgSILENT está vacío: {nombre!r}.')
    if len(limpio) > LARGO_MAXIMO:
        raise CarpetaError(
            f'El nombre de la carpeta de DIgSILENT supera {LARGO_MAXIMO} caracteres: {nombre!r}.')
    malos = sorted({c for c in limpio if c in NO_ADMITIDOS or not c.isprintable()})
    if malos:
        raise CarpetaError(
            f'El nombre de la carpeta de DIgSILENT lleva caracteres no admitidos '
            f'({" ".join(repr(c) for c in malos)}): {nombre!r}.')
    return limpio


def nombre_de_perfil(ruta: Path | None = None) -> str:
    """Nombre de la carpeta según el perfil de empresa, o el de por defecto si no lo da."""
    ruta = ruta_perfil() if ruta is None else Path(ruta)
    if not ruta.is_file():
        return NOMBRE_POR_DEFECTO
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CarpetaError(f'No se pudo leer el perfil de empresa {ruta.name}: {exc}') from exc
    if not isinstance(datos, dict):
        raise CarpetaError(f'El perfil de empresa {ruta.name} debe ser un objeto JSON.')
    nombre = datos.get(CLAVE_PERFIL)
    if nombre is None:
        return NOMBRE_POR_DEFECTO
    try:
        return validar_nombre(nombre)
    except CarpetaError as exc:
        raise CarpetaError(f'{exc} (perfil {ruta.name}, clave {CLAVE_PERFIL!r})') from exc


# --------------------------------------------------------------------------- árbol
# Las funciones siguientes reciben objetos de la API de PowerFactory (o el doble de
# tests/fake_pf.py) y solo usan GetContents, GetClassName, CreateObject y loc_name.

#: Separador de la ruta de un proyecto dentro de la carpeta. «/» no es un carácter
#: admitido en un nombre de DIgSILENT, así que no se confunde con uno.
SEPARADOR = '/'


def _hijos(objeto, clase: str) -> list:
    return [h for h in (objeto.GetContents() or []) if h.GetClassName() == clase]


def buscar_carpeta(usuario, nombre: str):
    """La ``IntFolder`` de la raíz del usuario con ese nombre, o None.

    Solo la raíz y solo carpetas: un proyecto que se llame igual, o una subcarpeta con
    ese nombre en otro sitio, no es la carpeta de importación.
    """
    for carpeta in _hijos(usuario, 'IntFolder'):
        if carpeta.loc_name == nombre:
            return carpeta
    return None


def asegurar_carpeta(usuario, nombre: str):
    """La carpeta de importación, creada en la raíz del usuario si aún no existe (RF-5)."""
    carpeta = buscar_carpeta(usuario, nombre)
    if carpeta is None:
        carpeta = usuario.CreateObject('IntFolder', nombre)
    if carpeta is None:
        raise CarpetaError(
            f'DIgSILENT no dejó crear la carpeta {nombre!r} en la raíz del usuario.')
    return carpeta


def nombre_libre(carpeta, nombre: str) -> str:
    """``nombre`` o el primero libre de ``nombre_2``, ``nombre_3``… en la carpeta (RF-7).

    Se compara sin distinguir mayúsculas, porque DIgSILENT tampoco las distingue al
    buscar un objeto por nombre. Solo cuentan los proyectos de la propia carpeta: los
    de la raíz, importados antes de la spec 005, se quedan donde están (RF-20).
    """
    ocupados = {p.loc_name.lower() for p in _hijos(carpeta, 'IntPrj')}
    if nombre.lower() not in ocupados:
        return nombre
    n = 2
    while True:
        sufijo = f'_{n}'
        candidato = nombre[:LARGO_MAXIMO - len(sufijo)] + sufijo
        if candidato.lower() not in ocupados:
            return candidato
        n += 1


def proyectos_de(carpeta) -> list[tuple[str, object]]:
    """``[(ruta relativa, IntPrj)]`` de la carpeta y sus subcarpetas, por ruta.

    Solo baja por ``IntFolder``: de un proyecto lee el nombre y nada más, para no abrir
    su contenido (RF-13), que es lo que hacía tardar minutos la lectura.
    """
    hallados: list[tuple[str, object]] = []

    def bajar(actual, prefijo: list[str]) -> None:
        for hijo in actual.GetContents() or []:
            clase = hijo.GetClassName()
            if clase == 'IntPrj':
                hallados.append((SEPARADOR.join([*prefijo, hijo.loc_name]), hijo))
            elif clase == 'IntFolder':
                bajar(hijo, [*prefijo, hijo.loc_name])

    bajar(carpeta, [])
    return sorted(hallados, key=lambda par: par[0].lower())


def proyecto_por_ruta(carpeta, ruta: str):
    """El proyecto de esa ruta relativa a la carpeta, o None (RF-16)."""
    *subcarpetas, nombre = ruta.split(SEPARADOR)
    actual = carpeta
    for parte in subcarpetas:
        actual = next((c for c in _hijos(actual, 'IntFolder') if c.loc_name == parte), None)
        if actual is None:
            return None
    return next((p for p in _hijos(actual, 'IntPrj') if p.loc_name == nombre), None)


# --------------------------------------------------------------------------- alimentadores
def _datos_de_red(proyecto) -> list:
    """Carpetas «Network Data» (``iopt_typ='netdat'``) del proyecto, sin activarlo.

    ``app.GetProjectFolder('netdat')`` solo sirve para el proyecto activo, y leer no activa
    nada (RF-15): se buscan a mano, directamente en el proyecto o dentro de «Network
    Model», que es donde las deja la importación de un DGS.
    """
    carpetas = _hijos(proyecto, 'IntPrjfolder')
    hallados = [c for c in carpetas if getattr(c, 'iopt_typ', None) == 'netdat']
    for modelo in carpetas:
        if getattr(modelo, 'iopt_typ', None) == 'netmod':
            hallados += [c for c in _hijos(modelo, 'IntPrjfolder')
                         if getattr(c, 'iopt_typ', None) == 'netdat']
    return hallados


def _nombres(donde: list, patron: str) -> set[str]:
    return {o.loc_name for d in donde for o in (d.GetContents(patron, 1) or [])}


def alimentadores_de(proyecto) -> tuple[list[str], str | None]:
    """Alimentadores del proyecto y, si no se pudo buscar solo en la red, la nota de por qué.

    Se busca solo en los datos de red (RF-17): buscar ``ElmFeeder`` en todo el proyecto
    abría también casos de estudio, resultados y bibliotecas, y en la prueba del
    2026-10-09 eso tenía la lectura más de seis minutos. Un proyecto hecho a mano sin
    «Network Data» se busca entero, como antes (RF-18).

    El DGS crea un ``ElmFeeder`` por alimentador; un proyecto sin ninguno muestra sus
    ``ElmNet`` (spec 004), salvo la red de resumen.
    """
    donde, nota = _datos_de_red(proyecto), None
    if not donde:
        donde = [proyecto]
        nota = (f'{proyecto.loc_name}: sin carpeta de datos de red; se buscaron los '
                'alimentadores en todo el proyecto.')
    nombres = _nombres(donde, '*.ElmFeeder')
    if not nombres:
        nombres = {n for n in _nombres(donde, '*.ElmNet') if 'summary' not in n.lower()}
    return sorted(nombres), nota


# --------------------------------------------------------------------------- activar
def buscar_proyecto(app, ruta: str, carpeta: str):
    """El proyecto de ``ruta`` en la carpeta, sin activarlo; None si no existe.

    ``app.ActivateProject(nombre)`` solo busca en la raíz del usuario: tras importar en
    la carpeta, un estudio de ``run_one_study.py`` no encontraba el proyecto, o activaba
    uno antiguo de la raíz con el mismo nombre. Si la ruta no está en la carpeta, se
    busca un proyecto de la raíz con ese nombre exacto, para seguir usando los
    importados antes de la spec 005 (RF-20). Las obras (spec 011, RF-91) leen así los
    tipos de otro proyecto sin cambiar cuál está activo.
    """
    usuario = app.GetCurrentUser()
    destino = buscar_carpeta(usuario, carpeta)
    proyecto = proyecto_por_ruta(destino, ruta) if destino is not None else None
    if proyecto is None and SEPARADOR not in ruta:
        proyecto = next((p for p in _hijos(usuario, 'IntPrj') if p.loc_name == ruta), None)
    return proyecto


def activar_proyecto(app, ruta: str, carpeta: str):
    """Activa por objeto el proyecto de ``ruta`` en la carpeta (``buscar_proyecto``)."""
    proyecto = buscar_proyecto(app, ruta, carpeta)
    if proyecto is None:
        return None
    # 019:RF-7: en el proceso que se queda abierto, el proyecto de la orden anterior sigue
    # activo; activarlo otra vez costaba minutos en CA101.
    activo = app.GetActiveProject() if hasattr(app, 'GetActiveProject') else None
    if activo is not None and activo.GetFullName() == proyecto.GetFullName():
        return proyecto
    proyecto.Activate()
    return proyecto
