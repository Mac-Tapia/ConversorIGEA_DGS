"""Entrenamiento en Colab como una opción más del local: paquete, cuaderno y vuelta del candidato (spec 113).

El 2026-11-26 el usuario pidió entrenar en Colab Pro «con todos los datasets reales» y que el modelo vuelva para
integrarse en la operación; y añadió: «todo lo que se está haciendo para Google Colab debe ser una opción, que no
limite ni impida el entrenamiento local». Por eso aquí no hay otro entrenamiento: el cuaderno ejecuta en Colab las
mismas órdenes de ``tools/`` que se ejecutan en el equipo, y lo que vuelve pasa por las mismas puertas locales
(113:RF-16). Este módulo solo hace lo que el viaje añade:

* el paquete: qué datos salen, con su huella y su manifiesto; nunca un conjunto sellado ni un dato crudo de la
  distribuidora (RF-5, RF-6);
* la vuelta: el candidato se acepta solo si su revisión, sus artefactos y el paquete con que se entrenó cuadran, y se
  deja en una carpeta local sin activarlo; su puerta es la orden local de su familia (RF-10, RF-11);
* el aviso de datos nuevos para reentrenar (RF-13).

No usa la red: el paquete se escribe en la carpeta de Google Drive de escritorio (``G:/Mi unidad/...``), que Drive
sincroniza solo y Colab monta; así no depende del OAuth de la 109. Sin esa carpeta, la opción Colab no aparece y lo
local sigue igual.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from ..dominio.util import write_json_atomic
from .asistente.corpus_redaccion import sin_nombres

SCHEMA_PAQUETE = 'csg-paquete-colab-v1'
SCHEMA_CANDIDATO = 'csg-candidato-colab-v1'
CUADERNO = 'notebooks/ConverterSmartGrid.ipynb'
#: Variable que fija la carpeta de Drive; si no, la de Google Drive de escritorio, si existe.
VARIABLE_DRIVE = 'CSG_DRIVE_COLAB'
DRIVE_ESCRITORIO = Path('G:/Mi unidad/ConverterSmartGrid/colab')

#: 113:RF-6: los datos crudos de la distribuidora nunca salen (TXT, Access, copias de SQL Server, libros, DGS y PFD).
EXTENSIONES_CRUDAS = frozenset({'.txt', '.mdb', '.accdb', '.bak', '.xlsx', '.xlsm', '.xls', '.xlsb', '.dgs', '.pfd'})
#: 113:RF-6: ni los conjuntos sellados de evaluación; se reconocen por el nombre de su carpeta o fichero.
_SELLADO = re.compile(r'(?i)(sellad|sealed|^prueba(\.|_|$)|^test(\.|_|$)|holdout)')

#: 113:RF-5: qué se anonimiza en cada familia. «texto»: cada cadena de los JSONL pasa por ``sin_nombres`` (072:RF-49);
#: «en_origen»: el dataset ya se construyó anonimizado y su propio manifiesto lleva la huella de cada fichero, así que se
#: copia byte a byte (anonimizarlo otra vez cambiaría sus bytes y su orden lo rechazaría en Colab); «tal_cual»: la red
#: y las curvas son lo que el modelo aprende y van como están. El manifiesto del paquete dice cuál se aplicó.
FAMILIAS: dict[str, dict[str, Any]] = {
    # 072 T9b: el alumno de redacción del PIDE; su orden y su reanudación (047:RF-84) están comprobadas con su --help.
    'asistente_redaccion': {'anonimizacion': 'en_origen',
                            'entrenar': 'tools/asistente_qlora.py entrenar --dataset {datos} --salida {salida} '
                                        '--epocas {epocas} --semilla {semilla}',
                            'reanudar': '--reanudar {punto}',
                            # Solo el QLoRA exige el experimento del plan; antes el cuaderno lo añadía a toda orden, y
                            # cualquier otro guion habría salido con «unrecognized arguments» (113 T8, 2026-11-27).
                            'autorizar': '--experimento-autorizado {experimento}',
                            'puerta': 'tools/asistente_qlora.py evaluar'},
    # 113 T8 (2026-11-27): cada orden de abajo se ensayó en el equipo con datos sintéticos, empaquetados con
    # ``preparar_paquete`` y entrenados desde la carpeta ``datos`` del paquete, como lo hará Colab.
    # 089: la competición de pronóstico de cabecera sobre el dataset limpio que deja ``--guardar-dataset`` (Parquet con
    # su huella; nunca los libros). Las curvas son lo que aprende: van tal cual. Las redes que pesan en el equipo
    # (nhits, patchtst, tft, gru) son las que ganan en Colab; los pasos y la puerta son los fijados en la 089, así que
    # ``{epocas}`` no cambia nada aquí y cada semilla es un candidato. No guarda pesos: el candidato es su informe con
    # el ganador, y la puerta local vuelve a medir en el equipo con la misma orden y el mismo dataset.
    'pronostico_demanda': {'anonimizacion': 'tal_cual',
                           'entrenar': 'tools/pronostico_demanda.py --dataset {datos} '
                                       '--modelos nhits,patchtst,tft,gru,lightgbm --clase cabecera '
                                       '--semilla {semilla} --output-json {salida}/competicion.json',
                           'puerta': 'tools/pronostico_demanda.py --dataset'},
    # 074: la política GATv2 con crítico central sobre el grafo del oráculo (``grafo.json`` en el paquete); deja sus
    # pesos y su manifiesto en ``{salida}/modelo`` para ``madrl_puerta.py aplicar``, que la mide en las redes que no
    # vio, y esas se quedan en el equipo (113:RF-6). Límites, banco y 40 iteraciones son los de la corrida de la 074
    # T7 (2026-11-21); la puerta los relee del manifiesto del modelo. MaskablePPO no entra: su espacio de acciones es
    # el de su red y no se guarda para otra (074:RF-13). Sin punto de control: cada semilla se rehace entera.
    'madrl_obras': {'anonimizacion': 'tal_cual',
                    'entrenar': 'tools/madrl_entrenar.py --grafo {datos}/grafo.json --tension-min 0.95 '
                                '--tension-max 1.05 --carga-max 100 --banco-mvar 0.3 --costo-banco 1 --politica gatv2 '
                                '--iteraciones 40 --semilla {semilla} --dispositivo cuda --salida {salida}/resultado.json '
                                '--modelo-salida {salida}/modelo',
                    'puerta': 'tools/madrl_puerta.py aplicar'},
    # Fuera todavía (113 T8), cada una con su motivo, porque su guion no entrena desde un paquete sin cambiarlo:
    # el intérprete (asistente_entrenar.py) lee el almacén del asistente o un dataset v2 que exige su «test.jsonl», y
    # lo sellado no sale (RF-6); la PINN (digital_twin_entrenar.py) escribe sus modelos y su índice dentro del búfer,
    # que sería el paquete; la GRU temporal lee los libros de medición, que son datos crudos; MASAC (114) no tiene guion.
}

_DETALLE_ANONIMIZACION = {
    'texto': 'nombres de empresa, sede, instalación y lugares ocultos al empaquetar',
    'en_origen': 'anonimizado al construir el dataset; copiado byte a byte',
    'tal_cual': 'red y curvas tal cual: es lo que aprende el modelo',
}

#: Dónde se puede entrenar. «local» siempre (113:RF-16).
LOCAL, COLAB = 'local', 'colab'


class PaqueteProhibido(ValueError):
    """El paquete llevaría algo que nunca sale del equipo (113:RF-6)."""


class CandidatoRechazado(ValueError):
    """El candidato traído no cuadra con su revisión, sus artefactos o su paquete (113:RF-10)."""


def _sha(ruta: Path) -> str:
    with ruta.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _canonico(valor: Any) -> bytes:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def carpeta_drive(environ: Mapping[str, str] | None = None) -> Path | None:
    """La carpeta de Drive para Colab, o ``None`` si no hay: entonces solo se ofrece lo local (113:RF-16)."""
    entorno = os.environ if environ is None else environ
    if entorno.get(VARIABLE_DRIVE):
        return Path(entorno[VARIABLE_DRIVE])
    # Drive para escritorio crea «Mi unidad»; la carpeta del proyecto dentro se crea al preparar el primer paquete.
    return DRIVE_ESCRITORIO if DRIVE_ESCRITORIO.parent.parent.is_dir() else None


def opciones_de_entrenamiento(drive: Path | None) -> list[dict[str, Any]]:
    """Las opciones que ve el operador: este equipo siempre; Colab solo con su carpeta de Drive (113:RF-16)."""
    opciones = [{'donde': LOCAL, 'disponible': True, 'texto': 'En este equipo'}]
    opciones.append({'donde': COLAB, 'disponible': drive is not None, 'texto': 'En Colab Pro',
                     **({} if drive is not None else {'motivo': 'sin carpeta de Google Drive'})})
    return opciones


def repositorio_de(remoto: str) -> str:
    """«dueño/repositorio» de GitHub desde la URL del remoto ``origin`` (https o ssh).

    El nombre no se fija en el código: sale del clon, así un clon con otro nombre o una bifurcación abre su propio
    cuaderno, y Colab clona el mismo repositorio del que salió el paquete (plan 113).
    """
    m = re.fullmatch(r'(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?/?',
                     remoto.strip())
    if not m:
        raise ValueError(f'el remoto origin no es de GitHub: {remoto.strip() or "(vacío)"}')
    return m.group(1)


def url_colab(revision: str, *, repositorio: str, cuaderno: str = CUADERNO) -> str:
    """El cuaderno en la revisión exacta, abierto desde GitHub: el código de Colab es el del commit (plan 113)."""
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('la revisión debe ser un commit completo de 40 caracteres')
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repositorio):
        raise ValueError(f'repositorio de GitHub inválido: {repositorio}')
    return f'https://colab.research.google.com/github/{repositorio}/blob/{revision}/{cuaderno}'


def cambios_sin_commit(porcelana: str) -> list[str]:
    """113:RF-4: los ficheros con cambios sin commit (salida de ``git status --porcelain``); Colab no los vería."""
    return [linea[3:] for linea in porcelana.splitlines() if linea.strip()]


def prohibidos(ficheros: Iterable[Path], raiz: Path) -> list[str]:
    """113:RF-6: lo que no puede salir: datos crudos y conjuntos sellados, con su motivo."""
    malos = []
    for ruta in ficheros:
        rel = ruta.relative_to(raiz)
        if ruta.suffix.lower() in EXTENSIONES_CRUDAS:
            malos.append(f'{rel.as_posix()}: dato crudo de la distribuidora ({ruta.suffix.lower()})')
        elif any(_SELLADO.search(parte) for parte in rel.parts):
            malos.append(f'{rel.as_posix()}: conjunto sellado de evaluación')
    return malos


def _anonimizar_valor(valor: Any, catalogo) -> Any:
    if isinstance(valor, str):
        return sin_nombres(valor, catalogo)
    if isinstance(valor, list):
        return [_anonimizar_valor(v, catalogo) for v in valor]
    if isinstance(valor, dict):
        return {k: _anonimizar_valor(v, catalogo) for k, v in valor.items()}
    return valor


#: 113:RF-6: campos de los metadatos de un dataset que nunca salen del equipo, en cualquier modo: dicen los libros de la
#: distribuidora de los que salió (su nombre y su ruta). El ``dataset.json`` de ``pronostico_demanda.py
#: --guardar-dataset`` los lleva (113 T8, 2026-11-27); las curvas, que son lo que se aprende, sí salen.
CAMPOS_QUE_NO_SALEN = {'dataset.json': ('libros', 'avisos')}


def _copiar(origen: Path, destino: Path, modo: str, catalogo) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    quitar = CAMPOS_QUE_NO_SALEN.get(origen.name.lower())
    if quitar:
        try:
            datos = json.loads(origen.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            datos = None
        if isinstance(datos, dict):
            limpio = {k: v for k, v in datos.items() if k not in quitar}
            write_json_atomic(destino, limpio)
            return
    if modo == 'texto' and origen.suffix.lower() == '.jsonl':
        with origen.open(encoding='utf-8') as f, destino.open('w', encoding='utf-8', newline='\n') as g:
            for linea in f:
                if linea.strip():
                    g.write(json.dumps(_anonimizar_valor(json.loads(linea), catalogo), ensure_ascii=False) + '\n')
        return
    shutil.copy2(origen, destino)


def preparar_paquete(origen: Path | str, *, familia: str, revision: str, destino: Path | str,
                     repositorio: str, catalogo=None, ahora: Callable[[], datetime] = datetime.now) -> dict[str, Any]:
    """Deja en ``destino`` el paquete de un dataset con su manifiesto; nada a medias (113:RF-4, RF-5, RF-6, RF-9).

    Se escribe en una carpeta temporal junto al destino y se publica con un solo ``rename``: Drive nunca sincroniza un
    paquete incompleto. Devuelve el manifiesto.
    """
    if familia not in FAMILIAS:
        raise ValueError(f'familia desconocida: {familia} (conocidas: {", ".join(sorted(FAMILIAS))})')
    url_colab(revision, repositorio=repositorio)           # valida la revisión y el repositorio
    origen, destino = Path(origen), Path(destino)
    ficheros = sorted(p for p in origen.rglob('*') if p.is_file())
    if not ficheros:
        raise ValueError(f'{origen}: el dataset no tiene ficheros')
    malos = prohibidos(ficheros, origen)
    if malos:
        raise PaqueteProhibido('no sale del equipo: ' + '; '.join(malos))
    modo = FAMILIAS[familia]['anonimizacion']
    destino.mkdir(parents=True, exist_ok=True)
    temporal = destino / f'.preparando_{os.getpid()}'
    shutil.rmtree(temporal, ignore_errors=True)
    try:
        lista = []
        for ruta in ficheros:
            rel = ruta.relative_to(origen).as_posix()
            copia = temporal / 'datos' / rel
            _copiar(ruta, copia, modo, catalogo)
            lista.append({'ruta': rel, 'sha256': _sha(copia), 'bytes': copia.stat().st_size,
                          'sha256_origen': _sha(ruta)})
        huella = hashlib.sha256(_canonico(lista)).hexdigest()
        manifiesto = {
            'schema': SCHEMA_PAQUETE, 'familia': familia, 'revision': revision, 'repositorio': repositorio,
            'huella': huella,
            'creado': ahora().isoformat(timespec='seconds'), 'origen': origen.name,
            'anonimizacion': {'modo': modo, 'detalle': _DETALLE_ANONIMIZACION[modo]},
            'excluidos': 'datos crudos (TXT, MDB, .bak, libros, DGS, PFD) y conjuntos sellados (113:RF-6)',
            'ficheros': lista,
        }
        write_json_atomic(temporal / 'manifiesto.json', manifiesto)
        final = destino / f'{familia}_{revision[:8]}_{huella[:8]}'
        if final.exists():                                  # el mismo paquete ya está: misma huella, mismo contenido
            shutil.rmtree(temporal)
            return verificar_paquete(final)
        os.replace(temporal, final)
        return manifiesto
    finally:
        shutil.rmtree(temporal, ignore_errors=True)


def verificar_paquete(carpeta: Path | str) -> dict[str, Any]:
    """Relee un paquete y comprueba cada huella; lo usa la primera celda del cuaderno antes de entrenar."""
    carpeta = Path(carpeta)
    manifiesto = json.loads((carpeta / 'manifiesto.json').read_text(encoding='utf-8'))
    if manifiesto.get('schema') != SCHEMA_PAQUETE:
        raise ValueError(f'{carpeta}: no es un paquete de Colab ({manifiesto.get("schema")})')
    for f in manifiesto['ficheros']:
        ruta = carpeta / 'datos' / f['ruta']
        if not ruta.is_file() or _sha(ruta) != f['sha256']:
            raise ValueError(f'{carpeta.name}: {f["ruta"]} no coincide con su huella')
    if hashlib.sha256(_canonico(manifiesto['ficheros'])).hexdigest() != manifiesto['huella']:
        raise ValueError(f'{carpeta.name}: la lista de ficheros no coincide con la huella del paquete')
    return manifiesto


def manifiesto_candidato(*, familia: str, revision: str, paquete: str, semilla: int, entorno: Mapping[str, Any],
                         hiperparametros: Mapping[str, Any], metricas: Mapping[str, Any], carpeta: Path | str,
                         pruebas: Iterable[Mapping[str, Any]] = (),
                         ahora: Callable[[], datetime] = datetime.now) -> dict[str, Any]:
    """113:RF-8, RF-9: lo que deja el cuaderno junto a cada candidato, con todas las pruebas de la búsqueda."""
    carpeta = Path(carpeta)
    artefactos = [{'ruta': p.relative_to(carpeta).as_posix(), 'sha256': _sha(p)}
                  for p in sorted(carpeta.rglob('*')) if p.is_file() and p.name != 'candidato.json']
    return {'schema': SCHEMA_CANDIDATO, 'familia': familia, 'revision': revision, 'paquete': paquete,
            'semilla': semilla, 'entorno': dict(entorno), 'hiperparametros': dict(hiperparametros),
            'metricas': dict(metricas), 'pruebas': [dict(p) for p in pruebas], 'artefactos': artefactos,
            'creado': ahora().isoformat(timespec='seconds')}


def verificar_candidato(carpeta: Path | str, *, revision: str,
                        paquetes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """113:RF-10: el candidato vale si es de esta revisión, de un paquete conocido de su familia y está entero.

    ``paquetes`` son los manifiestos de los paquetes preparados aquí, por su huella. Lanza
    :class:`CandidatoRechazado` con el motivo; si vale, devuelve su manifiesto.
    """
    carpeta = Path(carpeta)
    ruta = carpeta / 'candidato.json'
    if not ruta.is_file():
        raise CandidatoRechazado(f'{carpeta.name}: sin candidato.json')
    m = json.loads(ruta.read_text(encoding='utf-8'))
    if m.get('schema') != SCHEMA_CANDIDATO:
        raise CandidatoRechazado(f'{carpeta.name}: formato desconocido ({m.get("schema")})')
    if m.get('revision') != revision:
        raise CandidatoRechazado(f'{carpeta.name}: entrenado con la revisión {str(m.get("revision"))[:8]}, '
                                 f'y la de este equipo es {revision[:8]}')
    paquete = paquetes.get(m.get('paquete'))
    if paquete is None:
        raise CandidatoRechazado(f'{carpeta.name}: su paquete {str(m.get("paquete"))[:8]} no salió de este equipo')
    if paquete.get('familia') != m.get('familia'):
        raise CandidatoRechazado(f'{carpeta.name}: familia {m.get("familia")} con un paquete de '
                                 f'{paquete.get("familia")}')
    if not m.get('artefactos'):
        raise CandidatoRechazado(f'{carpeta.name}: sin artefactos')
    for a in m['artefactos']:
        p = carpeta / a['ruta']
        if not p.is_file() or _sha(p) != a['sha256']:
            raise CandidatoRechazado(f'{carpeta.name}: {a["ruta"]} falta o no coincide con su huella')
    return m


def traer_candidatos(origen: Path | str, destino: Path | str, *, revision: str,
                     paquetes: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """113:RF-10, RF-11: copia a ``destino`` los candidatos que cuadran, sin activar nada; los demás, con su motivo.

    Cada aceptado queda en ``destino/<familia>/<carpeta>`` con la orden local de su puerta, la misma que examina a un
    candidato entrenado en el equipo (113:RF-16).
    """
    origen, destino = Path(origen), Path(destino)
    resultados = []
    for carpeta in sorted(p for p in origen.iterdir() if p.is_dir()) if origen.is_dir() else []:
        try:
            m = verificar_candidato(carpeta, revision=revision, paquetes=paquetes)
        except CandidatoRechazado as e:
            resultados.append({'candidato': carpeta.name, 'aceptado': False, 'motivo': str(e)})
            continue
        final = destino / m['familia'] / carpeta.name
        if not final.exists():
            temporal = final.with_name(f'.trayendo_{carpeta.name}')
            shutil.rmtree(temporal, ignore_errors=True)
            shutil.copytree(carpeta, temporal)
            verificar_candidato(temporal, revision=revision, paquetes=paquetes)
            os.replace(temporal, final)
        resultados.append({'candidato': carpeta.name, 'aceptado': True, 'familia': m['familia'],
                           'carpeta': str(final), 'puerta': FAMILIAS[m['familia']]['puerta'],
                           'activado': False})
    return resultados


def paquetes_de(carpeta: Path | str) -> dict[str, dict[str, Any]]:
    """Los manifiestos de los paquetes de una carpeta, por su huella (los que salieron de este equipo)."""
    carpeta = Path(carpeta)
    hallados = {}
    for m in sorted(carpeta.glob('*/manifiesto.json')) if carpeta.is_dir() else []:
        dato = json.loads(m.read_text(encoding='utf-8'))
        if dato.get('schema') == SCHEMA_PAQUETE:
            hallados[dato['huella']] = dato
    return hallados


def orden_de_entrenamiento(familia: str, *, datos: str, salida: str, semilla: int = 11, epocas: int = 1) -> str:
    """La orden de ``tools/`` que entrena una familia: la misma en el equipo y en el cuaderno (113:RF-14, RF-16)."""
    if familia not in FAMILIAS:
        raise ValueError(f'familia desconocida: {familia}')
    return FAMILIAS[familia]['entrenar'].format(datos=datos, salida=salida, semilla=semilla, epocas=epocas)


def hay_datos_nuevos(actuales: int, al_entrenar: int, *, minimo_relativo: float = 0.2,
                     minimo_absoluto: int = 50) -> bool:
    """113:RF-13: proponer reentrenar cuando los ejemplos crecieron lo bastante desde el último entrenamiento."""
    nuevos = actuales - al_entrenar
    return nuevos >= minimo_absoluto and (al_entrenar <= 0 or nuevos / al_entrenar >= minimo_relativo)


#: 113:RF-13: lo que se preparó para cada familia, en local (el almacén del asistente), para saber cuándo creció.
REGISTRO_PREPARADOS = 'preparados.json'


def ejemplos_de(carpeta: Path | str) -> int:
    """Los ejemplos de un dataset: líneas no vacías de sus JSONL, sin contar los conjuntos sellados (113:RF-6)."""
    carpeta = Path(carpeta)
    total = 0
    for ruta in sorted(carpeta.rglob('*.jsonl')) if carpeta.is_dir() else ():
        if any(_SELLADO.search(parte) for parte in ruta.relative_to(carpeta).parts):
            continue
        with ruta.open(encoding='utf-8', errors='replace') as f:
            total += sum(1 for linea in f if linea.strip())
    return total


def registrar_preparado(registro: Path | str, *, familia: str, origen: Path | str, ejemplos: int, huella: str,
                        ahora: Callable[[], datetime] = datetime.now) -> dict[str, Any]:
    """113:RF-13: anota la carpeta y los ejemplos con que se preparó la familia; el último paquete manda."""
    registro = Path(registro)
    datos = leer_preparados(registro)
    datos[familia] = {'origen': str(Path(origen)), 'ejemplos': int(ejemplos), 'huella': huella,
                      'preparado': ahora().isoformat(timespec='seconds')}
    registro.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(registro, datos)
    return datos[familia]


def leer_preparados(registro: Path | str) -> dict[str, Any]:
    """El registro de lo preparado; uno ilegible o ausente es un registro vacío (nunca bloquea entrenar en local)."""
    try:
        datos = json.loads(Path(registro).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in datos.items() if isinstance(v, dict)} if isinstance(datos, dict) else {}


def avisos_de_reentreno(registro: Path | str) -> list[dict[str, Any]]:
    """113:RF-13: las familias cuyo dataset creció lo bastante desde que se preparó, para proponer reentrenarlas.

    Se vuelve a contar la misma carpeta que se empaquetó: el 2026-11-26 el corpus de redacción de la 072 tenía sus
    ejemplos en JSONL, y lo que el operador añade al reconstruirlo es lo que hay que comparar.
    """
    avisos = []
    for familia, dato in sorted(leer_preparados(registro).items()):
        origen = Path(str(dato.get('origen', '')))
        if familia not in FAMILIAS or not origen.is_dir():
            continue
        antes, ahora_n = int(dato.get('ejemplos') or 0), ejemplos_de(origen)
        if hay_datos_nuevos(ahora_n, antes):
            avisos.append({'familia': familia, 'origen': str(origen), 'ejemplos_al_preparar': antes,
                           'ejemplos': ahora_n, 'nuevos': ahora_n - antes, 'preparado': dato.get('preparado')})
    return avisos


def previa_paquete(origen: Path | str, *, familia: str) -> dict[str, Any]:
    """113:RF-4: lo que subiría, antes de que el operador confirme: ficheros, tamaño, anonimización y lo prohibido."""
    if familia not in FAMILIAS:
        raise ValueError(f'familia desconocida: {familia} (conocidas: {", ".join(sorted(FAMILIAS))})')
    origen = Path(origen)
    if not origen.is_dir():
        raise ValueError(f'{origen}: no es una carpeta')
    ficheros = sorted(p for p in origen.rglob('*') if p.is_file())
    modo = FAMILIAS[familia]['anonimizacion']
    return {'ficheros': len(ficheros), 'bytes': sum(p.stat().st_size for p in ficheros),
            'prohibidos': prohibidos(ficheros, origen), 'anonimizacion': _DETALLE_ANONIMIZACION[modo]}


class SinGpu(RuntimeError):
    """Colab sin GPU: entrenar ahí no aportaría nada frente al equipo."""


def perfil_colab(gpu: str | None, vram_gib: float | None) -> dict[str, Any]:
    """Lo que se entrena en Colab según su GPU, para que Colab Pro aporte frente al equipo (orden del 2026-11-26).

    El usuario: «debe preparar para Colab Pro, si no, de nada serviría usar Colab». El equipo tiene una RTX 4060 de
    8 GB y entrena una época con una semilla; una A100 o una H100 entrena tres épocas con tres semillas en el mismo
    tiempo, y cada semilla es un candidato que pasa sus puertas por su cuenta (elegir entre varias semillas es la
    búsqueda que admite el QLoRA, 113:RF-8). La orden es la misma de ``tools/``: solo cambian sus parámetros (RF-16).
    """
    if not gpu or not vram_gib:
        raise SinGpu('Colab no asignó GPU: en «Entorno de ejecución → Cambiar tipo», elige A100, H100 o L4.')
    if vram_gib >= 38:
        epocas, semillas, nota = 3, [11, 12, 13], 'GPU grande: tres épocas y tres semillas'
    elif vram_gib >= 20:
        epocas, semillas, nota = 2, [11, 12], 'L4: dos épocas y dos semillas'
    else:
        epocas, semillas, nota = 1, [11], ('GPU como la del equipo: en Colab Pro elige A100 o L4 para que aporte; '
                                           'con esta se entrena lo mismo que en el equipo')
    return {'gpu': gpu, 'vram_gib': round(float(vram_gib), 1), 'epocas': epocas, 'semillas': semillas, 'nota': nota}
