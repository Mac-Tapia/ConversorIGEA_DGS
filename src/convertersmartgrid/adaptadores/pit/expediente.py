"""Expediente del PIT: carpeta propia, instantánea del registro, traza de cada celda y determinismo (107:RF-1, RF-7 a
RF-9, RF-14).

Por qué así:

- **Carpeta aparte del PIDE** (``expedientes_pit/<área>/<periodo>``): el PIT tiene otra norma, otro horizonte y
  otros formatos; mezclarlo con el PIDE haría pasar un costeo de módulos por cumplimiento del PIT (RF-1).
- **Instantánea del registro al abrir.** Si después llega una modificatoria, el expediente lo avisa y lista las celdas
  afectadas, pero no recalcula solo: una norma publicada a mitad del expediente no cambia cifras sin que nadie lo
  decida.
- **Traza de cada celda** (fuente con su huella, cálculo, motor y regla con su estado); una celda sin traza no se
  emite.
- **Determinismo**: JSON con claves ordenadas y ninguna hora de reloj dentro; la fecha de apertura entra como dato.
- El expediente lo presenta la empresa: el sistema no lo declara aprobado por el regulador, y se comprueba que
  ninguna frase lo diga.
- **Relación de los documentos de sustento** (num. 5.3 de la Norma Tarifas, con el 5.5 para volúmenes y foliado): cada
  documento con su n.º, su fichero, su tipo, la descripción de su contenido, su aplicación (qué sección o formato
  sustenta) y su volumen y folios, agrupada por volúmenes con el foliado consecutivo, sin reiniciar en cada volumen
  (``relacion_documentos.json``). La relación no tiene plantilla. El regulador la evalúa junto con el «F-000», que
  no es una plantilla sino su nombre del grupo «Formatos de Información General» (F-001 a F-003, RCD 217-2013 art.
  30.1): se da por cumplido cuando el expediente trae los tres, y si falta alguno es un hueco que lo nombra. Lo que
  falta (una descripción, una aplicación, los folios) es un hueco nombrado, nunca un texto inventado.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..libro_informe import rellenar_con_excel
from ...dominio.registro_normativo import ReglaAmbigua, RegistroNormativo
from ...dominio.pit import PitError
from .alternativas import Comparacion
from .cuadros import plan_de_formatos
from .diagnostico import Diagnostico
from .informe import desde_carpeta
from .plantillas import cargar_mapeo
from ...dominio.pit.programa import FilaPrograma, Programa, comparar_programas

__all__ = ['COLUMNAS_RELACION', 'DOCUMENTOS', 'F000', 'RELACION', 'RELACION_DOCUMENTOS', 'SIN_ALTERNATIVAS', 'SIN_ELEGIDA',
           'TIPO_DIAGNOSTICO', 'TIPO_ESTUDIO', 'TIPOS_DOCUMENTO', 'abrir',
           'comprobar_modificatoria', 'emitir', 'escribir_informacion_general', 'filas_del_programa', 'formato_f000']

CARPETA = 'expedientes_pit'
_PROHIBIDA = re.compile(r'aprobad[oa]s?\s+por\s+(el\s+)?osinergmin', re.I)
_TRAZA = ('fuente', 'calculo', 'motor', 'regla')


def _json(ruta: Path, datos: Any) -> None:
    texto = json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True, default=str) + '\n'
    if _PROHIBIDA.search(texto):
        raise PitError(f'{ruta.name}: el expediente no puede declararse aprobado por el regulador')
    ruta.write_text(texto, encoding='utf-8', newline='\n')


def _huellas(registro: RegistroNormativo) -> dict[str, str]:
    """Huella de cada regla tal como la ve quien la usa (estado y versión de su norma incluidos)."""
    claves = sorted({r.clave for n in registro.normas.values() for r in n.reglas})
    return {c: _huella_de(registro, c) for c in claves}


def _huella_de(registro: RegistroNormativo, clave: str) -> str:
    """Una clave que va por empresa (VAD-FE26) puede tener varias fijaciones a la vez y el expediente del PIT no es
    de una empresa: su huella junta la regla de cada empresa, tal como el registro la reparte (107:RF-7). Una clave
    que traen varias normas que se suman (RN-AMB: las modificaciones del PIT de cada área) junta la de cada norma."""
    empresas = registro.empresas_de(clave)
    if not empresas:
        try:
            return registro.regla(clave).huella()
        except ReglaAmbigua:
            partes = {v.norma.acto: v.huella() for v in registro.reglas_vigentes(clave)}
            return hashlib.sha256(json.dumps(partes, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    partes = {e: registro.regla_de_empresa(clave, e).huella() for e in empresas}
    return hashlib.sha256(json.dumps(partes, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def abrir(raiz: Path | str, area: str, periodo: str, registro: RegistroNormativo, *, fecha_apertura: str) -> Path:
    """La carpeta del expediente; al crearla fija la instantánea del registro. Si ya existe, la respeta."""
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', fecha_apertura or ''):
        raise PitError(f'fecha de apertura {fecha_apertura!r}: tiene que ser AAAA-MM-DD')
    carpeta = Path(raiz) / CARPETA / re.sub(r'[^\w.-]+', '_', area) / re.sub(r'[^\w.-]+', '_', periodo)
    ficha = carpeta / 'expediente.json'
    if ficha.is_file():
        return carpeta
    carpeta.mkdir(parents=True, exist_ok=True)
    _json(ficha, {'estudio': 'PIT', 'area': area, 'periodo': periodo, 'fecha_apertura': fecha_apertura,
                  'registro': {'instantanea': registro.instantanea(), 'reglas': _huellas(registro)}})
    return carpeta


def _ficha(carpeta: Path) -> dict[str, Any]:
    ficha = Path(carpeta) / 'expediente.json'
    if not ficha.is_file():
        raise PitError(f'{carpeta} no es un expediente del PIT abierto (falta expediente.json)')
    return json.loads(ficha.read_text(encoding='utf-8'))


def comprobar_modificatoria(carpeta: Path | str, registro: RegistroNormativo) -> dict[str, Any]:
    """Si el registro cambió desde la apertura: aviso, reglas cambiadas y celdas afectadas. No recalcula nada."""
    carpeta = Path(carpeta)
    ficha = _ficha(carpeta)
    fijada = ficha['registro']
    if registro.instantanea() == fijada['instantanea']:
        return {'cambiado': False, 'reglas': [], 'celdas_afectadas': [], 'aviso': ''}
    ahora = _huellas(registro)
    cambiadas = sorted(c for c in set(fijada['reglas']) | set(ahora) if fijada['reglas'].get(c) != ahora.get(c))
    cuadros = carpeta / 'cuadros.json'
    celdas = json.loads(cuadros.read_text(encoding='utf-8')) if cuadros.is_file() else []
    afectadas = sorted(c['id'] for c in celdas if c['traza']['regla'].get('clave') in cambiadas
                       or set(c['traza'].get('reglas') or ()) & set(cambiadas))
    aviso = (f'el registro normativo cambió desde la apertura del {ficha["fecha_apertura"]}: '
             f'{len(cambiadas)} reglas y {len(afectadas)} celdas afectadas; no se ha recalculado nada')
    return {'cambiado': True, 'reglas': cambiadas, 'celdas_afectadas': afectadas, 'aviso': aviso}


def filas_del_programa(programa: Programa, comparacion: Comparacion, alternativa: str
                       ) -> dict[str, list[dict[str, Any]]]:
    """Las filas de los cuadros (``altas`` y ``bajas``) desde el programa y la alternativa elegida, con su traza."""
    elegida = next((a for a in comparacion.alternativas if a.nombre == alternativa), None)
    if elegida is None:
        raise PitError(f'la alternativa {alternativa!r} no está en la comparación')
    if not elegida.completa:
        raise PitError(f'la alternativa {alternativa!r} está incompleta: {elegida.motivos}')
    oficial = elegida.inversion_detalle.get('oficial') or {}
    fuentes = oficial.get('fuentes') or {}
    costo: dict[str, dict[str, Any]] = {}
    for v in oficial.get('valorados') or ():
        f = fuentes.get(v['ambito']) or {}
        costo[v['elemento']] = {'inversion': v['costo'], 'moneda': v['moneda'],
                                'fuente': {'nombre': f.get('nombre'), 'resolucion': v['fuente'],
                                           'huella': f.get('huella')},
                                'calculo': {'funcion': 'costos_fuentes.valorar_obra', 'codigo': v['codigo'],
                                            'cantidad': v['cantidad'], 'costo_unitario': v['costo_unitario']}}
    for x in elegida.inversion_detalle.get('empresa') or ():
        costo[x['elemento']] = {'inversion': x['costo'], 'moneda': x['moneda'],
                                'fuente': {'nombre': x['fuente'], 'descripcion': x['descripcion'],
                                           'huella': x.get('huella', '')},
                                'calculo': {'funcion': 'set_nueva.leer_modulos_pit'}}
    filas: dict[str, list[dict[str, Any]]] = {'altas': [], 'bajas': []}
    for f in programa.filas:
        traza = {'fuente': {'nombre': f'alternativa {alternativa}', 'huella': comparacion.demanda_huella},
                 'calculo': {'funcion': 'pit.programa.programar', 'accion': f.accion},
                 'motor': comparacion.motor}
        campos = {'anio': f.anio, 'titular': f.titular, 'descripcion': f.descripcion or f.elemento,
                  'instalacion': f.instalacion, 'elemento': f.elemento}
        if f.accion == 'alta' and f.elemento in costo:
            c = costo[f.elemento]
            campos.update(inversion=c['inversion'], moneda=c['moneda'])
            traza.update(fuente=c['fuente'], calculo=c['calculo'])
        filas['altas' if f.accion == 'alta' else 'bajas'].append({'campos': campos, 'traza': traza})
    return filas


def _reglas_aplicadas(diagnostico: Diagnostico | None, comparacion: Comparacion | None,
                      celdas: Sequence[Mapping[str, Any]], registro: RegistroNormativo) -> list[dict[str, Any]]:
    """RF-7: cada regla aplicada con su norma, artículo, estado, vigencia y si se usó como obligatoria."""
    claves = set()
    if diagnostico is not None:
        claves |= {v['regla'] for v in diagnostico.limites.values() if v.get('origen', '').startswith('registro')}
        claves |= set(diagnostico.tension.get('reglas') or ())  # la tensión por barra (107 T7, PIT-TEN)
        claves |= set(getattr(diagnostico, 'reglas', ()) or ())  # años, factor de potencia y N-1 (107:RF-20)
    if comparacion is not None:
        claves |= set(comparacion.reglas)
    claves |= {c['traza']['regla']['clave'] for c in celdas}
    out = []
    for clave in sorted(claves):
        r = registro.regla(clave)
        out.append({'clave': clave, 'valor': r.regla.valor, 'norma': r.norma.acto,
                    'articulo_o_anexo': r.regla.articulo_o_anexo, 'pagina': r.regla.pagina,
                    'estado': r.estado, 'vigencia_desde': r.norma.vigencia_desde,
                    'vigencia_hasta': r.norma.vigencia_hasta, 'obligatoria': r.obligatoria,
                    'uso': 'obligatoria' if r.obligatoria else 'referencia (no obligatoria: 107:RF-8)',
                    'pendientes': [dict(p) for p in r.regla.pendientes],
                    'verificacion': dict(r.regla.verificacion) if r.regla.verificacion else None})
    return out


#: Lo que el expediente escribe, con su descripción y su uso, para la relación de sustento (107:RF-14).
DOCUMENTOS = {
    'expediente.json': ('Ficha del expediente: área, periodo, fecha de apertura e instantánea del registro normativo',
                        'fija la norma con la que se abrió el estudio (107:RF-8)'),
    'cuadros.json': ('Celdas de los cuadros del periodo y del área, cada una con su traza',
                     'cuadros del expediente (107:RF-9)'),
    'formatos.json': ('Formatos que lista la norma vigente del registro, cada uno transcrito o nombrado como no '
                      'transcrito', 'qué formatos oficiales lleva el expediente (aclaración de 107:RF-9)'),
    'reglas_aplicadas.json': ('Cada regla aplicada con su norma, artículo, estado jurídico y vigencia',
                              'sustento normativo de cada cifra (107:RF-7)'),
    'resumen.json': ('Resumen técnico del expediente: reglas usadas como referencia, cuadros no transcritos y '
                     'modificatorias posteriores', 'control de lo que no es obligatorio o no está transcrito (107:RF-8)'),
    'diagnostico.json': ('Diagnóstico por año: caso base y N-1 de cada línea y transformador contra sus límites',
                         'sección de diagnóstico (107:RF-3, RF-4)'),
    'alternativas.json': ('Comparación de las alternativas por inversión, COyM, pérdidas, confiabilidad y valor '
                          'presente', 'sección de alternativas (107:RF-5)'),
    'programa.json': ('Programa de inversiones por año, titular y área, con bajas y reemplazos',
                      'sección del programa (107:RF-6)'),
    'memoria.json': ('Memoria de cada sección: criterios, metodología, entradas y resultados',
                     'explica cómo se obtuvo cada sección (107:RF-14)'),
    'resumen_ejecutivo.json': ('Resumen ejecutivo: demanda, alternativa elegida y programa, con sus fuentes',
                               'primera lectura del estudio (107:RF-13)'),
    'modificacion.json': ('Modificación del plan vigente: lo que se elimina, cambia o agrega, con su razón',
                          'sustento de la modificación (107:RF-17)'),
    'observaciones.json': ('Observaciones del regulador con su respuesta y su objeto',
                           'registro de observaciones (107:RF-10)'),
    'absolucion.json': ('Absolución de las observaciones con la traza de lo que cambió',
                        'respuesta al regulador (107:RF-10)'),
    'relacion_documentos.json': ('Relación de los documentos de sustento por volumen, con su descripción, su '
                                 'aplicación y sus folios, y si están los formatos del grupo F-000 (F-001 a F-003)',
                                 'relación de sustento que acompaña al estudio (107:RF-14)'),
}
RELACION = 'relacion_sustento.json'
RELACION_DOCUMENTOS = 'relacion_documentos.json'
#: Cómo se rotula el expediente en su resumen: con alternativas es el estudio; sin ellas, solo un diagnóstico.
TIPO_ESTUDIO = 'estudio del PIT de la empresa'
TIPO_DIAGNOSTICO = 'DE DIAGNÓSTICO, no presentable a Osinergmin'
SIN_ALTERNATIVAS = 'sin alternativas: no hay comparación ni programa'
SIN_ELEGIDA = 'sin una alternativa elegida completa: no hay programa ni resumen ejecutivo'
#: Código del formato de información general que el regulador pide junto con la relación de sustento.
F000 = 'F-000'
TIPOS_DOCUMENTO = ('electrónico', 'físico')
#: Lo que el expediente escribe con un nombre que cambia por área y periodo: prefijo → descripción y uso (107:RF-14).
#: El prefijo sale del nombre de fichero declarado en el alias del F-000 del mapeo (``_documentos_por_prefijo``).
_POR_PREFIJO = {F000: ('Libro de Información General (el «F-000» del regulador): los formatos F-001, F-002 y F-003 en '
                       'la plantilla oficial', 'formatos de Información General, RCD 217-2013 art. 30.1 y 31 '
                       '(107:RF-9; aclaración de RF-14)')}
#: Columnas de la relación legible, en su orden (107:RF-14).
COLUMNAS_RELACION = ('n.º', 'fichero', 'tipo', 'descripción', 'aplicación', 'volumen', 'folios')


def _memoria(diagnostico: Diagnostico | None, comparacion: Comparacion | None, programa: Programa | None,
             celdas: Sequence[Mapping[str, Any]], no_transcritos: list[str]) -> dict[str, dict[str, Any]]:
    """Criterios, metodología, entradas y resultados de cada sección que se emite, con lo que la produjo (RF-14)."""
    memoria: dict[str, dict[str, Any]] = {}
    if diagnostico is not None:
        memoria['diagnostico'] = {
            'criterios': {k: {c: v.get(c) for c in ('valor', 'origen', 'regla', 'norma', 'estado')}
                          for k, v in sorted(diagnostico.limites.items())},
            'metodologia': (f'flujo de potencia y contingencia N-1 de cada línea y transformador con el motor '
                            f'{diagnostico.motor}, año por año, con la demanda proyectada en las barras de carga de '
                            'cada SET; un año sin demanda se nombra y no se extrapola'),
            'entradas': {'area': diagnostico.area, 'anios': sorted([a.anio for a in diagnostico.anios] + diagnostico.sin_demanda),
                         'faltantes': sorted(str(f.get('id')) for f in diagnostico.faltantes),
                         'incompletos': sorted(diagnostico.incompletos)},
            'resultados': {'anios_diagnosticados': len(diagnostico.anios), 'sin_demanda': list(diagnostico.sin_demanda),
                           'violaciones_caso_base': sum(len(a.base.violaciones) for a in diagnostico.anios),
                           'huecos_tension': [dict(h) for h in diagnostico.huecos_tension],
                           'referencias_tension': [dict(r) for r in diagnostico.referencias],
                           'completo': diagnostico.completo, 'cancelado': diagnostico.cancelado}}
        # El criterio de tensión de cada barra y su norma (107 T7, PIT-TEN).
        memoria['diagnostico']['criterios']['tension_por_barra'] = {
            b: {c: e.get(c) for c in ('nivel', 'entrega', 'tipo_red', 'criterio', 'normal_pu', 'emergencia_pu',
                                      'regla', 'origen', 'obligatoria', 'fuente')}
            for b, e in sorted((diagnostico.tension.get('barras') or {}).items())}
    if comparacion is not None:
        memoria['alternativas'] = {
            'criterios': {k: {c: v.get(c) for c in ('valor', 'norma', 'estado', 'obligatoria')}
                          for k, v in sorted(comparacion.reglas.items())},
            'metodologia': ('valor presente de la inversión, el COyM y las pérdidas valoradas, con la misma demanda y '
                            f'el mismo motor ({comparacion.motor}) para todas; la que tiene un dato que falta queda '
                            'fuera de la comparación'),
            'entradas': {'demanda_huella': comparacion.demanda_huella, 'motor': comparacion.motor,
                         'alternativas': [a.nombre for a in comparacion.alternativas]},
            'resultados': {'orden': list(comparacion.orden),
                           'fuera_de_comparacion': list(comparacion.fuera_de_comparacion)}}
    if programa is not None:
        memoria['programa'] = {
            'criterios': 'cada elemento con su año de puesta en servicio, su titular y su área; un reemplazo es una '
                         'baja y un alta del mismo año',
            'metodologia': 'programa de la alternativa elegida, ordenado por año, acción, titular y elemento',
            'entradas': {'area': programa.area},
            'resultados': {'filas': len(programa.filas),
                           'por_titular': {t: len(f) for t, f in programa.por_titular().items()}}}
    cuadros = sorted({str(c['cuadro']) for c in celdas})
    memoria['cuadros'] = {
        'criterios': {c['traza']['regla']['clave']: {k: c['traza']['regla'].get(k) for k in ('norma', 'estado')}
                      for c in sorted(celdas, key=lambda c: c['id'])},
        'metodologia': 'columnas de cada cuadro desde su definición transcrita en el registro normativo; cada celda con '
                       'su fuente, su cálculo, su motor y su regla',
        'entradas': {'celdas': len(celdas)},
        'resultados': {'cuadros': cuadros, 'no_transcritos': no_transcritos}}
    return memoria


@lru_cache(maxsize=1)
def _documentos_por_prefijo() -> tuple[tuple[str, tuple[str, str]], ...]:
    """(prefijo del fichero, (descripción, uso)) de los documentos con nombre variable; el prefijo, del mapeo."""
    salida = []
    for codigo, texto in _POR_PREFIJO.items():
        plantilla = str((((cargar_mapeo().get('alias') or {}).get(codigo) or {}).get('nombre_de_fichero') or {})
                        .get('plantilla') or '')
        prefijo = plantilla.split('{', 1)[0]
        if prefijo:
            salida.append((prefijo, texto))
    return tuple(salida)


def _descrito(nombre: str) -> tuple[str, str] | None:
    """Descripción y uso de un documento que escribe el expediente, por su nombre o por su prefijo."""
    if nombre in DOCUMENTOS:
        return DOCUMENTOS[nombre]
    return next((t for prefijo, t in _documentos_por_prefijo() if nombre.startswith(prefijo) and '/' not in nombre),
                None)


def _declarados(carpeta: Path, sustento: Mapping[str, Mapping[str, Any]], incluir: Iterable[str] = ()) -> list[str]:
    """Los documentos que tendrá la relación: los de la carpeta y la propia relación por volúmenes (sin la de
    sustento, que los lista a todos). Uno que nadie describe (ni el expediente ni «sustento») es un error (RF-14)."""
    nombres = {r.relative_to(carpeta).as_posix() for r in carpeta.rglob('*') if r.is_file()} - {RELACION}
    sin = sorted(n for n in nombres if _descrito(n) is None and n not in sustento)
    if sin:
        raise PitError(f'documentos del expediente sin descripción o sin uso en la relación de sustento: {sin} '
                       '(se declaran en «sustento»)')
    return sorted(nombres | {RELACION_DOCUMENTOS, *incluir})


def _organizacion(volumenes: Mapping[str, Any] | None, conocidos: set[str]
                  ) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]]]:
    """Los volúmenes en su orden y, por documento, su volumen y sus folios. Se comprueba antes de escribir nada."""
    if volumenes is None:
        return [], {}
    lista = volumenes.get('volumenes') if isinstance(volumenes, Mapping) else None
    if not isinstance(lista, list) or not lista:
        raise PitError('«volumenes» necesita su lista «volumenes» (cada uno con «volumen» y «titulo»), en su orden')
    orden: list[dict[str, str]] = []
    for v in lista:
        v = v if isinstance(v, Mapping) else {}
        nombre, titulo = str(v.get('volumen') or '').strip(), str(v.get('titulo') or '').strip()
        if not nombre or not titulo:
            raise PitError(f'volumen sin nombre o sin título: {dict(v)!r}')
        if any(o['volumen'] == nombre for o in orden):
            raise PitError(f'el volumen {nombre!r} está dos veces en «volumenes»')
        orden.append({'volumen': nombre, 'titulo': titulo})
    documentos: dict[str, dict[str, Any]] = {}
    for fichero, d in (volumenes.get('documentos') or {}).items():
        d = d if isinstance(d, Mapping) else {}
        if fichero not in conocidos:
            raise PitError(f'«volumenes» coloca {fichero!r}, que no es un documento del expediente')
        volumen = str(d.get('volumen') or '').strip()
        if volumen not in {o['volumen'] for o in orden}:
            raise PitError(f'{fichero}: el volumen {volumen!r} no está en la lista de volúmenes')
        folios = d.get('folios')
        if folios is not None and (isinstance(folios, bool) or not isinstance(folios, int) or folios < 1):
            raise PitError(f'{fichero}: «folios» tiene que ser un entero de 1 o más (llegó {folios!r})')
        documentos[fichero] = {'volumen': volumen, 'folios': folios}
    return orden, documentos


def _contenido(nombre: str, sustento: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Tipo, descripción y aplicación de un documento, con el hueco de lo que falte; nada se inventa."""
    if nombre in sustento:
        d = sustento[nombre]
        descripcion = str(d.get('descripcion') or '').strip()
        uso = str(d.get('uso') or '').strip()
        aplicacion = str(d.get('aplicacion') or uso).strip()
        tipo = str(d.get('tipo') or TIPOS_DOCUMENTO[0])
        if tipo not in TIPOS_DOCUMENTO:
            raise PitError(f'{nombre}: tipo {tipo!r}; tiene que ser uno de {list(TIPOS_DOCUMENTO)}')
        origen = 'la empresa (sustento)'
    else:
        descripcion, aplicacion = _descrito(nombre) or ('', '')
        uso = aplicacion
        tipo, origen = TIPOS_DOCUMENTO[0], 'el expediente'
    huecos = []
    if not descripcion:
        huecos.append({'campo': 'descripcion', 'causa': f'{origen} no describe el contenido de {nombre}'})
    if not aplicacion:
        huecos.append({'campo': 'aplicacion', 'causa': f'{origen} no dice qué sección o formato sustenta {nombre}'})
    return {'tipo': tipo, 'descripcion': descripcion or None, 'aplicacion': aplicacion or None,
            'uso': uso or aplicacion or None, 'huecos': huecos}


def _relacion(carpeta: Path, sustento: Mapping[str, Mapping[str, Any]], volumenes: Mapping[str, Any] | None = None,
              incluir: Iterable[str] = ()) -> dict[str, Any]:
    """La relación de los documentos de sustento (RF-14): ``filas`` por fichero (la lista de ``relacion_sustento.json``,
    con su descripción, su uso y su huella) y ``volumenes``, en su orden, con el n.º y el foliado consecutivo.

    El n.º sigue el orden de los volúmenes y, dentro de cada uno, el orden en que se colocan sus documentos; los que no
    están en ningún volumen van al final, por nombre. Los folios corren de un volumen al siguiente sin reiniciar; un
    documento sin sus folios interrumpe el foliado de los que le siguen, y cada uno lo dice en su hueco. La propia
    relación por volúmenes figura sin huella (es el fichero que la contiene). ``incluir``: documentos que se escriben
    después de planear la relación (el resumen, que lleva sus pendientes); su huella se pone con ``_con_huellas``.
    """
    nombres = _declarados(carpeta, sustento, incluir)
    orden, colocados = _organizacion(volumenes, {*nombres, *DOCUMENTOS, *sustento})
    filas = {n: {'fichero': n, **_contenido(n, sustento)} for n in nombres}
    for n, f in filas.items():
        ruta = carpeta / n
        f['sha256'] = (hashlib.sha256(ruta.read_bytes()).hexdigest()
                       if n != RELACION_DOCUMENTOS and ruta.is_file() else None)
    grupos = [(o, [n for n in colocados if colocados[n]['volumen'] == o['volumen'] and n in filas]) for o in orden]
    sueltos = sorted(n for n in filas if n not in colocados)
    folio, interrumpe, numero = 1, None, 0
    for o, miembros in [*grupos, (None, sueltos)]:
        for n in miembros:
            f = filas[n]
            numero += 1
            f.update(numero=numero, volumen=o['volumen'] if o else None, folios=None, folio_desde=None,
                     folio_hasta=None)
            if o is None:
                causa = ('el expediente no declara su organización por volúmenes («volumenes»)' if not orden
                         else 'no está colocado en ningún volumen')
                f['huecos'].append({'campo': 'volumen', 'causa': causa})
                f['huecos'].append({'campo': 'folios', 'causa': 'sin volumen no se folia'})
                continue
            f['folios'] = colocados[n]['folios']
            if interrumpe is not None:
                f['huecos'].append({'campo': 'folios',
                                    'causa': f'foliado interrumpido: {interrumpe} no declara sus folios'})
            elif f['folios'] is None:
                f['huecos'].append({'campo': 'folios', 'causa': f'{n} no declara cuántos folios tiene'})
                interrumpe = n
            else:
                f['folio_desde'], f['folio_hasta'] = folio, folio + f['folios'] - 1
                folio += f['folios']
    salida = []
    for o, miembros in grupos:
        foliados = [filas[n] for n in miembros if filas[n]['folio_desde'] is not None]
        salida.append({**o, 'documentos': [filas[n]['numero'] for n in miembros],
                       'folio_desde': foliados[0]['folio_desde'] if foliados else None,
                       'folio_hasta': foliados[-1]['folio_hasta'] if foliados else None})
    if sueltos:
        salida.append({'volumen': None, 'titulo': None, 'documentos': [filas[n]['numero'] for n in sueltos],
                       'folio_desde': None, 'folio_hasta': None})
    return {'filas': [filas[n] for n in sorted(filas)], 'volumenes': salida,
            'no_emitidos': sorted(n for n in colocados if n not in filas)}


def _con_huellas(carpeta: Path, relacion: Mapping[str, Any]) -> None:
    """La huella de cada documento ya escrito; la de la relación por volúmenes se pone al escribirla."""
    for f in relacion['filas']:
        ruta = carpeta / f['fichero']
        if f['fichero'] != RELACION_DOCUMENTOS and ruta.is_file():
            f['sha256'] = hashlib.sha256(ruta.read_bytes()).hexdigest()


def _folios(f: Mapping[str, Any]) -> str:
    return '' if f['folio_desde'] is None else f'{f["folio_desde"]:03d}-{f["folio_hasta"]:03d}'


def formato_f000(celdas: Sequence[Mapping[str, Any]], mapeo: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """El «F-000» que el regulador pide junto con la relación de sustento (aclaración de 107:RF-14).

    No es una plantilla: es el nombre que el regulador da al grupo «Formatos de Información General» de la RCD
    217-2013 (art. 30.1, Tabla 1 y art. 31), que forman F-001, F-002 y F-003. Su equivalencia y sus citas van en el
    alias del mapeo de formatos (``alias``), no en el código. Se da por cumplido cuando las celdas del expediente traen
    los formatos del grupo; si falta alguno, lleva el hueco «F-000 incompleto: falta …».
    """
    mapeo = cargar_mapeo() if mapeo is None else mapeo
    alias = (mapeo.get('alias') or {}).get(F000)
    equivale = [str(c) for c in (alias or {}).get('equivale_a') or ()]
    if not equivale:
        raise PitError(f'el mapeo de formatos no declara el alias {F000} con su «equivale_a» '
                       '(config/pit_mapeo_formatos.json)')
    presentes = sorted({str(c.get('cuadro')) for c in celdas} & set(equivale))
    faltan = [c for c in equivale if c not in presentes]
    salida: dict[str, Any] = {
        'codigo': F000, 'nombre': alias.get('nombre') or F000, 'grupo': alias.get('grupo'), 'equivale_a': equivale,
        'norma': alias.get('norma'), 'citas': list(alias.get('citas') or ()),
        'nombre_de_fichero': alias.get('nombre_de_fichero'), 'presentes': presentes, 'faltan': faltan,
        'cumplido': not faltan}
    if faltan:
        salida['hueco'] = f'{F000} incompleto: falta {", ".join(faltan)}'
    return salida


def _sha_de(ruta: Path) -> str:
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()


def _plantilla_oficial(alias: Mapping[str, Any], fuentes: Path) -> tuple[Path, str]:
    """El libro oficial del grupo, comprobado su sha256 contra el declarado en el alias, antes de leerlo o copiarlo. Si
    no coincide, se para con el fichero y los dos sha (la misma regla que ``tools/normativa/fuentes.comprobar``)."""
    oficial = alias.get('plantilla_oficial') or {}
    relativa, esperado = str(oficial.get('ruta_relativa') or ''), str(oficial.get('sha256') or '').lower()
    if not relativa or not re.fullmatch(r'[0-9a-f]{64}', esperado):
        raise PitError(f'el alias {F000} del mapeo de formatos no declara su plantilla oficial con «ruta_relativa» y '
                       '«sha256» (config/pit_mapeo_formatos.json)')
    ruta = Path(fuentes) / relativa
    if not ruta.is_file():
        raise PitError(f'falta la plantilla oficial del {F000}: {ruta} (carpeta de fuentes {fuentes})')
    real = _sha_de(ruta)
    if real != esperado:
        raise PitError(f'FUENTE ALTERADA: {ruta} tiene sha256 {real} y el registrado es {esperado}. No se lee: '
                       'recupere el original (por ejemplo, del comprimido oficial) y repita.')
    return ruta, esperado


def escribir_informacion_general(carpeta: Path | str, resultados: Sequence[Mapping[str, Any]], fuentes: Path | str,
                                 ejecutar: Any = None, mapeo: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """El libro de Información General de la entrega, que el regulador llama «F-000» (107-P10b; aclaración de RF-14).

    Lleva las hojas F-001, F-002 y F-003 de la plantilla oficial, con las celdas de ``resultados`` (los de
    ``plantillas.celdas_de_formato`` de esos formatos), y se escribe en la carpeta del expediente con el nombre del
    alias del mapeo (``F-000-{area}_{periodo}.xlsx``, con el área y el periodo de la ficha). Se llama antes de
    ``emitir``, para que la relación del num. 5.3 lo vea; ``emitir`` no depende de Excel.

    - La plantilla oficial sale de la carpeta de fuentes (``fuentes``), con su ruta relativa y su sha256 del alias: se
      comprueba antes de copiarla a un directorio temporal, fuera de la carpeta de fuentes, y otra vez después de la
      corrida; Excel o WPS abren solo la copia. Si el original cambió, es un error que lo dice y se para.
    - El motor es el de los cuadros y los informes (``cuadros.plan_de_formatos`` → ``libro_informe.rellenar_con_excel``);
      sin Excel ni WPS no hay libro y se dice el motivo (``ejecutar`` lo sustituye en las pruebas).
    - Si falta un formato del grupo, el libro sale con lo que hay: la hoja que falta queda como la plantilla oficial
      vacía y sigue el hueco «F-000 incompleto: falta F-00x». El art. 30.1 de la RCD 217-2013 forma el grupo con los
      tres, y el regulador observa un F-000 incompleto como información incompleta (IT 438-2024, pág. 28) y uno no
      remitido deja la observación parcialmente subsanada (IT 599-2026, obs. 1.1): se entrega lo que hay, avisado.
    """
    carpeta = Path(carpeta)
    ficha = _ficha(carpeta)
    mapeo = cargar_mapeo() if mapeo is None else mapeo
    alias = (mapeo.get('alias') or {}).get(F000) or {}
    equivale = [str(c) for c in alias.get('equivale_a') or ()]
    codigos = [str(r.get('codigo')) for r in resultados]
    ajenos = sorted(set(codigos) - set(equivale))
    if ajenos:
        raise PitError(f'{ajenos} no son formatos del grupo {F000} ({", ".join(equivale) or "sin equivale_a"})')
    repetidos = sorted({c for c in codigos if codigos.count(c) > 1})
    if repetidos:
        raise PitError(f'formatos repetidos en el libro de Información General: {repetidos}')
    plantilla = str((alias.get('nombre_de_fichero') or {}).get('plantilla') or '')
    if '{area}' not in plantilla or '{periodo}' not in plantilla:
        raise PitError(f'el alias {F000} del mapeo no declara el nombre de su fichero con {{area}} y {{periodo}} '
                       f'(nombre_de_fichero.plantilla={plantilla!r})')
    nombre = plantilla.format(area=re.sub(r'[^\w.-]+', '_', ficha['area']),
                              periodo=re.sub(r'[^\w.-]+', '_', ficha['periodo']))
    oficial, esperado = _plantilla_oficial(alias, Path(fuentes))
    f000 = formato_f000([c for r in resultados for c in r.get('celdas') or ()], mapeo)
    ordenados = sorted(resultados, key=lambda r: equivale.index(str(r['codigo'])))
    destino = carpeta / nombre
    with tempfile.TemporaryDirectory() as temporal:
        copia = Path(temporal) / oficial.name
        shutil.copyfile(oficial, copia)
        plan = plan_de_formatos(ordenados, modelo=copia, destino=destino)
        libro, motivo = rellenar_con_excel(plan, ejecutar=ejecutar)
    despues = _sha_de(oficial)
    if despues != esperado:
        raise PitError(f'FUENTE ALTERADA tras la corrida: {oficial} tenía sha256 {esperado} y ahora tiene {despues}. '
                       'Alguien abrió o reescribió el original; recupérelo del comprimido oficial antes de repetir.')
    return {'libro': libro, 'motivo': motivo, 'nombre': nombre, 'hojas': list(equivale), F000: f000,
            'huecos': plan['huecos']}


def _relacion_documentos(relacion: Mapping[str, Any], f000: Mapping[str, Any]) -> dict[str, Any]:
    """La relación legible por volúmenes (tabla con sus columnas), sus huecos y el F-000 (RF-14)."""
    ordenadas = sorted(relacion['filas'], key=lambda f: f['numero'])
    por_numero = {f['numero']: f for f in ordenadas}
    campos = ('numero', 'fichero', 'tipo', 'descripcion', 'aplicacion', 'volumen', 'folios', 'folio_desde',
              'folio_hasta', 'sha256', 'huecos')
    volumenes = [{**v, 'documentos': [{c: por_numero[n][c] for c in campos} for n in v['documentos']]}
                 for v in relacion['volumenes']]
    huecos = [{'numero': f['numero'], 'fichero': f['fichero'], **h} for f in ordenadas for h in f['huecos']]
    huecos += [{'numero': None, 'fichero': n, 'campo': 'documento',
                'causa': f'«volumenes» coloca {n}, que este expediente no emitió'} for n in relacion['no_emitidos']]
    if f000.get('hueco'):
        huecos.append({'numero': None, 'fichero': None, 'campo': F000, 'causa': f000['hueco']})
    tabla = [[str(f['numero']), f['fichero'], f['tipo'], f['descripcion'] or '', f['aplicacion'] or '',
              f['volumen'] or '', _folios(f)] for f in ordenadas]
    return {'volumenes': volumenes, 'tabla': {'columnas': list(COLUMNAS_RELACION), 'filas': tabla},
            'huecos': huecos, 'completa': not huecos, F000: dict(f000)}


def _programa_de(datos: Mapping[str, Any]) -> Programa:
    return Programa(str(datos['area']), [FilaPrograma(**f) for f in datos.get('filas') or ()])


def _modificacion(carpeta: Path, programa: Programa | None, reglas: list[dict[str, Any]],
                  pedido: Mapping[str, Any]) -> dict[str, Any]:
    """RF-17: lo que el programa nuevo cambia del vigente, con su razón, y con los mismos criterios que el vigente."""
    if not pedido.get('vigente'):
        raise PitError('modificacion.vigente: falta la carpeta del expediente del plan vigente')
    vigente = Path(pedido['vigente'])
    if vigente.resolve() == carpeta.resolve():
        raise PitError('la modificación se emite en un expediente nuevo, no en el del plan vigente')
    if programa is None:
        raise PitError('la modificación del plan necesita el programa nuevo')
    ficha_vigente = _ficha(vigente)
    leidos = {}
    for nombre in ('programa.json', 'reglas_aplicadas.json'):
        ruta = vigente / nombre
        if not ruta.is_file():
            raise PitError(f'el expediente vigente {vigente.name} no tiene {nombre}')
        leidos[nombre] = json.loads(ruta.read_text(encoding='utf-8'))
    cambios = comparar_programas(_programa_de(leidos['programa.json']), programa, pedido.get('razones') or {})
    antes = {r['clave']: (r['valor'], r['norma']) for r in leidos['reglas_aplicadas.json']}
    ahora = {r['clave']: (r['valor'], r['norma']) for r in reglas}
    distintos = sorted(c for c in antes if c in ahora and antes[c] != ahora[c])
    if distintos:
        raise PitError(f'la modificación no usa los mismos criterios que el plan vigente: {distintos} cambian '
                       '(rehaga la demanda y las alternativas con los del vigente o justifique un estudio nuevo)')
    return {'vigente': {'area': ficha_vigente['area'], 'periodo': ficha_vigente['periodo'],
                        'instantanea': ficha_vigente['registro']['instantanea']},
            'cambios': [asdict(c) for c in cambios],
            'criterios_comunes': sorted(c for c in antes if c in ahora),
            'criterios_solo_vigente': sorted(set(antes) - set(ahora)),
            'criterios_nuevos': sorted(set(ahora) - set(antes))}


def emitir(carpeta: Path | str, registro: RegistroNormativo, *, celdas: Sequence[Mapping[str, Any]],
           diagnostico: Diagnostico | None = None, comparacion: Comparacion | None = None,
           programa: Programa | None = None, no_transcritos: Iterable[str] = (),
           alternativa_elegida: str | None = None, modificacion: Mapping[str, Any] | None = None,
           sustento: Mapping[str, Mapping[str, str]] | None = None,
           formatos: Mapping[str, Any] | None = None, volumenes: Mapping[str, Any] | None = None) -> dict[str, Path]:
    """Escribe el expediente. Una celda sin traza completa no se emite: es un error que la nombra.

    Además de los cuadros, las reglas y el resumen, cada sección lleva su memoria (``memoria.json``) y el expediente su
    relación de sustento (``relacion_sustento.json``, RF-14). Con ``alternativa_elegida`` (y el diagnóstico, la
    comparación y el programa) escribe el resumen ejecutivo (RF-13); con ``modificacion`` (``vigente``: la carpeta
    del plan vigente, y ``razones``: elemento → razón) escribe lo que cambia respecto de él (RF-17). ``sustento``
    describe los documentos que la empresa añada a la carpeta. Con ``formatos`` (de ``cuadros.formatos_aplicables``)
    guarda los formatos de la norma vigente y nombra en el resumen los no transcritos (aclaración de RF-9). Todo lo que
    puede fallar se comprueba antes de escribir.

    La relación de sustento va también por volúmenes (``relacion_documentos.json``, RF-14): n.º, fichero, tipo
    (``electrónico`` o ``físico``), descripción, aplicación y volumen con sus folios consecutivos, más el F-000 (el grupo
    F-001 a F-003: cumplido o el hueco del que falta). ``sustento`` admite, además de ``descripcion`` y ``uso``, ``aplicacion`` (qué sección o formato sustenta;
    sin ella vale el ``uso``) y ``tipo``; un documento declarado sin descripción o sin aplicación entra con su hueco
    nombrado, y el resumen (``resumen.json``) dice que el expediente sale ``incompleto``, con cada hueco de la
    relación en sus ``pendientes`` (aclaración de RF-14). ``volumenes``: ``volumenes`` (lista, en su orden, de
    ``volumen`` y ``titulo``) y ``documentos`` (fichero → ``volumen`` y ``folios``); sin él, cada documento lleva el hueco de su volumen y de sus folios.
    """
    carpeta = Path(carpeta)
    ficha = _ficha(carpeta)
    sin_traza = [c.get('id') for c in celdas if any(not c.get('traza', {}).get(k) for k in _TRAZA)]
    if sin_traza:
        raise PitError(f'celdas sin traza completa ({", ".join(_TRAZA)}): {sin_traza}')
    if formatos is not None and not isinstance(formatos.get('formatos'), list):
        raise PitError('«formatos» tiene que venir de cuadros.formatos_aplicables (falta su lista «formatos»)')
    no_transcritos = sorted({*no_transcritos, *((formatos or {}).get('no_transcritos') or ())})
    sustento = dict(sustento or {})
    if alternativa_elegida is not None:
        if diagnostico is None or comparacion is None or programa is None:
            raise PitError('el resumen ejecutivo necesita el diagnóstico, la comparación y el programa')
        elegida = next((a for a in comparacion.alternativas if a.nombre == alternativa_elegida), None)
        if elegida is None or not elegida.completa:
            raise PitError(f'la alternativa elegida {alternativa_elegida!r} no está completa en la comparación')
    # Un documento que nadie describe, o una organización por volúmenes mal formada, se detiene antes de escribir.
    _declarados(carpeta, sustento)
    _organizacion(volumenes, {*DOCUMENTOS, *sustento,
                              *(r.relative_to(carpeta).as_posix() for r in carpeta.rglob('*') if r.is_file())})
    for nombre in sustento:
        _contenido(nombre, sustento)
    f000 = formato_f000(celdas)
    reglas = _reglas_aplicadas(diagnostico, comparacion, celdas, registro)
    cambio_plan = _modificacion(carpeta, programa, reglas, modificacion) if modificacion is not None else None
    modificatoria = comprobar_modificatoria(carpeta, registro)
    salidas = {'cuadros': carpeta / 'cuadros.json', 'reglas': carpeta / 'reglas_aplicadas.json',
               'resumen': carpeta / 'resumen.json'}
    _json(salidas['cuadros'], sorted((dict(c) for c in celdas), key=lambda c: c['id']))
    _json(salidas['reglas'], reglas)
    if formatos is not None:
        salidas['formatos'] = carpeta / 'formatos.json'
        _json(salidas['formatos'], dict(formatos))
    if diagnostico is not None:
        salidas['diagnostico'] = carpeta / 'diagnostico.json'
        _json(salidas['diagnostico'], diagnostico.como_dict())
    if comparacion is not None:
        salidas['alternativas'] = carpeta / 'alternativas.json'
        _json(salidas['alternativas'], comparacion.como_dict())
    if programa is not None:
        salidas['programa'] = carpeta / 'programa.json'
        _json(salidas['programa'], programa.como_dict())
    salidas['memoria'] = carpeta / 'memoria.json'
    _json(salidas['memoria'], _memoria(diagnostico, comparacion, programa, celdas, no_transcritos))
    if cambio_plan is not None:
        salidas['modificacion'] = carpeta / 'modificacion.json'
        _json(salidas['modificacion'], cambio_plan)
    if alternativa_elegida is not None:
        # Cada cifra, de lo que se acaba de escribir (107:RF-13): se lee de los ficheros, no de los objetos.
        salidas['resumen_ejecutivo'] = carpeta / 'resumen_ejecutivo.json'
        _json(salidas['resumen_ejecutivo'], desde_carpeta(carpeta, alternativa_elegida))
    # El resumen se escribe el último antes de la relación para llevar sus pendientes (aclaración de RF-14): el
    # expediente con un hueco en su relación de sustento sale «incompleto», con cada hueco nombrado.
    relacion = _relacion(carpeta, sustento, volumenes, incluir=[salidas['resumen'].name])
    pendientes = _relacion_documentos(relacion, f000)['huecos']
    # Sin alternativas no hay comparación ni programa: el expediente es de diagnóstico y nunca sale completo, aunque
    # no le falte nada más (aclaración de RF-5, condición de 28 en 107-P10c).
    tipo = TIPO_ESTUDIO if comparacion is not None and alternativa_elegida is not None else TIPO_DIAGNOSTICO
    if tipo == TIPO_DIAGNOSTICO:
        causa = SIN_ALTERNATIVAS if comparacion is None else SIN_ELEGIDA
        pendientes = [*pendientes, {'numero': None, 'fichero': None, 'campo': 'alternativas', 'causa': causa}]
        # Cada hueco nombrado de la norma o de los datos (un año sin porcentaje de COyM publicado, un elemento sin
        # ubicación) va como pendiente propio: es lo que deja el expediente de diagnóstico (aclaración de RF-5).
        pendientes += [{'numero': None, 'fichero': 'alternativas.json',
                        'campo': f'alternativas.{a.nombre}.{h["regla"]}'
                                 + (f'.{h["anio"]}' if h.get('anio') is not None else '')
                                 + (f'.{h["elemento"]}' if h.get('elemento') else ''),
                        'causa': h['causa']}
                       for a in (comparacion.alternativas if comparacion is not None else ()) for h in a.huecos]
    if diagnostico is not None:
        # Lo que falta para la tensión de una barra o un transformador es un pendiente del expediente (107 T7, PIT-TEN).
        pendientes = [*pendientes, *({'numero': None, 'fichero': 'diagnostico.json',
                                      'campo': f'diagnostico.tension.{h.get("elemento") or h["barra"]}',
                                      'causa': 'falta ' + '; '.join(h['falta'])} for h in diagnostico.huecos_tension)]
    referencias = [r['clave'] for r in reglas if not r['obligatoria']]
    _json(salidas['resumen'], {
        'estudio': 'PIT', 'area': ficha['area'], 'periodo': ficha['periodo'],
        'presentacion': 'estudio de la empresa; lo presenta la empresa al regulador',
        'reglas_como_referencia': referencias, 'cuadros_no_transcritos': no_transcritos,
        # Las tensiones de referencia (RM 129-2009), por barra con su cifra y su fuente: visibles, no violaciones.
        'avisos_diagnostico': [a for a in (diagnostico.avisos if diagnostico is not None else ())
                               if a.startswith('tensión de referencia')],
        'modificatoria_posterior': modificatoria, 'celdas': len(celdas),
        'tipo': tipo, 'estado': 'incompleto' if pendientes else 'completo', 'pendientes': pendientes})
    _con_huellas(carpeta, relacion)
    salidas['relacion_documentos'] = carpeta / RELACION_DOCUMENTOS
    _json(salidas['relacion_documentos'], _relacion_documentos(relacion, f000))
    propia = next(f for f in relacion['filas'] if f['fichero'] == RELACION_DOCUMENTOS)
    propia['sha256'] = hashlib.sha256(salidas['relacion_documentos'].read_bytes()).hexdigest()
    salidas['relacion'] = carpeta / RELACION
    _json(salidas['relacion'], relacion['filas'])
    return salidas
