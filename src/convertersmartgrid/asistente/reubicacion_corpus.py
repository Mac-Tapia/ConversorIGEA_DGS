"""Reubicar custodia sellada sin volver a redactar ni repartir el dataset (047/065)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from ..evaluacion_modelos import huella
from ..runtime_paths import rutas_runtime, staging_publicacion
from .custodia_corpus import CustodiaCorpus, sin_enlaces
from .llm_destilacion import auditar_fuentes_corpus, custodiar, verificar_fuente


def _evidencias(valor):
    if isinstance(valor, dict):
        if {'ruta', 'sha256', 'bytes', 'localizador'} <= valor.keys():
            yield {k: valor[k] for k in ('ruta', 'sha256', 'bytes', 'localizador')}
        for elemento in valor.values():
            yield from _evidencias(elemento)
    elif isinstance(valor, list):
        for elemento in valor:
            yield from _evidencias(elemento)


def _comprobar_destino(origen: Path, destino: Path, anterior: Path, nueva: Path) -> None:
    politica = rutas_runtime()
    if destino.exists():
        raise ValueError('destino existente conservado')
    for raiz in (origen, anterior, nueva):
        if destino.is_relative_to(raiz) or raiz.is_relative_to(destino):
            raise ValueError('cruce entre destino y fuentes conservadas')
    if any(destino.is_relative_to(r) for r in (politica.checkout, politica.primario)):
        raise ValueError('destino debe ser externo al checkout y al repositorio principal')


def _resolver_original(evidencia: dict, anterior: Path, nueva: Path) -> Path:
    declarada = Path(evidencia['ruta'])
    if not declarada.is_absolute():
        raise ValueError('fuente original sin ruta absoluta')
    original = sin_enlaces(declarada)
    candidatos = [original]
    if original.is_relative_to(anterior):
        trasladada = sin_enlaces(nueva / original.relative_to(anterior))
        if not trasladada.is_file():
            raise ValueError('fuente ausente en la raíz nueva: ' + str(trasladada))
        if trasladada != original:
            candidatos.append(trasladada)
    existentes = [ruta for ruta in candidatos if ruta.is_file()]
    if not existentes:
        raise ValueError('fuente ausente en el mapeo relativo exacto: ' + str(original))
    if len(existentes) != 1:
        raise ValueError('resolución ambigua: ambas raíces contienen la fuente ' + str(original))
    actual = custodiar(existentes[0], localizador=evidencia['localizador'])
    if (actual['sha256'], actual['bytes']) != (evidencia['sha256'], evidencia['bytes']):
        raise ValueError('huella de fuente modificada: ' + str(existentes[0]))
    return existentes[0]


def _inventario(origen: Path) -> tuple[dict, dict, list[dict]]:
    archivos, documentos = {}, {}
    for archivo in sorted(origen.iterdir()):
        sin_enlaces(archivo)
        if not archivo.is_file():
            raise ValueError('carpeta o enlace inesperado dentro del corpus sellado')
        archivos[archivo.name] = custodiar(archivo, localizador=archivo.name)
        if archivo.suffix == '.json':
            documentos[archivo.name] = json.loads(archivo.read_text(encoding='utf-8'))
        elif archivo.suffix == '.jsonl':
            documentos[archivo.name] = [json.loads(l) for l in archivo.read_text(encoding='utf-8').splitlines()]
    meta = documentos['dataset_manifest.json']
    if 'reubicacion_fuentes' in meta:
        raise ValueError('origen ya reubicado; se requiere el corpus sellado original')
    evidencias = [e for documento in documentos.values() for e in _evidencias(documento)]
    return archivos, meta, evidencias


def reubicar_corpus(origen: Path, destino: Path, raiz_anterior: Path, raiz_nueva: Path, *,
                    ejecutar: bool = False, max_bytes: int = 1024 ** 3) -> dict:
    """Validar el traslado exacto y publicar una versión nueva, por defecto solo simular."""
    origen, destino, anterior, nueva = (sin_enlaces(Path(p)) for p in
                                         (origen, destino, raiz_anterior, raiz_nueva))
    if not origen.is_dir() or not nueva.is_dir():
        raise ValueError('fuente de corpus o raíz nueva ausente')
    if anterior == nueva or anterior.is_relative_to(nueva) or nueva.is_relative_to(anterior):
        raise ValueError('cruce entre las raíces del traslado')
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError('cuota de bytes invalida')
    _comprobar_destino(origen, destino, anterior, nueva)
    archivos, meta, evidencias = _inventario(origen)
    resoluciones, entradas = {}, {}
    for evidencia in evidencias:
        original = evidencia['ruta']
        firma = (evidencia['sha256'], evidencia['bytes'])
        if original in resoluciones:
            if resoluciones[original][1:] != firma:
                raise ValueError('huellas ambiguas para una fuente')
            continue
        ruta = _resolver_original(evidencia, anterior, nueva)
        if ruta.is_relative_to(destino) or destino.is_relative_to(ruta):
            raise ValueError('cruce entre destino y archivo fuente')
        resoluciones[original] = (ruta, *firma)
        if ruta.parent == origen and ruta.name in archivos:
            relativa = ruta.name
        else:
            relativa = 'fuentes/' + firma[0] + '.bin'
        entradas[original] = {'origen': original, 'resuelto_desde': str(ruta),
                              'destino': relativa, 'sha256': firma[0], 'bytes': firma[1]}
    custodia = CustodiaCorpus(origen, resoluciones)
    # Se valida el sellado anterior con las fuentes reales resueltas, sin reescribir IDs.
    auditoria = auditar_fuentes_corpus(origen, custodia=custodia)
    copias = {e['destino']: (resoluciones[r][0], e['sha256'], e['bytes'])
              for r, e in entradas.items()}
    for nombre, evidencia in archivos.items():
        copias[nombre] = (origen / nombre, evidencia['sha256'], evidencia['bytes'])
    copias['origen/dataset_manifest.json'] = (origen / 'dataset_manifest.json',
        archivos['dataset_manifest.json']['sha256'], archivos['dataset_manifest.json']['bytes'])
    traslado = {'schema_version': 1, 'metodo': 'mapeo_relativo_exacto_y_copia_SHA256',
        'raiz_anterior': str(anterior), 'raiz_nueva': str(nueva),
        'origen_manifest': archivos['dataset_manifest.json'],
        'dataset_hash_preservado': meta['dataset_hash'],
        'muestras_y_contextos_identicos': True, 'entrenamiento_solicitado': False,
        'resoluciones': [entradas[k] for k in sorted(entradas)],
        'archivos_originales': archivos}
    traslado['huella'] = huella(traslado)
    nuevo = {**meta, 'reubicacion_fuentes': traslado}
    nuevo['archivos_particion'] = {p: {**e, 'ruta': p + '.jsonl'}
                                   for p, e in meta['archivos_particion'].items()}
    for clave, nombre in (('contextos_fuente', 'contextos_fuente.json'),
                          ('humanas_reservadas_archivo', 'humanas_reservadas.json')):
        nuevo[clave] = {**meta[clave], 'ruta': nombre}
    manifiesto_bytes = json.dumps(nuevo, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    necesarios = sum(v[2] for k, v in copias.items() if k != 'dataset_manifest.json') + len(manifiesto_bytes)
    if necesarios > max_bytes:
        raise ValueError(f'cuota de custodia excedida: {necesarios}/{max_bytes} bytes')
    existente = next(p for p in (destino.parent, *destino.parents) if p.exists())
    if shutil.disk_usage(existente).free < necesarios + 1024 ** 2:
        raise ValueError('espacio insuficiente para la custodia y su manifiesto')
    resultado = {'ejecutado': False, 'origen': str(origen), 'destino': str(destino),
        'dataset_hash': meta['dataset_hash'], 'custodia_hash': traslado['huella'],
        'fuentes_resueltas': len(entradas), 'bytes_custodia': necesarios,
        'auditoria': auditoria, 'resoluciones': traslado['resoluciones'],
        'training_completed': False, 'promovido': False, 'aceptacion_cientifica': False}
    if not ejecutar:
        return resultado
    destino.parent.mkdir(parents=True, exist_ok=True)
    _comprobar_destino(origen, sin_enlaces(destino), anterior, nueva)
    with staging_publicacion(destino) as staging:
        staging.mkdir()
        for relativa, (fuente, sha, cantidad) in copias.items():
            if relativa == 'dataset_manifest.json':
                continue
            copia = staging / relativa
            copia.parent.mkdir(parents=True, exist_ok=True)
            sin_enlaces(fuente)
            with fuente.open('rb') as entrada, copia.open('xb') as salida:
                shutil.copyfileobj(entrada, salida, length=1024 ** 2)
            verificar_fuente({'ruta': str(copia.resolve()), 'sha256': sha,
                              'bytes': cantidad, 'localizador': relativa})
        (staging / 'dataset_manifest.json').write_bytes(manifiesto_bytes)
        resultado['auditoria'] = auditar_fuentes_corpus(staging)
        # Una copia correcta no autoriza cambios concurrentes en el corpus de origen.
        for nombre, evidencia in archivos.items():
            verificar_fuente(evidencia)
        if destino.exists():
            raise ValueError('destino concurrente conservado')
        os.rename(staging, destino)
    resultado['ejecutado'] = True
    resultado['auditoria'] = auditar_fuentes_corpus(destino)
    return resultado
