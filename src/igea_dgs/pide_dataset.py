"""Corpus PIDE universal con custodia empresarial y salidas seguras para LLM.

El módulo no interpreta un expediente empresarial como aprobación. Todo material derivado de
documentos queda en ``context``; la aceptación nativa/humana vive fuera de este constructor.
"""
from __future__ import annotations

import hashlib
import json
import re
import csv
import os
from collections import Counter
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArticuloPide:
    numero: int
    titulo: str
    etapa: str
    entradas: tuple[str, ...]
    procedimiento: tuple[str, ...]
    evidencias: tuple[str, ...]
    entregables: tuple[str, ...]


@dataclass(frozen=True)
class FormatoPide:
    codigo: str
    nombre: str
    campos: tuple[str, ...]


@dataclass(frozen=True)
class AlternativaPide:
    codigo: str
    familia: str
    resuelve: tuple[str, ...]


@dataclass(frozen=True)
class ContratoPide:
    schema: str
    version: str
    estado_juridico: str
    fuente: dict[str, str]
    articulos: tuple[ArticuloPide, ...]
    formatos: tuple[FormatoPide, ...]
    alternativas: tuple[AlternativaPide, ...]

    def validar(self) -> list[str]:
        errores: list[str] = []
        if [a.numero for a in self.articulos] != list(range(1, 21)):
            errores.append('los artículos deben ser exactamente 1..20')
        if [f.codigo for f in self.formatos] != [f'F{i:02d}' for i in range(1, 16)]:
            errores.append('los formatos deben ser exactamente F01..F15')
        if self.estado_juridico not in {
            'vigente', 'proyecto', 'pendiente', 'derogada', 'evidencia_tecnica'
        }:
            errores.append('estado jurídico no permitido')
        for articulo in self.articulos:
            if not all((articulo.titulo, articulo.etapa, articulo.entradas,
                        articulo.procedimiento, articulo.evidencias, articulo.entregables)):
                errores.append(f'artículo {articulo.numero} incompleto')
        codigos = [a.codigo for a in self.alternativas]
        if len(codigos) != len(set(codigos)):
            errores.append('alternativas duplicadas')
        return errores

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def cargar_contrato(path: Path | str) -> ContratoPide:
    """Carga el contrato versionado y falla cerrado si está incompleto."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    contrato = ContratoPide(
        schema=str(data['schema']), version=str(data['version']),
        estado_juridico=str(data['estado_juridico']), fuente=dict(data['fuente']),
        articulos=tuple(ArticuloPide(
            numero=int(a['numero']), titulo=str(a['titulo']), etapa=str(a['etapa']),
            entradas=tuple(a['entradas']), procedimiento=tuple(a['procedimiento']),
            evidencias=tuple(a['evidencias']), entregables=tuple(a['entregables']))
            for a in data['articulos']),
        formatos=tuple(FormatoPide(str(f['codigo']), str(f['nombre']), tuple(f['campos']))
                       for f in data['formatos']),
        alternativas=tuple(AlternativaPide(str(a['codigo']), str(a['familia']),
                                           tuple(a['resuelve']))
                           for a in data['alternativas']),
    )
    errores = contrato.validar()
    if errores:
        raise ValueError('contrato PIDE inválido: ' + '; '.join(errores))
    return contrato


@dataclass(frozen=True)
class ClasificacionPide:
    periodo: str
    entregable: str
    revision: str
    anexo: str
    familia: str
    articulos: tuple[int, ...]


@dataclass(frozen=True)
class ArchivoPide:
    file_id: str
    content_id: str
    relative_path: str
    sha256: str
    bytes: int
    modified_utc: str
    empresa: str
    periodo: str
    entregable: str
    revision: str
    anexo: str
    familia: str
    articulos: tuple[int, ...]
    extension: str
    signature_kind: str
    extractability: str
    temporal: bool
    duplicate_of: str | None
    advertencias: tuple[str, ...]
    hash_error: str = ''

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExtraccionPide:
    file_id: str
    sha256: str
    status: str
    method: str
    fragments: tuple[dict[str, Any], ...]
    assets: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_estable(path: Path | str, chunk_size: int = 4 * 1024 * 1024) -> tuple[str, str]:
    """Calcula SHA-256 y rechaza un archivo cambiado mientras era leído."""
    ruta = Path(path)
    try:
        antes = ruta.stat()
        digest = hashlib.sha256()
        with ruta.open('rb') as stream:
            while bloque := stream.read(chunk_size):
                digest.update(bloque)
        despues = ruta.stat()
    except OSError as exc:
        return '', f'error_lectura:{type(exc).__name__}'
    if (antes.st_size, antes.st_mtime_ns) != (despues.st_size, despues.st_mtime_ns):
        return '', 'archivo_modificado_durante_lectura'
    return digest.hexdigest(), ''


def _firma(path: Path) -> tuple[str, str]:
    try:
        with path.open('rb') as stream:
            inicio = stream.read(16)
    except OSError:
        return 'unreadable', 'native_required'
    ext = path.suffix.lower()
    if inicio.startswith(b'TAPE'):
        return 'sqlserver_backup', 'native_required'
    if inicio.startswith(b'%PDF'):
        return 'pdf', 'extractable'
    if inicio.startswith(b'PK\x03\x04'):
        return 'zip_container', 'extractable' if ext in {'.xlsx', '.docx', '.pptx', '.kmz'} else 'archive'
    if inicio.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):
        return 'ole_compound', 'native_required'
    if inicio.startswith(b'Rar!'):
        return 'rar_archive', 'archive'
    if ext in {'.pfd', '.dwg', '.mpp', '.msg', '.bak', '.wf1', '.ci1', '.geprint'} or not ext:
        return 'proprietary_binary', 'native_required'
    if ext in {'.pdf', '.docx', '.xlsx', '.csv', '.shp', '.gpkg', '.json', '.xml', '.html'}:
        return ext.lstrip('.'), 'extractable'
    return 'binary_or_unknown', 'metadata_only'


def clasificar_ruta(relative_path: str | Path) -> ClasificacionPide:
    """Clasifica por evidencia del nombre sin convertir el nombre en aceptación."""
    rel = Path(str(relative_path).replace('\\', '/'))
    partes = rel.parts
    texto = ' / '.join(partes)
    periodo = next((m.group(1) for p in partes if (m := re.search(r'PIDE\s+(20\d{2})', p, re.I))), '')
    entregable = ''
    if periodo == '2021' and len(partes) >= 3 and partes[1].lower() == 'informes':
        entregable = partes[2]
    elif periodo and len(partes) >= 2:
        entregable = partes[1]
    revision = ''
    if re.search(r'absoluci[oó]n|levantamiento', texto, re.I):
        revision = 'absolucion'
    elif re.search(r'observaciones?', texto, re.I):
        revision = 'observacion'
    elif re.search(r'resumen final|definitiv|\bvf\b|_ok', texto, re.I):
        revision = 'final'
    elif entregable:
        revision = 'entrega'
    anexo = next((re.sub(r'_+', ' ', p).strip() for p in partes
                  if re.search(r'\banexo\b', p, re.I)), '')
    bajo = texto.lower()
    if any(x in bajo for x in ('demanda', 'mercado', 'densidad')):
        familia, articulos = 'mercado_demanda', (7,)
    elif any(x in bajo for x in ('diagn[oó]stico', 'flujo', 'calidad', 'p[eé]rdida')):
        familia, articulos = 'diagnostico', (8,)
    elif any(x in bajo for x in ('evaluacion economica', 'evaluación económica', 'valorizacion', 'costos')):
        familia, articulos = 'economia', (14, 15)
    elif any(x in bajo for x in ('alternativa', 'propuesta', 'proyecto')):
        familia, articulos = 'alternativas', (9, 12, 13)
    elif any(x in bajo for x in ('formato', 'ficha')):
        familia, articulos = 'formatos', (17, 18)
    elif any(x in bajo for x in ('cronograma', '.mpp')):
        familia, articulos = 'cronograma', (16, 20)
    elif any(x in bajo for x in ('norma', 'resoluci')):
        familia, articulos = 'normativa', (3,)
    else:
        familia, articulos = 'evidencia_general', ()
    return ClasificacionPide(periodo, entregable, revision, anexo, familia, articulos)


def inventariar(raiz: Path | str, empresa: str, contrato: ContratoPide) -> tuple[ArchivoPide, ...]:
    """Inventaría todas las rutas; deduplica semánticamente sin borrar ocurrencias."""
    del contrato  # La clasificación queda desacoplada de los valores de una empresa.
    base = Path(raiz).resolve()
    preliminares: list[dict[str, Any]] = []
    for ruta in sorted((p for p in base.rglob('*') if p.is_file()), key=lambda p: p.as_posix().lower()):
        relative = ruta.relative_to(base).as_posix()
        sha, error = sha256_estable(ruta)
        stat = ruta.stat()
        clas = clasificar_ruta(relative)
        signature, extractability = _firma(ruta)
        temporal = ruta.name.startswith('~$')
        advertencias: list[str] = []
        if temporal:
            advertencias.append('temporal_office')
            extractability = 'excluded'
        if error:
            advertencias.append(error)
            extractability = 'unavailable'
        content_id = f'sha256:{sha}' if sha else ''
        file_id = hashlib.sha256(f'{empresa}\n{relative}\n{sha}'.encode('utf-8')).hexdigest()
        preliminares.append({
            'file_id': file_id, 'content_id': content_id, 'relative_path': relative,
            'sha256': sha, 'bytes': stat.st_size,
            'modified_utc': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            'empresa': empresa, **asdict(clas), 'extension': ruta.suffix.lower(),
            'signature_kind': signature, 'extractability': extractability,
            'temporal': temporal, 'advertencias': advertencias, 'hash_error': error,
        })
    primero: dict[str, str] = {}
    salida: list[ArchivoPide] = []
    for item in preliminares:
        cid = item['content_id']
        duplicado = primero.get(cid) if cid else None
        if cid and cid not in primero:
            primero[cid] = item['file_id']
        advertencias = list(item.pop('advertencias'))
        if duplicado:
            advertencias.append('duplicado_contenido')
        salida.append(ArchivoPide(**item, duplicate_of=duplicado,
                                  advertencias=tuple(advertencias)))
    return tuple(salida)


def _fragmentos(texto: str, location: str, max_chars: int) -> list[dict[str, Any]]:
    limpio = re.sub(r'[ \t]+', ' ', texto).strip()
    if not limpio:
        return []
    return [{'location': location, 'part': i // max_chars + 1, 'text': limpio[i:i + max_chars]}
            for i in range(0, len(limpio), max_chars)]


def _extraer_pdf(path: Path, max_chars: int) -> tuple[list[dict], list[dict], list[str]]:
    from pypdf import PdfReader

    reader = PdfReader(path, strict=False)
    fragments: list[dict[str, Any]] = []
    warnings: list[str] = []
    for numero, page in enumerate(reader.pages, 1):
        try:
            texto = page.extract_text() or ''
        except Exception as exc:  # una página dañada no descarta las restantes
            warnings.append(f'pdf_page_{numero}:{type(exc).__name__}')
            continue
        fragments.extend(_fragmentos(texto, f'page:{numero}', max_chars))
    if not fragments:
        warnings.append('pdf_sin_texto_extraible')
    return fragments, [{'kind': 'pdf', 'pages': len(reader.pages)}], warnings


def _extraer_docx(path: Path, max_chars: int) -> tuple[list[dict], list[dict], list[str]]:
    from docx import Document

    doc = Document(path)
    fragments: list[dict[str, Any]] = []
    for numero, paragraph in enumerate(doc.paragraphs, 1):
        fragments.extend(_fragmentos(paragraph.text, f'paragraph:{numero}', max_chars))
    for tabla_num, table in enumerate(doc.tables, 1):
        texto = '\n'.join(' | '.join(cell.text for cell in row.cells) for row in table.rows)
        fragments.extend(_fragmentos(texto, f'table:{tabla_num}', max_chars))
    return fragments, [{'kind': 'docx', 'paragraphs': len(doc.paragraphs),
                        'tables': len(doc.tables)}], []


def _extraer_xlsx(path: Path) -> tuple[list[dict], list[dict], list[str]]:
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
          'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
          'pr': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        relations: dict[str, str] = {}
        rel_name = 'xl/_rels/workbook.xml.rels'
        if rel_name in names:
            rels = ET.fromstring(archive.read(rel_name))
            relations = {r.attrib['Id']: r.attrib['Target'] for r in rels.findall('pr:Relationship', ns)}
        assets: list[dict[str, Any]] = []
        for sheet in workbook.findall('.//m:sheets/m:sheet', ns):
            rid = sheet.attrib.get(f'{{{ns["r"]}}}id', '')
            target = relations.get(rid, '')
            member = target.lstrip('/') if target.startswith('/') else f'xl/{target.lstrip("/")}'
            member = str(Path(member)).replace('\\', '/')
            dimension = ''
            if member in names:
                root = ET.fromstring(archive.read(member))
                dim = root.find('m:dimension', ns)
                dimension = dim.attrib.get('ref', '') if dim is not None else ''
            assets.append({'kind': 'xlsx_sheet', 'sheet': sheet.attrib.get('name', ''),
                           'dimension': dimension, 'state': sheet.attrib.get('state', 'visible')})
        external = len({n for n in names if n.startswith('xl/externalLinks/externalLink')
                        and n.endswith('.xml')})
        warnings = [f'vinculos_externos:{external}'] if external else []
        for asset in assets:
            asset['external_links'] = external
        return [], assets, warnings


def _extraer_csv(path: Path, max_chars: int) -> tuple[list[dict], list[dict], list[str]]:
    bruto = path.read_bytes()
    try:
        texto = bruto.decode('utf-8-sig')
        encoding = 'utf-8'
    except UnicodeDecodeError:
        texto = bruto.decode('latin-1')
        encoding = 'latin-1'
    muestra = texto[:8192]
    try:
        dialect = csv.Sniffer().sniff(muestra, delimiters=',;\t|')
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ','
    rows = list(csv.reader(texto.splitlines(), delimiter=delimiter))
    columns = rows[0] if rows else []
    fragments = _fragmentos('\n'.join(delimiter.join(r) for r in rows[:30]), 'rows:1-30', max_chars)
    return fragments, [{'kind': 'table', 'columns': columns, 'rows': max(len(rows) - 1, 0),
                        'delimiter': delimiter, 'encoding': encoding}], []


def _extraer_geojson(path: Path) -> tuple[list[dict], list[dict], list[str]]:
    data = json.loads(path.read_text(encoding='utf-8'))
    features = data.get('features') or []
    geometries = sorted({str((f.get('geometry') or {}).get('type') or '') for f in features})
    fields = sorted({str(k) for f in features for k in (f.get('properties') or {})})
    crs = data.get('crs')
    warnings = [] if crs else ['crs_no_declarado']
    return [], [{'kind': 'gis_layer', 'features': len(features), 'geometry_types': geometries,
                 'fields': fields, 'crs': crs}], warnings


def _extraer_vector(path: Path) -> tuple[list[dict], list[dict], list[str]]:
    import pyogrio

    layers = pyogrio.list_layers(path) if path.suffix.lower() == '.gpkg' else [(path.stem, '')]
    assets: list[dict[str, Any]] = []
    warnings: list[str] = []
    for name, _ in layers:
        info = pyogrio.read_info(path, layer=name if path.suffix.lower() == '.gpkg' else None)
        crs = info.get('crs')
        if not crs:
            warnings.append(f'crs_no_declarado:{name}')
        assets.append({'kind': 'gis_layer', 'layer': str(name),
                       'features': int(info.get('features') or 0),
                       'geometry_type': str(info.get('geometry_type') or ''),
                       'fields': [str(x) for x in info.get('fields', [])], 'crs': crs})
    return [], assets, warnings


def extraer_archivo(archivo: ArchivoPide, raiz: Path | str, *,
                    max_chars: int = 1800) -> ExtraccionPide:
    """Extrae solo formatos comprendidos y conserva un estado verificable en los demás."""
    if archivo.duplicate_of:
        return ExtraccionPide(archivo.file_id, archivo.sha256, 'duplicate', 'sha256', (), (),
                              ('contenido_representado_por:' + archivo.duplicate_of,))
    if archivo.temporal or archivo.extractability == 'excluded':
        return ExtraccionPide(archivo.file_id, archivo.sha256, 'excluded', 'policy', (), (),
                              archivo.advertencias)
    if archivo.extractability == 'native_required':
        return ExtraccionPide(archivo.file_id, archivo.sha256, 'native_required',
                              archivo.signature_kind, (), (), ('lector_nativo_requerido',))
    path = Path(raiz) / Path(archivo.relative_path)
    extension = archivo.extension
    try:
        if extension == '.pdf':
            fragments, assets, warnings = _extraer_pdf(path, max_chars)
            method = 'pypdf'
        elif extension == '.docx':
            fragments, assets, warnings = _extraer_docx(path, max_chars)
            method = 'python-docx'
        elif extension == '.xlsx':
            fragments, assets, warnings = _extraer_xlsx(path)
            method = 'ooxml'
        elif extension == '.csv':
            fragments, assets, warnings = _extraer_csv(path, max_chars)
            method = 'csv'
        elif extension in {'.geojson', '.json'}:
            fragments, assets, warnings = _extraer_geojson(path)
            method = 'json'
        elif extension in {'.shp', '.gpkg'}:
            fragments, assets, warnings = _extraer_vector(path)
            method = 'pyogrio'
        elif extension in {'.txt', '.xml', '.html', '.js', '.css'}:
            texto = path.read_text(encoding='utf-8', errors='replace')
            fragments, assets, warnings = _fragmentos(texto, 'document', max_chars), [], []
            method = 'text'
        else:
            return ExtraccionPide(archivo.file_id, archivo.sha256, 'metadata_only',
                                  archivo.signature_kind, (), (), ('sin_extractor_semantico',))
        return ExtraccionPide(archivo.file_id, archivo.sha256, 'ok', method,
                              tuple(fragments), tuple(assets), tuple(warnings))
    except Exception as exc:  # frontera por archivo: uno roto no aborta los demás
        return ExtraccionPide(archivo.file_id, archivo.sha256, 'error',
                              extension.lstrip('.') or archivo.signature_kind, (), (),
                              (f'{type(exc).__name__}:{str(exc)[:300]}',))


def _record_id(tipo: str, payload: dict[str, Any]) -> str:
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(f'{tipo}\n{canon}'.encode('utf-8')).hexdigest()


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temporal = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    texto = ''.join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')) + '\n' for row in rows)
    temporal.write_text(texto, encoding='utf-8', newline='\n')
    os.replace(temporal, path)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporal = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temporal.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
                        encoding='utf-8', newline='\n')
    os.replace(temporal, path)


def _training_from_contract(contract: ContratoPide) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for article in contract.articulos:
        respuesta = {
            'articulo': article.numero, 'titulo': article.titulo, 'etapa': article.etapa,
            'entradas': article.entradas, 'procedimiento': article.procedimiento,
            'evidencias': article.evidencias, 'entregables': article.entregables,
            'estado_juridico': contract.estado_juridico,
        }
        payload = {
            'schema': 'igea-pide-training-candidate-v1', 'tipo': 'metodologia_pide',
            'estado': 'context', 'empresa': None, 'articulos': [article.numero],
            'messages': [
                {'role': 'system', 'content': (
                    'Aplica el contrato PIDE universal. Distingue norma, evidencia empresarial, '
                    'cálculo reproducido y aceptación; nunca copies resultados de otra empresa.')},
                {'role': 'user', 'content': f'¿Cómo se desarrolla el artículo {article.numero}: {article.titulo}?'},
                {'role': 'assistant', 'content': json.dumps(respuesta, ensure_ascii=False,
                                                            sort_keys=True)},
            ],
            'provenance': {'contract_version': contract.version,
                           'legal_status': contract.estado_juridico,
                           'source': contract.fuente},
            'verification': 'requiere_revision_humana_antes_de_gold',
        }
        payload['record_id'] = _record_id('training', payload)
        rows.append(payload)
    return rows


def construir_dataset(raiz: Path | str, destino: Path | str, empresa: str,
                      contrato_path: Path | str, *, sin_texto: bool = False,
                      max_chars: int = 1800) -> dict[str, Any]:
    """Publica un dataset determinista; cada registro semántico conserva custodia."""
    contract = cargar_contrato(contrato_path)
    files = inventariar(raiz, empresa, contract)
    destination = Path(destino)
    destination.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    quality: list[dict[str, Any]] = []
    statuses: Counter[str] = Counter()

    for file in files:
        extraction = (ExtraccionPide(file.file_id, file.sha256, 'not_requested', 'policy', (), ())
                      if sin_texto else extraer_archivo(file, raiz, max_chars=max_chars))
        statuses[extraction.status] += 1
        manifest_row = file.as_dict()
        manifest_row.update({'extract_status': extraction.status,
                             'extract_method': extraction.method,
                             'extract_warnings': extraction.warnings})
        manifest.append(manifest_row)
        for item in extraction.fragments:
            payload = {
                'schema': 'igea-pide-fragment-v1', 'estado': 'context',
                'empresa': empresa, 'file_id': file.file_id, 'content_id': file.content_id,
                'sha256': file.sha256, 'relative_path': file.relative_path,
                'periodo': file.periodo, 'entregable': file.entregable,
                'revision': file.revision, 'familia': file.familia,
                'articulos': file.articulos, **item,
            }
            payload['record_id'] = _record_id('fragment', payload)
            fragments.append(payload)
        for item in extraction.assets:
            payload = {
                'schema': 'igea-pide-asset-v1', 'estado': 'context',
                'empresa': empresa, 'file_id': file.file_id, 'content_id': file.content_id,
                'sha256': file.sha256, 'relative_path': file.relative_path,
                'periodo': file.periodo, 'entregable': file.entregable,
                'familia': file.familia, 'articulos': file.articulos, **item,
            }
            payload['record_id'] = _record_id('asset', payload)
            assets.append(payload)
        warnings = tuple(file.advertencias) + tuple(extraction.warnings)
        for warning in dict.fromkeys(warnings):
            payload = {
                'schema': 'igea-pide-quality-finding-v1', 'file_id': file.file_id,
                'sha256': file.sha256, 'relative_path': file.relative_path,
                'empresa': empresa, 'severity': ('error' if extraction.status == 'error' else 'warning'),
                'finding': warning, 'extract_status': extraction.status,
            }
            payload['finding_id'] = _record_id('quality', payload)
            quality.append(payload)

    training = _training_from_contract(contract)
    manifest.sort(key=lambda r: r['relative_path'].lower())
    fragments.sort(key=lambda r: (r['relative_path'].lower(), r['location'], r['part']))
    assets.sort(key=lambda r: (r['relative_path'].lower(), r.get('sheet', ''), r.get('layer', '')))
    quality.sort(key=lambda r: (r['relative_path'].lower(), r['finding']))
    training.sort(key=lambda r: r['articulos'])
    summary = {
        'schema': 'igea-pide-dataset-summary-v1', 'empresa': empresa,
        'contract_version': contract.version, 'contract_legal_status': contract.estado_juridico,
        'files': len(files), 'unique_contents': len({f.sha256 for f in files if f.sha256}),
        'duplicates': sum(f.duplicate_of is not None for f in files),
        'bytes': sum(f.bytes for f in files), 'articles': len(contract.articulos),
        'formats': len(contract.formatos), 'fragments': len(fragments), 'assets': len(assets),
        'training_records': len(training), 'quality_findings': len(quality),
        'extract_status': dict(sorted(statuses.items())),
        'extensions': dict(sorted(Counter(f.extension or '[sin_ext]' for f in files).items())),
        'publication_policy': 'context_only; gold requiere revisión humana o aceptación nativa',
    }
    _write_jsonl_atomic(destination / 'manifest.jsonl', manifest)
    _write_jsonl_atomic(destination / 'fragments.jsonl', fragments)
    _write_jsonl_atomic(destination / 'assets.jsonl', assets)
    _write_jsonl_atomic(destination / 'training.jsonl', training)
    _write_jsonl_atomic(destination / 'quality.jsonl', quality)
    _write_json_atomic(destination / 'summary.json', summary)
    return summary
