"""Expediente del PIT: carpeta propia, instantánea del registro, traza de cada celda y determinismo (107:RF-1, RF-7 a
RF-9).

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
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..registro_normativo import RegistroNormativo
from . import PitError
from .alternativas import Comparacion
from .diagnostico import Diagnostico
from .informe import desde_carpeta
from .programa import FilaPrograma, Programa, comparar_programas

__all__ = ['DOCUMENTOS', 'RELACION', 'abrir', 'comprobar_modificatoria', 'emitir', 'filas_del_programa']

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
    return {c: registro.regla(c).huella() for c in claves}


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
                    'uso': 'obligatoria' if r.obligatoria else 'referencia (no obligatoria: 107:RF-8)'})
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
}
RELACION = 'relacion_sustento.json'


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
                           'completo': diagnostico.completo, 'cancelado': diagnostico.cancelado}}
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


def _relacion(carpeta: Path, sustento: Mapping[str, Mapping[str, str]]) -> list[dict[str, str]]:
    """Cada documento de la carpeta con su descripción, su uso y su huella; uno sin descripción es un error (RF-14)."""
    out, sin = [], []
    for ruta in sorted(p for p in carpeta.rglob('*') if p.is_file()):
        nombre = ruta.relative_to(carpeta).as_posix()
        if nombre == RELACION:
            continue
        if nombre in sustento:
            d = sustento[nombre]
            descripcion, uso = str(d.get('descripcion') or ''), str(d.get('uso') or '')
        else:
            descripcion, uso = DOCUMENTOS.get(nombre, ('', ''))
        if not descripcion.strip() or not uso.strip():
            sin.append(nombre)
            continue
        out.append({'fichero': nombre, 'descripcion': descripcion, 'uso': uso,
                    'sha256': hashlib.sha256(ruta.read_bytes()).hexdigest()})
    if sin:
        raise PitError(f'documentos del expediente sin descripción o sin uso en la relación de sustento: {sin} '
                       '(se declaran en «sustento»)')
    return out


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
           formatos: Mapping[str, Any] | None = None) -> dict[str, Path]:
    """Escribe el expediente. Una celda sin traza completa no se emite: es un error que la nombra.

    Además de los cuadros, las reglas y el resumen, cada sección lleva su memoria (``memoria.json``) y el expediente su
    relación de sustento (``relacion_sustento.json``, RF-14). Con ``alternativa_elegida`` (y el diagnóstico, la
    comparación y el programa) escribe el resumen ejecutivo (RF-13); con ``modificacion`` (``vigente``: la carpeta
    del plan vigente, y ``razones``: elemento → razón) escribe lo que cambia respecto de él (RF-17). ``sustento``
    describe los documentos que la empresa añada a la carpeta. Con ``formatos`` (de ``cuadros.formatos_aplicables``)
    guarda los formatos de la norma vigente y nombra en el resumen los no transcritos (aclaración de RF-9). Todo lo que
    puede fallar se comprueba antes de escribir.
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
    sin_describir = sorted(r.relative_to(carpeta).as_posix() for r in carpeta.rglob('*') if r.is_file()
                           and r.relative_to(carpeta).as_posix() not in {*DOCUMENTOS, RELACION, *sustento})
    sin_describir += sorted(n for n, d in sustento.items()
                            if not str(d.get('descripcion') or '').strip() or not str(d.get('uso') or '').strip())
    if sin_describir:
        raise PitError(f'documentos del expediente sin descripción o sin uso en la relación de sustento: '
                       f'{sin_describir} (se declaran en «sustento»)')
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
    referencias = [r['clave'] for r in reglas if not r['obligatoria']]
    _json(salidas['resumen'], {
        'estudio': 'PIT', 'area': ficha['area'], 'periodo': ficha['periodo'],
        'presentacion': 'estudio de la empresa; lo presenta la empresa al regulador',
        'reglas_como_referencia': referencias, 'cuadros_no_transcritos': no_transcritos,
        'modificatoria_posterior': modificatoria, 'celdas': len(celdas)})
    salidas['memoria'] = carpeta / 'memoria.json'
    _json(salidas['memoria'], _memoria(diagnostico, comparacion, programa, celdas, no_transcritos))
    if cambio_plan is not None:
        salidas['modificacion'] = carpeta / 'modificacion.json'
        _json(salidas['modificacion'], cambio_plan)
    if alternativa_elegida is not None:
        # Cada cifra, de lo que se acaba de escribir (107:RF-13): se lee de los ficheros, no de los objetos.
        salidas['resumen_ejecutivo'] = carpeta / 'resumen_ejecutivo.json'
        _json(salidas['resumen_ejecutivo'], desde_carpeta(carpeta, alternativa_elegida))
    salidas['relacion'] = carpeta / RELACION
    _json(salidas['relacion'], _relacion(carpeta, sustento))
    return salidas
