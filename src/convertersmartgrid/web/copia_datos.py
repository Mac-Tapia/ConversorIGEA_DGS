"""Copia y restauración de los datos del conversor, con manifiesto (086:RF-10, RF-47).

Qué se copia lo decide la misma regla que la limpieza diaria (``retencion.py``): una ejecución
sin referencias, sin modelo ni informe y de más de siete días la retiraría la limpieza, y aquí
tampoco entra; ``tmp`` y los automáticos sin uso tampoco. Lo demás entra entero. Los ficheros de
fuera de los datos a los que apunta un espacio (un TXT en otra unidad) no se copian: son del
operador, y el manifiesto los lista para que se sepa que hay que guardarlos aparte.

Una copia nunca queda a medias con aspecto de buena: se escribe en una carpeta ``.parcial`` y solo
se le da su nombre con todo copiado y el manifiesto sincronizado. Restaurar comprueba cada huella
antes de tocar nada, y lo que hubiera se aparta en vez de borrarse.

Cada fichero físico se guarda una vez (086:RF-78 a RF-80). El 2026-11-12 la copia iba a escribir 95 GB
de unos datos que ocupaban 21 en el disco: el paquete VNR-GIS ``ELOR25_V2`` (5,4 GB) estaba en once
ejecuciones de ``output/web`` como enlaces duros de un solo fichero, y lo mismo los TXT y la ``.mdb``. El
destino del usuario era Google Drive, con 41 GB libres y sin enlaces duros. Se agrupa por identidad física
(``st_dev``, ``st_ino``) y, entre ficheros distintos del mismo tamaño, por su huella; el manifiesto lleva
todos los nombres, y restaurar los recrea como enlaces si la unidad lo admite.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import shutil
import uuid
from collections import Counter
from collections.abc import Callable
from itertools import chain
from pathlib import Path
from typing import Any

from ..powerfactory_env import project_root
from ..runtime_paths import es_programa_instalado, raiz_local
from ..runtime_paths import FICHERO_INSTALACION, rutas_runtime
from ..util import publicar_duradero, sha256_file, sincronizar_carpeta, write_json_atomic
from .jobs import FINISHED
from .retencion import PESOS, RUN_EN_TEXTO, es_valioso
from .source_runs import valid_run_id
from .workspace import CAMPOS_CON_RUTAS, data_root, expandir_rutas, raiz_componente

#: 3: cada fichero físico una vez, con sus ``otros_nombres`` (086:RF-79); se siguen leyendo la 1 y la 2.
VERSION_MANIFIESTO = 3
VERSIONES_LEIDAS = (1, 2, VERSION_MANIFIESTO)
MANIFIESTO = 'manifiesto.json'
#: Lo que se deja libre en el destino además de los ficheros: el manifiesto y lo que apunta la unidad.
MARGEN_BYTES = 64 * 1024 * 1024
#: Intentos y espera inicial (se dobla en cada uno) ante un fichero que bloquea la sincronización de
#: Google Drive o de OneDrive (086:RF-81): con 0,5 s y seis intentos, hasta unos 15 s por fichero.
REINTENTOS = 6
ESPERA_S = 0.5
#: Dónde recuerda cada equipo la carpeta de sus copias, como ``config/archivo.json`` de la 105 (086:RF-85).
FICHERO_CARPETA = 'copia_datos.json'
#: Antigüedad de la última copia a partir de la cual se avisa; se cambia con ``CSG_COPIA_MAX_DIAS``.
DIAS_MAXIMOS = 7.0
SIETE_DIAS_S = 7 * 86400
#: Local y fuera de git: si se pierde, no hay de dónde recuperarlo.
FICHEROS_CONFIG = ('perfil_empresa.json', 'line_type_aliases.json')
_ESPACIO_RE = re.compile(r'[a-f0-9]{8,32}')
_MODELOS = ('_asistente', '_digital_twin')


class CopiaNoValida(ValueError):
    """La copia está incompleta o alterada: no se restaura, y nada se ha tocado."""


class SinEspacio(ValueError):
    """La copia no cabe en el destino: no se empieza (086:RF-83)."""


def raices_de_datos(checkout: Path | None = None) -> dict[str, Path]:
    """Dónde están hoy los datos: los espacios, los heredados de ``output/web`` y la configuración local.

    Con ``checkout``, los de esa instalación: copiar los datos del árbol principal con la orden de otro árbol
    (una rama en su worktree) copiaba los de la rama, que no tienen nada.
    """
    programa = checkout or project_root()
    if checkout is None:
        raices = {'datos': data_root()}
    else:
        from ..runtime_paths import raiz_datos_web

        raices = {'datos': raiz_datos_web(programa)}
    heredada = programa / 'output' / 'web'
    if heredada.is_dir() and heredada.resolve() != raices['datos'].resolve():
        raices['heredada'] = heredada
    raices['config'] = raiz_local(programa) / 'config'
    # Instalado, los catálogos con las fichas del operador también se quedan fuera del programa y son datos.
    entrada = raiz_local(programa) / 'input'
    if es_programa_instalado(programa) and entrada.is_dir():
        raices['input'] = entrada
    for nombre, componente, variable in (('asistente', '_asistente', 'CSG_ASISTENTE_DATA'),
                                         ('gemelo', '_digital_twin', 'CSG_TWIN_DATA')):
        if checkout is None:
            ruta = raiz_componente(componente, variable)
        else:
            from .. import runtime_paths

            ruta = runtime_paths.raiz_componente(componente, variable, programa)
        if not any(ruta.resolve().is_relative_to(base.resolve()) for n, base in raices.items() if n != 'config'):
            raices[nombre] = ruta
    from ..perfil_empresa import ruta_perfil_activo

    perfil = (ruta_perfil_activo() if checkout is None or os.environ.get('CSG_PERFIL_EMPRESA', '').strip()
              else raiz_local(programa) / 'config' / 'perfil_empresa.json')
    # La ruta declarada sigue siendo destino de restauración si se perdió el archivo.
    raices['perfil_empresa'] = perfil
    return raices


def _planificar_raices(raices: dict[str, Path]) -> tuple[dict[str, Path], dict[str, str], dict[str, list[Path]]]:
    """086:RF-38/47 — raíces sin enlaces ni directorios ambiguos; archivos cubiertos se consolidan."""
    origenes, tipos = {}, {}
    for nombre, valor in raices.items():
        ruta = Path(valor)
        if not nombre or nombre in ('.', '..') or Path(nombre).name != nombre:
            raise CopiaNoValida('Nombre de raíz de copia no válido.')
        if _es_redireccion(ruta):
            raise CopiaNoValida(f'La raíz es un enlace; indique su ruta física: {ruta}')
        if nombre == 'perfil_empresa' and ruta.exists() and not ruta.is_file():
            raise CopiaNoValida('El perfil de empresa debe ser un archivo.')
        if ruta.is_file() or ruta.is_dir():
            origenes[nombre] = ruta.resolve()
            tipos[nombre] = 'archivo' if ruta.is_file() else ('configuracion' if nombre == 'config' else 'directorio')
    completos = {n: p for n, p in origenes.items() if tipos[n] == 'directorio'}
    for i, (nombre, ruta) in enumerate(completos.items()):
        for otra, base in list(completos.items())[i + 1:]:
            if ruta.is_relative_to(base) or base.is_relative_to(ruta):
                raise CopiaNoValida(f'Directorios de copia solapados: {nombre} y {otra}.')
    extras: dict[str, list[Path]] = {n: [] for n in origenes}
    for nombre, ruta in list(origenes.items()):
        if tipos[nombre] == 'archivo':
            cubre = next((n for n, base in origenes.items() if n != nombre and tipos[n] != 'archivo'
                          and ruta.is_relative_to(base)), None)
            if cubre is not None:
                extras[cubre].append(ruta)
                del origenes[nombre], tipos[nombre]
        elif tipos[nombre] == 'configuracion':
            cubre = next((n for n, base in completos.items() if ruta.is_relative_to(base)), None)
            if cubre is not None:
                extras[cubre].extend(ruta / f for f in FICHEROS_CONFIG if (ruta / f).is_file())
                extras[cubre].extend(extras[nombre])
                del origenes[nombre], tipos[nombre]
    return origenes, tipos, extras


def _es_redireccion(ruta: Path) -> bool:
    return ruta.is_symlink() or ruta.is_junction()


def _recorrer(carpeta: Path, omitidos: list[dict]):
    """Los ficheros de ``carpeta``; un enlace no se sigue: puede salir de los datos."""
    pendientes = [carpeta]
    while pendientes:
        actual = pendientes.pop()
        for hijo in sorted(actual.iterdir()):
            if _es_redireccion(hijo):
                omitidos.append({'ruta': str(hijo), 'motivo': 'enlace: no se sigue'})
            elif hijo.is_dir():
                pendientes.append(hijo)
            elif hijo.is_file():
                yield hijo


def _textos_de_metadatos(espacio: Path) -> tuple[str, bool]:
    """Lo guardado del espacio, en bruto, y si se pudo leer entero."""
    textos, sano = [], True
    for nombre in ('workspace.json', 'conversiones.json', 'workspace.json.bak', 'conversiones.json.bak'):
        ruta = espacio / nombre
        if not ruta.is_file():
            continue
        try:
            texto = ruta.read_text(encoding='utf-8')
            json.loads(texto)
            textos.append(texto)
        except (OSError, ValueError):
            sano = sano and nombre.endswith('.bak')
    return '\n'.join(textos), sano


def _ejecucion_retirable(run: Path, referidas: set[str], ahora: float, omitidos: list[dict]) -> bool:
    """La misma regla de ``retencion``: sin referencia, sin nada valioso y sin actividad en siete días."""
    if run.name in referidas or not valid_run_id(run.name):
        return False
    for fichero in _recorrer(run, omitidos):
        if es_valioso(fichero) or fichero.stat().st_mtime >= ahora - SIETE_DIAS_S:
            return False
    return True


def _ficheros_de_espacio(espacio: Path, ahora: float, omitidos: list[dict]):
    texto, sano = _textos_de_metadatos(espacio)
    referidas = set(RUN_EN_TEXTO.findall(texto))
    pendientes = [espacio]
    while pendientes:
        actual = pendientes.pop()
        for hijo in sorted(actual.iterdir()):
            if _es_redireccion(hijo):
                omitidos.append({'ruta': str(hijo), 'motivo': 'enlace: no se sigue'})
            elif hijo.is_file():
                yield hijo
            elif hijo.is_dir():
                relativa = hijo.relative_to(espacio).parts
                if relativa == ('tmp',):
                    omitidos.append({'ruta': str(hijo), 'motivo': 'temporales del espacio'})
                elif relativa == ('entradas', '_auto'):
                    for auto in _recorrer(hijo, omitidos):
                        if auto.name in texto or es_valioso(auto):
                            yield auto
                        else:
                            omitidos.append({'ruta': str(auto), 'motivo': 'automático sin referencias'})
                elif (len(relativa) == 2 and relativa[0] == 'runs' and sano
                      and _ejecucion_retirable(hijo, referidas, ahora, omitidos)):
                    omitidos.append({'ruta': str(hijo), 'motivo': 'ejecución que retiraría la limpieza'})
                else:
                    pendientes.append(hijo)


def _ficheros_de_raiz(nombre: str, raiz: Path, ahora: float, sin_modelos: bool, omitidos: list[dict]):
    if raiz.is_file():
        yield raiz
        return
    if nombre == 'config':
        for fichero in FICHEROS_CONFIG:
            if (raiz / fichero).is_file():
                yield raiz / fichero
        return
    for hijo in sorted(raiz.iterdir()):
        if _es_redireccion(hijo):
            omitidos.append({'ruta': str(hijo), 'motivo': 'enlace: no se sigue'})
        elif hijo.is_file():
            yield hijo
        elif _ESPACIO_RE.fullmatch(hijo.name) and ((hijo / 'workspace.json').is_file()
                                                   or (hijo / 'workspace.json.bak').is_file()):
            yield from _ficheros_de_espacio(hijo, ahora, omitidos)
        else:
            for fichero in _recorrer(hijo, omitidos):
                if sin_modelos and (hijo.name in _MODELOS or nombre in ('asistente', 'gemelo')) and fichero.suffix.lower() in PESOS:
                    omitidos.append({'ruta': str(fichero), 'motivo': 'pesos: pedido sin modelos'})
                else:
                    yield fichero


def _rutas_externas(raiz: Path) -> list[str]:
    """Ficheros fuera de los datos a los que apunta algún espacio: la copia no los lleva."""
    externas: set[str] = set()

    def recoger(valor: Any) -> None:
        if isinstance(valor, dict):
            if isinstance(valor.get('path'), str) and Path(valor['path']).is_absolute():
                ruta = Path(valor['path'])
                if not ruta.is_relative_to(raiz):
                    externas.add(str(ruta))
            for item in valor.values():
                recoger(item)
        elif isinstance(valor, list):
            for item in valor:
                recoger(item)

    for espacio in raiz.iterdir():
        try:
            datos = json.loads((espacio / 'workspace.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(datos, dict):
            recoger({k: expandir_rutas(v, espacio) for k, v in datos.items() if k in CAMPOS_CON_RUTAS})
    return sorted(externas)


def _copiar_con_huella(origen: Path, destino: Path) -> tuple[int, str]:
    destino.parent.mkdir(parents=True, exist_ok=True)
    resumen = hashlib.sha256()
    bytes_copiados = 0
    with origen.open('rb') as fuente, destino.open('xb') as salida:
        while bloque := fuente.read(1024 * 1024):
            salida.write(bloque)
            resumen.update(bloque)
            bytes_copiados += len(bloque)
        salida.flush()
        os.fsync(salida.fileno())
    return bytes_copiados, resumen.hexdigest()


def _con_reintentos(accion: Callable[[], Any], *, reintentos: int, espera: float,
                    limpiar: Callable[[], None] | None = None) -> Any:
    """086:RF-81: Google Drive bloquea un fichero mientras lo sube; se repite, y el fallo final se dice.

    ``FileNotFoundError`` no se repite: el origen ya no está y lo decide quien llama.
    """
    for intento in range(max(1, reintentos)):
        try:
            return accion()
        except FileNotFoundError:
            raise
        except OSError:
            if intento >= reintentos - 1:
                raise
            if limpiar is not None:
                try:
                    limpiar()
                except OSError:
                    pass
            time.sleep(espera * 2 ** intento)
    return None


def _existente(ruta: Path) -> Path:
    """La carpeta más cercana que existe: el destino de una copia nueva puede no estar creado aún."""
    actual = Path(ruta)
    while not actual.exists() and actual.parent != actual:
        actual = actual.parent
    return actual


def trabajos_en_marcha(raiz: Path) -> list[str]:
    """Trabajos sin terminar anotados en el diario: copiar o restaurar en medio mezclaría estados.

    El diario guarda también el recibo terminado de un trabajo relanzado (096:RF-6): ese no está en marcha.
    """
    carpeta = raiz / '_trabajos'
    if not carpeta.is_dir():
        return []
    en_marcha = []
    for ruta in carpeta.glob('*.json'):
        try:
            datos = json.loads(ruta.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(datos, dict) and datos.get('status') not in FINISHED:
            en_marcha.append(str(datos.get('title') or ruta.stem))
    return en_marcha


def _inventario(origenes: dict[str, Path], tipos: dict[str, str], extras: dict[str, list[Path]], momento: float,
                sin_modelos: bool, omitidos: list[dict]) -> list[tuple[str, str, Path, bool]]:
    """Cada nombre que entra en la copia: ``(raíz, ruta relativa, fichero, imprescindible)``.

    Imprescindible es lo que, si desaparece, deja la copia incompleta (un perfil, la configuración); una
    ejecución que se borra mientras se copia solo se anota como omitida.
    """
    nombres = []
    for nombre, raiz in origenes.items():
        vistos = set()
        for fichero in chain(_ficheros_de_raiz(nombre, raiz, momento, sin_modelos, omitidos), extras.get(nombre, [])):
            if fichero in vistos:
                continue
            vistos.add(fichero)
            if sin_modelos and nombre in ('asistente', 'gemelo') and fichero.suffix.lower() in PESOS:
                omitidos.append({'ruta': str(fichero), 'motivo': 'pesos: pedido sin modelos'})
                continue
            relativa = fichero.name if tipos[nombre] == 'archivo' else fichero.relative_to(raiz).as_posix()
            critico = tipos[nombre] in ('archivo', 'configuracion') or fichero in extras.get(nombre, [])
            nombres.append((nombre, relativa, fichero, critico))
    return nombres


def _agrupar(nombres: list[tuple[str, str, Path, bool]], omitidos: list[dict],
             errores: list[dict]) -> list[dict[str, Any]]:
    """086:RF-78: los nombres de un mismo fichero físico juntos, por ``(st_dev, st_ino)``.

    Un sistema que no da identidad (``st_ino`` 0) deja cada nombre en su grupo; la huella lo resuelve luego.
    """
    grupos: dict[Any, dict[str, Any]] = {}
    for indice, (nombre, relativa, fichero, critico) in enumerate(nombres):
        try:
            datos = os.stat(fichero)
        except FileNotFoundError:
            (errores if critico else omitidos).append({'ruta': str(fichero), 'motivo': 'desapareció durante la copia'})
            continue
        except OSError as exc:
            errores.append({'ruta': str(fichero), 'motivo': str(exc)})
            continue
        clave = (datos.st_dev, datos.st_ino) if datos.st_ino else ('nombre', indice)
        grupo = grupos.setdefault(clave, {'bytes': datos.st_size, 'nombres': []})
        grupo['nombres'].append((nombre, relativa, fichero, critico))
    return list(grupos.values())


def _resumen_plan(grupos: list[dict[str, Any]], destino: Path) -> dict[str, Any]:
    bytes_fisicos = sum(g['bytes'] for g in grupos)
    libre = shutil.disk_usage(_existente(destino)).free
    return {
        'destino': str(destino), 'ficheros_fisicos': len(grupos), 'nombres': sum(len(g['nombres']) for g in grupos),
        'bytes_fisicos': bytes_fisicos, 'bytes_logicos': sum(g['bytes'] * len(g['nombres']) for g in grupos),
        'libre': libre, 'margen': MARGEN_BYTES, 'cabe': bytes_fisicos + MARGEN_BYTES <= libre,
    }


def _gb(valor: int | float) -> str:
    return f'{valor / 1024 ** 3:.1f}'.replace('.', ',')


def texto_plan(plan: dict[str, Any]) -> str:
    """086:RF-82: lo que ocupará y lo que hay libre, en una frase para la orden y para el registro de la web."""
    return (f"La copia ocupará {_gb(plan['bytes_fisicos'])} GB: {plan['ficheros_fisicos']} ficheros físicos con "
            f"{plan['nombres']} nombres ({_gb(plan['bytes_logicos'])} GB si se contara cada nombre). Libres en "
            f"{plan['destino']}: {_gb(plan['libre'])} GB." + ('' if plan['cabe'] else ' No cabe: no se empieza.'))


def _preparar(destino: Path, raices: dict[str, Path] | None, sin_modelos: bool, momento: float):
    origenes, tipos, extras = _planificar_raices(raices if raices is not None else raices_de_datos())
    destino = Path(destino).resolve()
    for nombre, raiz in origenes.items():
        if nombre != 'config' and destino.is_relative_to(raiz.resolve()):
            raise ValueError(f'La copia no puede guardarse dentro de los datos que copia: {raiz}')
    omitidos: list[dict] = []
    errores: list[dict] = []
    grupos = _agrupar(_inventario(origenes, tipos, extras, momento, sin_modelos, omitidos), omitidos, errores)
    return destino, origenes, tipos, grupos, omitidos, errores


def planificar_copia(destino: Path, *, raices: dict[str, Path] | None = None, sin_modelos: bool = False,
                     ahora: float | None = None) -> dict[str, Any]:
    """086:RF-82: cuánto ocupará la copia (bytes físicos únicos) y cuánto hay libre, sin escribir nada."""
    momento = time.time() if ahora is None else ahora
    destino, _, _, grupos, _, _ = _preparar(destino, raices, sin_modelos, momento)
    return _resumen_plan(grupos, destino)


def _retirar(carpeta: Path, *, reintentos: int = REINTENTOS, espera: float = ESPERA_S) -> None:
    """La ``.parcial`` de una copia que no terminó es solo de esta copia: no se deja ocupando el destino.

    086:RF-84 con RF-81: ``shutil.rmtree`` se para en el primer fichero que no puede borrar, y Drive tiene bloqueado
    el último que se subía; se repite como cualquier escritura en el destino. Si aun así queda, se calla: el error que
    importa es el de la copia, y una ``.parcial`` no tiene el nombre de una copia buena.
    """
    try:
        _con_reintentos(lambda: shutil.rmtree(carpeta) if carpeta.exists() else None,
                        reintentos=reintentos, espera=espera)
    except OSError:
        pass


def crear_copia(destino: Path, *, raices: dict[str, Path] | None = None, sin_modelos: bool = False,
                ahora: float | None = None, avisar: Callable[[dict[str, Any]], None] | None = None,
                progreso: Callable[[int, int, str], None] | None = None,
                comprobar_cancelacion: Callable[[], None] | None = None,
                reintentos: int = REINTENTOS, espera: float = ESPERA_S) -> dict[str, Any]:
    """Crea ``<destino>/csg-copia-<fecha>-<id>`` y devuelve su manifiesto.

    ``avisar`` recibe el cálculo de 086:RF-82 antes de escribir nada; si no cabe, ``SinEspacio`` (RF-83).
    ``comprobar_cancelacion`` lanza su excepción entre ficheros: la ``.parcial`` se retira y nada queda con el
    nombre de una copia buena (RF-84).
    """
    momento = time.time() if ahora is None else ahora
    destino, origenes, tipos, grupos, omitidos, errores = _preparar(destino, raices, sin_modelos, momento)
    plan = _resumen_plan(grupos, destino)
    if avisar is not None:
        avisar(plan)
    if not plan['cabe']:
        raise SinEspacio(texto_plan(plan))
    nombre_copia = f"csg-copia-{time.strftime('%Y%m%dT%H%M%S', time.localtime(momento))}-{uuid.uuid4().hex[:8]}"
    parcial = destino / f'.parcial-{nombre_copia}'
    final = destino / nombre_copia
    _con_reintentos(lambda: parcial.mkdir(parents=True), reintentos=reintentos, espera=espera)
    orden = {n: i for i, n in enumerate(origenes)}
    for grupo in grupos:
        grupo['nombres'].sort(key=lambda n: (orden[n[0]], n[1]))
    grupos.sort(key=lambda g: (orden[g['nombres'][0][0]], g['nombres'][0][1]))
    # Solo se lee dos veces un fichero cuyo tamaño comparte con otro: su huella decide si ya está guardado.
    tamanos = Counter(g['bytes'] for g in grupos)
    ficheros: list[dict[str, Any]] = []
    por_huella: dict[tuple[str, int], dict[str, Any]] = {}
    hechos = 0
    try:
        for indice, grupo in enumerate(grupos):
            if comprobar_cancelacion is not None:
                comprobar_cancelacion()
            if progreso is not None:
                progreso(indice, len(grupos), f"{_gb(hechos)} de {_gb(plan['bytes_fisicos'])} GB")
            nombre, relativa, fichero, _ = grupo['nombres'][0]
            critico = any(n[3] for n in grupo['nombres'])
            otros = [{'raiz': n[0], 'ruta': n[1]} for n in grupo['nombres'][1:]]
            try:
                if tamanos[grupo['bytes']] > 1:
                    igual = por_huella.get((sha256_file(fichero), grupo['bytes']))
                    if igual is not None:
                        # 086:RF-78: otro fichero físico con el mismo contenido; se guarda su nombre, no sus bytes.
                        # 086:RF-80: ``fisico`` dice que no era un enlace del primero, y restaurar lo devuelve aparte
                        # (como ``rsync -H``, que solo enlaza lo que ya era un enlace en el origen).
                        fisico = 1 + max((o.get('fisico', 0) for o in igual.get('otros_nombres') or []), default=0)
                        igual.setdefault('otros_nombres', []).extend(
                            {**o, 'fisico': fisico} for o in [{'raiz': nombre, 'ruta': relativa}, *otros])
                        hechos += grupo['bytes']
                        continue
                salida = parcial / 'archivos' / nombre / relativa
                tamano, huella = _con_reintentos(lambda: _copiar_con_huella(fichero, salida), reintentos=reintentos,
                                                 espera=espera, limpiar=lambda: salida.unlink(missing_ok=True))
            except FileNotFoundError:
                (errores if critico else omitidos).append({'ruta': str(fichero), 'motivo': 'desapareció durante la copia'})
                continue
            except OSError as exc:
                errores.append({'ruta': str(fichero), 'motivo': str(exc)})
                continue
            item: dict[str, Any] = {'raiz': nombre, 'ruta': relativa, 'bytes': tamano, 'sha256': huella}
            if otros:
                item['otros_nombres'] = otros
            ficheros.append(item)
            por_huella.setdefault((huella, tamano), item)
            hechos += tamano
        if progreso is not None:
            progreso(len(grupos), len(grupos), f"{_gb(hechos)} de {_gb(plan['bytes_fisicos'])} GB")
        externas = []
        for nombre, raiz in origenes.items():
            if tipos[nombre] == 'directorio':
                externas.extend(_rutas_externas(raiz))
        identidad = rutas_runtime().identidad
        enlaces = sum(len(f.get('otros_nombres') or []) for f in ficheros)
        manifiesto = {
            'version': VERSION_MANIFIESTO, 'creada': momento, 'instalacion': identidad,
            'raices': {n: str(r) for n, r in origenes.items()},
            'tipos_raiz': tipos,
            'ficheros': ficheros, 'bytes_total': sum(f['bytes'] for f in ficheros),
            'bytes_logicos': sum(f['bytes'] * (1 + len(f.get('otros_nombres') or [])) for f in ficheros),
            'nombres': len(ficheros) + enlaces, 'otros_nombres': enlaces,
            'omitidos': omitidos, 'errores': errores, 'rutas_externas_sin_copiar': sorted(set(externas)),
        }
        texto = json.dumps(manifiesto, indent=2, ensure_ascii=False)
        _con_reintentos(lambda: publicar_duradero(parcial / MANIFIESTO, texto), reintentos=reintentos, espera=espera)
        # 086:RF-84: el nombre de copia buena se da al final, de una vez; Drive puede tener la carpeta ocupada.
        _con_reintentos(lambda: parcial.replace(final), reintentos=reintentos, espera=espera)
    except BaseException:
        _retirar(parcial, reintentos=reintentos, espera=espera)
        raise
    sincronizar_carpeta(destino)
    manifiesto['ruta'] = str(final)
    if not errores and 'datos' in origenes:
        # Una copia con errores no calla el aviso: el operador cree tener lo que no tiene.
        write_json_atomic(_registro_ultima(origenes['datos']), {
            'creada': momento, 'ruta': str(final), 'ficheros': len(ficheros),
            'bytes': manifiesto['bytes_total'],
        })
    return manifiesto


def ruta_carpeta_recordada(programa: Path | None = None) -> Path:
    return raiz_local(programa or project_root()) / 'config' / FICHERO_CARPETA


def carpeta_recordada() -> Path | None:
    """086:RF-85: la carpeta de las copias que este equipo usó la última vez, o ``None``."""
    try:
        datos = json.loads(ruta_carpeta_recordada().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    ruta = str(datos.get('ruta') or '').strip() if isinstance(datos, dict) else ''
    return Path(ruta) if ruta else None


def recordar_carpeta(ruta: str) -> Path:
    """086:RF-85: valida y recuerda la carpeta de las copias; una que no es una carpeta de esta máquina se rechaza."""
    texto = (ruta or '').strip().strip('"')
    carpeta = Path(texto)
    if not texto or not carpeta.is_absolute() or not carpeta.is_dir():
        raise ValueError(f'{texto or "(vacía)"}: no es una carpeta de esta máquina.')
    write_json_atomic(ruta_carpeta_recordada(), {'ruta': carpeta.as_posix()})
    return carpeta


def _nombres(item: dict[str, Any]) -> list[tuple[str, str]]:
    """El nombre guardado de un fichero y los demás que tenía (086:RF-79); un manifiesto 1 o 2 solo trae el primero."""
    return [(item['raiz'], item['ruta'])] + [(o['raiz'], o['ruta']) for o in item.get('otros_nombres') or []]


def _leer_manifiesto(copia: Path) -> dict[str, Any]:
    try:
        datos = json.loads((Path(copia) / MANIFIESTO).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CopiaNoValida(f'Sin un manifiesto legible no hay copia: {exc}') from exc
    if not isinstance(datos, dict) or not isinstance(datos.get('ficheros'), list):
        raise CopiaNoValida('El manifiesto no tiene el contenido esperado.')
    if type(datos.get('version')) is not int or datos.get('version') not in VERSIONES_LEIDAS:
        raise CopiaNoValida(f"Manifiesto de la versión {datos.get('version')!r}; este programa lee la "
                            f'{VERSION_MANIFIESTO}. Actualice el programa antes de restaurar.')
    raices = datos.get('raices')
    if (not isinstance(raices, dict) or any(not isinstance(n, str) or not n or n in ('.', '..')
            or Path(n).name != n or not isinstance(r, str) or not r for n, r in raices.items())):
        raise CopiaNoValida('El manifiesto no identifica sus raíces.')
    vistos = set()
    for item in datos['ficheros']:
        if (not isinstance(item, dict) or not isinstance(item.get('raiz'), str)
                or item['raiz'] not in raices or not isinstance(item.get('ruta'), str) or not item['ruta']
                or type(item.get('bytes')) is not int or item['bytes'] < 0
                or not isinstance(item.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])):
            raise CopiaNoValida('Metadatos de archivo no válidos en el manifiesto.')
        otros = item.get('otros_nombres', [])
        if datos['version'] < 3:
            # Antes de la 3 no había otros nombres: uno que aparezca no es de esta copia.
            otros = []
            item.pop('otros_nombres', None)
        if (not isinstance(otros, list) or any(not isinstance(o, dict) or not isinstance(o.get('raiz'), str)
                or o['raiz'] not in raices or not isinstance(o.get('ruta'), str) or not o['ruta']
                or type(o.get('fisico', 0)) is not int or o.get('fisico', 0) < 0 for o in otros)):
            raise CopiaNoValida('Otros nombres de un archivo no válidos en el manifiesto.')
        for raiz, ruta in _nombres(item):
            clave = (raiz, Path(ruta))
            if clave in vistos:
                raise CopiaNoValida('El manifiesto contiene archivos duplicados.')
            vistos.add(clave)
    tipos = ({n: 'configuracion' if n == 'config' else 'directorio' for n in raices}
             if datos['version'] == 1 else datos.get('tipos_raiz'))
    if (not isinstance(tipos, dict) or set(tipos) != set(raices)
            or any(t not in ('archivo', 'directorio', 'configuracion') for t in tipos.values())):
        raise CopiaNoValida('Tipos de raíz del manifiesto no válidos.')
    for nombre, tipo in tipos.items():
        if tipo == 'archivo':
            rutas = [r for item in datos['ficheros'] for n, r in _nombres(item) if n == nombre]
            if len(rutas) != 1 or rutas[0] != Path(raices[nombre]).name:
                raise CopiaNoValida('Una raíz de archivo debe identificar exactamente su fichero.')
    datos['tipos_raiz'] = tipos
    return datos


def _ruta_segura(raiz: str, ruta: str, raices: dict[str, str]) -> bool:
    """El manifiesto es una entrada: una ruta que sale de la copia o de su raíz no se sigue."""
    relativa = Path(str(ruta))
    return not (relativa.is_absolute() or relativa.drive or '..' in relativa.parts or str(raiz) in ('', '.', '..')
                or str(raiz) != Path(str(raiz)).name or raiz not in raices)


def verificar_copia(copia: Path) -> dict[str, Any]:
    """Comprueba cada fichero contra su huella; ``ok`` solo si todos están y son iguales."""
    manifiesto = _leer_manifiesto(copia)
    faltan, distintos = [], []
    for item in manifiesto['ficheros']:
        if not all(_ruta_segura(r, p, manifiesto['raices']) for r, p in _nombres(item)):
            distintos.append(str(item['ruta']))
            continue
        ruta = Path(copia) / 'archivos' / str(item['raiz']) / Path(str(item['ruta']))
        if not ruta.resolve().is_relative_to(Path(copia).resolve()) or _es_redireccion(ruta):
            distintos.append(str(item['ruta']))
        elif not ruta.is_file():
            faltan.append(str(item['ruta']))
        elif ruta.stat().st_size != item['bytes'] or sha256_file(ruta) != item['sha256']:
            distintos.append(str(item['ruta']))
    return {'ok': not faltan and not distintos and not manifiesto.get('errores'), 'faltan': faltan, 'distintos': distintos,
            'errores': manifiesto.get('errores') or [], 'ficheros': len(manifiesto['ficheros']),
            'nombres': sum(len(_nombres(i)) for i in manifiesto['ficheros'])}


def restaurar_copia(copia: Path, *, raices: dict[str, Path] | None = None) -> dict[str, Any]:
    """Devuelve los datos al estado de la copia; lo que hubiera queda apartado, sin borrar nada.

    086:RF-80: cada nombre de un fichero guardado una vez vuelve como enlace duro del primero si la unidad lo
    admite, y como copia con su huella comprobada si no (otra unidad, FAT, una unidad de Drive).
    """
    copia = Path(copia)
    comprobado = verificar_copia(copia)
    if not comprobado['ok']:
        raise CopiaNoValida(f"La copia no está sana y no se restaura: faltan {len(comprobado['faltan'])}, "
                            f"distintos {len(comprobado['distintos'])}, errores al crearla {len(comprobado['errores'])}.")
    manifiesto = _leer_manifiesto(copia)
    solicitados = dict(raices if raices is not None else raices_de_datos())
    destinos = {n: Path(r).resolve() for n, r in solicitados.items()}
    sin_destino = sorted(set(manifiesto['raices']) - set(destinos))
    if sin_destino:
        raise CopiaNoValida(f'La copia trae raíces que aquí no existen: {sin_destino}')
    tipos = manifiesto['tipos_raiz']
    completos = [destinos[n] for n in manifiesto['raices'] if tipos[n] == 'directorio']
    for i, destino in enumerate(completos):
        for otra in completos[i + 1:]:
            if destino.is_relative_to(otra) or otra.is_relative_to(destino):
                raise CopiaNoValida('Los directorios de restauración están solapados.')
    for nombre in manifiesto['raices']:
        destino = destinos[nombre]
        original = Path(solicitados[nombre])
        if _es_redireccion(original) or destino == Path(destino.anchor):
            raise CopiaNoValida(f'Destino de restauración no permitido: {original}')
        if destino.exists() and ((tipos[nombre] == 'archivo') != destino.is_file()):
            raise CopiaNoValida(f'El tipo del destino no coincide con la copia: {destino}')
        if tipos[nombre] == 'directorio' and (destino / '.git').exists():
            raise CopiaNoValida('No se sustituye una raíz de código Git al restaurar datos.')
    seleccionados = set()
    for nombre in manifiesto['raices']:
        objetivos = ([destinos[nombre]] if tipos[nombre] != 'configuracion' else
                     [destinos[nombre] / ruta for item in manifiesto['ficheros'] for n, ruta in _nombres(item)
                      if n == nombre])
        for objetivo in objetivos:
            if objetivo.resolve() in seleccionados:
                raise CopiaNoValida(f'Destino de restauración duplicado: {objetivo}')
            seleccionados.add(objetivo.resolve())
    sello = time.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex
    apartados: list[str] = []
    preparados_dir: list[tuple[Path, Path]] = []
    preparados_arch: list[tuple[Path, Path]] = []
    publicados: list[tuple[Path, Path | None]] = []
    pendientes_originales: list[tuple[Path, Path]] = []
    temporales_dir: dict[str, Path] = {}
    enlaces = copias_de_nombres = 0

    def ubicar(nombre: str, ruta: str) -> Path:
        """Dónde se prepara un nombre antes de publicarlo: en la carpeta temporal de su raíz, o a su lado."""
        if tipos[nombre] == 'directorio':
            return temporales_dir[nombre] / ruta
        fichero = destinos[nombre] if tipos[nombre] == 'archivo' else destinos[nombre] / ruta
        # Si el archivo está bajo otra raíz que se sustituirá, preparar fuera
        # de ella conserva el staging durante ese cambio de directorio.
        padre = min((d for d in completos if fichero.is_relative_to(d)), key=lambda d: len(d.parts), default=None)
        base = padre.parent if padre is not None else fichero.parent
        temporal = base / f'{fichero.name}.restaurando-{sello}-{len(preparados_arch)}'
        preparados_arch.append((temporal, fichero))
        return temporal

    try:
        # Directorios completos primero; archivos y configuración se publican después.
        for nombre in sorted(manifiesto['raices'], key=lambda n: (tipos[n] != 'directorio', n)):
            if tipos[nombre] == 'directorio':
                temporal = destinos[nombre].with_name(f'{destinos[nombre].name}.restaurando-{sello}')
                temporal.mkdir(parents=True, exist_ok=False)
                temporales_dir[nombre] = temporal
                preparados_dir.append((temporal, destinos[nombre]))
        for item in manifiesto['ficheros']:
            primero = ubicar(item['raiz'], item['ruta'])
            _, huella = _copiar_con_huella(copia / 'archivos' / item['raiz'] / item['ruta'], primero)
            if huella != item['sha256']:
                raise CopiaNoValida(f"{item['ruta']} cambió mientras se restauraba.")
            # 086:RF-80: los nombres de un mismo ``fisico`` vuelven enlazados entre sí; uno de otro fichero físico
            # con el mismo contenido, aparte. Un manifiesto 3 sin ``fisico`` es todo del primero, como se escribió.
            cabezas = {0: primero}
            for otro in item.get('otros_nombres') or []:
                nombre_otro = ubicar(otro['raiz'], otro['ruta'])
                nombre_otro.parent.mkdir(parents=True, exist_ok=True)
                cabeza = cabezas.get(otro.get('fisico', 0))
                if cabeza is not None:
                    try:
                        os.link(cabeza, nombre_otro)
                        enlaces += 1
                        continue
                    except OSError:
                        # Otra unidad o un sistema sin enlaces duros: una copia, con su huella comprobada.
                        nombre_otro.unlink(missing_ok=True)
                else:
                    cabezas[otro.get('fisico', 0)] = nombre_otro
                _, huella = _copiar_con_huella(primero, nombre_otro)
                if huella != item['sha256']:
                    raise CopiaNoValida(f"{otro['ruta']} cambió mientras se restauraba.")
                copias_de_nombres += 1
        # Todo preparado antes de cambiar un original; una publicación fallida
        # revierte los cambios ya hechos y conserva lo preparado para diagnóstico.
        for temporal, destino in preparados_dir + preparados_arch:
            destino.parent.mkdir(parents=True, exist_ok=True)
            apartado = None
            if destino.exists():
                apartado = destino.with_name(f'{destino.name}.antes-restaurar-{sello}')
                destino.replace(apartado)
                pendientes_originales.append((apartado, destino))
                apartados.append(str(apartado))
            temporal.replace(destino)
            publicados.append((destino, apartado))
            if apartado is not None:
                pendientes_originales.pop()
            sincronizar_carpeta(destino.parent)
        if 'datos' in destinos:
            # Lo restaurado es de antes de crear la copia, y sin esto avisaría de que no hay ninguna.
            write_json_atomic(_registro_ultima(destinos['datos']), {
                'creada': manifiesto.get('creada'), 'ruta': str(copia.resolve()),
                'ficheros': comprobado['ficheros'], 'bytes': manifiesto.get('bytes_total'),
            })
    except BaseException as exc:
        errores_reversion = []
        for apartado, destino in reversed(pendientes_originales):
            try:
                apartado.replace(destino)
            except OSError as error:
                errores_reversion.append(f'{apartado} -> {destino}: {error}')
        for destino, apartado in reversed(publicados):
            try:
                if destino.exists():
                    destino.replace(destino.with_name(f'{destino.name}.restauracion-no-publicada-{sello}'))
                if apartado is not None:
                    apartado.replace(destino)
            except OSError as error:
                errores_reversion.append(f'{apartado} -> {destino}: {error}')
        if errores_reversion:
            raise CopiaNoValida('Falló la recuperación de originales; se conservan las rutas: '
                                + '; '.join(errores_reversion)) from exc
        raise
    return {'restaurados': comprobado['nombres'], 'ficheros_fisicos': comprobado['ficheros'],
            'enlaces': enlaces, 'copias_de_nombres': copias_de_nombres, 'apartados': apartados,
            'creada': manifiesto.get('creada'),
            'rutas_externas_sin_copiar': manifiesto.get('rutas_externas_sin_copiar') or []}


def _registro_ultima(raiz: Path) -> Path:
    return Path(raiz) / '_mantenimiento' / 'ultima_copia.json'


def dias_maximos() -> float:
    try:
        return float(os.environ.get('CSG_COPIA_MAX_DIAS') or DIAS_MAXIMOS)
    except ValueError:
        return DIAS_MAXIMOS


def estado_copia(raiz: Path, *, ahora: float | None = None) -> dict[str, Any]:
    """Cuándo fue la última copia y si toca avisar (086:RF-47); sin copias también avisa."""
    momento = time.time() if ahora is None else ahora
    maxima = dias_maximos()
    try:
        ultima = json.loads(_registro_ultima(raiz).read_text(encoding='utf-8'))
        creada = float(ultima['creada'])
        ruta = str(ultima.get('ruta') or '') or None
    except (OSError, ValueError, KeyError, TypeError):
        return {'ultima': None, 'ruta': None, 'edad_dias': None, 'maxima_dias': maxima, 'vencida': True,
                'aviso': 'No hay ninguna copia de los datos: hágala desde la web o con tools/copia_datos.py crear.'}
    edad = (momento - creada) / 86400
    vencida = edad > maxima
    return {'ultima': creada, 'ruta': ruta, 'edad_dias': round(edad, 2), 'maxima_dias': maxima, 'vencida': vencida,
            'aviso': (f'La última copia de los datos tiene {edad:.0f} días (el máximo son {maxima:g}): '
                      'hágala desde la web o con tools/copia_datos.py crear.') if vencida else None}


def identidad_instalacion() -> dict[str, Any]:
    """La identidad de esta instalación y dónde están sus datos, sin escribir nada."""
    rutas = rutas_runtime()
    return {'id': rutas.identidad, 'runtime': str(rutas.runtime), 'fichero': str(rutas.checkout / FICHERO_INSTALACION),
            'fijada': (rutas.checkout / FICHERO_INSTALACION).is_file()}
