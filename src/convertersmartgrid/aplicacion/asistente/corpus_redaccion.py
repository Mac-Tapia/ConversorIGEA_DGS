"""Lo que los entregables de otra empresa enseñan al asistente: redactar y dar formato (spec 072, RF-19).

El usuario autorizó el 2026-11-02 usar los entregables PIDE de otra distribuidora para entrenar, «con revisión
humana», y la spec lo limita a redactar y dar formato, nunca como verdad eléctrica: las cifras de esos
informes son de otra red y tienen incoherencias propias (más proyectos en una alternativa que hojas de
evaluación). Por eso aquí:

* solo entra un fragmento aprobado con su revisor, su fecha y su origen declarado: ``humano`` (una persona) o
  ``maestro`` (un revisor independiente, por orden del usuario del 2026-11-19: «no deberían ser limitaciones otras
  personas para cerrar»); cualquier otro origen, o ninguno, no entra (072:RF-48). El origen nunca se cambia: lo del
  maestro va marcado ``maestro`` en el registro, en cada ejemplo y en el recuento del corpus sellado;
* el uso declarado es ``redaccion`` o ``formato``; cualquier otro se rechaza al registrar;
* el texto entra con las cifras, los códigos de elementos y los nombres de empresa, sede e instalación ocultos
  (072:RF-49): el modelo aprende cómo se escribe una sección, no los kW, las barras ni los nombres de otra empresa;
* lo aprobado se sella en el formato de corpus que lee ``tools/asistente_qlora.py``, con su prompt (072:RF-50, RF-51);
* el registro es solo de añadir (JSONL), la última decisión de cada fragmento manda, y una revisión vale
  para el texto que se revisó: si el corpus se reconstruye y el texto cambia, vuelve a estar pendiente.

Los fragmentos son los de ``pide_dataset`` (``fragments.jsonl``). Las hojas de cálculo no son redacción: los
formatos se aprenden por sus columnas en ``ejemplos_pide`` (027:RF-48), no por sus cifras.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

#: Usos que autoriza 072:RF-19; «verdad eléctrica» no es uno de ellos.
USOS = ('redaccion', 'formato')
#: Orígenes que admite el registro y que entran, cada uno marcado con el suyo (072:RF-48).
ORIGENES = ('humano', 'maestro')
SCHEMA = 'csg-corpus-redaccion-revision-v1'

_CODIGO = re.compile(r'\b(?=[A-Za-zÁÉÍÓÚÑáéíóúñ]*\d)(?=\d*[A-Za-zÁÉÍÓÚÑáéíóúñ])[A-Za-zÁÉÍÓÚÑáéíóúñ0-9_]*\d'
                     r'[A-Za-zÁÉÍÓÚÑáéíóúñ0-9_]*\b')
_NUMERO = re.compile(r'\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*')


class CorpusRedaccionError(ValueError):
    """Una revisión que no cumple lo que autoriza 072:RF-19."""


#: Etiqueta de cada clase del catálogo de nombres (072:RF-49); una lista sin clases usa ``‹nombre›``.
_ETIQUETAS = {'empresa': '‹empresa›', 'sede': '‹sede›', 'instalacion': '‹instalación›', 'instalación': '‹instalación›'}
_VARIANTES = {'a': 'aáàä', 'e': 'eéèë', 'i': 'iíìï', 'o': 'oóòö', 'u': 'uúùü', 'n': 'nñ'}
_SIN_TILDE = str.maketrans('áàäéèëíìïóòöúùüñ', 'aaaeeeiiiooouuun')
_PALABRA = r"[A-ZÁÉÍÓÚÑÜ][\w'’\-]*"
_NOMBRE = rf'{_PALABRA}(?:\s+(?:(?:de|del|la|las|los|el)\s+){{0,2}}{_PALABRA})*'
#: Patrones genéricos, sin nombres reales: lo que sigue a «SET», a una subestación, central o sede, y la razón social.
_INSTALACION = re.compile(r'(?<!\w)((?:SET|S\.E\.T\.|S\.E\.|Subestaci[oó]n|SUBESTACI[OÓ]N|C\.T\.|C\.H\.|'
                          r'(?:Central|CENTRAL)\s+(?:T[eé]rmica|T[EÉ]RMICA|Hidroel[eé]ctrica|HIDROEL[EÉ]CTRICA|'
                          r'Solar|SOLAR|E[oó]lica|E[OÓ]LICA))\s+(?:de\s+)?)' + f'({_NOMBRE})')
_SEDE = re.compile(r'(?<!\w)((?i:sede(?:\s+regional)?|unidad\s+de\s+negocios?|zonal)\s+(?i:de\s+)?)' + f'({_NOMBRE})')
_EMPRESA = re.compile(rf'(?<!\w){_NOMBRE},?\s+(?:S\.A\.A\.|S\.A\.C\.|S\.A\.|S\.R\.L\.|E\.I\.R\.L\.|SAA|SAC)(?!\w)')


def _patron_nombre(nombre: str) -> str:
    """El nombre sin distinguir mayúsculas ni tildes, con cualquier espacio entre palabras."""
    partes: list[str] = []
    for c in nombre.strip():
        base = c.lower().translate(_SIN_TILDE)
        if c.isspace():
            if partes[-1:] != [r'\s+']:
                partes.append(r'\s+')
        elif base in _VARIANTES:
            partes.append('[' + _VARIANTES[base] + ']')
        else:
            partes.append(re.escape(c))
    return r'(?<!\w)' + ''.join(partes) + r'(?!\w)'


def _nombres(catalogo) -> list[tuple[str, str]]:
    """(nombre, etiqueta) del catálogo, el más largo primero: «Villa Quimera Alta» antes que «Villa Quimera»."""
    if not catalogo:
        return []
    if isinstance(catalogo, Mapping):
        pares = [(str(n), _ETIQUETAS.get(str(clase).lower(), '‹nombre›')) for clase, nombres in catalogo.items()
                 for n in ([nombres] if isinstance(nombres, str) else nombres or ())]
    else:
        pares = [(str(n), '‹nombre›') for n in ([catalogo] if isinstance(catalogo, str) else catalogo)]
    vistos: dict[str, str] = {}
    for n, etiqueta in pares:
        if n.strip():
            vistos.setdefault(n.strip(), etiqueta)
    return sorted(vistos.items(), key=lambda p: -len(p[0]))


def sin_nombres(texto: str, catalogo=None) -> str:
    """El texto con los nombres de empresa, sede e instalación ocultos (072:RF-49).

    ``catalogo`` llega en tiempo de ejecución, de los datos del espacio: ``{'empresa': [...], 'sede': [...],
    'instalacion': [...]}`` o una lista de nombres. Sin catálogo también se ocultan el nombre que sigue a «SET», a una
    subestación, central o sede, y la razón social que termina en «S.A.A.», «S.A.» o semejantes. Ocultar de más es
    seguro; ocultar de menos filtra la red de referencia.
    """
    for nombre, etiqueta in _nombres(catalogo):
        texto = re.sub(_patron_nombre(nombre), etiqueta, texto, flags=re.IGNORECASE)
    texto = _INSTALACION.sub(lambda m: m.group(1) + '‹instalación›', texto)
    texto = _SEDE.sub(lambda m: m.group(1) + '‹sede›', texto)
    return _EMPRESA.sub('‹empresa›', texto)


def sin_cifras(texto: str, catalogo=None) -> str:
    """El texto con los nombres, los códigos de elementos y las cifras ocultos: la forma queda, los valores no."""
    return _NUMERO.sub('‹n›', _CODIGO.sub('‹código›', sin_nombres(texto, catalogo)))


def catalogo_del_corpus(fragmentos: Iterable[Mapping[str, Any]], catalogo=None) -> dict[str, list[str]]:
    """El catálogo dado más la empresa que declara cada fragmento: su propio nombre nunca sale (072:RF-49)."""
    clases = {v: k for k, v in _ETIQUETAS.items() if k != 'instalación'}
    out: dict[str, list[str]] = {}
    for nombre, etiqueta in _nombres(catalogo):
        out.setdefault(clases.get(etiqueta, 'nombre'), []).append(nombre)
    for f in fragmentos:
        empresa = str(f.get('empresa') or '').strip()
        for variante in (empresa, empresa.replace('_', ' ')):
            if variante and variante not in out.setdefault('empresa', []):
                out['empresa'].append(variante)
    return out


def huella_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def _es_redaccion(fragmento: Mapping[str, Any]) -> bool:
    return not str(fragmento.get('location') or '').startswith('sheet:') and bool(str(fragmento.get('text') or '').strip())


def _leer(registro: Path) -> list[dict]:
    if not registro.is_file():
        return []
    return [json.loads(x) for x in registro.read_text(encoding='utf-8').splitlines() if x.strip()]


def _vigentes(registro: Path) -> dict[str, dict]:
    """La última decisión de cada fragmento: el registro solo se añade, nunca se reescribe."""
    ultimas: dict[str, dict] = {}
    for fila in _leer(registro):
        ultimas[fila['record_id']] = fila
    return ultimas


def registrar_revision(registro: Path | str, fragmento: Mapping[str, Any], *, revisor: str, origen: str,
                       aprobado: bool, uso: str, fecha: str | None = None, nota: str = '') -> dict:
    """Anota la decisión de una persona sobre un fragmento (072:RF-19) y la devuelve."""
    if origen not in ORIGENES:
        raise CorpusRedaccionError(f'origen «{origen}» no admitido: {" o ".join(ORIGENES)}; la revisión humana '
                                   'o la del revisor independiente, cada una con su origen declarado')
    if not str(revisor or '').strip():
        raise CorpusRedaccionError('la revisión no dice quién es el revisor')
    if uso not in USOS:
        raise CorpusRedaccionError(f'uso «{uso}» no autorizado: solo {", ".join(USOS)}, nunca como verdad eléctrica')
    if not fragmento.get('record_id') or not _es_redaccion(fragmento):
        raise CorpusRedaccionError('el fragmento no es texto de un informe con su record_id')
    fila = {'schema': SCHEMA, 'record_id': str(fragmento['record_id']),
            'huella_texto': huella_texto(str(fragmento['text'])), 'fuente': fragmento.get('relative_path') or '',
            'empresa': fragmento.get('empresa') or '', 'periodo': fragmento.get('periodo') or '',
            'uso': uso, 'aprobado': bool(aprobado), 'verdad_electrica': False,
            'revisor': str(revisor).strip(), 'origen': origen, 'fecha': fecha or date.today().isoformat(),
            'nota': nota}
    registro = Path(registro)
    registro.parent.mkdir(parents=True, exist_ok=True)
    with registro.open('a', encoding='utf-8') as f:
        f.write(json.dumps(fila, ensure_ascii=False, sort_keys=True) + '\n')
    return fila


def ejemplos_para_entrenar(registro: Path | str, fragmentos: Iterable[Mapping[str, Any]], *,
                           catalogo=None) -> list[dict]:
    """Los fragmentos aprobados, sin cifras ni nombres, con su procedencia y su origen (072:RF-19, RF-48, RF-49)."""
    vigentes = _vigentes(Path(registro))
    fragmentos = list(fragmentos)
    catalogo = catalogo_del_corpus(fragmentos, catalogo)
    out = []
    for f in fragmentos:
        r = vigentes.get(str(f.get('record_id')))
        if (r is None or not r['aprobado'] or r.get('origen') not in ORIGENES or r.get('uso') not in USOS
                or not _es_redaccion(f) or r['huella_texto'] != huella_texto(str(f['text']))):
            continue
        out.append({'record_id': r['record_id'], 'uso': r['uso'], 'texto': sin_cifras(str(f['text']), catalogo),
                    'fuente': r['fuente'], 'empresa': r['empresa'], 'periodo': r['periodo'],
                    'revisor': r['revisor'], 'fecha': r['fecha'], 'origen': r['origen'],
                    'huella_texto': r['huella_texto'], 'verdad_electrica': False})
    return out


def pendientes(registro: Path | str, fragmentos: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Los fragmentos de redacción sin una revisión del texto que tienen hoy."""
    vigentes = _vigentes(Path(registro))
    return [f for f in fragmentos if _es_redaccion(f)
            and (vigentes.get(str(f.get('record_id'))) or {}).get('huella_texto') != huella_texto(str(f['text']))]


def resumen(registro: Path | str, fragmentos: Iterable[Mapping[str, Any]]) -> dict:
    """Cuánto del corpus está revisado, aprobado y pendiente: el registro del corpus revisado (T9)."""
    fragmentos = [f for f in fragmentos if _es_redaccion(f)]
    vigentes = _vigentes(Path(registro))
    revisadas = [vigentes[str(f['record_id'])] for f in fragmentos
                 if (vigentes.get(str(f.get('record_id'))) or {}).get('huella_texto') == huella_texto(str(f['text']))]
    aprobadas = [r for r in revisadas if r['aprobado']]
    return {'fragmentos': len(fragmentos), 'revisados': len(revisadas), 'aprobados': len(aprobadas),
            'rechazados': len(revisadas) - len(aprobadas), 'pendientes': len(fragmentos) - len(revisadas),
            'por_uso': dict(Counter(r['uso'] for r in aprobadas)),
            'revisores': sorted({r['revisor'] for r in revisadas})}


# --- 072:RF-50: el puente de lo aprobado al corpus sellado que lee tools/asistente_qlora.py -------------------------

TIPO_CORPUS = 'redaccion_pide'
CALIDAD = 'redaccion_revisada'
#: El prompt de sistema del ajuste de redacción; su huella queda sellada como la del alumno de órdenes.
SISTEMA_REDACCION = ('Redactas y das formato a secciones de informes PIDE en español formal y claro. Las cifras, los '
                     'códigos y los nombres de otra red van ocultos (‹n›, ‹código›, ‹empresa›, ‹sede›, '
                     '‹instalación›): aprendes la forma, nunca la verdad eléctrica.')
INSTRUCCIONES = {'redaccion': 'Redacta un párrafo de un informe PIDE, claro y formal.',
                 'formato': 'Escribe el título, la leyenda o la línea de un informe PIDE con su formato.'}
#: Reparto por documento, ordenado por su huella: siete de cada diez van a entrenamiento.
_REPARTO = ('entrenamiento',) * 7 + ('seleccion', 'calibracion', 'prueba')


def tipo_corpus(dataset: Path | str) -> str | None:
    """El tipo que declara el manifiesto de un corpus sellado; ``None`` si no lo declara o no se lee."""
    try:
        meta = json.loads((Path(dataset) / 'dataset_manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return meta.get('tipo_corpus') if isinstance(meta, dict) else None


def _anonimo(texto: str, catalogo) -> str:
    """``sin_cifras`` hasta que no cambie: lo sellado no conserva nada que un segundo paso aún ocultaría."""
    for _ in range(4):
        siguiente = sin_cifras(texto, catalogo)
        if siguiente == texto:
            break
        texto = siguiente
    return texto


def validar_corpus_redaccion(filas: list[dict], meta: dict) -> None:
    """Lo que admite el corpus sellado de redacción: aprobado con su origen declarado, anónimo y con su fuente."""
    from ..evaluacion_modelos import huella, texto_canonico
    from .llm_destilacion import PARTICIONES, verificar_fuente
    if (meta.get('tipo_corpus') != TIPO_CORPUS or meta.get('schema_version') != 2
            or meta.get('verdad_electrica') is not False or huella(filas) != meta.get('dataset_hash')):
        raise ValueError('integridad del corpus de redacción inválida')
    textos: dict[str, str] = {}
    grupos: dict[str, str] = {}
    fuentes: dict[tuple, dict] = {}
    for r in filas:
        if r.get('record_id') != huella({k: v for k, v in r.items() if k != 'record_id'}):
            raise ValueError('registro modificado')
        if r.get('particion') not in PARTICIONES or r.get('quality') != CALIDAD or not r.get('fuentes'):
            raise ValueError('partición, calidad o fuentes inválidas')
        if r.get('uso') not in USOS or r.get('texto') != INSTRUCCIONES[r['uso']]:
            raise ValueError('uso o instrucción no autorizados')
        revision = r.get('revision') or {}
        if revision.get('origen') not in ORIGENES or not str(revision.get('revisor') or '').strip():
            raise ValueError('ejemplo sin revisor u origen declarado (humano o maestro)')
        if r.get('verdad_electrica') is not False or r.get('ejecutado') or 'resultado_electrico' in r:
            raise ValueError('la redacción nunca es verdad eléctrica ni resultado ejecutado')
        respuesta = r.get('respuesta')
        # Cifra es un dígito decimal: el «²» de m² o km² es unidad, no valor.
        if (not isinstance(respuesta, str) or not respuesta.strip() or re.search(r'\d', respuesta)
                or sin_cifras(respuesta) != respuesta):
            raise ValueError('texto con cifras o nombres sin ocultar')
        for tabla, clave in ((textos, texto_canonico(respuesta)), (grupos, r['group_id'])):
            if tabla.setdefault(clave, r['particion']) != r['particion']:
                raise ValueError('fuga entre particiones')
        for f in r['fuentes']:
            fuentes.setdefault((f['ruta'], f['sha256'], f['localizador']), f)
    if not any(r['particion'] == 'entrenamiento' for r in filas):
        raise ValueError('el corpus de redacción no trae ejemplos de entrenamiento')
    if meta.get('por_origen') != dict(Counter(r['revision']['origen'] for r in filas)):
        raise ValueError('el recuento por origen del manifiesto no es el de sus ejemplos')
    for f in fuentes.values():
        verificar_fuente(f)


def sellar_corpus_redaccion(dataset: Path | str, destino: Path | str, *, registro: Path | str | None = None,
                            catalogo=None) -> dict:
    """Sella lo aprobado, anónimo y con su origen, con el formato de ``sellar_particiones`` (072:RF-50).

    Solo entra lo que exporta :func:`ejemplos_para_entrenar` (origen ``humano`` o ``maestro``, aprobado, texto sin
    cambios); cada ejemplo lleva su origen y el manifiesto, el recuento ``por_origen``. Entra con
    las cifras y los nombres ocultos. Los textos que quedan iguales tras ocultarlos entran una vez. Cada documento va
    entero a una partición; la respuesta es el texto, y la orden, la instrucción fija de su uso.
    """
    import tempfile
    from ..evaluacion_modelos import huella, texto_canonico
    from .llm_destilacion import custodiar, sellar_particiones
    from ...dominio.util import write_json_atomic
    dataset, destino = Path(dataset), Path(destino)
    if destino.exists():
        raise ValueError('destino existente conservado')
    ruta_fragmentos = dataset / 'fragments.jsonl'
    fragmentos = _leer(ruta_fragmentos)
    registro = Path(registro) if registro else dataset / 'revision_redaccion.jsonl'
    catalogo = catalogo_del_corpus(fragmentos, catalogo)
    ejemplos = ejemplos_para_entrenar(registro, fragmentos, catalogo=catalogo)
    if not ejemplos:
        raise CorpusRedaccionError('ninguna aprobación vigente con origen declarado (humano o maestro): '
                                   'no se sella nada')
    fuente = custodiar(ruta_fragmentos, localizador='fragments.jsonl')
    unicos, vistos = [], set()
    for e in ejemplos:
        texto = _anonimo(e['texto'], catalogo)
        if texto_canonico(texto) not in vistos:
            vistos.add(texto_canonico(texto))
            unicos.append((e, texto))
    grupos = sorted({huella(['redaccion_pide', e['fuente']]) for e, _ in unicos})
    parte_de = {g: _REPARTO[i % len(_REPARTO)] for i, g in enumerate(grupos)}
    filas = []
    for e, texto in unicos:
        grupo = huella(['redaccion_pide', e['fuente']])
        r = {'texto': INSTRUCCIONES[e['uso']], 'respuesta': texto, 'uso': e['uso'], 'particion': parte_de[grupo],
             'group_id': grupo, 'fragmento': e['record_id'], 'quality': CALIDAD,
             'revision': {'origen': e['origen'], 'revisor': e['revisor'], 'fecha': e['fecha'],
                          'huella_texto': e['huella_texto']},
             'fuentes': [{**fuente, 'localizador': f"fragments.jsonl/record_id={e['record_id']}"}],
             'verdad_electrica': False, 'ejecutado': False, 'observacion_humana': False}
        r['record_id'] = huella(r)
        filas.append(r)
    meta = {'schema_version': 2, 'tipo_corpus': TIPO_CORPUS, 'dataset_hash': huella(filas),
            'por_particion': dict(Counter(r['particion'] for r in filas)),
            'por_uso': dict(Counter(r['uso'] for r in filas)), 'verdad_electrica': False,
            'por_origen': dict(Counter(r['revision']['origen'] for r in filas)),
            'ordenes_humanas': 0, 'resultados_nativos_generados': 0,
            'sistema': SISTEMA_REDACCION, 'instrucciones': INSTRUCCIONES, 'fuente_fragmentos': fuente,
            'registro_revision': {'sha256': hashlib.sha256(registro.read_bytes()).hexdigest(),
                                  'aprobadas': len(ejemplos),
                                  'aprobadas_por_origen': dict(Counter(e['origen'] for e in ejemplos))},
            'catalogo': {'huella': huella({k: sorted(v) for k, v in catalogo.items()}),
                         'nombres': sum(len(v) for v in catalogo.values())},
            'duplicados_omitidos': len(ejemplos) - len(unicos)}
    validar_corpus_redaccion(filas, meta)
    with tempfile.TemporaryDirectory() as tmp:
        # 001:RF-5: la escritura atómica única, también en el temporal que lee el sellado.
        write_json_atomic(Path(tmp) / 'corpus.json', filas)
        write_json_atomic(Path(tmp) / 'dataset_manifest.json', meta)
        return sellar_particiones(Path(tmp), destino, validar=validar_corpus_redaccion, sistema=SISTEMA_REDACCION)


def _sellado(dataset: Path) -> tuple[dict, list[dict]]:
    """El manifiesto y el corpus de auditoría, validados, con el prompt sellado de la redacción."""
    from ..evaluacion_modelos import huella
    meta = json.loads((dataset / 'dataset_manifest.json').read_text(encoding='utf-8'))
    if meta.get('tipo_corpus') != TIPO_CORPUS:
        raise ValueError('no es un corpus de redacción sellado')
    filas = json.loads((dataset / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    validar_corpus_redaccion(filas, meta)
    if meta.get('sistema') != SISTEMA_REDACCION or meta.get('prompt_hash') != huella(SISTEMA_REDACCION):
        raise ValueError('prompt distinto del protocolo sellado')
    return meta, filas


def _particion(dataset: Path, meta: dict, filas: list[dict], parte: str) -> list[dict]:
    from ..evaluacion_modelos import huella
    from .llm_destilacion import verificar_fuente
    archivo = (meta.get('archivos_particion') or {}).get(parte)
    if not archivo:
        raise ValueError('partición ausente: ' + parte)
    verificar_fuente({k: archivo[k] for k in ('ruta', 'sha256', 'bytes', 'localizador')})
    if Path(archivo['ruta']).resolve() != (dataset / (parte + '.jsonl')).resolve():
        raise ValueError('archivo de otra partición')
    registros = [json.loads(x) for x in Path(archivo['ruta']).read_text(encoding='utf-8').splitlines() if x.strip()]
    if (len(registros) != archivo['registros'] or huella(registros) != (meta.get('huellas_particion') or {}).get(parte)
            or registros != [r for r in filas if r['particion'] == parte]):
        raise ValueError('partición distinta de la sellada: ' + parte)
    return registros


def leer_particion_redaccion(dataset: Path | str, parte: str) -> tuple[list[dict], dict]:
    """Los ejemplos de una partición sellada, comprobados, y su manifiesto: lo que consume el ajuste (072:RF-51)."""
    from .llm_destilacion import PARTICIONES
    if parte not in PARTICIONES:
        raise ValueError('partición inválida: ' + parte)
    dataset = Path(dataset)
    meta, filas = _sellado(dataset)
    registros = _particion(dataset, meta, filas, parte)
    if not registros:
        raise ValueError('partición vacía: ' + parte)
    return registros, meta


def auditar_corpus_redaccion(dataset: Path | str) -> dict:
    """El preflight del corpus de redacción sellado: particiones, huellas, fuente, anonimato y origen (072:RF-50)."""
    from .llm_destilacion import PARTICIONES
    dataset = Path(dataset)
    meta, filas = _sellado(dataset)
    for parte in PARTICIONES:
        _particion(dataset, meta, filas, parte)
    return {'ok': True, 'tipo_corpus': TIPO_CORPUS, 'dataset_hash': meta['dataset_hash'],
            'por_particion': meta['por_particion'], 'por_uso': meta['por_uso'], 'ejemplos': len(filas),
            'por_origen': meta['por_origen'], 'verdad_electrica': False, 'resultados_electricos': 0,
            'escrituras_nativas': 0}
