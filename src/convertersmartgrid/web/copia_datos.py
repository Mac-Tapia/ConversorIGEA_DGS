"""Copia y restauración de los datos del conversor, con manifiesto (086:RF-10, RF-47).

Qué se copia lo decide la misma regla que la limpieza diaria (``retencion.py``): una ejecución
sin referencias, sin modelo ni informe y de más de siete días la retiraría la limpieza, y aquí
tampoco entra; ``tmp`` y los automáticos sin uso tampoco. Lo demás entra entero. Los ficheros de
fuera de los datos a los que apunta un espacio (un TXT en otra unidad) no se copian: son del
operador, y el manifiesto los lista para que se sepa que hay que guardarlos aparte.

Una copia nunca queda a medias con aspecto de buena: se escribe en una carpeta ``.parcial`` y solo
se le da su nombre con todo copiado y el manifiesto sincronizado. Restaurar comprueba cada huella
antes de tocar nada, y lo que hubiera se aparta en vez de borrarse.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from itertools import chain
from pathlib import Path
from typing import Any

from ..powerfactory_env import project_root
from ..runtime_paths import es_programa_instalado, raiz_local
from ..runtime_paths import FICHERO_INSTALACION, rutas_runtime
from ..util import publicar_duradero, sha256_file, sincronizar_carpeta, write_json_atomic
from .jobs import INTERRUMPIDO
from .retencion import PESOS, RUN_EN_TEXTO, es_valioso
from .source_runs import valid_run_id
from .workspace import CAMPOS_CON_RUTAS, data_root, expandir_rutas, raiz_componente

VERSION_MANIFIESTO = 2
MANIFIESTO = 'manifiesto.json'
#: Antigüedad de la última copia a partir de la cual se avisa; se cambia con ``CSG_COPIA_MAX_DIAS``.
DIAS_MAXIMOS = 7.0
SIETE_DIAS_S = 7 * 86400
#: Local y fuera de git: si se pierde, no hay de dónde recuperarlo.
FICHEROS_CONFIG = ('perfil_empresa.json', 'line_type_aliases.json')
_ESPACIO_RE = re.compile(r'[a-f0-9]{8,32}')
_MODELOS = ('_asistente', '_digital_twin')


class CopiaNoValida(ValueError):
    """La copia está incompleta o alterada: no se restaura, y nada se ha tocado."""


def raices_de_datos(checkout: Path | None = None) -> dict[str, Path]:
    """Dónde están hoy los datos: los espacios, los heredados de ``output/web`` y la configuración local."""
    programa = checkout or project_root()
    raices = {'datos': data_root()}
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
        ruta = raiz_componente(componente, variable)
        if not any(ruta.resolve().is_relative_to(base.resolve()) for n, base in raices.items() if n != 'config'):
            raices[nombre] = ruta
    from ..perfil_empresa import ruta_perfil_activo

    perfil = ruta_perfil_activo()
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


def trabajos_en_marcha(raiz: Path) -> list[str]:
    """Trabajos sin terminar anotados en el diario: copiar o restaurar en medio mezclaría estados."""
    carpeta = raiz / '_trabajos'
    if not carpeta.is_dir():
        return []
    en_marcha = []
    for ruta in carpeta.glob('*.json'):
        try:
            datos = json.loads(ruta.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if datos.get('status') != INTERRUMPIDO:
            en_marcha.append(str(datos.get('title') or ruta.stem))
    return en_marcha


def crear_copia(destino: Path, *, raices: dict[str, Path] | None = None, sin_modelos: bool = False,
                ahora: float | None = None) -> dict[str, Any]:
    """Crea ``<destino>/csg-copia-<fecha>-<id>`` y devuelve su manifiesto."""
    momento = time.time() if ahora is None else ahora
    origenes, tipos, extras = _planificar_raices(raices if raices is not None else raices_de_datos())
    destino = Path(destino).resolve()
    for nombre, raiz in origenes.items():
        if nombre != 'config' and destino.is_relative_to(raiz.resolve()):
            raise ValueError(f'La copia no puede guardarse dentro de los datos que copia: {raiz}')
    nombre_copia = f"csg-copia-{time.strftime('%Y%m%dT%H%M%S', time.localtime(momento))}-{uuid.uuid4().hex[:8]}"
    parcial = destino / f'.parcial-{nombre_copia}'
    final = destino / nombre_copia
    parcial.mkdir(parents=True)
    ficheros, omitidos, errores, externas = [], [], [], []
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
            try:
                tamano, huella = _copiar_con_huella(fichero, parcial / 'archivos' / nombre / relativa)
            except FileNotFoundError:
                registro = (errores if tipos[nombre] in ('archivo', 'configuracion')
                            or fichero in extras.get(nombre, []) else omitidos)
                registro.append({'ruta': str(fichero), 'motivo': 'desapareció durante la copia'})
                continue
            except OSError as exc:
                errores.append({'ruta': str(fichero), 'motivo': str(exc)})
                continue
            ficheros.append({'raiz': nombre, 'ruta': relativa, 'bytes': tamano, 'sha256': huella})
        if tipos[nombre] == 'directorio':
            externas.extend(_rutas_externas(raiz))
    identidad = rutas_runtime().identidad
    manifiesto = {
        'version': VERSION_MANIFIESTO, 'creada': momento, 'instalacion': identidad,
        'raices': {n: str(r) for n, r in origenes.items()},
        'tipos_raiz': tipos,
        'ficheros': ficheros, 'bytes_total': sum(f['bytes'] for f in ficheros),
        'omitidos': omitidos, 'errores': errores, 'rutas_externas_sin_copiar': sorted(set(externas)),
    }
    publicar_duradero(parcial / MANIFIESTO, json.dumps(manifiesto, indent=2, ensure_ascii=False))
    parcial.replace(final)
    sincronizar_carpeta(destino)
    manifiesto['ruta'] = str(final)
    if not errores and 'datos' in origenes:
        # Una copia con errores no calla el aviso: el operador cree tener lo que no tiene.
        write_json_atomic(_registro_ultima(origenes['datos']), {
            'creada': momento, 'ruta': str(final), 'ficheros': len(ficheros),
            'bytes': manifiesto['bytes_total'],
        })
    return manifiesto


def _leer_manifiesto(copia: Path) -> dict[str, Any]:
    try:
        datos = json.loads((Path(copia) / MANIFIESTO).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CopiaNoValida(f'Sin un manifiesto legible no hay copia: {exc}') from exc
    if not isinstance(datos, dict) or not isinstance(datos.get('ficheros'), list):
        raise CopiaNoValida('El manifiesto no tiene el contenido esperado.')
    if type(datos.get('version')) is not int or datos.get('version') not in (1, VERSION_MANIFIESTO):
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
        clave = (item['raiz'], Path(item['ruta']))
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
            items = [f for f in datos['ficheros'] if f.get('raiz') == nombre]
            if len(items) != 1 or items[0].get('ruta') != Path(raices[nombre]).name:
                raise CopiaNoValida('Una raíz de archivo debe identificar exactamente su fichero.')
    datos['tipos_raiz'] = tipos
    return datos


def verificar_copia(copia: Path) -> dict[str, Any]:
    """Comprueba cada fichero contra su huella; ``ok`` solo si todos están y son iguales."""
    manifiesto = _leer_manifiesto(copia)
    faltan, distintos = [], []
    for item in manifiesto['ficheros']:
        relativa = Path(str(item['ruta']))
        # El manifiesto es una entrada: una ruta que sale de la copia no se sigue.
        if (relativa.is_absolute() or '..' in relativa.parts or str(item['raiz']) in ('', '.', '..')
                or str(item['raiz']) != Path(str(item['raiz'])).name or item['raiz'] not in manifiesto['raices']):
            distintos.append(str(item['ruta']))
            continue
        ruta = Path(copia) / 'archivos' / str(item['raiz']) / relativa
        if not ruta.resolve().is_relative_to(Path(copia).resolve()) or _es_redireccion(ruta):
            distintos.append(str(item['ruta']))
        elif not ruta.is_file():
            faltan.append(str(item['ruta']))
        elif ruta.stat().st_size != item['bytes'] or sha256_file(ruta) != item['sha256']:
            distintos.append(str(item['ruta']))
    return {'ok': not faltan and not distintos and not manifiesto.get('errores'), 'faltan': faltan, 'distintos': distintos,
            'errores': manifiesto.get('errores') or [], 'ficheros': len(manifiesto['ficheros'])}


def restaurar_copia(copia: Path, *, raices: dict[str, Path] | None = None) -> dict[str, Any]:
    """Devuelve los datos al estado de la copia; lo que hubiera queda apartado, sin borrar nada."""
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
                     [destinos[nombre] / item['ruta'] for item in manifiesto['ficheros'] if item['raiz'] == nombre])
        for objetivo in objetivos:
            if objetivo.resolve() in seleccionados:
                raise CopiaNoValida(f'Destino de restauración duplicado: {objetivo}')
            seleccionados.add(objetivo.resolve())
    sello = time.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex
    apartados: list[str] = []
    preparados: list[tuple[Path, Path]] = []
    publicados: list[tuple[Path, Path | None]] = []
    pendientes_originales: list[tuple[Path, Path]] = []
    try:
        # Directorios completos primero; archivos y configuración se publican después.
        for nombre in sorted(manifiesto['raices'], key=lambda n: (tipos[n] != 'directorio', n)):
            destino = destinos[nombre]
            items = [i for i in manifiesto['ficheros'] if i['raiz'] == nombre]
            if tipos[nombre] != 'directorio':
                for item in items:
                    fichero = destino if tipos[nombre] == 'archivo' else destino / item['ruta']
                    # Si el archivo está bajo otra raíz que se sustituirá, preparar fuera
                    # de ella conserva el staging durante ese cambio de directorio.
                    padre = min((d for d in completos if fichero.is_relative_to(d)),
                                key=lambda d: len(d.parts), default=None)
                    base = padre.parent if padre is not None else fichero.parent
                    temporal = base / f'{fichero.name}.restaurando-{sello}-{len(preparados)}'
                    _, huella = _copiar_con_huella(copia / 'archivos' / nombre / item['ruta'], temporal)
                    if huella != item['sha256']:
                        raise CopiaNoValida(f"{item['ruta']} cambió mientras se restauraba.")
                    preparados.append((temporal, fichero))
                continue
            temporal = destino.with_name(f'{destino.name}.restaurando-{sello}')
            temporal.mkdir(parents=True, exist_ok=False)
            for item in items:
                _, huella = _copiar_con_huella(copia / 'archivos' / nombre / item['ruta'], temporal / item['ruta'])
                if huella != item['sha256']:
                    raise CopiaNoValida(f"{item['ruta']} cambió mientras se restauraba.")
            preparados.append((temporal, destino))
        # Todo preparado antes de cambiar un original; una publicación fallida
        # revierte los cambios ya hechos y conserva lo preparado para diagnóstico.
        for temporal, destino in preparados:
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
    return {'restaurados': comprobado['ficheros'], 'apartados': apartados, 'creada': manifiesto.get('creada'),
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
                'aviso': 'No hay ninguna copia de los datos: ejecute tools/copia_datos.py crear.'}
    edad = (momento - creada) / 86400
    vencida = edad > maxima
    return {'ultima': creada, 'ruta': ruta, 'edad_dias': round(edad, 2), 'maxima_dias': maxima, 'vencida': vencida,
            'aviso': (f'La última copia de los datos tiene {edad:.0f} días (el máximo son {maxima:g}): '
                      'ejecute tools/copia_datos.py crear.') if vencida else None}


def identidad_instalacion() -> dict[str, Any]:
    """La identidad de esta instalación y dónde están sus datos, sin escribir nada."""
    rutas = rutas_runtime()
    return {'id': rutas.identidad, 'runtime': str(rutas.runtime), 'fichero': str(rutas.checkout / FICHERO_INSTALACION),
            'fijada': (rutas.checkout / FICHERO_INSTALACION).is_file()}
