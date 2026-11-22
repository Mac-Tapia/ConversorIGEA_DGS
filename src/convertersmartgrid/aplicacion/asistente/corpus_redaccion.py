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

import functools
import hashlib
import json
import re
import unicodedata
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

#: 072:RF-63: un código con guion o subrayado («TA-201», «CMC_1», «TD_SM») se oculta entero. Con ``_CODIGO`` solo, «TA-201»
#: quedaba «TA-‹n›»: el prefijo es la sigla de la sede (la ratificación del 2026-11-22 rechazó 88 decisiones por eso).
_LETRA = r'A-Za-zÁÉÍÓÚÑÜáéíóúñü'
_CODIGO_COMPUESTO = re.compile(rf'(?<![\w‹\-])(?=[\w\-]*[{_LETRA}])(?=[\w\-]*[\d_])[{_LETRA}0-9]+'
                               rf'(?:[\-_][{_LETRA}0-9]+)+(?![\w\-])')
#: Lo que quedó de un código oculto a medias: su prefijo pegado a un marcador («YUS_‹n›», «TA-‹código›»).
_PREFIJO_A_LA_VISTA = re.compile(rf'(?<![\w‹])[{_LETRA}]{{1,8}}[\-_]‹(?:n|código)›')


class CorpusRedaccionError(ValueError):
    """Una revisión que no cumple lo que autoriza 072:RF-19."""


#: Etiqueta de cada clase del catálogo de nombres (072:RF-49); una lista sin clases usa ``‹nombre›``.
_ETIQUETAS = {'empresa': '‹empresa›', 'sede': '‹sede›', 'instalacion': '‹instalación›', 'instalación': '‹instalación›'}
#: 072:RF-64: cada vocal y la «n» admiten sus tildes, el carácter de reemplazo y la doble letra de un UTF-8 leído como
#: Latin-1 («Ã±»); la «n», también «Ð» («MARAÐON» en un informe real mal codificado).
_VARIANTES = {'a': 'aáàäâ', 'e': 'eéèëê', 'i': 'iíìïî', 'o': 'oóòöô', 'u': 'uúùüû', 'n': 'nñð'}
_SIN_TILDE = str.maketrans('áàäéèëíìïóòöúùüñ', 'aaaeeeiiiooouuun')
_PALABRA = r"[A-ZÁÉÍÓÚÑÜ][\w'’\-]*"
_NOMBRE = rf'{_PALABRA}(?:\s+(?:(?:de|del|la|las|los|el)\s+){{0,2}}{_PALABRA})*'
#: Patrones genéricos, sin nombres reales: lo que sigue a «SET», a una subestación, central o sede, y la razón social.
_INSTALACION = re.compile(r'(?<!\w)((?:SET|S\.E\.T\.|S\.E\.|Subestaci[oó]n|SUBESTACI[OÓ]N|C\.T\.|C\.H\.|'
                          r'(?:Central|CENTRAL)\s+(?:T[eé]rmica|T[EÉ]RMICA|Hidroel[eé]ctrica|HIDROEL[EÉ]CTRICA|'
                          r'Solar|SOLAR|E[oó]lica|E[OÓ]LICA))\s+(?:de\s+)?)' + f'({_NOMBRE})')
_SEDE = re.compile(r'(?<!\w)((?i:sede(?:\s+regional)?|unidad\s+de\s+negocios?|zonal)\s+(?i:de\s+)?)' + f'({_NOMBRE})')
_EMPRESA = re.compile(rf'(?<!\w){_NOMBRE},?\s+(?:S\.A\.A\.|S\.A\.C\.|S\.A\.|S\.R\.L\.|E\.I\.R\.L\.|SAA|SAC)(?!\w)')
#: 072:RF-64: el nombre que sigue a un río, una provincia, un distrito, un departamento, una región, una localidad, un
#: centro poblado o un caserío; ninguno va en el catálogo de la empresa y todos señalan su red.
_LUGAR = re.compile(r'(?<!\w)((?i:r[ií]o|provincia|distrito|departamento|regi[oó]n|localidad|centro\s+poblado|'
                    r'caser[ií]o|ciudad|cuenca|valle)\s+(?i:de\s+|del\s+)?)' + f'({_NOMBRE})')


def _patron_nombre(nombre: str) -> str:
    """El nombre sin distinguir mayúsculas ni tildes, con cualquier espacio entre palabras (072:RF-64).

    Admite además la codificación rota de sus vocales y su «n» (ver ``_VARIANTES``) y, si su última palabra tiene cinco
    letras o más, cualquier final de hasta tres letras en lugar de la última: el plural y la errata del final.
    """
    nombre = nombre.strip()
    final = len(nombre)
    ultima = nombre.split()[-1] if nombre.split() else ''
    if len(ultima) >= 5 and ultima[-1].isalpha():
        final -= 1
    partes: list[str] = []
    for c in nombre[:final]:
        base = c.lower().translate(_SIN_TILDE)
        if c.isspace():
            if partes[-1:] != [r'\s+']:
                partes.append(r'\s+')
        elif base in _VARIANTES:
            partes.append('(?:[' + _VARIANTES[base] + '\ufffd]|Ã.)')
        else:
            partes.append(re.escape(c))
    cola = r'\w{0,3}' if final < len(nombre) else ''
    return r'(?<!\w)' + ''.join(partes) + cola + r'(?!\w)'


def _normal(texto: str) -> str:
    """Minúsculas y sin tildes: la criba rápida antes de aplicar el patrón de cada nombre."""
    # «ð» es la «ñ» de un informe mal codificado: la criba la lee como «n», igual que el patrón (_VARIANTES).
    return unicodedata.normalize('NFKD', texto.casefold().replace('ð', 'n')).encode('ascii', 'ignore').decode('ascii')


@functools.lru_cache(maxsize=32)
def _patrones(pares: tuple[tuple[str, str], ...]) -> tuple[tuple[str, re.Pattern, str], ...]:
    """(criba, patrón compilado, etiqueta) de cada nombre: un catálogo de cientos de nombres sobre miles de textos."""
    return tuple((_normal(n)[:2], re.compile(_patron_nombre(n), re.IGNORECASE), e) for n, e in pares)


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
    normal = _normal(texto)
    for criba, patron, etiqueta in _patrones(tuple(_nombres(catalogo))):
        # La criba solo descarta lo que no puede casar; con la codificación rota se aplica el patrón igual.
        if criba in normal or 'Ã' in texto or '\ufffd' in texto or not criba.isalpha():
            texto = patron.sub(etiqueta, texto)
    texto = _INSTALACION.sub(lambda m: m.group(1) + '‹instalación›', texto)
    texto = _SEDE.sub(lambda m: m.group(1) + '‹sede›', texto)
    texto = _LUGAR.sub(lambda m: m.group(1) + '‹nombre›', texto)
    return _EMPRESA.sub('‹empresa›', texto)


def sin_cifras(texto: str, catalogo=None) -> str:
    """El texto con los nombres, los códigos de elementos y las cifras ocultos: la forma queda, los valores no.

    Los códigos con guion o subrayado se ocultan enteros, y un prefijo que quedara pegado a un marcador también (RF-63).
    """
    texto = _CODIGO.sub('‹código›', _CODIGO_COMPUESTO.sub('‹código›', sin_nombres(texto, catalogo)))
    return _PREFIJO_A_LA_VISTA.sub('‹código›', _NUMERO.sub('‹n›', texto))


_ENLACES = ('de', 'del', 'la', 'las', 'los', 'el', 'y')


def catalogo_del_corpus(fragmentos: Iterable[Mapping[str, Any]], catalogo=None) -> dict[str, list[str]]:
    """El catálogo dado, la empresa que declara cada fragmento y los nombres que el propio corpus señala (072:RF-49,
    RF-64).

    Un nombre que en un fragmento sigue a «SET», a una sede o a un río, provincia o localidad se oculta también donde
    sale solo («la línea a ‹instalación›» y luego «…llega a Puerto Imaginario»): se recoge de todos los fragmentos y entra
    en el catálogo con su clase. Nada de esto va en el repositorio: sale de los datos del espacio en cada sellado.
    """
    fragmentos = list(fragmentos)
    clases = {v: k for k, v in _ETIQUETAS.items() if k != 'instalación'}
    out: dict[str, list[str]] = {}
    for nombre, etiqueta in _nombres(catalogo):
        out.setdefault(clases.get(etiqueta, 'nombre'), []).append(nombre)
    for f in fragmentos:
        empresa = str(f.get('empresa') or '').strip()
        for variante in (empresa, empresa.replace('_', ' ')):
            if variante and variante not in out.setdefault('empresa', []):
                out['empresa'].append(variante)
    vistos = {n for v in out.values() for n in v}
    textos = [str(f.get('text') or '') for f in fragmentos]
    comunes = {w for t in textos for w in re.findall(r'(?<![\w‹])[a-záéíóúñü]{3,}', t)}
    for texto in textos:
        for patron, clase in ((_INSTALACION, 'instalacion'), (_SEDE, 'sede'), (_LUGAR, 'nombre')):
            for m in patron.finditer(texto):
                # Una línea y sin las palabras comunes del final («Puerto Imaginario Asimismo»): una palabra que el
                # corpus también escribe en minúscula no es parte del nombre («zonal de Distribución» no es uno).
                palabras = m.group(2).splitlines()[0].split()
                while palabras and (palabras[-1].lower() in comunes or palabras[-1].lower() in _ENLACES):
                    palabras.pop()
                nombre = ' '.join(palabras).strip(" '’-")
                if len(nombre) >= 4 and palabras and palabras[0].lower() not in comunes and nombre not in vistos:
                    vistos.add(nombre)
                    out.setdefault(clase, []).append(nombre)
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
#: El primer prompt de sistema del ajuste de redacción (sellado el 2026-11-20). Describía los marcadores pero no exigía
#: escribirlos: el candidato del 2026-11-21 puso cifras y repitió una frase en la prueba (072:RF-58).
SISTEMA_REDACCION_V1 = ('Redactas y das formato a secciones de informes PIDE en español formal y claro. Las cifras, los '
                        'códigos y los nombres de otra red van ocultos (‹n›, ‹código›, ‹empresa›, ‹sede›, '
                        '‹instalación›): aprendes la forma, nunca la verdad eléctrica.')
#: 072:RF-58: el prompt vigente exige los marcadores en lugar de cada cifra, código o nombre y prohíbe repetir frases; su
#: huella queda sellada como la del alumno de órdenes.
SISTEMA_REDACCION = ('Redactas y das formato a secciones de informes PIDE en español formal y claro. Nunca escribes '
                     'dígitos, códigos de elementos ni nombres de empresa, sede, instalación o lugar: en su lugar '
                     'escribes ‹n› por cada cifra, ‹código› por cada código, y ‹empresa›, ‹sede›, ‹instalación› o '
                     '‹nombre› por cada nombre. No repites frases. Aprendes la forma, nunca la verdad eléctrica.')
#: Los prompts con los que se puede leer un corpus sellado: el vigente sella; el anterior se sigue leyendo para examinar
#: lo que ya se entrenó con él.
SISTEMAS_REDACCION = (SISTEMA_REDACCION, SISTEMA_REDACCION_V1)
#: 072:RF-59: la decodificación del modelo de redacción, la misma al examinarlo y al publicarlo en Ollama: muestreo con
#: penalización de repeticiones (el candidato del 2026-11-21 repitió «…por antigüedad del conductor…» hasta el tope).
DECODIFICACION = {'temperature': 0.7, 'top_p': 0.9, 'repeat_penalty': 1.15, 'repeat_last_n': 256}
#: En transformers no hay ``repeat_last_n``: se prohíbe repetir cualquier secuencia de ocho tokens.
NO_REPETIR_NGRAMA = 8
INSTRUCCIONES = {'redaccion': 'Redacta un párrafo de un informe PIDE, claro y formal.',
                 'formato': 'Escribe el título, la leyenda o la línea de un informe PIDE con su formato.'}
#: Reparto por documento, ordenado por su huella: siete de cada diez van a entrenamiento.
_REPARTO = ('entrenamiento',) * 7 + ('seleccion', 'calibracion', 'prueba')
_APARTADAS = ('seleccion', 'calibracion', 'prueba')


def repartir_documentos(tamanos: Mapping[str, int], fijos: Mapping[str, str] | None = None) -> dict[str, str]:
    """La partición de cada documento por su número de ejemplos, no por su huella (072:RF-52).

    Con el reparto por huella, en el corpus real de la empresa de referencia (diez documentos, 704 ejemplos) el documento
    de 444 cayó entero en «selección» y el entrenamiento se quedó con 259. Cada documento sigue entero en una partición:
    del más grande al más pequeño (empate por su huella), uno va a una apartada si cabe en su décima parte del total, o si
    esa apartada está vacía y cabe en el doble; a la que más le falte. Lo que no cabe va a entrenamiento. Con menos de
    cuatro documentos no hay con qué apartar y todo entrena.

    ``fijos`` (072:RF-62) son las particiones de un sellado anterior: cada documento que ya tenía la suya la conserva, y
    cuenta en su apartada; solo los documentos nuevos se reparten. Así un sellado que crece no pasa a entrenamiento lo que
    antes examinaba, ni a examen lo que antes entrenaba.
    """
    fijos = {g: p for g, p in (fijos or {}).items() if g in tamanos}
    if len(tamanos) < 4 and not fijos:
        return {g: 'entrenamiento' for g in tamanos}
    objetivo = sum(tamanos.values()) / len(_REPARTO)
    actual = dict.fromkeys(_APARTADAS, 0)
    parte: dict[str, str] = dict(fijos)
    for g, p in fijos.items():
        if p in actual:
            actual[p] += tamanos[g]
    for g in sorted((g for g in tamanos if g not in fijos), key=lambda g: (-tamanos[g], g)):
        n = tamanos[g]
        caben = [p for p in _APARTADAS
                 if actual[p] + n <= objetivo or (actual[p] == 0 and n <= 2 * objetivo)]
        if caben:
            elegida = max(caben, key=lambda p: (objetivo - actual[p], -_APARTADAS.index(p)))
            actual[elegida] += n
            parte[g] = elegida
        else:
            parte[g] = 'entrenamiento'
    return parte


def tramos_de_documentos(documentos: list[str]) -> list[str]:
    """El grupo de cada ejemplo, en su orden: su documento o, si este es mayor que la décima parte del total, su tramo
    (072:RF-68).

    En el sellado del 2026-11-22 dos informes traían 1 227 de los 1 295 ejemplos: enteros, a selección y prueba solo les
    quedaban 23 y 22, pocos para decidir. Un documento así se parte en tramos seguidos de la centésima parte del total
    (redondeada hacia arriba; trece párrafos en ese sellado), en el orden de sus fragmentos, y cada tramo va entero a una
    partición: lo que se examina es un trozo seguido de una sección, no frases sueltas. Con tramos de la centésima parte
    cada apartada se llena casi hasta su décima parte sin pasarse (RF-52). Con menos de cuatro documentos no se parte
    nada (RF-52: todo entrena).
    """
    from ..evaluacion_modelos import huella
    tamanos = Counter(documentos)
    total = len(documentos)
    if len(tamanos) < 4:
        return [huella(['redaccion_pide', d]) for d in documentos]
    tramo = max(1, -(-total // (10 * len(_REPARTO))))
    vistos: Counter = Counter()
    grupos = []
    for d in documentos:
        if tamanos[d] * len(_REPARTO) > total:
            grupos.append(huella(['redaccion_pide', d, 'tramo', vistos[d] // tramo]))
        else:
            grupos.append(huella(['redaccion_pide', d]))
        vistos[d] += 1
    return grupos


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
    if meta.get('sin_repetidas') and any(frase_repetida(r['respuesta']) for r in filas):
        raise ValueError('ejemplo con una frase repetida en un corpus sellado sin repetidas')
    if meta.get('sin_encabezado') and any(sin_encabezado(r['respuesta']) != r['respuesta'] for r in filas):
        raise ValueError('ejemplo con el encabezado de la página en un corpus sellado sin encabezados')
    if not any(r['particion'] == 'entrenamiento' for r in filas):
        raise ValueError('el corpus de redacción no trae ejemplos de entrenamiento')
    if meta.get('por_origen') != dict(Counter(r['revision']['origen'] for r in filas)):
        raise ValueError('el recuento por origen del manifiesto no es el de sus ejemplos')
    for f in fuentes.values():
        verificar_fuente(f)


def sellar_corpus_redaccion(dataset: Path | str, destino: Path | str, *, registro: Path | str | None = None,
                            catalogo=None, anterior: Path | str | None = None) -> dict:
    """Sella lo aprobado, anónimo y con su origen, con el formato de ``sellar_particiones`` (072:RF-50).

    Solo entra lo que exporta :func:`ejemplos_para_entrenar` (origen ``humano`` o ``maestro``, aprobado, texto sin
    cambios); cada ejemplo lleva su origen y el manifiesto, el recuento ``por_origen``. Entra con
    las cifras y los nombres ocultos. Los textos que quedan iguales tras ocultarlos entran una vez. Cada documento va
    entero a una partición; la respuesta es el texto, y la orden, la instrucción fija de su uso. Con ``anterior``, el
    corpus sellado al que este sustituye (072:RF-62): sus documentos conservan su partición y el manifiesto lo declara,
    con sus huellas y lo que crece, antes de entrenar con el nuevo.
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
    repetidas = vacias = 0
    for e in ejemplos:
        texto = sin_encabezado(_anonimo(e['texto'], catalogo))
        if not texto:
            vacias += 1     # 072:RF-65: solo traía el encabezado de la página
            continue
        if frase_repetida(texto):
            # 072:RF-61: al ocultar los códigos, filas distintas de una tabla quedan iguales y seguidas; enseñan al
            # modelo a encadenar la misma frase, como hizo el candidato del 2026-11-21. No entran.
            repetidas += 1
            continue
        if texto_canonico(texto) not in vistos:
            vistos.add(texto_canonico(texto))
            unicos.append((e, texto))
    # 072:RF-68: los documentos muy grandes se reparten por tramos; con un sellado anterior, enteros (RF-62).
    grupos = ([huella(['redaccion_pide', e['fuente']]) for e, _ in unicos] if anterior is not None
              else tramos_de_documentos([e['fuente'] for e, _ in unicos]))
    tamanos = Counter(grupos)
    declarado = None
    fijos = None
    if anterior is not None:
        meta_ant, filas_ant = _sellado_anterior(Path(anterior))
        fijos = {r['group_id']: r['particion'] for r in filas_ant}
        declarado = {'dataset_hash_anterior': meta_ant['dataset_hash'], 'prompt_hash_anterior': meta_ant['prompt_hash'],
                     'por_particion_anterior': meta_ant['por_particion'],
                     'documentos_conservados': sum(g in tamanos for g in fijos),
                     'documentos_nuevos': sum(g not in fijos for g in tamanos)}
    parte_de = repartir_documentos(tamanos, fijos)
    filas = []
    for (e, texto), grupo in zip(unicos, grupos):
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
            'duplicados_omitidos': len(ejemplos) - len(unicos) - repetidas - vacias, 'repetidas_omitidas': repetidas,
            'sin_repetidas': True, 'sin_encabezado': True, 'solo_encabezado_omitidos': vacias,
            'documentos': len({e['fuente'] for e, _ in unicos}), 'grupos': len(tamanos),
            'sustituye_a': declarado}
    validar_corpus_redaccion(filas, meta)
    with tempfile.TemporaryDirectory() as tmp:
        # 001:RF-5: la escritura atómica única, también en el temporal que lee el sellado.
        write_json_atomic(Path(tmp) / 'corpus.json', filas)
        write_json_atomic(Path(tmp) / 'dataset_manifest.json', meta)
        return sellar_particiones(Path(tmp), destino, validar=validar_corpus_redaccion, sistema=SISTEMA_REDACCION)


def _sellado_anterior(dataset: Path) -> tuple[dict, list[dict]]:
    """El sellado al que sustituye uno nuevo, comprobado por sus huellas (072:RF-62).

    No se vuelve a validar su anonimato con las reglas de hoy: se sustituye justo porque las de entonces dejaban cosas a
    la vista (el prefijo de «YUS_‹n›», 072:RF-63). Solo hacen falta sus particiones y que sean las que se sellaron.
    """
    from ..evaluacion_modelos import huella
    meta = json.loads((dataset / 'dataset_manifest.json').read_text(encoding='utf-8'))
    filas = json.loads((dataset / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    if (meta.get('tipo_corpus') != TIPO_CORPUS or huella(filas) != meta.get('dataset_hash')
            or meta.get('prompt_hash') != huella(meta.get('sistema') or '')):
        raise ValueError('el sellado anterior no es un corpus de redacción íntegro')
    return meta, filas


def _sellado(dataset: Path) -> tuple[dict, list[dict]]:
    """El manifiesto y el corpus de auditoría, validados, con el prompt sellado de la redacción."""
    from ..evaluacion_modelos import huella
    meta = json.loads((dataset / 'dataset_manifest.json').read_text(encoding='utf-8'))
    if meta.get('tipo_corpus') != TIPO_CORPUS:
        raise ValueError('no es un corpus de redacción sellado')
    filas = json.loads((dataset / 'corpus_auditoria.json').read_text(encoding='utf-8'))
    validar_corpus_redaccion(filas, meta)
    if meta.get('sistema') not in SISTEMAS_REDACCION or meta.get('prompt_hash') != huella(meta['sistema']):
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


# --- 072:RF-53 a RF-57: las puertas de un modelo de redacción entrenado con este corpus ----------------------------

#: Las particiones selladas que examinan al modelo de redacción: selección y prueba (calibración queda para ajustar).
PARTES_EVALUACION = ('seleccion', 'prueba')
#: 072:RF-53: el candidato no puede tener más pérdida por token que la base NF4 en la misma partición. Sin holgura: con
#: 12 a 19 ejemplos apartados por partición, cualquier subida es la única señal de que el ajuste estropeó la forma.
TOLERANCIA_PERDIDA = 0.0


def catalogo_sellado(dataset: Path | str, catalogo=None) -> dict[str, list[str]]:
    """El catálogo de nombres con el que se selló el corpus, comprobado por su huella (072:RF-54).

    El manifiesto guarda solo la huella del catálogo, no los nombres, que son de la empresa y llegan en tiempo de
    ejecución. Se rehace como al sellar, con la empresa de cada fragmento custodiado, y tiene que dar la misma huella:
    revisar las salidas con otro catálogo dejaría pasar los nombres que el sellado sí ocultó.
    """
    from ..evaluacion_modelos import huella
    from .llm_destilacion import verificar_fuente
    meta, _filas = _sellado(Path(dataset))
    fuente = meta.get('fuente_fragmentos') or {}
    verificar_fuente(fuente)
    completo = catalogo_del_corpus(_leer(Path(fuente['ruta'])), catalogo)
    if huella({k: sorted(v) for k, v in completo.items()}) != (meta.get('catalogo') or {}).get('huella'):
        raise ValueError('catálogo de nombres distinto del que se usó al sellar el corpus')
    return completo


_MESES = r'(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|se(?:p)?tiembre|octubre|noviembre|diciembre)'
#: 072:RF-65: el encabezado y el pie de cada página de un PDF, ya anonimizados: «Informe … – Diciembre ‹n›» y
#: «Página ‹n› de ‹n›». Se repiten en todas las páginas y el modelo los aprendería como si fueran redacción.
_ENCABEZADO = re.compile(r'(?im)^[ \t]*(?:p[áa]gina[ \t]+‹n›(?:[ \t]+(?:de|/)[ \t]+‹n›)?'
                         rf'|[^\n|]{{3,200}}[ \t][–—-][ \t]*{_MESES}[ \t]+(?:de[ \t]+)?‹n›)[ \t]*$')


def sin_encabezado(texto: str) -> str:
    """El texto anonimizado sin el encabezado ni el pie de página del PDF, y sin las líneas en blanco que dejan."""
    texto = _ENCABEZADO.sub('', texto)
    return re.sub(r'\n(?:[ \t]*\n)+', '\n\n', texto).strip()


_PALABRA_O_MARCA = re.compile(r'‹[^›]*›|\w+')
#: 072:RF-60: un trozo de al menos ocho palabras (cinco que no sean marcadores) seguido de sí mismo es una frase
#: repetida: el candidato del 2026-11-21 encadenó la misma frase hasta agotar su tope de tokens. Solo cuenta la
#: repetición seguida: en las tablas del corpus aprobado una fila se parece a otra, pero no se repite entera a
#: continuación (las 704 respuestas selladas del 2026-11-20 no tienen ninguna).
LARGO_REPETICION = 8


def frase_repetida(texto: str) -> bool:
    """Si el texto repite seguido un trozo de :data:`LARGO_REPETICION` palabras o más, con contenido (072:RF-60)."""
    fichas = [t.casefold() for t in _PALABRA_O_MARCA.findall(texto)]
    for largo in range(LARGO_REPETICION, len(fichas) // 2 + 1):
        for i in range(len(fichas) - 2 * largo + 1):
            trozo = fichas[i:i + largo]
            if trozo == fichas[i + largo:i + 2 * largo] and sum(not t.startswith('‹') for t in trozo) >= 5:
                return True
    return False


def revisar_salida(entrada: str, salida: str, catalogo=None) -> list[str]:
    """Por qué una salida generada no vale (072:RF-54); vacío si vale.

    ``nombre``: deja un nombre de empresa, sede o instalación que el anonimizador oculta (:func:`sin_nombres`);
    ``código``: trae un código de elemento que no está en la entrada; ``cifra``: trae una cifra que no está en la entrada
    (``contradicciones.cifras_sin_respaldo``); ``repetida``: repite una frase (:func:`frase_repetida`, 072:RF-60);
    ``vacía``: no redacta nada.
    """
    from .contradicciones import cifras_sin_respaldo
    if not isinstance(salida, str) or not salida.strip():
        return ['vacía']
    motivos = []
    if sin_nombres(salida, catalogo) != salida:
        motivos.append('nombre')
    if (any(c not in entrada for c in _CODIGO.findall(salida) + _CODIGO_COMPUESTO.findall(salida))
            or _PREFIJO_A_LA_VISTA.search(salida)):
        # 072:RF-66: también el prefijo de una sede pegado a un marcador («TA-‹n›»).
        motivos.append('código')
    if cifras_sin_respaldo(salida, entrada):
        motivos.append('cifra')
    if frase_repetida(salida) and not frase_repetida(entrada):
        motivos.append('repetida')
    return motivos


def _perdida_valida(p) -> bool:
    import math
    return (isinstance(p, Mapping) and type(p.get('tokens')) is int and p['tokens'] > 0
            and isinstance(p.get('por_token'), (int, float)) and math.isfinite(p['por_token']))


def puerta_interprete(candidato: Mapping | None, en_uso: Mapping | None) -> dict:
    """072:RF-56: si el modelo de redacción no baja la prueba sellada del intérprete de órdenes.

    No se repite la medida: son los ``resultado.json`` de ``llm_destilar.py evaluar --parte prueba`` (la de 070 T22),
    del candidato y del modelo en uso, sobre el mismo corpus de órdenes y el mismo prompt. Sin ellos, no aplica: el
    modelo de redacción no sustituye al intérprete y no se puede activar como tal.
    """
    if candidato is None and en_uso is None:
        return {'estado': 'no_aplica', 'activable_como_interprete': False,
                'motivo': 'el modelo de redacción no sustituye al intérprete de órdenes; para usarlo como tal hacen '
                          'falta su prueba sellada de órdenes y la del modelo en uso'}
    motivos = []
    if candidato is None or en_uso is None:
        motivos.append('falta la prueba sellada del candidato o la del modelo en uso')
    else:
        if candidato.get('particion') != 'prueba' or en_uso.get('particion') != 'prueba':
            motivos.append('un informe no es de la partición de prueba')
        if (candidato.get('dataset_hash'), candidato.get('prompt_hash')) != (en_uso.get('dataset_hash'),
                                                                             en_uso.get('prompt_hash')):
            motivos.append('los dos informes no son del mismo corpus sellado y el mismo prompt')
    if not motivos:
        for clave in ('acierto_tarea', 'f1_datos'):
            c, u = ((r.get('metricas') or {}).get(clave) for r in (candidato, en_uso))
            if not isinstance(c, (int, float)) or not isinstance(u, (int, float)):
                motivos.append(f'{clave} sin medir')
            elif c < u:
                motivos.append(f'{clave} baja de {u:.4f} a {c:.4f}')
    return {'estado': 'rechazada' if motivos else 'aprobada', 'activable_como_interprete': not motivos,
            'motivo': '; '.join(motivos) or 'no baja la prueba sellada del intérprete',
            'modelo': (candidato or {}).get('modelo'), 'modelo_en_uso': (en_uso or {}).get('modelo')}


def decidir_redaccion(dataset: Path | str, perdidas: Mapping, salidas: Mapping, *, catalogo=None,
                      interprete: Mapping | None = None) -> dict:
    """Aprobado o rechazado, con su informe, para un modelo de redacción del PIDE (072:RF-53 a RF-57).

    ``perdidas``: ``{parte: {'base': {'tokens', 'por_token'}, 'candidato': {...}}}`` medidas con la misma partición;
    ``salidas``: ``{parte: [texto generado por ejemplo, en su orden]}``. Aprueba solo si en selección y en prueba la
    pérdida por token del candidato no supera la de la base y ninguna salida deja un nombre, un código o una cifra que
    no estén en su entrada. Nunca promueve ni activa nada (047:RF-8); el informe no copia las salidas sin anonimizar.
    """
    import math
    dataset = Path(dataset)
    meta, filas = _sellado(dataset)
    motivos: list[str] = []
    partes = {}
    for parte in PARTES_EVALUACION:
        registros = _particion(dataset, meta, filas, parte)
        if not registros:
            motivos.append(f'{parte}: partición vacía, nada con qué medir')
            partes[parte] = {'ejemplos': 0}
            continue
        p = (perdidas or {}).get(parte) or {}
        base, cand = p.get('base'), p.get('candidato')
        info: dict[str, Any] = {'ejemplos': len(registros)}
        if not (_perdida_valida(base) and _perdida_valida(cand)):
            motivos.append(f'{parte}: pérdida sin medir frente a la base NF4')
        else:
            if base['tokens'] != cand['tokens']:
                motivos.append(f'{parte}: la base y el candidato no se midieron con los mismos tokens')
            info['perdida'] = {'base': dict(base, perplejidad=math.exp(base['por_token'])),
                               'candidato': dict(cand, perplejidad=math.exp(cand['por_token'])),
                               'diferencia': cand['por_token'] - base['por_token']}
            if cand['por_token'] > base['por_token'] + TOLERANCIA_PERDIDA:
                motivos.append(f"{parte}: la pérdida por token sube de {base['por_token']:.4f} a "
                               f"{cand['por_token']:.4f}")
        textos = list((salidas or {}).get(parte) or [])
        if len(textos) != len(registros):
            motivos.append(f'{parte}: {len(textos)} salidas para {len(registros)} ejemplos')
        fallos = []
        for i, (r, salida) in enumerate(zip(registros, textos)):
            m = revisar_salida(r['texto'], salida, catalogo)
            if m:
                fallos.append({'indice': i, 'record_id': r['record_id'], 'motivos': m,
                               'huella_salida': huella_texto(str(salida)),
                               'muestra': _anonimo(str(salida), catalogo)[:400]})
        if fallos:
            motivos.append(f'{parte}: {len(fallos)} salidas con nombres, códigos o cifras que no están en la entrada, '
                           'o con frases repetidas')
        info.update(salidas=len(textos), salidas_con_fallo=fallos,
                    por_motivo=dict(Counter(m for f in fallos for m in f['motivos'])))
        partes[parte] = info
    interprete = dict(interprete) if interprete is not None else puerta_interprete(None, None)
    aprobado = not motivos
    return {'tipo_corpus': TIPO_CORPUS, 'dataset_hash': meta['dataset_hash'], 'prompt_hash': meta['prompt_hash'],
            'status': 'APROBADO' if aprobado else 'RECHAZADO', 'aprobado': aprobado, 'motivos': motivos,
            'particiones': partes, 'tolerancia_perdida': TOLERANCIA_PERDIDA, 'interprete': interprete,
            'uso': 'redaccion_pide', 'promovido': False, 'activado': False, 'verdad_electrica': False}
