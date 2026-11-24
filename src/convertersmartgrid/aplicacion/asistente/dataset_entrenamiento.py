"""Dataset local v2 con procedencia, grupos indivisibles y calidad explícita."""
from __future__ import annotations

from ...dominio.runtime_paths import staging_publicacion
from ...dominio.util import publicar_duradero

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from .calidad_datos import CALIDADES, auditar_contaminacion, texto_canonico
from ...dominio.util import raiz_union


ESQUEMA = 'convertersmartgrid-training-record-v2'
ESQUEMA_DATASET = 'convertersmartgrid-training-dataset-v2'
_RUTA_WINDOWS = re.compile(r'(?i)(?:[a-z]:\\)[^\s"\']+')


def _limpiar(valor: Any) -> Any:
    if isinstance(valor, str):
        return _RUTA_WINDOWS.sub('<RUTA_LOCAL>', valor)
    if isinstance(valor, dict):
        return {str(k): _limpiar(v) for k, v in valor.items()
                if str(k).casefold() not in {'ruta', 'path', 'email', 'telefono', 'dni'}}
    if isinstance(valor, (list, tuple)):
        return type(valor)(_limpiar(v) for v in valor)
    return valor


def _hash(payload: Any) -> str:
    serializado = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), default=str)
    return hashlib.sha256(serializado.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class RegistroEntrenamiento:
    record_id: str
    group_id: str
    tipo: str
    quality: str
    tarea: str
    texto: str
    sistema: str
    sets: tuple[str, ...]
    alimentadores: tuple[str, ...]
    mensajes: tuple[dict[str, str], ...]
    datos: tuple[tuple[str, str], ...]
    resultado: dict[str, Any]
    provenance: dict[str, Any]
    evidence_hashes: tuple[str, ...]
    license: str
    verification: str
    motivo: str = ''
    schema: str = ESQUEMA

    @property
    def estado(self) -> str:
        """Alias de lectura para consumidores v1 durante la migración."""
        if self.quality in {'gold_human', 'gold_native'}:
            return 'gold'
        return self.quality

    @property
    def procedencia(self) -> dict[str, Any]:
        return self.provenance

    @property
    def verificacion(self) -> str:
        return self.verification

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DatasetConstruido:
    registros: tuple[RegistroEntrenamiento, ...]
    inventario: dict[str, int]


def descubrir_alimentadores_inventarios(raiz_web: Path | str) -> list[str]:
    """Une identidades explícitas; un sufijo de nombre no prueba pertenencia (043:RF-2)."""
    codigos: set[str] = set()
    for ruta in Path(raiz_web).rglob('dataset_inventory.json'):
        try:
            inventario = json.loads(ruta.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        for fila in inventario.get('feeders') or ():
            valor = str(fila.get('feeder') or fila.get('network_id') or '').strip()
            if valor:
                codigos.add(valor)
    return sorted(codigos)


def _crear(*, group_basis: Any | None = None, **campos: Any) -> RegistroEntrenamiento:
    campos = _limpiar(campos)
    quality = str(campos['quality'])
    if quality not in CALIDADES:
        raise ValueError(f'calidad desconocida: {quality}')
    grupo = _hash(group_basis if group_basis is not None else {
        'tipo': campos['tipo'], 'tarea': campos['tarea'],
        'texto': texto_canonico(campos['texto']),
        'source_run_id': campos['provenance'].get('source_run_id'),
    })
    identidad = _hash({'schema': ESQUEMA, 'group_id': grupo, **campos})
    return RegistroEntrenamiento(record_id=identidad, group_id=grupo, **campos)


def crear_registro(*, group_basis: Any | None = None, **campos: Any) -> RegistroEntrenamiento:
    """Construye un registro v2 validado para productores internos del dataset."""
    return _crear(group_basis=group_basis, **campos)


def normalizar_orden(fila: dict[str, Any]) -> RegistroEntrenamiento:
    from .tareas import TAREAS,TIPOS_DATO

    texto_crudo=str(fila.get('texto') or '')
    crudos=fila.get('datos',[])
    crudos=[] if crudos is None else crudos
    anotaciones_validas=isinstance(crudos,(list,tuple))
    pares=[]
    for d in crudos if anotaciones_validas else ():
        if not isinstance(d,(list,tuple)):
            anotaciones_validas=False;continue
        if len(d)==3 and type(d[0]) is int and type(d[1]) is int and 0<=d[0]<d[1]<=len(texto_crudo):
            tipo,valor=d[2],texto_crudo[d[0]:d[1]]
        elif len(d)==2:
            tipo,valor=d
        else:
            anotaciones_validas=False;continue
        if not isinstance(tipo,str) or tipo not in TIPOS_DATO or not isinstance(valor,str) or not valor or valor not in texto_crudo:
            anotaciones_validas=False;continue
        pares.append((tipo,str(_limpiar(valor))))
    datos=tuple(pares)
    alimentadores = tuple(sorted({valor for clave, valor in datos
                                  if clave == 'alimentadores' and valor}))
    confirmada = fila.get('origen') in {'confirmado', 'corregido'}
    valida = bool(fila.get('tarea') in (*TAREAS,'ninguna') and texto_crudo.strip() and anotaciones_validas)
    quality = 'gold_human' if confirmada and valida else 'quarantine'
    texto = str(_limpiar(str(fila.get('texto') or '')))
    tarea = str(fila.get('tarea') or '')
    verification = 'operator_corrected' if fila.get('origen') == 'corregido' else (
        'operator_confirmed' if quality == 'gold_human' else '')
    provenance = {'fecha': fila.get('fecha'), 'origen': fila.get('origen'),'anotaciones_hash':_hash(crudos)}
    for clave in ('operador', 'challenge_id', 'plan_id'):
        if fila.get(clave):
            provenance[clave] = fila[clave]
    return crear_registro(
        group_basis={'tipo': 'orden', 'tarea': tarea, 'texto': texto_canonico(texto)},
        tipo='orden', quality=quality, tarea=tarea, texto=texto, sistema='', sets=(),
        alimentadores=alimentadores, mensajes=({'role': 'user', 'content': texto},),
        datos=datos, resultado={}, provenance=provenance, evidence_hashes=(),
        license='internal', verification=verification,
        motivo='' if quality == 'gold_human' else ('anotaciones de entidades inválidas o no literales'
            if not anotaciones_validas else 'orden sin confirmación/corrección o tarea válida'))


def normalizar_informe(fila: dict[str, Any]) -> RegistroEntrenamiento:
    """043:RF-3: las etiquetas del maestro o del generador no son humanas."""
    from ...dominio.contratos_aprendizaje import TIPOS_INFORME

    texto=str(fila.get('texto') or '')
    tipo=str(fila.get('tipo') or '')
    subtipo=str(fila.get('subtipo') or '').strip()
    origen=str(fila.get('origen') or '')
    valido=bool(texto.strip() and tipo in TIPOS_INFORME and subtipo)
    humana=valido and origen in {'confirmado','corregido'}
    quality='gold_human' if humana else ('context' if valido and origen=='generado' else 'quarantine')
    verificacion=('operator_corrected' if origen=='corregido' else 'operator_confirmed') if humana else ''
    provenance={'fecha':fila.get('fecha'),'origen':origen}
    for clave in ('origen_inicial','revision_humana'):
        if fila.get(clave) is not None:
            provenance[clave]=fila[clave]
    return _crear(group_basis={'tipo':'informe','texto':texto_canonico(str(_limpiar(texto)))},
        tipo='informe',quality=quality,tarea='clasificar_informe',texto=texto,sistema='',
        sets=(),alimentadores=(),mensajes=({'role':'user','content':texto},),datos=(),
        resultado={'tipo_informe':tipo,'subtipo':subtipo},
        provenance=provenance,evidence_hashes=(),
        license='internal',verification=verificacion,
        motivo='' if humana else ('informe generado: etiqueta de contexto' if quality=='context'
                                   else 'informe sin etiquetas válidas confirmadas/corregidas por el operador'))


def normalizar_episodio(payload: dict[str, Any]) -> RegistroEntrenamiento:
    nativo = payload.get('nativo') or {}
    topologia = payload.get('topologia') or {}
    aceptacion = payload.get('aceptacion') or {}
    fuente = payload.get('fuente') or {}
    sets = tuple(sorted(str(s) for s in topologia.get('sets') or () if s))
    alimentadores = tuple(sorted(str(f) for f in nativo.get('feeders') or () if f))
    accepted = (
        payload.get('clase') == 'accepted' and bool(sets)
        and nativo.get('reopen_verified') is True
        and (payload.get('flujo') or {}).get('convergio') is True
        and aceptacion.get('estado_nativo') == 'aceptado'
        and not aceptacion.get('bloqueos')
    )
    if 'schema' in payload:
        # 043:RF-3: el formato vigente se valida en su única vía, no con campos legacy.
        from ...dominio.digital_twin.episode import Clase, EpisodioInvalido, leer_episodio
        try:
            episodio = leer_episodio(payload)
            # Sin exigir ``sets``: ningún episodio real lo escribe, y los 66 aceptados del buffer
            # (2026-11-02) iban a cuarentena. ``particionar_dataset`` agrupa por alimentador.
            accepted = (episodio.clase is Clase.ACCEPTED and bool(alimentadores)
                        and nativo.get('reopen_verified') is True and not aceptacion.get('bloqueos'))
        except EpisodioInvalido:
            accepted = False
    quality = 'gold_native' if accepted else 'quarantine'
    tarea = str((payload.get('accion') or {}).get('tipo') or 'accion_nativa')
    proyecto = str(nativo.get('project') or '')
    texto = f'{tarea} en {proyecto} para {", ".join(alimentadores)}'.strip()
    hashes = tuple(sorted({str(v) for k, v in fuente.items()
                           if ('sha256' in str(k).casefold() or k == 'source_fingerprint') and v}
                          | {str(a['sha256']) for a in payload.get('artefactos', ())
                             if isinstance(a, dict) and a.get('sha256')}))
    provenance = {
        'episode_id': payload.get('episode_id'),
        'source_run_id': fuente.get('source_run_id'),
        'source_mode': fuente.get('source_mode'),
        'source_fingerprint': fuente.get('source_fingerprint'),
        'reopen_verified': nativo.get('reopen_verified') is True,
        'pf_version': nativo.get('pf_version'),
    }
    result = {'clase': payload.get('clase'),
              'convergio': (payload.get('flujo') or {}).get('convergio'),
              'estado_nativo': aceptacion.get('estado_nativo')}
    return _crear(
        group_basis={'tipo': 'episodio', 'episode_id': payload.get('episode_id'),
                     'source_run_id': fuente.get('source_run_id')},
        tipo='episodio', quality=quality, tarea=tarea, texto=texto, sistema=proyecto,
        sets=sets, alimentadores=alimentadores,
        mensajes=({'role': 'user', 'content': texto},
                  {'role': 'assistant', 'content': json.dumps(result, ensure_ascii=False)}),
        datos=(), resultado=result, provenance=provenance, evidence_hashes=hashes,
        license='internal', verification='powerfactory_reopened' if accepted else '',
        motivo='' if accepted else 'episodio sin aceptación nativa convergente y reabierta')


def registrar_evento_conversion(
    *, outbox: Path | str, source_run_id: str, source_mode: str,
    source_fingerprint: str, todos_alimentadores: list[str] | tuple[str, ...],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Deposita contexto sin permitir que un error bloquee la conversión."""
    try:
        modo = str(source_mode).casefold()
        if modo not in {'txt', 'mdb', 'vnr'}:
            raise ValueError(f'modo no soportado: {source_mode}')
        items = manifest.get('feeders') or ()
        estados = {str(i.get('network_id') or i.get('feeder')): str(i.get('status'))
                   for i in items if i.get('network_id') or i.get('feeder')}
        payload = {
            'schema': 'convertersmartgrid-conversion-event-v1', 'source_run_id': str(source_run_id),
            'source_mode': modo, 'source_fingerprint': str(source_fingerprint),
            'todos_alimentadores': sorted({str(f) for f in todos_alimentadores if f}),
            'convertidos': sorted(f for f, estado in estados.items() if estado == 'ok'),
            'estados': dict(sorted(estados.items())),
        }
        event_id = _hash(payload)
        payload['event_id'] = event_id
        raiz = Path(outbox)
        raiz.mkdir(parents=True, exist_ok=True)
        final = raiz / f'{event_id}.json'
        if not final.exists():
            publicar_duradero(final, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))   # 001:RF-5
        return {'ok': True, 'event_id': event_id, 'path': str(final)}
    except Exception as exc:  # frontera: la IA no bloquea la conversión
        return {'ok': False, 'warning': f'DATASET_IA_NO_ACTUALIZADO: {exc}'}


def normalizar_evento_conversion(evento: dict[str, Any]) -> tuple[RegistroEntrenamiento, ...]:
    convertidos = set(str(f) for f in evento.get('convertidos') or ())
    salida = []
    for alimentador in sorted(set(str(f) for f in evento.get('todos_alimentadores') or ())):
        completada = alimentador in convertidos
        texto = (f'Fuente {evento.get("source_mode")} contiene el alimentador {alimentador}; '
                 f'conversión {"completada" if completada else "no solicitada"}.')
        salida.append(_crear(
            group_basis={'source': evento.get('source_fingerprint'), 'feeder': alimentador},
            tipo='contexto_conversion', quality='context', tarea='convertir', texto=texto,
            sistema='', sets=(), alimentadores=(alimentador,),
            mensajes=({'role': 'user', 'content': texto},), datos=(),
            resultado={'convertido': completada,
                       'estado': (evento.get('estados') or {}).get(alimentador)},
            provenance={k: evento.get(k) for k in (
                'event_id', 'source_run_id', 'source_mode', 'source_fingerprint')},
            evidence_hashes=(str(evento.get('source_fingerprint')),), license='internal',
            verification='conversion_manifest', motivo='contexto; no es aceptación eléctrica'))
    return tuple(salida)


def importar_historial_web(web_root: Path | str, outbox: Path | str) -> dict[str, Any]:
    """Consolida recargas de una fuente por modo+huella antes de depositar contexto."""
    grupos: dict[tuple[str, str], dict[str, Any]] = {}
    runs = 0
    for manifiesto in sorted(Path(web_root).glob('*/runs/*/source_manifest.json')):
        try:
            fuente = json.loads(manifiesto.read_text(encoding='utf-8'))
            modo = str(fuente.get('mode') or '').casefold()
            huella = str(fuente.get('fingerprint') or '')
            inventario_path = manifiesto.parent / 'salida' / 'dataset_inventory.json'
            if modo not in {'txt', 'mdb', 'vnr'} or not huella or not inventario_path.is_file():
                continue
            grupo = grupos.setdefault((modo, huella), {'feeders': set(), 'states': {}})
            inventario = json.loads(inventario_path.read_text(encoding='utf-8'))
            for item in inventario.get('feeders') or ():
                feeder = item.get('network_id') or item.get('feeder')
                if feeder:
                    grupo['feeders'].add(str(feeder))
            lote_path = manifiesto.parent / 'salida' / 'batch_manifest.json'
            if lote_path.is_file():
                lote = json.loads(lote_path.read_text(encoding='utf-8'))
                for item in lote.get('feeders') or ():
                    feeder = item.get('network_id') or item.get('feeder')
                    if not feeder:
                        continue
                    estado = str(item.get('status') or '')
                    anterior = grupo['states'].get(str(feeder))
                    if anterior != 'ok' or estado == 'ok':
                        grupo['states'][str(feeder)] = estado
            runs += 1
        except (OSError, ValueError, TypeError):
            continue
    created = 0
    for (modo, huella), grupo in sorted(grupos.items()):
        manifest = {'feeders': [{'network_id': f, 'status': e}
                                for f, e in sorted(grupo['states'].items())]}
        result = registrar_evento_conversion(
            outbox=outbox, source_run_id=f'history:{modo}:{huella}',
            source_mode=modo, source_fingerprint=huella,
            todos_alimentadores=sorted(grupo['feeders']), manifest=manifest)
        created += int(bool(result.get('ok')))
    return {'runs': runs, 'sources': len(grupos), 'events': created}


_EXTENSIONES_CONTEXTO = {'.csv', '.dgs', '.docx', '.json', '.mdb', '.pdf', '.txt',
                         '.xls', '.xlsb', '.xlsx'}


def importar_artefactos_contexto(
    raiz: Path | str, *, origen: str,
) -> tuple[RegistroEntrenamiento, ...]:
    """Inventaría por huella sin convertir existencia en verdad supervisada."""
    base = Path(raiz)
    if not base.is_dir():
        return ()
    salida: dict[str, RegistroEntrenamiento] = {}
    for path in sorted(base.rglob('*')):
        if not path.is_file() or path.suffix.casefold() not in _EXTENSIONES_CONTEXTO:
            continue
        if any(p in {'.git', '.venv', '__pycache__', 'node_modules'}
               for p in path.relative_to(base).parts):
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            size = path.stat().st_size
        except OSError:
            continue
        if digest in salida:
            continue
        relative = path.relative_to(base).as_posix()
        text = f'Artefacto {origen}: {relative} ({size} bytes).'
        salida[digest] = _crear(
            group_basis={'artifact_sha256': digest}, tipo='artefacto_contexto',
            quality='context', tarea='seleccionar_datos_pide', texto=text,
            sistema='', sets=(), alimentadores=(),
            mensajes=({'role': 'user', 'content': text},), datos=(),
            resultado={'sha256': digest, 'bytes': size, 'extension': path.suffix.casefold()},
            provenance={'origen': origen, 'ruta_relativa': relative,
                        'source_run_id': f'{origen}:{digest}'},
            evidence_hashes=(digest,), license='internal', verification='file_hash',
            motivo='contexto; no es aceptación')
    return tuple(salida[key] for key in sorted(salida))


def importar_normativa(raiz: Path | str) -> tuple[RegistroEntrenamiento, ...]:
    """Importa snapshots citables; licencia ausente mantiene el registro en cuarentena."""
    base = Path(raiz)
    manifest_path = base / 'manifest.json'
    if not manifest_path.is_file():
        return ()
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ()
    salida = []
    base_resuelta = base.resolve()
    vistos: set[str] = set()
    for doc in manifest.get('documentos') or ():
        digest = str(doc.get('sha256') or '')
        relative = str(doc.get('texto') or '')
        if not digest or digest in vistos or not relative:
            continue
        path = (base / relative).resolve()
        if not path.is_relative_to(base_resuelta) or not path.is_file():
            continue
        license_name = str(doc.get('license') or doc.get('licencia') or '').strip()
        compatible = bool(license_name and license_name.casefold() not in {
            'unknown', 'desconocida', 'sin declarar'})
        try:
            text = path.read_text(encoding='utf-8', errors='replace').strip()
        except OSError:
            continue
        vistos.add(digest)
        quality = 'context' if compatible else 'quarantine'
        title = str(doc.get('titulo') or doc.get('id') or 'Norma')
        salida.append(_crear(
            group_basis={'normative_sha256': digest}, tipo='contexto_normativo',
            quality=quality, tarea='consultar_normativa_pide', texto=text,
            sistema='', sets=(), alimentadores=(),
            mensajes=({'role': 'user', 'content': f'Fuente oficial: {title}'},
                      {'role': 'assistant', 'content': text}), datos=(),
            resultado={'titulo': title}, provenance={
                'source_run_id': f'normativa:{digest}', 'source_url': doc.get('url'),
                'autoridad': doc.get('autoridad')}, evidence_hashes=(digest,),
            license=license_name, verification='normative_snapshot_sha256',
            motivo='' if compatible else 'licencia ausente o sin declarar'))
    return tuple(salida)


#: 026:RF-49: cómo acabó una operación del diario (061), en las palabras del corpus. «interrumpido» es un fallo: la web
#: cayó con el trabajo dentro y no se sabe qué dejó.
RESULTADO_ACCION = {'done': 'hecho', 'parcial': 'parcial', 'failed': 'fallido', 'no_converge': 'fallido',
                    'interrumpido': 'fallido', 'cancelled': 'cancelado'}
#: La tarea de los registros de acciones: no es una de ``TAREAS``, así que el entrenamiento del intérprete de órdenes
#: (``entrenamiento_dataset``) no las toma por órdenes; las lee el planificador (``evaluar_acciones_aprendidas``).
TAREA_ACCION = 'proponer_accion'
_CLASE_TRABAJO = re.compile(r'^[a-z][a-z0-9_]{0,63}$')


def _anonimo(prefijo: str, valor: Any) -> str:
    return f'{prefijo}-{hashlib.sha256(f"csg-{prefijo}:{valor}".encode()).hexdigest()[:12]}' if valor else ''


def normalizar_accion_operador(fila: dict[str, Any], *, espacio: str,
                               anterior: tuple[str, str] | None = None,
                               selladas: frozenset[str] = frozenset()) -> RegistroEntrenamiento:
    """026:RF-49: una operación acabada del diario (061), anonimizada, con su contexto y su resultado.

    Del trabajo solo se queda lo que no identifica a nadie: su clase (``convert``, ``pf_calibrar``…, un código del
    programa), cómo acabó, la fuente del espacio (txt, mdb o vnr) y qué se hizo antes en el mismo espacio. Nada del
    título, del error ni del resultado detallado (llevan alimentadores, proyectos y rutas); el espacio, la huella de la
    fuente y el trabajo, por su huella con sal; de los proyectos de DIgSILENT, cuántos hay, nunca sus nombres. Un texto
    que coincida con una frase sellada (``fuga_evaluacion.frases_selladas``) va a cuarentena: lo aprendido entrena, nunca
    examina."""
    from ..evaluacion_modelos import texto_canonico as canon

    contexto = fila.get('contexto') if isinstance(fila.get('contexto'), dict) else {}
    clase = str(fila.get('kind') or '')
    resultado = RESULTADO_ACCION.get(str(fila.get('status') or ''), '')
    modo = str(contexto.get('source_mode') or '').casefold()
    fuente = modo if modo in {'txt', 'mdb', 'vnr'} else 'sin_fuente'
    previa = f'{anterior[0]} {anterior[1]}' if anterior else 'nada'
    # Lo que hace el propio programa (el asistente encola sus trabajos con su prefijo) se aprende igual, con su
    # procedencia: «de lo que el operador hace en la web y de lo que hace el programa» (usuario, 2026-11-18).
    procedencia = 'programa' if clase.startswith('asistente') else 'operador_web'
    valida = bool(_CLASE_TRABAJO.match(clase) and resultado)
    quien = 'el asistente' if procedencia == 'programa' else 'el operador'
    trabajo = _anonimo('trabajo', fila.get('id'))
    # El texto lleva la operación (anonimizada): dos operaciones del mismo contexto son dos casos distintos, no el mismo
    # texto repetido. Sin ella, ``particionar_dataset`` las juntaba en una partición por su texto y lo que evalúa nunca
    # tenía un contexto que se hubiera aprendido: la puerta no se podía pasar nunca.
    texto = (f'Operación {trabajo}. Espacio con fuente {fuente}; antes: {previa}. Lo siguiente que lanzó {quien}: '
             f'{clase}; acabó {resultado}.' if valida else f'Operación {trabajo} del diario sin clase o sin resultado.')
    sellada = valida and canon(texto) in selladas
    espacio_anonimo = _anonimo('espacio', espacio)
    proyectos = contexto.get('proyectos_registrados')
    provenance = {'origen': 'diario_operaciones_061', 'procedencia': procedencia, 'espacio': espacio_anonimo,
                  'trabajo': trabajo,
                  'source_fingerprint': _anonimo('huella', contexto.get('source_fingerprint')),
                  'proyectos_registrados': len(proyectos) if isinstance(proyectos, dict) else 0,
                  'creado': fila.get('created_at'), 'diario_seq': fila.get('seq_registro')}
    quality = ('quarantine' if not valida or sellada else
               'gold_human' if procedencia == 'operador_web' else 'silver_deterministic')
    return _crear(
        group_basis={'tipo': 'accion_operador', 'espacio': espacio_anonimo, 'trabajo': provenance['trabajo']},
        tipo='accion_operador', quality=quality, tarea=TAREA_ACCION, texto=texto, sistema='', sets=(),
        alimentadores=(), mensajes=({'role': 'user', 'content': texto},), datos=(),
        resultado={'accion': clase, 'resultado': resultado, 'fuente': fuente, 'anterior': previa},
        provenance=provenance, evidence_hashes=(), license='internal',
        verification='' if quality == 'quarantine' else (
            'operator_action_observed' if procedencia == 'operador_web' else 'program_action_observed'),
        motivo=('' if quality != 'quarantine' else 'texto de una prueba sellada' if sellada
                else 'operación sin clase o sin resultado válidos'))


def importar_diarios_operaciones(raiz_web: Path | str) -> tuple[RegistroEntrenamiento, ...]:
    """026:RF-49: las operaciones acabadas de los diarios de cada espacio (061) al corpus del planificador.

    Cada espacio tiene su diario en su ``salida`` (o en la de cada corrida); el espacio es la carpeta. Lo de antes de
    cada operación es la anterior acabada del mismo espacio: así se aprende «tras convertir, calibrar»."""
    from .fuga_evaluacion import frases_selladas

    base = Path(raiz_web)
    if not base.is_dir():
        return ()
    selladas = frozenset().union(*frases_selladas().values())
    salida: list[RegistroEntrenamiento] = []
    diarios = sorted({*base.glob('*/salida/observacion/operaciones.sqlite3'),
                      *base.glob('*/runs/*/salida/observacion/operaciones.sqlite3')})
    for diario in diarios:
        salida.extend(_acciones_del_diario(diario, diario.relative_to(base).parts[0], selladas))
    return tuple(salida)


def _acciones_del_diario(diario: Path, espacio: str, selladas: frozenset[str]) -> list[RegistroEntrenamiento]:
    """Las operaciones acabadas de un diario, en orden, cada una con la anterior acabada que no fue a cuarentena."""
    from .observacion import RegistroOperaciones

    salida: list[RegistroEntrenamiento] = []
    anterior: tuple[str, str] | None = None
    for fila in RegistroOperaciones(diario, espacio).terminadas():
        registro = normalizar_accion_operador(fila, espacio=espacio, anterior=anterior, selladas=selladas)
        salida.append(registro)
        if registro.quality != 'quarantine':
            anterior = (registro.resultado['accion'], registro.resultado['resultado'])
    return salida


def auditar_registro(registro: RegistroEntrenamiento) -> list[str]:
    errores = []
    pendientes=[registro.as_dict()]
    while pendientes:
        valor=pendientes.pop()
        if isinstance(valor,str) and _RUTA_WINDOWS.search(valor):
            errores.append('contiene ruta local');break
        if isinstance(valor,dict):
            pendientes.extend(valor.keys());pendientes.extend(valor.values())
        elif isinstance(valor,(list,tuple)):
            pendientes.extend(valor)
    if registro.quality.startswith('gold_') and not registro.verification:
        errores.append('oro sin verificación')
    if registro.quality == 'gold_native' and not registro.evidence_hashes:
        errores.append('oro nativo sin evidencia')
    return errores


def construir_dataset(
    raiz_asistente: Path | str, raiz_gemelo: Path | str, *,
    raices_contexto: list[tuple[str, Path | str]] | None = None,
    raiz_normativa: Path | str | None = None,
    raiz_web: Path | str | None = None,
) -> DatasetConstruido:
    registros: list[RegistroEntrenamiento] = []
    ejemplos = Path(raiz_asistente) / 'ejemplos.jsonl'
    if ejemplos.is_file():
        for linea in ejemplos.read_text(encoding='utf-8').splitlines():
            if linea.strip():
                registros.append(normalizar_orden(json.loads(linea)))
    informes=Path(raiz_asistente)/'informes.jsonl'
    if informes.is_file():
        filas=[normalizar_informe(json.loads(l)) for l in informes.read_text(encoding='utf-8').splitlines() if l.strip()]
        etiquetas: dict[str,set[str]]={}
        for r in filas:
            if r.quality=='gold_human':
                etiquetas.setdefault(texto_canonico(r.texto),set()).add(json.dumps(r.resultado,sort_keys=True))
        for r in filas:
            if r.quality=='gold_human' and len(etiquetas[texto_canonico(r.texto)])>1:
                campos=r.as_dict();campos.pop('record_id');campos.pop('group_id')
                campos.update(quality='quarantine',verification='',motivo='etiquetas humanas contradictorias del mismo informe')
                r=_crear(group_basis={'tipo':'informe','texto':texto_canonico(r.texto)},**campos)
            registros.append(r)
    objetos = Path(raiz_gemelo) / 'objetos'
    if objetos.is_dir():
        for ruta in sorted(objetos.rglob('*.json')):
            registros.append(normalizar_episodio(json.loads(ruta.read_text(encoding='utf-8'))))
    outbox = Path(raiz_asistente) / 'conversion_outbox'
    if outbox.is_dir():
        for ruta in sorted(outbox.glob('*.json')):
            registros.extend(normalizar_evento_conversion(
                json.loads(ruta.read_text(encoding='utf-8'))))
    for origen, raiz_contexto in raices_contexto or ():
        registros.extend(importar_artefactos_contexto(raiz_contexto, origen=origen))
    if raiz_normativa is not None:
        registros.extend(importar_normativa(raiz_normativa))
    if raiz_web is not None:
        registros.extend(importar_diarios_operaciones(raiz_web))      # 026:RF-49
    unicos = {r.record_id: r for r in registros if not auditar_registro(r)}
    ordenados = tuple(unicos[k] for k in sorted(unicos))
    inventario = Counter(r.quality for r in ordenados)
    return DatasetConstruido(ordenados, {q: inventario.get(q, 0) for q in CALIDADES})


def particionar_dataset(
    registros: list[RegistroEntrenamiento] | tuple[RegistroEntrenamiento, ...],
    *, semilla: str = 'convertersmartgrid-v2',
) -> dict[str, tuple[RegistroEntrenamiento, ...]]:
    partes: dict[str, list[RegistroEntrenamiento]] = {
        'train': [], 'validation': [], 'test': []}
    elegibles = sorted((r for r in registros if r.quality != 'quarantine'),
                       key=lambda r: r.record_id)
    padre = list(range(len(elegibles)))

    def raiz(i: int) -> int:
        return raiz_union(padre, i)

    def unir(a: int, b: int) -> None:
        x, y = raiz(a), raiz(b)
        if x != y:
            padre[max(x, y)] = min(x, y)

    por_grupo: dict[str, int] = {}
    por_texto: dict[str, int] = {}
    # 043:RF-4: los episodios de un alimentador van juntos. Con ``group_id`` solo, SM298, NA293, AL195
    # y CA191 caían en varias particiones (2026-11-02), y se evaluaba con redes ya vistas al entrenar.
    por_alimentador: dict[str, int] = {}
    for i, registro in enumerate(elegibles):
        if registro.tipo == 'episodio':
            for alimentador in registro.alimentadores:
                if alimentador in por_alimentador:
                    unir(i, por_alimentador[alimentador])
                por_alimentador.setdefault(alimentador, i)
        texto = texto_canonico(registro.texto)
        for clave, indice in ((registro.group_id, por_grupo.get(registro.group_id)),
                              (texto, por_texto.get(texto))):
            if clave and indice is not None:
                unir(i, indice)
        por_grupo.setdefault(registro.group_id, i)
        if texto:
            por_texto.setdefault(texto, i)
    componentes: dict[int, list[RegistroEntrenamiento]] = {}
    for i, registro in enumerate(elegibles):
        componentes.setdefault(raiz(i), []).append(registro)
    for filas in componentes.values():
        identidad = min(r.group_id for r in filas)
        cubeta = int(hashlib.sha256(f'{semilla}:{identidad}'.encode()).hexdigest()[:8], 16) % 100
        nombre = 'train' if cubeta < 80 else ('validation' if cubeta < 90 else 'test')
        partes[nombre].extend(filas)
    return {nombre: tuple(filas) for nombre, filas in partes.items()}


def escribir_particiones(
    particiones: dict[str, tuple[RegistroEntrenamiento, ...]], destino: Path | str,
) -> dict[str, Any]:
    auditoria = auditar_contaminacion(particiones)
    if not auditoria['valid']:
        raise ValueError(f'dataset contaminado: {auditoria}')
    raiz = Path(destino)
    raiz.mkdir(parents=True, exist_ok=True)
    archivos = {}
    for nombre in ('train', 'validation', 'test'):
        filas = particiones.get(nombre, ())
        contenido = ''.join(json.dumps(r.as_dict(), ensure_ascii=False, sort_keys=True) + '\n'
                            for r in filas)
        with staging_publicacion(raiz / f'{nombre}.jsonl') as temporal:
            temporal.write_bytes(contenido.encode('utf-8'))
            final = raiz / f'{nombre}.jsonl'
            os.replace(temporal, final)
        archivos[nombre] = {
            'count': len(filas), 'sha256': hashlib.sha256(contenido.encode()).hexdigest(),
            'qualities': dict(sorted(Counter(r.quality for r in filas).items())),
        }
    qualities = Counter(r.quality for rows in particiones.values() for r in rows)
    base = {'schema': ESQUEMA_DATASET, 'partitions': archivos,
            'qualities': dict(sorted(qualities.items())), 'audit': auditoria}
    base['sha256'] = _hash(base)
    publicar_duradero(raiz / 'manifest.json', json.dumps(base, ensure_ascii=False, sort_keys=True, indent=2))
    return base


def muestras_aprendizaje(instantanea: dict, referencias: dict, familias: list[str], *, leer_dataset) -> list:
    """050:RF-2/3: conserva las partes y calidades v2 que consumirán los trabajadores."""
    from ...dominio.contratos_aprendizaje import CicloBloqueado, muestra_de_registro, ruta_de

    partes, _ = leer_dataset(ruta_de(instantanea, 'dataset'))
    nombres = {'train': 'entrenamiento', 'validation': 'seleccion', 'test': 'prueba'}
    muestras = []
    for parte, filas in partes.items():
        for fila in filas:
            elegidas = [f for f in familias if (f == 'transformer' and fila.get('tipo') == 'orden'
                or f == 'clasificador' and fila.get('tipo') == 'informe')]
            if not elegidas:
                continue
            calidad = fila.get('quality')
            if calidad == 'quarantine':
                raise CicloBloqueado(f'{fila["record_id"]}: registro en cuarentena dentro de una partición v2')
            etiqueta = {'gold_human': 'operador', 'gold_native': 'motor_nativo',
                        'silver_deterministic': 'maestro', 'silver_teacher_verified': 'maestro',
                        'silver_maestro_texto_real': 'maestro', 'context': 'maestro'}.get(calidad)
            if etiqueta is None:
                raise CicloBloqueado(f'{fila["record_id"]}: calidad v2 desconocida')
            origen = ('observado' if calidad == 'gold_human' else
                      'simulado_nativo' if calidad == 'gold_native' else 'redactado')
            for familia in elegidas:
                muestras.append(muestra_de_registro(instantanea, referencias, 'dataset',
                    fila['record_id'], fila, familia=familia, particion=nombres[parte],
                    origen=origen, etiqueta=etiqueta))
    if 'embeddings' in familias:
        dataset = ruta_de(instantanea, 'dataset')
        for entrenamiento, nombre, particion in ((True, 'retrieval_train', 'entrenamiento'),
                                                  (False, 'retrieval_test', 'prueba')):
            for clave, r in consultas_recuperacion(dataset, partes, entrenamiento=entrenamiento):
                humana = r.get('verification') in ('operator_confirmed', 'operator_corrected')
                muestras.append(muestra_de_registro(instantanea, referencias, 'dataset',
                    clave, r, familia='embeddings', particion=particion,
                    origen='observado' if humana else 'redactado',
                    etiqueta='operador' if humana else 'maestro'))
    return muestras


def consultas_recuperacion(dataset: Path, partes: dict, *, entrenamiento: bool) -> list[tuple[str, dict]]:
    """050:RF-2/11: ``(registro, consulta)`` consumidos; las mismas al declarar y al comprobar."""
    from ...dominio.contratos_aprendizaje import CicloBloqueado
    from .embeddings import cargar_dataset_recuperacion, construir_preguntas_extractivas
    from .indice import Fragmento
    nombre = 'retrieval_train' if entrenamiento else 'retrieval_test'
    # El lector verifica grupos, textos, reservas y fuentes de los pares consumidos.
    _, pares = cargar_dataset_recuperacion(dataset, entrenamiento=entrenamiento)
    ruta = dataset / f'{nombre}.jsonl'
    if ruta.is_file():
        consultas = [json.loads(l) for l in ruta.read_text(encoding='utf-8').splitlines() if l.strip()]
    else:
        fragmentos = [Fragmento(i, f'{(r.get("provenance") or {}).get("source_url") or "documento_local"}#{r["record_id"]}', r['texto'])
            for i, r in enumerate(partes['train']) if r.get('quality') == 'context']
        consultas = construir_preguntas_extractivas(fragmentos)
    if len(consultas) != len(pares):
        raise CicloBloqueado('embeddings: consultas distintas de las consumidas')
    return [(f'{nombre}:{_hash(r)}', r) for r in consultas]


#: 026:RF-49: lo aprendido del operador se usa solo si, con casos que no vio al aprender, acierta lo que hizo el operador
#: al menos así y con al menos tantos casos. Con menos no se sabe: se dice cuántos faltan.
ACIERTO_MINIMO_ACCIONES = 0.8
MIN_CASOS_ACCIONES = 5
ESQUEMA_ACCIONES = 'convertersmartgrid-acciones-aprendidas-v1'


def _acciones(registros) -> list[dict[str, Any]]:
    filas = [r.as_dict() if isinstance(r, RegistroEntrenamiento) else dict(r) for r in registros]
    return [f for f in filas if f.get('tipo') == 'accion_operador' and f.get('quality') != 'quarantine']


def _huella_acciones(candidato: Mapping[str, Any]) -> str:
    return _hash({k: candidato.get(k) for k in ('schema', 'tabla', 'evaluacion', 'puertas')})


def acciones_intactas(candidato: Mapping[str, Any] | None) -> bool:
    """026:RF-49: si lo aprendido es lo que se midió (su huella cuadra con su tabla, evaluación y puertas)."""
    return bool(candidato) and candidato.get('huella') == _huella_acciones(candidato)


def evaluar_acciones_aprendidas(entrenamiento, evaluacion) -> dict[str, Any]:
    """026:RF-49: aprende de ``entrenamiento`` qué lanza el operador en cada contexto (fuente del espacio y lo de antes)
    y lo mide con ``evaluacion``, que no puede compartir registro ni grupo con lo aprendido (027:RF-18).

    En cada contexto se queda la acción que más veces acabó bien, restando las que fallaron o se cancelaron allí: un
    paso que el operador lanza y siempre falla no se propone. El candidato sale con sus puertas y **sin promover**: lo
    promueve el operador (``promover_acciones_aprendidas``), nunca esta función ni un ciclo (027:RF-21, 061:RF-8)."""
    aprende, examina = _acciones(entrenamiento), _acciones(evaluacion)
    if ({f['record_id'] for f in aprende} & {f['record_id'] for f in examina}
            or {f['group_id'] for f in aprende} & {f['group_id'] for f in examina}):
        raise ValueError('lo que evalúa las acciones aprendidas comparte registros o grupos con lo que aprende')
    puntos: Counter = Counter()
    for f in aprende:
        r = f['resultado']
        peso = {'hecho': 1, 'fallido': -1, 'cancelado': -1}.get(r['resultado'], 0)
        puntos[(r['fuente'], r['anterior'], r['accion'])] += peso
    mejor: dict[tuple[str, str], tuple[int, str]] = {}
    for (fuente, previa, accion), n in sorted(puntos.items()):
        if n > 0 and (n, accion) > mejor.get((fuente, previa), (0, '')):
            mejor[(fuente, previa)] = (n, accion)
    tabla = [[fuente, previa, accion] for (fuente, previa), (_, accion) in sorted(mejor.items())]
    propone = {(fuente, previa): accion for fuente, previa, accion in tabla}
    casos = [f['resultado'] for f in examina if f['resultado']['resultado'] == 'hecho']
    aciertos = sum(propone.get((r['fuente'], r['anterior'])) == r['accion'] for r in casos)
    acierto = round(aciertos / len(casos), 4) if casos else None
    fallos = []
    if len(casos) < MIN_CASOS_ACCIONES:
        fallos.append(f'faltan casos de evaluación: {len(casos)} de {MIN_CASOS_ACCIONES}')
    elif acierto < ACIERTO_MINIMO_ACCIONES:
        fallos.append(f'acierto {acierto} bajo {ACIERTO_MINIMO_ACCIONES} con {len(casos)} casos')
    candidato = {'schema': ESQUEMA_ACCIONES, 'tabla': tabla,
                 'evaluacion': {'casos': len(casos), 'aciertos': aciertos, 'acierto': acierto,
                                'aprendidas_de': len(aprende)},
                 'puertas': {'superadas': not fallos, 'fallos': fallos,
                             'acierto_minimo': ACIERTO_MINIMO_ACCIONES, 'casos_minimos': MIN_CASOS_ACCIONES}}
    return {**candidato, 'huella': _huella_acciones(candidato), 'promovido': False}


def promover_acciones_aprendidas(candidato: Mapping[str, Any], *, confirmado_por: str) -> dict[str, Any]:
    """026:RF-49: el operador promueve lo aprendido, y solo si pasó sus puertas y nadie lo tocó después de medirlo."""
    if candidato.get('huella') != _huella_acciones(candidato):
        raise ValueError('las acciones aprendidas cambiaron después de evaluarse: hay que evaluarlas de nuevo')
    if not (candidato.get('puertas') or {}).get('superadas'):
        raise ValueError('las acciones aprendidas no pasaron sus puertas: ' +
                         '; '.join((candidato.get('puertas') or {}).get('fallos') or ['sin evaluar']))
    if not str(confirmado_por or '').strip():
        raise ValueError('promover lo aprendido lo confirma el operador')
    return {**candidato, 'promovido': True, 'promovido_por': str(confirmado_por)}


def propuesta_aprendida(candidato: Mapping[str, Any] | None, *, fuente: str, anterior: str) -> dict[str, Any] | None:
    """026:RF-49: lo que propone el asistente porque lo aprendió del operador, o ``None`` si no hay nada promovido,
    evaluado e intacto para ese contexto. La propuesta se confirma como cualquier otra: aprender no da permiso."""
    if (not candidato or candidato.get('promovido') is not True
            or candidato.get('huella') != _huella_acciones(candidato)
            or not (candidato.get('puertas') or {}).get('superadas')):
        return None
    for f, previa, accion in candidato.get('tabla') or ():
        if f == fuente and previa == anterior:
            ev = candidato['evaluacion']
            return {'accion': accion, 'confirma_el_operador': True,
                    'motivo': (f'el operador lo lanzó en este contexto; aprendido y evaluado con {ev["casos"]} casos '
                               f'que no vio (acierto {ev["acierto"]})')}
    return None


#: 026:RF-49: dónde queda lo aprendido en el almacén del asistente (fuera de git). El candidato medido y lo que el
#: operador promovió van en ficheros distintos: construir el dataset otra vez rehace el candidato y nunca toca lo que
#: está en uso, que solo cambia cuando el operador promueve.
CARPETA_ACCIONES = 'acciones_aprendidas'


def _rutas_acciones(raiz: Path | str) -> tuple[Path, Path]:
    base = Path(raiz) / CARPETA_ACCIONES
    return base / 'candidato.json', base / 'en_uso.json'


def _leer_acciones(ruta: Path) -> dict[str, Any] | None:
    try:
        datos = json.loads(ruta.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise ValueError(f'{ruta.name} de lo aprendido no se puede leer: {exc}') from exc
    return datos if isinstance(datos, dict) else None


def guardar_candidato_acciones(raiz: Path | str, candidato: Mapping[str, Any]) -> Path:
    """026:RF-49: deja el candidato entero (tabla, evaluación, puertas y huella) para que el operador lo vea y decida.

    Siempre sin promover, y nunca encima de uno promovido: lo promovido no se rehace construyendo el dataset."""
    ruta, _ = _rutas_acciones(raiz)
    if candidato.get('promovido') is not False or candidato.get('schema') != ESQUEMA_ACCIONES:
        raise ValueError('lo aprendido se guarda como candidato, medido y sin promover')
    previo = _leer_acciones(ruta)
    if previo and previo.get('promovido') is True:
        raise ValueError('ya hay unas acciones aprendidas promovidas en el sitio del candidato: no se pisan')
    publicar_duradero(ruta, json.dumps(dict(candidato), ensure_ascii=False, indent=2) + '\n')
    return ruta


def leer_acciones_aprendidas(raiz: Path | str) -> dict[str, Any]:
    """026:RF-49: el candidato medido y lo que está en uso, tal como están en el almacén (``None`` si no hay)."""
    candidato, en_uso = _rutas_acciones(raiz)
    return {'candidato': _leer_acciones(candidato), 'en_uso': _leer_acciones(en_uso)}


def promover_y_guardar_acciones(raiz: Path | str, *, huella: str, confirmado_por: str, fecha: str) -> dict[str, Any]:
    """026:RF-49: el operador promueve el candidato que vio (``huella``); queda aparte, en uso, de forma atómica.

    Falla con su motivo si no hay candidato, si no es el que vio, si no pasó sus puertas o si lo tocaron tras medirlo."""
    candidato_ruta, en_uso_ruta = _rutas_acciones(raiz)
    candidato = _leer_acciones(candidato_ruta)
    if not candidato:
        raise ValueError('no hay acciones aprendidas que promover: construya antes el dataset')
    if candidato.get('huella') != huella:
        raise ValueError('las acciones aprendidas no son las que se revisaron: vuelva a revisarlas')
    promovido = {**promover_acciones_aprendidas(candidato, confirmado_por=confirmado_por), 'promovido_en': fecha}
    publicar_duradero(en_uso_ruta, json.dumps(promovido, ensure_ascii=False, indent=2) + '\n')
    return promovido


def anterior_del_espacio(diario: Path | str, espacio: str) -> str:
    """026:RF-49: lo último acabado en el espacio, en la forma del corpus («convert hecho» o «nada»), con la misma
    anonimización y la misma cuarentena con que se aprendió: la propuesta busca el contexto tal como se midió."""
    from .fuga_evaluacion import frases_selladas

    hechas = [r for r in _acciones_del_diario(Path(diario), espacio, frozenset().union(*frases_selladas().values()))
              if r.quality != 'quarantine']
    return f'{hechas[-1].resultado["accion"]} {hechas[-1].resultado["resultado"]}' if hechas else 'nada'
