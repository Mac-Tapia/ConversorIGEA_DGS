"""Qué le falta a esta instalación, qué función afecta y cómo arreglarlo (086:RF-40).

Lo mismo para la orden ``convertersmartgrid doctor`` y para la pantalla de la web: solo lee, no instala ni
conecta con DIgSILENT (ni gasta licencia). Parte de ``runtime.diagnostico_capacidades``, que ya separaba
módulos y drivers, y añade lo que el operador no ve: de cada cosa, la función que se queda sin ella. «Falta
pyodbc» no le dice a nadie que no podrá cargar una base Access.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .. import __version__
from ..edicion import es_edicion_producto
from ..powerfactory_env import pf_python_dir, project_root
from ..runtime_paths import es_programa_instalado, rutas_runtime
from .runtime import DRIVERS_POR_CAPACIDAD, diagnostico_capacidades, integridad_del_front

#: Sin esto no trabaja nada; lo demás deja sin una función, y se dice cuál.
OBLIGATORIAS = ('python', 'web', 'txt', 'interfaz', 'carpeta_datos')
#: Espacio libre por debajo del cual avisa: una conversión de una entrega grande escribe cientos de MB.
ESPACIO_MINIMO_MB = 2048

_REINSTALAR = 'Vuelva a ejecutar el instalador: repone lo que falte sin tocar sus datos.'
_DESARROLLO = 'En desarrollo: python -m pip install -r requirements.txt.'

#: De cada capacidad de ``runtime.MODULOS_POR_CAPACIDAD``: nombre, función que afecta y cómo arreglarlo.
_CAPACIDADES: dict[str, tuple[str, str, str]] = {
    'web': ('Servidor web', 'Toda la interfaz web.', ''),
    'txt': ('Motor de conversión', 'Toda conversión a DGS.', ''),
    'geografia': ('Georreferenciación', 'Coordenadas GPS del DGS y mapas; solo se podría convertir sin geografía.', ''),
    'xlsx': ('Lectura de Excel', 'Libros de demandas, cargas nuevas y medición de cabecera.', ''),
    'pdf': ('Lectura de PDF', 'Leer los documentos del solicitante en factibilidad.', ''),
    'informes': ('Informes en Word', 'Informes de estudio y de factibilidad.', ''),
    'oraculo': ('Flujo sin DIgSILENT', 'Comprobar la red antes de importarla y antes de calibrar.', ''),
    'mdb': ('Fuente Access', 'Cargar una base .mdb de CYMDIST.',
            'Instale Microsoft Access Database Engine de 64 bits, que trae el driver «Microsoft Access Driver (*.mdb, *.accdb)».'),
    'vnr_gis': ('Fuente VNR-GIS', 'Cargar un paquete VNR-GIS.', ''),
    'vnr_sqlserver': ('VNR-GIS desde SQL Server', 'Cargar una copia .bak de VNR-GIS.',
                      'Instale «ODBC Driver 18 for SQL Server» de Microsoft, y SQL Server Express si la copia es local.'),
}


@dataclass(frozen=True)
class Comprobacion:
    clave: str
    nombre: str
    ok: bool
    #: Sin esto no se puede trabajar: el programa no se da por instalado.
    obligatoria: bool
    detalle: str
    #: La función que se queda sin esto.
    afecta: str
    #: Vacío cuando no hay nada que arreglar.
    arreglo: str


def _arreglo_de_paquete(faltan: tuple[str, ...]) -> str:
    return f'Faltan {", ".join(faltan)}. ' + (_REINSTALAR if es_programa_instalado(project_root()) else _DESARROLLO)


def _capacidades(diagnostico: Mapping[str, Any]) -> list[Comprobacion]:
    salida = []
    for clave, (nombre, afecta, arreglo_drivers) in _CAPACIDADES.items():
        estado = diagnostico['capacidades'].get(clave, {'disponible': False, 'modulos_faltantes': (), 'drivers_faltantes': ()})
        modulos, drivers = tuple(estado['modulos_faltantes']), tuple(estado['drivers_faltantes'])
        partes = [_arreglo_de_paquete(modulos)] if modulos else []
        if drivers:
            partes.append(arreglo_drivers or f'Instale {", ".join(drivers)}.')
        # Un driver es del equipo y es opcional. Una librería viene en el paquete: si no carga, la instalación está mal, y
        # un candidato con geopandas sin cargar se daba por bueno hasta que el operador abría un VNR-GIS.
        errores = [str(diagnostico['errores_importacion'].get(m, '')) for m in modulos]
        motivo = next((e for e in errores if e), '')
        salida.append(Comprobacion(
            clave, nombre, bool(estado['disponible']), clave in OBLIGATORIAS or bool(modulos) or clave not in DRIVERS_POR_CAPACIDAD,
            'Disponible.' if estado['disponible'] else f'Falta: {", ".join((*modulos, *drivers))}.' + (f' {motivo}' if motivo else ''),
            afecta, ' '.join(partes)))
    return salida


def _digsilent(carpeta: Callable[[], Path | None]) -> Comprobacion:
    """No se conecta: abrir DIgSILENT gasta licencia y aquí solo se pregunta si está."""
    pf = carpeta()
    afecta = 'Importar en DIgSILENT, calibrar, estudios, obras e informes. Convertir a DGS sigue funcionando.'
    arreglo = ('Instale DIgSILENT PowerFactory 2024 con su Python 3.12, o indique la carpeta de su API con la variable PF_PYTHON.')
    if pf is None:
        return Comprobacion('digsilent', 'DIgSILENT PowerFactory', False, False, 'No se encuentra la API de Python.', afecta, arreglo)
    if not (Path(pf) / 'powerfactory.pyd').is_file():
        return Comprobacion('digsilent', 'DIgSILENT PowerFactory', False, False, f'En {pf} no está powerfactory.pyd.', afecta, arreglo)
    return Comprobacion('digsilent', 'DIgSILENT PowerFactory', True, False, f'API en {pf}.', afecta, '')


def _interfaz(programa: Path) -> Comprobacion:
    afecta = 'La interfaz web: solo respondería la API.'
    dist = Path(os.environ.get('CSG_WEB_FRONTEND', '').strip() or programa / 'frontend' / 'dist')
    if not (dist / 'index.html').is_file():
        arreglo = _REINSTALAR if es_programa_instalado(programa) else 'En desarrollo: cd frontend && npm ci && npm run build.'
        return Comprobacion('interfaz', 'Interfaz web', False, True, 'No está compilada.', afecta, arreglo)
    motivo = integridad_del_front(dist)
    if motivo:
        return Comprobacion('interfaz', 'Interfaz web', False, True, f'Compilación incompleta: {motivo}.', afecta, _REINSTALAR)
    return Comprobacion('interfaz', 'Interfaz web', True, True, 'Compilación completa.', afecta, '')


def _carpeta_datos(programa: Path, espacio_minimo_mb: int = ESPACIO_MINIMO_MB) -> list[Comprobacion]:
    datos = rutas_runtime(programa).runtime
    afecta = 'Guardar espacios, perfiles, resultados e informes.'
    arreglo = f'Dé permiso de escritura sobre {datos} o elija otra carpeta con la variable CSG_DATOS_HOME.'
    prueba = datos / f'.csg-doctor-{os.getpid()}'
    try:
        datos.mkdir(parents=True, exist_ok=True)
        prueba.write_bytes(b'')
        prueba.unlink()
    except OSError as exc:
        return [Comprobacion('carpeta_datos', 'Carpeta de datos', False, True, f'{datos}: {exc}', afecta, arreglo)]
    salida = [Comprobacion('carpeta_datos', 'Carpeta de datos', True, True, str(datos), afecta, '')]
    libre_mb = shutil.disk_usage(datos).free // (1 << 20)
    salida.append(Comprobacion(
        'espacio_libre', 'Espacio en disco', libre_mb >= espacio_minimo_mb, False, f'{libre_mb} MB libres.',
        'Conversiones grandes, resultados e informes.',
        '' if libre_mb >= espacio_minimo_mb else f'Libere espacio: se recomiendan al menos {espacio_minimo_mb} MB.'))
    return salida


def _perfil() -> Comprobacion:
    from ..perfil_esquema import validar_fichero

    afecta = 'Informes, bandas de tensión, moneda y lo que dependa de la empresa.'
    try:
        r = validar_fichero(None, None)
    except (OSError, ValueError) as exc:
        return Comprobacion('perfil', 'Perfil de empresa', False, False, str(exc), afecta,
                            'Corrija el fichero siguiendo PERFIL_EMPRESA.md y compruébelo con «validar-perfil».')
    errores = list(getattr(r, 'errores', ()) or ())
    if errores:
        return Comprobacion('perfil', 'Perfil de empresa', False, False, f'{len(errores)} errores en el perfil.', afecta,
                            'Compruébelo con «convertersmartgrid validar-perfil» y corríjalo siguiendo PERFIL_EMPRESA.md.')
    return Comprobacion('perfil', 'Perfil de empresa', True, False, 'Se puede leer.', afecta, '')


def _calibracion_del_perfil() -> Comprobacion:
    """086:RF-55: sin fichas de transformadores de SED ni tamaño de banco, la calibración no resuelve una SED sobrecargada.

    Programa instalado de prueba (2026-11-11): sin perfil, «Perfil de empresa: se puede leer» salía en verde y CA101 no
    quedó válido porque SE20701 (1 506 kVA de cliente en 50 kVA) no se pudo cambiar por su ficha (101) ni se pusieron bancos.
    """
    from ..perfil_empresa import datos_perfil, seccion_transformadores_sed

    nombre, afecta = 'Calibración del perfil', 'Calibrar un alimentador con una SED sobrecargada o sin reactiva suficiente.'
    try:
        datos = datos_perfil()
    except (OSError, ValueError):
        datos = {}
    cal = dict(datos.get('calibracion') or {})
    fichas = seccion_transformadores_sed(datos) or {}            # 020:RF-63: del perfil o las del conversor
    de_donde = 'las del conversor (NTP 370.400)' if fichas.get('origen') == 'conversor' else 'las del perfil'
    faltan = [texto for texto, hay in (('las fichas de transformadores de SED (calibracion.transformadores_sed)',
                                        bool(fichas.get('tablas'))),
                                       ('el tamaño de banco por tensión (calibracion.bancos_kvar_por_tension)',
                                        bool(cal.get('bancos_kvar_por_tension')))) if not hay]
    if not faltan:
        return Comprobacion('perfil_calibracion', nombre, True, False,
                            f'Fichas de transformadores ({de_donde}) y bancos por tensión.', afecta, '')
    return Comprobacion('perfil_calibracion', nombre, False, False, 'Faltan ' + ' y '.join(faltan) + '.', afecta,
                        'Complételas en el perfil de su empresa siguiendo PERFIL_EMPRESA.md, con las fichas de su norma (en '
                        'Perú, NTP 370.400), y compruébelo con «validar-perfil».')


def _ia(buscar: Callable[[str], Any]) -> Comprobacion:
    """El complemento de IA es opcional en la 1.0: faltarle no estropea nada de lo que se vende (086:RF-37)."""
    hay = buscar('torch') is not None
    afecta = 'Modelos locales del asistente de órdenes, en beta. Convertir, calibrar e informes no los usan.'
    return Comprobacion('complemento_ia', 'Complemento de IA', hay, False, 'Instalado.' if hay else 'No instalado.', afecta,
                        '' if hay else 'Es opcional: si quiere esos modelos, instale el complemento de IA según el manual de instalación.')


def _tesseract_en_sus_rutas() -> str | None:
    from ..documentos_solicitud import tesseract

    return tesseract()


def _tesseract(buscar: Callable[[str], str | None],
               hallar: Callable[[], str | None] = _tesseract_en_sus_rutas) -> Comprobacion:
    # 091:RF-32: instalado en Archivos de programa, fuera del PATH, leía los PDF y aquí decía que no.
    hay = buscar('tesseract') or os.environ.get('CSG_TESSERACT') or hallar()
    return Comprobacion('tesseract', 'Tesseract OCR', bool(hay), False, 'Encontrado.' if hay else 'No se encuentra.',
                        'Leer un PDF escaneado del solicitante; un PDF con texto se lee sin él.',
                        '' if hay else 'Es opcional: instale Tesseract con el idioma español, en el PATH o con la variable CSG_TESSERACT.')


def _python_propio() -> Comprobacion:
    """Sin PYTHONHOME, el Python del programa añade a su ruta las carpetas de otro del registro de Windows."""
    propias = [Path(sys.prefix).resolve(), *(Path(p).resolve() for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p)]
    ajenas = [p for p in sys.path if p and not any(Path(p).resolve().is_relative_to(base) for base in propias)]
    return Comprobacion('python_propio', 'Python del programa', not ajenas, False,
                        f'Lee {len(ajenas)} carpetas de otro Python del equipo.' if ajenas else 'Solo usa sus propias librerías.',
                        'Cualquier función: podría cargar una librería de otra instalación.',
                        'Abra el programa con su acceso directo o con csg.cmd, que preparan su entorno.' if ajenas else '')


def _edicion() -> Comprobacion:
    producto = es_edicion_producto()
    return Comprobacion('edicion', 'Edición', True, False, 'Producto.' if producto else 'Desarrollo.', 'Qué funciones se ofrecen.', '')


def diagnosticar(
    *, importer: Callable[[str], object] = importlib.import_module, drivers: Callable[[], object] | None = None,
    version: tuple[int, ...] | None = None, carpeta_pf: Callable[[], Path | None] = pf_python_dir,
    programa: Path | None = None, buscar_modulo: Callable[[str], Any] = importlib.util.find_spec,
    buscar_programa: Callable[[str], str | None] = shutil.which, espacio_minimo_mb: int = ESPACIO_MINIMO_MB,
) -> dict[str, Any]:
    """El informe del doctor. Las dependencias se inyectan para poder quitar cada requisito en una prueba."""
    raiz = project_root() if programa is None else programa
    capacidades = diagnostico_capacidades(importer, version=version, drivers=drivers)
    python_ok = bool(capacidades['python_valido'])
    comprobaciones = [
        Comprobacion('python', 'Python', python_ok, True, f'Python {capacidades["python"]}.',
                     'Todo el programa, y hablar con DIgSILENT, cuya API solo carga en 3.12.',
                     '' if python_ok else f'Se requiere 3.12. {_REINSTALAR}'),
        *_capacidades(capacidades), _interfaz(raiz), *_carpeta_datos(raiz, espacio_minimo_mb),
        _digsilent(carpeta_pf), _perfil(), _calibracion_del_perfil(), _ia(buscar_modulo), _tesseract(buscar_programa), _edicion(),
        *([_python_propio()] if es_programa_instalado(raiz) else []),
    ]
    filas = [asdict(c) for c in comprobaciones]
    return {'version': __version__, 'instalado': es_programa_instalado(raiz), 'python': sys.version.split()[0],
            'listo': all(c.ok for c in comprobaciones if c.obligatoria),
            'pendientes': sum(1 for c in comprobaciones if not c.ok), 'comprobaciones': filas}


def texto_del_informe(informe: Mapping[str, Any]) -> str:
    lineas = [f'ConverterSmartGrid {informe["version"]}: ' + ('listo para trabajar.' if informe['listo'] else 'falta algo imprescindible.')]
    for c in informe['comprobaciones']:
        lineas.append(f'[{"bien" if c["ok"] else "FALTA" if c["obligatoria"] else "aviso"}] {c["nombre"]}: {c["detalle"]}')
        if not c['ok']:
            lineas.append(f'    Afecta a: {c["afecta"]}')
            if c['arreglo']:
                lineas.append(f'    Cómo arreglarlo: {c["arreglo"]}')
    return '\n'.join(lineas)
