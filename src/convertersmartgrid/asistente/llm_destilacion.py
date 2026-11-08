"""047 T7: respuestas del maestro para el LLM, con fuentes reales verificables."""
from __future__ import annotations

from ..runtime_paths import staging_publicacion

from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
import re
import random

from .contratos_salida import validar_orden
from .custodia_corpus import CustodiaCorpus, leer_custodia, ruta_fuente
# El corpus del ajuste generativo se selló con estas tareas; el catálogo nuevo no lo cambia (070, limitaciones).
from .tareas import TIPOS_DATO, TAREAS_HASTA_069 as TAREAS, sistema_alumno
from ..evaluacion_modelos import huella, texto_canonico
from ..runtime_paths import raiz_programa

PARTICIONES = ('entrenamiento', 'seleccion', 'calibracion', 'prueba')


def muestras_aprendizaje(instantanea: dict, referencias: dict) -> list:
    """050:RF-2/3: lee las partes selladas del alumno; maestro conserva su procedencia."""
    from ..aprendizaje_continuo import muestra_de_registro, ruta_de
    dataset = ruta_de(instantanea, 'llm_dataset')
    resultado = []
    for parte in PARTICIONES:
        registros, _ = leer_particion_real(dataset, parte)
        for r in registros:
            resultado.append(muestra_de_registro(instantanea, referencias, 'llm_dataset',
                r['record_id'], r, familia='qlora', particion=parte,
                origen='redactado', etiqueta='maestro'))
    return resultado


def parte_contexto(fuente: str, alimentador: str, semilla: int = 0) -> str:
    n = int(huella({'fuente': fuente, 'alimentador': alimentador, 'semilla': semilla})[:8], 16) % 100
    return PARTICIONES[0 if n < 70 else 1 if n < 80 else 2 if n < 90 else 3]


def repartir_contextos(fuente: str, vinculos: dict[str, list[str]]) -> tuple[dict[str, str], int]:
    """El primer reparto hash que permite evaluar pares reales en las cuatro partes."""
    for semilla in range(256):
        partes = {n: parte_contexto(fuente, n, semilla) for n in sorted(vinculos)}
        grupos = Counter((partes[n], proyecto) for n, proyectos in vinculos.items() for proyecto in set(proyectos))
        if all(any(parte == p and cantidad >= 2 for (parte, _), cantidad in grupos.items()) for p in PARTICIONES):
            return partes, semilla
    raise ValueError('vinculos reales insuficientes para separar pares sin fuga')


def objetivo_causal(prompt: list[int], respuesta: list[int], *, max_tokens: int) -> tuple[list[int], list[int]]:
    if not prompt or not respuesta or len(prompt) + len(respuesta) > max_tokens:
        raise ValueError('no se permite truncar prompt o respuesta')
    return prompt + respuesta, [-100] * len(prompt) + respuesta


def renderizar_orden(plantilla: str, valores: dict[str, str], rnd: random.Random) -> tuple[str, list]:
    """Solo altera la formulacion: cada entidad procede de un valor aportado."""
    texto, datos, pos = '', [], 0
    for m in re.finditer(r'\[([^\]]*)\]|\{(\w+)\}', plantilla):
        texto += plantilla[pos:m.start()]
        if m[1] is not None:
            texto += rnd.choice(m[1].split('|'))
        else:
            tipo = m[2]
            valor = valores.get(tipo)
            if not isinstance(valor, str) or not valor.strip():
                raise ValueError(f'falta valor real para {tipo}')
            datos.append([len(texto), len(texto) + len(valor), tipo])
            texto += valor
        pos = m.end()
    return texto + plantilla[pos:], datos


def custodiar(ruta: Path | str, *, localizador: str) -> dict:
    ruta = Path(ruta).resolve(strict=True)
    if not ruta.is_file() or not isinstance(localizador, str) or not localizador.strip():
        raise ValueError('fuente o localizador invalido')
    with ruta.open('rb') as f:
        sha = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'ruta': str(ruta), 'sha256': sha, 'bytes': ruta.stat().st_size,
            'localizador': localizador}


def verificar_fuente(evidencia: dict, *, custodia: CustodiaCorpus | None = None) -> bool:
    if not isinstance(evidencia, dict) or not evidencia.get('localizador'):
        raise ValueError('fuente sin localizador')
    try:
        actual = custodiar(ruta_fuente(evidencia, custodia), localizador=evidencia['localizador'])
        if custodia is not None:
            # La ruta histórica integra record_id; solo cambia el localizador físico.
            actual['ruta'] = evidencia['ruta']
    except (KeyError, OSError, TypeError) as exc:
        raise ValueError('fuente ausente o invalida') from exc
    if actual != evidencia:
        raise ValueError('huella de fuente modificada')
    return True


def custodiar_politica(origen: Path, destino: Path) -> dict:
    """060:RF-4: la versión de política del corpus no depende de futuras ediciones."""
    import shutil
    original = custodiar(origen, localizador='política original de la preparación')
    copia = destino / 'fuentes' / 'politica.md'
    copia.parent.mkdir(parents=True, exist_ok=True)
    with origen.open('rb') as entrada, copia.open('xb') as salida:
        shutil.copyfileobj(entrada, salida)
    evidencia = custodiar(copia, localizador='P9/P11: custodia local y resultados comprobados')
    if evidencia['sha256'] != original['sha256']:
        raise ValueError('la política cambió durante la copia de custodia')
    return {'origen': original, 'copia': evidencia}


def respuesta_maestro(registro: dict) -> str:
    """Anota una solicitud; no convierte una orden redactada en operacion ejecutada."""
    if 'resultado_electrico' in registro or registro.get('ejecutado'):
        raise ValueError('resultado electrico no admitido en una anotacion de intencion')
    if not registro.get('fuentes'):
        raise ValueError('se requiere una fuente real con custodia')
    for fuente in registro['fuentes']:
        verificar_fuente(fuente)
    return _respuesta_de_spans(registro)


def _respuesta_de_spans(registro: dict) -> str:
    texto = registro['texto']
    if not isinstance(texto, str) or not texto.strip():
        raise ValueError('texto vacio')
    datos = defaultdict(list)
    for a, b, tipo in registro.get('datos', []):
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(texto) or tipo not in TIPOS_DATO:
            raise ValueError('span invalido')
        valor = texto[a:b]
        if valor not in datos[tipo]:
            datos[tipo].append(valor)
    respuesta = {'tarea': registro['tarea'], 'datos': dict(datos), 'confianza': .9 if registro['tarea'] is not None else 0.}
    validar_orden(respuesta)
    return json.dumps(respuesta, ensure_ascii=False, separators=(',', ':'))


def extraer_referencia(*, red: Path, cargas: Path, equipos: Path, estructura_pdf: Path,
                      mediciones: Path, nuevos_clientes: Path, workspaces: list[Path]) -> tuple[list[dict], dict]:
    """Lee registros reales; el PDF no reemplaza la pertenencia del TXT."""
    from ..dataset import CymdistDataset
    from ..model import extract_sed_code
    from ..naming import feeder_short_name
    from ..sources.snapshot import snapshot_from_paths
    from pypdf import PdfReader
    from openpyxl import load_workbook
    from datetime import datetime, date

    archivos = {'red': Path(red), 'loads': Path(cargas), 'equipment': Path(equipos)}
    snapshot = snapshot_from_paths('txt', archivos, Path(red).parent, origin='dataset-llm')
    dataset = CymdistDataset.from_files(red, cargas, equipos)
    fuentes = {k: custodiar(v, localizador='archivo completo') for k, v in archivos.items()}
    fuentes['estructura'] = custodiar(estructura_pdf, localizador='paginas del inventario')
    fuentes['mediciones'] = custodiar(mediciones, localizador='celdas de fechas de medicion')
    fuentes['nuevos_clientes'] = custodiar(nuevos_clientes, localizador='libro original de cargas nuevas')
    sistemas = {}
    for pagina, hoja in enumerate(PdfReader(estructura_pdf).pages, 1):
        for linea in (hoja.extract_text() or '').splitlines():
            m = re.match(r'^(SE\d+)\s+(.+?)\s+\d+\s+(?:Set-\d+\s+)?([A-Z]+\d+)\s+(?:EN|FUERA DE) SERVICIO', linea)
            if m:
                sistemas[m[3]] = {'valor': m[2], 'pagina': pagina, 'linea': linea}
    periodos = {}
    libro = load_workbook(mediciones, read_only=True, data_only=True)
    try:
        for hoja in libro.worksheets:
            for fila in hoja.iter_rows(max_row=min(hoja.max_row or 500, 500)):
                for celda in fila:
                    if isinstance(celda.value, (datetime, date)):
                        valor = celda.value.strftime('%Y-%m')
                        periodos.setdefault(valor, {'hoja': hoja.title, 'celda': celda.coordinate,
                                                    'valor_original': celda.value.isoformat()})
            if len(periodos) >= 12:
                break
    finally:
        libro.close()
    if not periodos:
        raise ValueError('el libro no aporta fechas de medicion verificables; no se inventan periodos')
    proyectos = defaultdict(list)
    bindings = []
    for archivo in workspaces:
        fuente_binding = custodiar(archivo, localizador='archivo completo')
        datos = json.loads(Path(archivo).read_text(encoding='utf-8'))
        for clave, vinculo in (datos.get('pf_project_bindings') or {}).items():
            if vinculo.get('source_mode') != 'txt' or vinculo.get('source_fingerprint') != snapshot.fingerprint:
                continue
            nombre = vinculo.get('project')
            if not isinstance(nombre, str) or not nombre.strip():
                continue
            prueba = {**fuente_binding, 'localizador': f'pf_project_bindings/{clave}'}
            bindings.append({'project': nombre, 'source_fingerprint': snapshot.fingerprint,
                             'feeders': vinculo.get('feeders') or [], 'fuente': prueba})
            for feeder in vinculo.get('feeders') or []:
                try:
                    network = dataset.resolve_feeder(feeder)
                except KeyError:
                    continue  # No inferir miembros de un nombre de grupo unido.
                proyectos[network].append({'valor': nombre, 'fuente': prueba})
    partes, semilla_particion = repartir_contextos(snapshot.fingerprint,
        {n: [p['valor'] for p in proyectos.get(n, [])] for n in dataset.feeders})
    contextos = []
    for network in sorted(dataset.feeders):
        feeder = feeder_short_name(network)
        seds = []
        for (section, device), fila in dataset.customer_loads_by_feeder.get(network, ()):
            sed = extract_sed_code(fila.get('CustomerNumber', ''), device, section)
            if sed:
                seds.append({'valor': sed, 'section': section, 'device': device})
        contextos.append({'network_id': network, 'alimentador': feeder,
            'source_fingerprint': snapshot.fingerprint, 'particion': partes[network],
            'seds': seds, 'proyectos': proyectos.get(network, []), 'sistema': sistemas.get(feeder),
            'periodos': sorted(periodos), 'ruta': str(Path(nuevos_clientes).resolve()),
            'fuentes': fuentes})
    return contextos, {'schema_version': 1, 'source_fingerprint': snapshot.fingerprint,
        'fuentes': fuentes, 'periodos': periodos, 'bindings': bindings,
        'semilla_particion': semilla_particion,
        'conteos_reales': {'alimentadores': len(dataset.feeders), 'tramos': len(dataset.sections),
                          'cargas': len(dataset.customer_loads)},
        'autoridad_pertenencia': 'section_owner del TXT; PDF consultivo, sin corregir planos',
        'resultados_nativos_generados': 0}


def reservar_humanas(eventos: list[dict]) -> list[dict]:
    unicas = {}
    for r in eventos:
        if r.get('origen') not in ('confirmado', 'corregido') or r.get('tarea') not in TAREAS or not str(r.get('texto') or '').strip():
            continue
        clave = texto_canonico(r['texto'])
        if clave in unicas and (unicas[clave]['tarea'], unicas[clave].get('datos')) != (r['tarea'], r.get('datos')):
            raise ValueError('anotaciones humanas contradictorias')
        unicas[clave] = r
    return list(unicas.values())


def construir_corpus_real(contextos: list[dict], fuentes_manifest: dict, *, max_train_por_tarea: int = 64,
                         humanas: list[dict] | None = None, politica: Path | None = None) -> tuple[list[dict], dict]:
    """Redacta solicitudes con valores observados; no genera resultados de ingenieria."""
    from .curriculo_maestro import FAMILIAS
    from .curriculo_llm_real import PRUEBA_NUEVA, PREFIJOS
    if not contextos:
        raise ValueError('se requieren contextos reales')
    if type(max_train_por_tarea) is not int or max_train_por_tarea < 1:
        raise ValueError('presupuesto de corpus invalido')
    reservadas = {texto_canonico(r['texto']) for r in reservar_humanas(humanas or [])}
    if set(PRUEBA_NUEVA) != set(TAREAS):
        raise ValueError('prueba sin cobertura del catalogo')
    verificadas = set()
    for c in contextos:
        for f in [*c['fuentes'].values(), *(p['fuente'] for p in c['proyectos'])]:
            clave = (f['ruta'], f['sha256'])
            if clave not in verificadas:
                verificar_fuente(f); verificadas.add(clave)
    por_proyecto = defaultdict(list)
    for c in contextos:
        for p in c['proyectos']:
            por_proyecto[(c['particion'], p['valor'])].append(c)
    filas, vistos, omitidos = [], {}, Counter()
    for c in contextos:
        parte = c['particion']
        for tarea in sorted(TAREAS):
            plantillas = ([*TAREAS[tarea].plantillas, FAMILIAS[tarea][0]] if parte == 'entrenamiento'
                          else [FAMILIAS[tarea][1 if parte == 'seleccion' else 2]]
                          if parte != 'prueba' else [PRUEBA_NUEVA[tarea]])
            for plantilla in dict.fromkeys(plantillas):
                for i, prefijo in enumerate(PREFIJOS):
                    rnd = random.Random(int(huella([c['network_id'], tarea, plantilla, i])[:8], 16))
                    proyecto = c['proyectos'][i % len(c['proyectos'])] if c['proyectos'] else None
                    sistema = c.get('sistema') or {}
                    sed = c['seds'][i % len(c['seds'])] if c['seds'] else None
                    valores = {'alimentadores': c['alimentador'], 'ruta': c['ruta'],
                        'numero': '1', 'texto': 'la lectura de ' + Path(c['ruta']).name,
                        'subtipo': 'alimentación de carga nueva',
                        'periodo': c['periodos'][i % len(c['periodos'])]}
                    if proyecto:
                        valores['proyecto'] = proyecto['valor']
                    if sistema:
                        valores['sistema'] = sistema['valor']
                    if sed:
                        valores['sed'] = sed['valor']
                    if tarea in ('unir', 'transferencia'):
                        candidatos = (por_proyecto[(parte, proyecto['valor'])] if proyecto else
                                      [v for v in contextos if v['particion'] == parte])
                        otros = [v['alimentador'] for v in candidatos if v['network_id'] != c['network_id']]
                        if not otros:
                            omitidos[(parte, tarea)] += 1; continue
                        valores['alimentadores'] += ' y ' + otros[i % len(otros)]
                    if any(not valores.get(t) for t in re.findall(r'\{(\w+)\}', plantilla)):
                        omitidos[(parte, tarea)] += 1; continue
                    texto, datos = renderizar_orden(prefijo + plantilla, valores, rnd)
                    firma = (parte, tarea, tuple((a, b, t) for a, b, t in datos))
                    canonico = texto_canonico(texto)
                    if canonico in reservadas:
                        continue
                    if canonico in vistos:
                        if vistos[canonico] != firma:
                            raise ValueError('solapamiento o contradiccion en instrucciones')
                        continue
                    vistos[canonico] = firma
                    evidencias = [{**c['fuentes'][k], 'localizador':
                                  (f'SECTION/FEEDER={c["network_id"]}' if k == 'red' else c['fuentes'][k]['localizador'])}
                                  for k in ('red', 'loads', 'equipment')]
                    if proyecto and 'proyecto' in {t for _, _, t in datos}:
                        evidencias.append(proyecto['fuente'])
                    for tipo, archivo in (('sistema', 'estructura'), ('periodo', 'mediciones'), ('ruta', 'nuevos_clientes')):
                        if tipo in {t for _, _, t in datos}:
                            evidencias.append(c['fuentes'][archivo])
                    if sed and 'sed' in {t for _, _, t in datos}:
                        evidencias[1] = {**c['fuentes']['loads'], 'localizador':
                                        f'CUSTOMER LOADS/SectionID={sed["section"]}/DeviceNumber={sed["device"]}'}
                    r = {'texto': texto, 'tarea': tarea, 'datos': datos, 'particion': parte,
                         'group_id': huella({'plantilla': plantilla, 'tarea': tarea}),
                         'context_id': huella([c['source_fingerprint'], c['network_id']]),
                         'quality': 'silver_teacher_real_source', 'fuentes': evidencias,
                         'origen': 'Codex maestro de sesion; solicitud redactada con datos reales',
                         'ejecutado': False, 'observacion_humana': False}
                    r['respuesta'] = _respuesta_de_spans(r)
                    r['record_id'] = huella(r)
                    filas.append(r)
    # La prueba se fija balanceada antes del ajuste; el resto no se recicla como train.
    prueba = []
    for i, tarea in enumerate(sorted(TAREAS)):
        candidatos = [r for r in filas if r['particion'] == 'prueba' and r['tarea'] == tarea]
        random.Random(901 + i).shuffle(candidatos)
        n = 8 if i < 11 else 7
        if len(candidatos) < n:
            raise ValueError(f'fuentes insuficientes para prueba nueva de {tarea}: {len(candidatos)}/{n}')
        prueba.extend(candidatos[:n])
    preparadas = []
    for parte, limite in (('entrenamiento', max_train_por_tarea), ('seleccion', 2), ('calibracion', 2)):
        for tarea in sorted(TAREAS):
            candidatos = [r for r in filas if r['particion'] == parte and r['tarea'] == tarea]
            random.Random(int(huella([parte, tarea, 4721])[:8], 16)).shuffle(candidatos)
            preparadas.extend(candidatos[:limite])
    filas = preparadas + prueba
    for parte in PARTICIONES:
        tareas = {r['tarea'] for r in filas if r['particion'] == parte}
        if tareas != set(TAREAS):
            raise ValueError(f'faltan tareas con fuentes reales en {parte}: {set(TAREAS) - tareas}')
    from .curriculo_llm_real import ABSTENCION_TRAIN
    norma = custodiar(politica or raiz_programa() / 'docs/constitution.md',
                      localizador='P9/P11: custodia local y resultados comprobados')
    fuente_real = next(r['fuentes'] for r in filas if r['particion'] == 'entrenamiento')
    for orden in ABSTENCION_TRAIN:
        for prefijo in PREFIJOS:
            r = {'texto': prefijo + orden, 'tarea': None, 'datos': [], 'particion': 'entrenamiento',
                 'group_id': huella(['abstencion', orden]), 'context_id': huella(['control_politica', 'train']),
                 'quality': 'silver_teacher_real_source', 'fuentes': [norma, *fuente_real],
                 'origen': 'Codex maestro de sesion; control de politica fundamentado, no operacion observada',
                 'ejecutado': False, 'observacion_humana': False}
            r['respuesta'] = _respuesta_de_spans(r); r['record_id'] = huella(r); filas.append(r)
    meta = {'schema_version': 2, 'dataset_hash': huella(filas), 'fuentes_manifest': fuentes_manifest,
            'por_particion': dict(Counter(r['particion'] for r in filas)),
            'por_tarea': {p: dict(Counter(r['tarea'] for r in filas if r['particion'] == p)) for p in PARTICIONES},
            'ordenes_humanas': 0, 'instrucciones_redactadas_maestro': True,
            'humanas_reservadas': len(reservadas), 'humanas_text_hashes': sorted(huella(t) for t in reservadas),
            'entidades_red_fuentes_reales': True, 'resultados_nativos_generados': 0,
            'parametros_operativos_maestro': 'numero de escenarios solicitado; subtipo del catalogo, no mediciones',
            'presupuesto_corpus': {'max_train_por_tarea': max_train_por_tarea, 'seleccion_por_tarea': 2,
                                   'calibracion_por_tarea': 2, 'prueba': 200},
            'confianza_anotada': '0.9 es etiqueta de entrenamiento, no posterior calibrado',
            'omitidas_sin_fuente': {f'{p}/{t}': n for (p, t), n in omitidos.items()},
            'maestro': {'autor': 'Codex de sesion', 'metodo': 'response_distillation', 'revision': '20261101-real-v1', 'votos': 1}}
    validar_corpus_real(filas, meta)
    return filas, meta


def validar_corpus_real(filas: list[dict], meta: dict, *, custodia: CustodiaCorpus | None = None) -> None:
    if meta.get('schema_version') != 2 or huella(filas) != meta.get('dataset_hash'):
        raise ValueError('integridad de corpus real invalida')
    textos, grupos, contextos, fuentes = {}, {}, {}, {}
    for r in filas:
        if r.get('record_id') != huella({k: v for k, v in r.items() if k != 'record_id'}):
            raise ValueError('registro modificado')
        if r['particion'] not in PARTICIONES or r.get('quality') != 'silver_teacher_real_source' or not r.get('fuentes'):
            raise ValueError('particion, calidad o fuentes invalidas')
        if r.get('observacion_humana') or r.get('ejecutado') or 'resultado_electrico' in r:
            raise ValueError('no presentar solicitudes del maestro como observacion o resultado real')
        if _respuesta_de_spans(r) != r.get('respuesta'):
            raise ValueError('respuesta distinta de sus etiquetas verificadas')
        for tabla, clave in ((textos, texto_canonico(r['texto'])), (grupos, r['group_id']), (contextos, r['context_id'])):
            if clave in tabla and tabla[clave] != r['particion']:
                raise ValueError('fuga entre particiones')
            tabla[clave] = r['particion']
        for f in r['fuentes']:
            fuentes.setdefault((f['ruta'], f['sha256']), f)
    for f in fuentes.values():
        verificar_fuente(f, custodia=custodia)


def sellar_particiones(dataset: Path, destino: Path) -> dict:
    """El entrenador no necesita abrir los textos de prueba para validar su entrada."""
    import shutil
    filas = json.loads((dataset / 'corpus.json').read_text(encoding='utf-8'))
    meta = json.loads((dataset / 'dataset_manifest.json').read_text(encoding='utf-8'))
    validar_corpus_real(filas, meta)
    if destino.exists():
        raise ValueError('destino existente conservado')
    destino.mkdir(parents=True)
    archivos, huellas = {}, {}
    for parte in PARTICIONES:
        p = destino / (parte + '.jsonl')
        registros = [r for r in filas if r['particion'] == parte]
        p.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in registros), encoding='utf-8')
        archivos[parte] = {**custodiar(p, localizador=parte), 'registros': len(registros)}
        huellas[parte] = huella(registros)
    meta = {**meta, 'archivos_particion': archivos, 'huellas_particion':huellas,
            'prompt_hash': huella(sistema_alumno())}
    for origen, nombre, clave in (('contextos.json', 'contextos_fuente.json', 'contextos_fuente'),
                                 ('humanas_reservadas.json', 'humanas_reservadas.json', 'humanas_reservadas_archivo')):
        if (dataset / origen).is_file():
            shutil.copyfile(dataset / origen, destino / nombre)
            meta[clave] = custodiar(destino / nombre, localizador=clave)
    (destino / 'dataset_manifest.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copyfile(dataset / 'corpus.json', destino / 'corpus_auditoria.json')
    return meta


def leer_particion_real(dataset: Path, parte: str, *, custodia: CustodiaCorpus | None = None) -> tuple[list[dict], dict]:
    meta = json.loads((dataset / 'dataset_manifest.json').read_text(encoding='utf-8'))
    custodia = leer_custodia(dataset, meta) or custodia
    if parte not in PARTICIONES or parte not in (meta.get('archivos_particion') or {}):
        raise ValueError('particion ausente o invalida')
    archivo = meta['archivos_particion'][parte]
    prueba = {k: archivo[k] for k in ('ruta', 'sha256', 'bytes', 'localizador')}
    verificar_fuente(prueba, custodia=custodia)
    if ruta_fuente(archivo, custodia).resolve() != (dataset / (parte + '.jsonl')).resolve():
        raise ValueError('archivo de otra particion')
    registros = [json.loads(l) for l in ruta_fuente(archivo, custodia).read_text(encoding='utf-8').splitlines()]
    if len(registros) != archivo['registros'] or not registros:
        raise ValueError('particion incompleta')
    if huella(registros) != (meta.get('huellas_particion') or {}).get(parte):
        raise ValueError('subconjunto distinto del sellado')
    fuentes = {}
    for r in registros:
        if r['particion'] != parte or r['record_id'] != huella({k: v for k, v in r.items() if k != 'record_id'}):
            raise ValueError('registro de particion modificado')
        if r['respuesta'] != _respuesta_de_spans(r):
            raise ValueError('etiqueta modificada')
        if (r.get('quality') != 'silver_teacher_real_source' or r.get('observacion_humana') or
                r.get('ejecutado') or 'resultado_electrico' in r):
            raise ValueError('procedencia del registro consumido invalida')
        for f in r['fuentes']:
            fuentes.setdefault((f['ruta'], f['sha256']), f)
    for f in fuentes.values():
        verificar_fuente(f, custodia=custodia)
    if meta.get('prompt_hash') != huella(sistema_alumno()):
        raise ValueError('prompt distinto del protocolo sellado')
    if meta.get('humanas_reservadas_archivo'):
        evidencia=meta['humanas_reservadas_archivo'];verificar_fuente(evidencia, custodia=custodia)
        humanas=json.loads(ruta_fuente(evidencia, custodia).read_text(encoding='utf-8'))
        reservadas={texto_canonico(r['texto']) for r in humanas}
        if any(texto_canonico(r['texto']) in reservadas for r in registros):
            raise ValueError('orden humana reservada en particion redactada')
    return registros, meta


def elegir_version_llm(informes: list[dict]) -> dict:
    import math
    if not informes or any(r.get('particion') != 'seleccion' for r in informes):
        raise ValueError('solo se permite elegir con seleccion')
    if len({r.get('dataset_hash') for r in informes}) != 1 or len({r.get('prompt_hash') for r in informes}) != 1:
        raise ValueError('informes de seleccion incompatibles')
    for r in informes:
        m = r['metricas']
        if (m['ejemplos'] <= 0 or set(m['familias']) != set(TAREAS) or
            any(type(m[k]) not in (float, int) or not math.isfinite(m[k]) or not 0 <= m[k] <= 1
                for k in ('acierto_tarea', 'f1_datos'))):
            raise ValueError('metricas de seleccion incompletas')
    ganador = max(informes, key=lambda r: (sum(f['acierto_tarea'] for f in r['metricas']['familias'].values())/len(TAREAS),
                                          r['metricas']['f1_datos']))
    return {'modelo':ganador['modelo'],'modelo_digest':ganador['modelo_digest'],
            'dataset_hash':ganador['dataset_hash'],'prompt_hash':ganador['prompt_hash'],
            'perfil_prompt':'llm_destilado_v1','criterio':'seleccion',
            'metricas_seleccion':ganador['metricas']}


def auditar_fuentes_corpus(dataset: Path, *, custodia: CustodiaCorpus | None = None) -> dict:
    """Comprueba entidades contra registros extraidos; no infiere ni ejecuta estudios."""
    meta=json.loads((dataset/'dataset_manifest.json').read_text(encoding='utf-8'))
    custodia = leer_custodia(dataset, meta) or custodia
    filas=json.loads((dataset/'corpus_auditoria.json').read_text(encoding='utf-8'))
    validar_corpus_real(filas,meta,custodia=custodia)
    evidencia=meta['contextos_fuente'];verificar_fuente(evidencia,custodia=custodia)
    contextos=json.loads(ruta_fuente(evidencia,custodia).read_text(encoding='utf-8'))
    custodia_h=meta['humanas_reservadas_archivo'];verificar_fuente(custodia_h,custodia=custodia)
    humanas=json.loads(ruta_fuente(custodia_h,custodia).read_text(encoding='utf-8'))
    textos_h={texto_canonico(r['texto']) for r in humanas}
    if any(texto_canonico(r['texto']) in textos_h for r in filas):
        raise ValueError('orden humana reservada dentro del corpus redactado')
    por_id={huella([c['source_fingerprint'],c['network_id']]):c for c in contextos}
    revisadas=Counter(); parametros=Counter(); fuentes=set()
    for parte in PARTICIONES:
        registros,_=leer_particion_real(dataset,parte,custodia=custodia)
        if registros != [r for r in filas if r['particion']==parte]:
            raise ValueError('subconjunto consumido distinto del corpus auditado')
        for r in registros:
            fuentes.update((f['ruta'],f['sha256']) for f in r['fuentes'])
            if r['tarea'] is None:
                if parte!='entrenamiento' or r['datos']:
                    raise ValueError('control de politica invalido')
                continue
            c=por_id.get(r['context_id'])
            if c is None or c['particion']!=parte:
                raise ValueError('entidad sin contexto de fuente')
            permitidos={'proyecto':{p['valor'] for p in c['proyectos']},
                'sistema':{c['sistema']['valor']} if c.get('sistema') else set(),
                'sed':{s['valor'] for s in c['seds']},'ruta':{c['ruta']},'periodo':set(c['periodos'])}
            for a,b,tipo in r['datos']:
                valor=r['texto'][a:b]
                if tipo=='alimentadores':
                    nombres=valor.split(' y ')
                    if c['alimentador'] not in nombres:
                        raise ValueError('alimentador ajeno al contexto')
                    for nombre in nombres:
                        otro=next((v for v in contextos if v['alimentador']==nombre and v['particion']==parte),None)
                        if otro is None:
                            raise ValueError('alimentador sin registro TXT en la particion')
                    revisadas[tipo]+=len(nombres)
                elif tipo in permitidos:
                    if valor not in permitidos[tipo]:
                        raise ValueError('valor sin respaldo en referencia: '+tipo)
                    revisadas[tipo]+=1
                elif ((tipo=='numero' and valor=='1') or
                      (tipo=='subtipo' and valor=='alimentación de carga nueva') or
                      (tipo=='texto' and valor=='la lectura de '+Path(c['ruta']).name)):
                    parametros[tipo]+=1
                else:
                    raise ValueError('parametro no declarado o entidad desconocida: '+tipo)
    return {'ok':True,'dataset_hash':meta['dataset_hash'],'por_particion':meta['por_particion'],
        'contextos_reales':len(contextos),'archivos_fuente_verificados':len(fuentes),
        'entidades_contrastadas':dict(revisadas),'parametros_redactados_no_mediciones':dict(parametros),
        'ordenes_humanas_unicas_reservadas':len(textos_h),
        'observaciones_humanas_en_train':0,'resultados_electricos':0,'escrituras_nativas':0}


def evaluar_version_llm(dataset: Path, modelo: str, *, parte: str = 'seleccion',
                        seleccion: Path | None = None, log=print) -> dict:
    from .ollama import ClienteOllama
    from .aceptacion import evaluar_ordenes
    meta = json.loads((dataset / 'dataset_manifest.json').read_text(encoding='utf-8'))
    cliente = ClienteOllama(modelo=modelo, tiempo_max_s=180, pensar=False,
        revisar_transformer=True, perfil_prompt='llm_destilado_v1')
    tags = (cliente._pedir('/api/tags') or {}).get('models') or []
    instalado = next((m for m in tags if m['name'] == modelo), None)
    if not instalado:
        raise ValueError('version local no instalada')
    if parte == 'prueba':
        if seleccion is None:
            raise ValueError('falta seleccion sellada antes de abrir prueba')
        ganador = json.loads(seleccion.read_text(encoding='utf-8'))
        if (ganador.get('criterio') != 'seleccion' or ganador.get('modelo') != modelo or
            ganador.get('modelo_digest') != instalado['digest'] or ganador.get('dataset_hash') != meta['dataset_hash'] or
            ganador.get('prompt_hash') != meta['prompt_hash']):
            raise ValueError('version distinta de la seleccion fijada')
    registros, meta = leer_particion_real(dataset, parte)
    custodia = leer_custodia(dataset, meta)
    evidencia = meta['contextos_fuente']; verificar_fuente(evidencia, custodia=custodia)
    contextos = json.loads(ruta_fuente(evidencia, custodia).read_text(encoding='utf-8'))
    vocabulario = {'alimentadores': sorted({c['alimentador'] for c in contextos}),
        'proyecto': sorted({p['valor'] for c in contextos for p in c['proyectos']}),
        'sistema': sorted({c['sistema']['valor'] for c in contextos if c.get('sistema')}),
        'sed': sorted({s['valor'] for c in contextos for s in c['seds']})}
    try:
        metricas = evaluar_ordenes(registros, cliente=cliente, vocabulario=vocabulario, log=log)
    finally:
        cliente.liberar_gpu(solo_actual=True)
    return {'particion':parte,'modelo':modelo,'modelo_digest':instalado['digest'],
        'dataset_hash':meta['dataset_hash'],'prompt_hash':meta['prompt_hash'],
        'perfil_prompt':'llm_destilado_v1','metricas':metricas,'escrituras_nativas':0}


def config_exportacion(original: dict) -> dict:
    salida = dict(original)
    salida.pop('quantization_config', None)
    salida['torch_dtype'] = 'float16'
    salida['dtype'] = 'float16'
    return salida


def validar_reanudacion(estado: dict, configuracion: dict, epoca: int, base: dict) -> None:
    from .llm_checkpoint import validar_base_checkpoint
    validar_base_checkpoint(estado,base)
    if estado['configuracion'] != configuracion or estado['epoca'] not in (epoca,epoca-1):
        raise ValueError('checkpoint incompatible con datos/configuracion/epoca')
    if estado['epoca'] == epoca-1 and not estado.get('training_completed'):
        raise ValueError('epoca previa incompleta; reanude esa misma epoca primero')
    if estado.get('training_completed') and estado['epoca'] == epoca:
        raise ValueError('epoca ya completada; no acreditar otro entrenamiento')


def ficha_base() -> dict:
    catalogo=json.loads((raiz_programa()/'docs/MODELOS_IA_LOCK.json').read_text(encoding='utf-8'))
    return next(m for m in catalogo['modelos'] if m['backend']=='huggingface' and 'Instruct-2507-bnb-4bit' in m['id'])


def entrenar_epoca(dataset: Path, destino: Path, *, epoca: int = 1, desde: Path | None = None,
                   semilla: int = 11, rango: int = 8, lr: float = 2e-4,
                   acumulacion: int = 8, max_tokens: int = 2048, log=print) -> dict:
    """QLoRA real de todo el train sellado; cada checkpoint permite continuar sin prueba."""
    import math
    import time
    if destino.exists():
        raise ValueError('destino existente conservado')
    if any(type(v) is not int or v < 1 for v in (epoca, rango, acumulacion, max_tokens)) or not 0 < lr < 1:
        raise ValueError('configuracion de entrenamiento invalida')
    registros, meta = leer_particion_real(dataset, 'entrenamiento')
    configuracion = {'dataset_hash': meta['dataset_hash'], 'prompt_hash': meta['prompt_hash'],
        'semilla': semilla, 'rango': rango, 'lr': lr, 'acumulacion': acumulacion, 'max_tokens': max_tokens}
    estado_previo = None
    base=ficha_base()
    if desde:
        from .llm_checkpoint import verificar_checkpoint
        estado_previo = verificar_checkpoint(desde, exigir_completo=False)
        validar_reanudacion(estado_previo,configuracion,epoca,base)
    destino.mkdir(parents=True)
    modelo, tok, ficha = _base_local(base)
    import torch
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    torch.manual_seed(semilla + epoca)
    modelo.config.use_cache = False
    modelo = prepare_model_for_kbit_training(modelo, use_gradient_checkpointing=True,
        gradient_checkpointing_kwargs={'use_reentrant': False})
    modelo = (PeftModel.from_pretrained(modelo, desde / 'adaptador', is_trainable=True, local_files_only=True)
              if desde else get_peft_model(modelo, LoraConfig(r=rango, lora_alpha=2*rango,
                  target_modules='all-linear', lora_dropout=.05, bias='none', task_type='CAUSAL_LM')))
    parametros = [p for p in modelo.parameters() if p.requires_grad]
    if not parametros or any(p.device.type != 'cuda' for p in parametros):
        raise RuntimeError('adaptadores entrenables no estan exclusivamente en CUDA')
    opt = torch.optim.AdamW(parametros, lr=lr)
    if desde:
        guardado = torch.load(desde / 'optimizador.pt', map_location='cpu', weights_only=True)
        opt.load_state_dict(guardado['optimizer'])
        torch.set_rng_state(guardado['rng_cpu'])
        torch.cuda.set_rng_state_all(guardado['rng_cuda'])
    codificados = []
    for r in registros:
        prompt = tok.apply_chat_template([{'role':'system','content':sistema_alumno()},
            {'role':'user','content':r['texto']}], tokenize=False, add_generation_prompt=True)
        prefijo = tok.encode(prompt, add_special_tokens=False)
        respuesta = tok.encode(r['respuesta'] + tok.eos_token, add_special_tokens=False)
        codificados.append(objetivo_causal(prefijo, respuesta, max_tokens=max_tokens))
    orden = list(range(len(registros))); random.Random(semilla + epoca).shuffle(orden)
    misma_epoca = estado_previo is not None and estado_previo['epoca'] == epoca
    inicio_indice = estado_previo['siguiente_indice'] if misma_epoca else 0
    suma = estado_previo['loss_sum'] if misma_epoca else 0.
    vistas = estado_previo['ejemplos_vistos_epoca'] if misma_epoca else 0
    updates = estado_previo['optimizer_updates'] if estado_previo else 0
    inicio = time.monotonic()
    trainables, total_parametros = modelo.get_nb_trainable_parameters()
    torch.cuda.reset_peak_memory_stats(); modelo.train(); opt.zero_grad(set_to_none=True)
    (destino / 'protocolo.json').write_text(json.dumps({'configuracion':configuracion,'base':ficha,
        'epoca':epoca,'registros_train':len(registros),'max_tokens_observados':max(len(a) for a,_ in codificados),
        'parametros_entrenables':trainables,'parametros_totales':total_parametros,
        'desde':str(desde) if desde else None,'teacher_logits':False,'metodo':'response_distillation_QLoRA'},indent=2),encoding='utf-8')

    def guardar(siguiente, completada=False):
        carpeta = destino / ('final' if completada else f'progreso_{updates:06d}')
        carpeta.mkdir()
        modelo.save_pretrained(carpeta / 'adaptador', safe_serialization=True, save_embedding_layers=False)
        torch.save({'optimizer': opt.state_dict(), 'rng_cpu': torch.get_rng_state(),
                    'rng_cuda': torch.cuda.get_rng_state_all()}, carpeta / 'optimizador.pt')
        artefactos = {}
        for archivo in sorted(carpeta.rglob('*')):
            if archivo.is_file():
                with archivo.open('rb') as f:
                    artefactos[archivo.relative_to(carpeta).as_posix()] = hashlib.file_digest(f, 'sha256').hexdigest()
        estado = {'configuracion':configuracion,'base':base,'epoca':epoca,'siguiente_indice':siguiente,
            'ejemplos_vistos_epoca':vistas,'registros_train':len(registros),'optimizer_updates':updates,
            'loss_sum':suma,'loss_media':suma/max(vistas,1),'training_completed':completada,
            'device':'cuda','gpu_peak_bytes':torch.cuda.max_memory_allocated(),
            'duracion_s':time.monotonic()-inicio,'promovido':False,'artefactos':artefactos}
        (carpeta / 'estado.json').write_text(json.dumps(estado,indent=2,allow_nan=False),encoding='utf-8')
        (destino / 'ultimo_checkpoint.json').write_text(json.dumps({'ruta':str(carpeta.resolve()),
            'optimizer_updates':updates,'training_completed':completada}),encoding='utf-8')
        return {**estado,'checkpoint':str(carpeta.resolve())}

    pendientes = len(orden) - inicio_indice
    if pendientes <= 0:
        raise ValueError('checkpoint sin muestras pendientes')
    for posicion in range(inicio_indice, len(orden)):
        ids, labels = codificados[orden[posicion]]
        x = torch.tensor([ids], device='cuda', dtype=torch.long)
        indices = [j-1 for j,v in enumerate(labels) if j > 0 and v != -100]
        objetivo = torch.tensor([labels[j+1] for j in indices], device='cuda', dtype=torch.long)
        with torch.autocast('cuda', dtype=torch.bfloat16):
            logits = modelo(input_ids=x, attention_mask=torch.ones_like(x), use_cache=False,
                            logits_to_keep=torch.tensor(indices,device='cuda')).logits
            perdida = torch.nn.functional.cross_entropy(logits[0].float(), objetivo)
        if not torch.isfinite(perdida):
            raise RuntimeError('perdida no finita; entrenamiento no acreditado')
        tramo = min(acumulacion, len(orden) - (posicion - (posicion-inicio_indice)%acumulacion))
        (perdida / tramo).backward()
        suma += perdida.item(); vistas += 1
        del x, objetivo, logits, perdida
        if (posicion-inicio_indice+1)%acumulacion == 0 or posicion+1 == len(orden):
            norma = torch.nn.utils.clip_grad_norm_(parametros, 1.)
            if not math.isfinite(float(norma)):
                raise RuntimeError('gradientes no finitos')
            updates += 1
            for grupo in opt.param_groups:
                grupo['lr'] = lr * min(1., updates/10.)
            opt.step(); opt.zero_grad(set_to_none=True)
            log(json.dumps({'epoca':epoca,'vistos':vistas,'total':len(registros),
                'optimizer_updates':updates,'loss_media':suma/vistas,'gpu_peak_bytes':torch.cuda.max_memory_allocated(),
                'segundos':round(time.monotonic()-inicio,1)}),flush=True)
            if updates%64 == 0 and posicion+1 != len(orden):
                guardar(posicion+1)
    if vistas != len(registros):
        raise RuntimeError('no se consumio el corpus completo')
    resultado = guardar(len(orden), True)
    (destino / 'resultado.json').write_text(json.dumps(resultado,indent=2,allow_nan=False),encoding='utf-8')
    return resultado


def _base_local(esperada: dict | None = None):
    import os
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    from ..training_coordinator import exigir_memoria_ml
    exigir_memoria_ml(6., minimo_commit_gib=8.)
    ficha=ficha_base()
    if esperada is not None and ficha != esperada:
        raise ValueError('base modificada durante la preparacion')
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA requerida; no hay fallback de entrenamiento a CPU')
    tokenizer = AutoTokenizer.from_pretrained(ficha['id'], revision=ficha['revision'],
        local_files_only=True, trust_remote_code=False)
    modelo = AutoModelForCausalLM.from_pretrained(ficha['id'], revision=ficha['revision'],
        local_files_only=True, trust_remote_code=False, dtype=torch.bfloat16,
        device_map={'': 0}, attn_implementation='sdpa')
    return modelo, tokenizer, ficha


def exportar_fusionado(destino: Path, adaptador: Path | None = None, *, log=print) -> dict:
    """Fusion por tensor usando PEFT; no conserva una copia FP16 completa en RAM/GPU."""
    if destino.exists():
        raise ValueError('destino existente conservado')
    base=ficha_base()
    if adaptador:
        from .llm_checkpoint import verificar_checkpoint, validar_base_checkpoint
        estado=verificar_checkpoint(adaptador.parent)
        validar_base_checkpoint(estado,base)
    destino.mkdir(parents=True)
    modelo, tokenizer, ficha = _base_local(base)
    import torch
    import bitsandbytes as bnb
    from peft import PeftModel
    from peft.tuners.lora.layer import LoraLayer
    from safetensors.torch import save_file
    if adaptador:
        modelo = PeftModel.from_pretrained(modelo, adaptador, local_files_only=True)
        puro = modelo.base_model.model
    else:
        puro = modelo
    lote, bytes_lote, index, artefactos, manejados = {}, 0, {}, [], []
    vistos = set(); total = 0

    def guardar():
        nonlocal lote, bytes_lote
        if not lote:
            return
        nombre = f'model-{len(artefactos)+1:05d}.safetensors'
        with staging_publicacion(destino / nombre) as temporal:
            save_file(lote, str(temporal), metadata={'format': 'pt'})
            temporal.replace(destino / nombre)
        for clave in lote:
            index[clave] = nombre
        with (destino / nombre).open('rb') as f:
            sha = hashlib.file_digest(f, 'sha256').hexdigest()
        artefactos.append({'archivo': nombre, 'sha256': sha, 'bytes': (destino / nombre).stat().st_size})
        log(f'exportacion: shard {len(artefactos)}, {len(index)} tensores', flush=True)
        lote, bytes_lote = {}, 0

    def agregar(nombre, tensor):
        nonlocal bytes_lote, total
        cpu = tensor.detach().to(device='cpu', dtype=torch.float16).contiguous()
        tam = cpu.numel() * cpu.element_size()
        if lote and bytes_lote + tam > 256 * 1024**2:
            guardar()
        lote[nombre] = cpu; bytes_lote += tam; total += tam
        if bytes_lote >= 256 * 1024**2:
            guardar()

    for nombre, modulo in puro.named_modules():
        if not nombre or any(nombre.startswith(p + '.') for p in manejados):
            continue
        if isinstance(modulo, LoraLayer):
            base = modulo.get_base_layer()
            peso = (bnb.functional.dequantize_4bit(base.weight.data, base.weight.quant_state)
                    if isinstance(base, bnb.nn.Linear4bit) else base.weight.detach())
            fusion = peso.float()
            for adapter in modulo.active_adapters:
                fusion = fusion + modulo.get_delta_weight(adapter).float()
            agregar(nombre + '.weight', fusion)
            if base.bias is not None:
                agregar(nombre + '.bias', base.bias)
            manejados.append(nombre)
            del peso, fusion
        elif isinstance(modulo, bnb.nn.Linear4bit):
            peso = bnb.functional.dequantize_4bit(modulo.weight.data, modulo.weight.quant_state)
            agregar(nombre + '.weight', peso)
            if modulo.bias is not None:
                agregar(nombre + '.bias', modulo.bias)
            manejados.append(nombre)
            del peso
        else:
            for clave, parametro in modulo.named_parameters(recurse=False):
                if id(parametro) in vistos:
                    continue  # Embedding/head compartidos: politica HF de pesos ligados.
                vistos.add(id(parametro))
                agregar(nombre + '.' + clave, parametro)
    guardar()
    (destino / 'model.safetensors.index.json').write_text(json.dumps({'metadata': {'total_size': total},
        'weight_map': index}, indent=2), encoding='utf-8')
    (destino / 'config.json').write_text(json.dumps(config_exportacion(puro.config.to_dict()), indent=2), encoding='utf-8')
    tokenizer.save_pretrained(destino)
    resultado = {'ok': True, 'base': ficha['id'], 'revision': ficha['revision'],
        'adaptador': str(adaptador) if adaptador else None, 'tensores': len(index),
        'bytes_pesos': total, 'artefactos': artefactos, 'metodo': 'NF4 dequant + PEFT delta, FP16 por shard',
        'requiere_evaluacion_runtime': True, 'activado': False}
    (destino / 'exportacion.json').write_text(json.dumps(resultado, indent=2), encoding='utf-8')
    return resultado
