"""El proyecto entero desde un espacio vacío, etapa por etapa (spec 027, T21; RF-43, RF-44).

El agente encadena lo que el operador hace a mano en la web, por las mismas rutas y trabajos:
cargar la fuente, el sistema eléctrico de punta a punta (convertir, importar en DIgSILENT y
calibrar, ``tools/sistema_web.py``), verificar el «Caso base», integrar las cargas nuevas,
aplicar las obras, los estudios, el PIDE y el informe. Al terminar cada etapa guarda un punto
de control; si la ejecución se corta (DIgSILENT ocupado, la web reiniciada), la siguiente
retoma desde la primera etapa sin hacer y no repite nada (RF-44). Una etapa que necesita un
dato que no se dio (el libro de cargas nuevas, el formulario del informe) se omite y se dice.

027:RF-72: tras el informe, el PIT, el VAD y el VNR, opcionales, se saltan con su motivo si falta su dato. 026:RF-48:
``camino_de`` propone el camino entero (la etapa que sigue, sus entradas y sus parámetros según la norma y el perfil),
con su motivo, sobre la misma lista que confirma el operador.
"""
from __future__ import annotations

from ...dominio.util import publicar_duradero

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..evaluacion_modelos import huella
from .ejecutor import ClienteWeb, ejecutar, pasos
from .tareas import TAREAS, descripcion_para_operador


@dataclass(frozen=True)
class Etapa:
    nombre: str
    tarea: str
    requiere: tuple[str, ...] = ()
    """Datos sin los que no se hace; si faltan y es ``opcional``, se omite."""
    opcional: bool = False
    proceso: bool = False
    """La hace una herramienta de ``tools/`` (``sistema_web.py``), no una ruta."""
    condicion: str = ''
    """Cuándo hace falta, comprobado al llegar a ella; vacío, siempre (070:RF-53, RF-54)."""


#: Las etapas del proyecto desde cero (RF-43), en orden.
ETAPAS: tuple[Etapa, ...] = (
    Etapa('fuente', 'cargar_fuente'),
    Etapa('sistema', 'sistema_completo', ('sistema', 'periodo', 'ruta'), proceso=True),
    Etapa('caso_base', 'verificar_caso_base', ('proyecto',)),
    Etapa('cargas_nuevas', 'cargas_nuevas', ('proyecto', 'ruta_cargas'), opcional=True),
    Etapa('obras', 'obras', ('proyecto',)),
    Etapa('estudios', 'estudios', ('proyecto',)),
    Etapa('pide', 'pide', ('proyecto',)),
    Etapa('informe', 'informe_estudio', ('proyecto', 'formulario'), opcional=True),
)


#: 027:RF-72: los módulos tras el informe, cada uno opcional y con lo que requiere: el expediente del PIT con su libro y su
#: proyección, la empresa modelo del VAD con su caso y su estudio, y el Estudio VNR con su sector, su resolución y su año.
#: Sin su dato se saltan con su motivo, nunca con un error, y el proyecto sigue con los demás.
ETAPAS_MODULOS: tuple[Etapa, ...] = (
    Etapa('pit', 'pit_expediente', ('pit',), opcional=True),
    Etapa('vad', 'vad_empresa_modelo', ('vad',), opcional=True),
    Etapa('vnr', 'vnr_estudio', ('vnr',), opcional=True),
)
#: 027:RF-72: «el proyecto entero» hasta los entregables de todos los módulos.
ETAPAS_PROYECTO_ENTERO: tuple[Etapa, ...] = (*ETAPAS, *ETAPAS_MODULOS)
#: Lo que necesita cada módulo, dentro de su dato; si falta una parte, el módulo se salta con ella en su motivo.
REQUISITOS_MODULO: dict[str, tuple[str, ...]] = {
    'pit': ('workspace_id', 'libro_red', 'proyeccion', 'area', 'anios', 'periodo'),
    'vad': ('estudio', 'ficheros'),
    'vnr': ('sector', 'sector_sicodi', 'resolucion', 'anio', 'moneda'),
}
#: Por qué se salta un módulo sin su dato, en las palabras del operador.
MOTIVO_SIN_DATO = {'pit': 'sin el libro PIT y su proyección', 'vad': 'sin los datos del VAD (su caso y su estudio)',
                   'vnr': 'sin los datos del VNR (sector, resolución del SICODI y año)'}


def falta_del_modulo(nombre: str, dato: Any) -> str:
    """027:RF-72: por qué el módulo ``nombre`` no se puede hacer con ``dato``; vacío si se puede."""
    if not isinstance(dato, Mapping) or not dato:
        return MOTIVO_SIN_DATO[nombre]
    faltan = [k for k in REQUISITOS_MODULO[nombre] if dato.get(k) in (None, '', [], {})]
    if faltan:
        return f"{MOTIVO_SIN_DATO[nombre]}: falta {', '.join(k.replace('_', ' ') for k in faltan)}"
    ficheros = [dato.get('libro_red'), dato.get('proyeccion')] if nombre == 'pit' else (
        list(dato.get('ficheros') or []) if nombre == 'vad' else [])
    sueltos = [Path(str(f)).name for f in ficheros if f and not Path(str(f)).is_file()]
    return f"{MOTIVO_SIN_DATO[nombre]}: no está {', '.join(sueltos)}" if sueltos else ''


#: 070:RF-50: evaluar una carga nueva. El informe se hace al evaluar porque ya prepara los casos y concluye
#: (063:RF-1); solo se rehace si hubo obras. Su libro lo decide el perfil, dentro del propio informe (066:RF-1).
ETAPAS_CARGA: tuple[Etapa, ...] = (
    Etapa('diagnostico', 'verificar_convergencia', ('proyecto',)),
    Etapa('calibracion', 'recalibrar', ('proyecto', 'periodo'), proceso=True, condicion='sin_calibracion'),
    Etapa('carga', 'carga_nueva_sola', ('proyecto', 'alimentadores', 'sed', 'nueva')),
    Etapa('evaluacion', 'informe_factibilidad', ('proyecto', 'alimentadores', 'sed', 'formulario')),
    Etapa('obras', 'optimizar_con_proyecto', ('proyecto', 'alimentadores'), condicion='si_no_factible'),
    Etapa('informe', 'informe_factibilidad', ('proyecto', 'alimentadores', 'sed', 'formulario'), condicion='si_hubo_obras'),
)

#: 072:RF-31 a RF-33: el estudio de corto plazo con una carga nueva, en su orden: la carga sobre la calibración, la
#: escalera de obras de implementación inmediata (025:RF-44), los estudios de la red con ella y el informe de estudio
#: (spec 017). La factibilidad de una carga sola es otro análisis (``ETAPAS_CARGA``).
ETAPAS_CORTO_PLAZO: tuple[Etapa, ...] = (
    Etapa('carga', 'carga_nueva_sola', ('proyecto', 'alimentadores', 'sed', 'nueva')),
    Etapa('obras', 'obras_escalera', ('proyecto', 'alimentadores')),
    Etapa('estudios', 'estudios', ('proyecto', 'alimentadores')),
    Etapa('informe', 'informe_estudio', ('proyecto', 'alimentadores', 'formulario')),
)
#: El mismo, con las cargas nuevas de un libro de planificación en vez de una sola (specs 007 y 014).
ETAPAS_CORTO_PLAZO_LIBRO: tuple[Etapa, ...] = (
    Etapa('cargas', 'cargas_nuevas', ('proyecto', 'alimentadores', 'ruta_cargas')), *ETAPAS_CORTO_PLAZO[1:])

#: Qué se enseña de una condición antes de que se pueda comprobar.
_CONDICIONES = {'sin_calibracion': 'solo si no tiene calibración', 'si_no_factible': 'solo si la evaluación pide obras',
                'si_hubo_obras': 'solo si hubo obras'}

#: Datos que deja una etapa para las siguientes, y que por eso no faltan antes de empezar.
LOS_DEJA_UNA_ETAPA = ('proyecto', 'alimentadores')


@dataclass
class PuntoDeControl:
    """Las etapas hechas de un proyecto, en un JSON que sobrevive a un reinicio (RF-44)."""

    ruta: Path
    estado: dict[str, Any] = field(default_factory=dict)
    identidad_actual: Callable[[],dict] | None = field(default=None,repr=False)

    def validar_identidad(self) -> None:
        if self.identidad_actual is not None and self.estado.get('identidad')!=self.identidad_actual():
            raise ValueError('la identidad de la fuente cambió durante la ejecución; se detiene el agente')

    @classmethod
    def abrir(cls, ruta: Path | str) -> PuntoDeControl:
        ruta = Path(ruta)
        estado = json.loads(ruta.read_text(encoding='utf-8')) if ruta.is_file() else {}
        estado.setdefault('etapas', {})
        estado.setdefault('datos', {})
        return cls(ruta, estado)

    def hecha(self, etapa: str) -> bool:
        return (self.estado['etapas'].get(etapa) or {}).get('estado') in ('hecha', 'omitida')

    def marcar(self, etapa: str, estado: str, resultado: Any = None, datos: Mapping[str, Any] | None = None) -> None:
        if self.identidad_actual is not None:
            if etapa=='fuente' and estado=='hecha':
                self.estado['identidad']=self.identidad_actual()
            else:self.validar_identidad()
        self.estado['etapas'][etapa] = {'estado': estado, 'resultado': resultado,
                                        'fecha': time.strftime('%Y-%m-%dT%H:%M:%S')}
        if datos is not None:
            self.estado['datos'] = dict(datos)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        publicar_duradero(self.ruta, json.dumps(self.estado, ensure_ascii=False, indent=1, default=str))   # 001:RF-5


def lista_de_etapas(datos: Mapping[str, Any], control: Mapping[str, Any], contexto: Mapping[str, Any],
                    *, reiniciar: bool = False, etapas: tuple[Etapa, ...] = ETAPAS,
                    omitir: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Lo que hará el proyecto entero, antes del único clic (067:RF-37, RF-39).

    Un clic confirmaba todas las etapas sin enseñarlas. La huella ata la confirmación a lo que se vio:
    otra fuente, otros datos u otras etapas hechas ya no son lo que el operador aceptó.
    """
    hechas = {} if reiniciar else (control.get('etapas') or {})
    conocidos = {**({} if reiniciar else (control.get('datos') or {})), **dict(datos)}
    # El proyecto y sus alimentadores los deja la etapa del sistema: no faltan si aún va a correr.
    if (hechas.get('sistema') or {}).get('estado') not in ('hecha', 'omitida'):
        conocidos.setdefault('proyecto', '(lo deja la etapa del sistema)')
    filas = []
    omitir = omitir or {}
    for e in etapas:
        falta = [k for k in e.requiere if not conocidos.get(k)]
        motivo = omitir.get(e.nombre, '')
        if e.nombre in REQUISITOS_MODULO and not motivo:
            motivo = falta_del_modulo(e.nombre, conocidos.get(e.nombre))           # 027:RF-72
        if (hechas.get(e.nombre) or {}).get('estado') in ('hecha', 'omitida'):
            estado = 'hecha'
        elif e.nombre in omitir or (e.nombre in REQUISITOS_MODULO and motivo):
            estado, falta = 'se_omitira', []
        elif falta:
            estado = 'se_omitira' if e.opcional else 'falta_dato'
        else:
            estado = 'pendiente'
        # 070:RF-51: lo que lee el operador, sin las citas del catálogo (la del catálogo entra en las huellas selladas).
        filas.append({'nombre': e.nombre, 'tarea': e.tarea, 'descripcion': descripcion_para_operador(e.tarea),
                      'escribe': TAREAS[e.tarea].escribe, 'estado': estado, 'falta': falta,
                      'motivo': motivo if estado == 'se_omitira' else '', 'condicion': _CONDICIONES.get(e.condicion, '')})
    escrituras = [f['nombre'] for f in filas if f['escribe'] and f['estado'] == 'pendiente']
    identidad = None if reiniciar else control.get('identidad')
    requeridos = {k for e in etapas for k in e.requiere}
    return {'etapas': filas, 'etapas_escritura': escrituras,
            # 026:RF-48: con qué va cada etapa, lo dado y lo que dejaron las hechas, para proponer el camino.
            'conocidos': {k: v for k, v in conocidos.items() if k in requeridos and v},
            'bloqueo': (
                'Hay un punto de control de otra fuente o solicitud: marque «Empezar de nuevo».'
                if hechas and identidad != {**dict(contexto), 'solicitud': dict(datos)} else ''),
            'confirmacion': huella({'contexto': dict(contexto), 'solicitud': dict(datos), 'reiniciar': reiniciar,
                                     'etapas': [(f['nombre'], f['estado']) for f in filas]})}


#: 026:RF-48: los parámetros con que el asistente propone cada etapa y de dónde salen: una regla vigente de la biblioteca
#: normativa (por su clave) o una clave del perfil de la empresa. Ninguno se inventa: sin la regla o sin la clave, el
#: parámetro queda como falta, con su motivo.
PARAMETROS_DE_ETAPA: dict[str, tuple[tuple[str, str, str], ...]] = {
    'caso_base': (('tension_min_pu', 'perfil', 'estudios.tension_min_pu'),
                  ('tension_max_pu', 'perfil', 'estudios.tension_max_pu')),
    'estudios': (('tolerancia_tension', 'norma', 'calidad.tension.tolerancia_ntcse'),
                 ('cargabilidad_max_pct', 'perfil', 'estudios.cargabilidad_max_pct')),
    'obras': (('cargabilidad_max_pct', 'perfil', 'estudios.cargabilidad_max_pct'),),
    'pide': (('horizonte_anios', 'norma', 'vinculo.pide.horizonte_estudio_anios'),
             ('anio_presentacion', 'perfil', 'planificacion.anio_presentacion')),
    'informe': (('tolerancia_tension', 'norma', 'calidad.tension.tolerancia_ntcse'),),
    'pit': (('horizonte_demanda_anios', 'norma', 'pit.horizonte_demanda_anios'),
            ('horizonte_alternativas_anios', 'norma', 'pit.horizonte_alternativas_anios')),
    'vnr': (('anio_md', 'norma', 'vnr.md.anio'),),
}

#: Por qué va cada estado de una etapa en el camino, en las palabras del operador.
_MOTIVO_DEL_ESTADO = {'hecha': 'ya hecha: no se repite', 'falta_dato': 'falta {falta}: sin ello no se puede seguir',
                      'se_omitira': 'se salta: {motivo}'}


def norma_de_la_biblioteca(fecha: str) -> Callable[[str], dict | None]:
    """026:RF-48: la regla vigente en ``fecha`` de la biblioteca normativa (107), con su acto y su artículo."""
    from ..biblioteca_normativa import cargar_biblioteca
    from ...dominio.registro_normativo import RegistroError

    registro = cargar_biblioteca()

    def regla(clave: str) -> dict | None:
        try:
            r = registro.regla(clave, fecha)
        except RegistroError:
            return None
        return {'valor': r.regla.valor, 'acto': r.norma.acto, 'articulo': r.regla.articulo_o_anexo}
    return regla


def _del_perfil(perfil: Mapping[str, Any] | None, clave: str) -> Any:
    valor: Any = perfil or {}
    for parte in clave.split('.'):
        valor = valor.get(parte) if isinstance(valor, Mapping) else None
    return valor


def _parametros(nombre: str, norma: Callable[[str], dict | None] | None, perfil: Mapping[str, Any] | None) -> list[dict]:
    filas = []
    for parametro, de, clave in PARAMETROS_DE_ETAPA.get(nombre, ()):
        if de == 'norma':
            regla = norma(clave) if norma is not None else None
            filas.append({'parametro': parametro, 'de': 'norma', 'clave': clave, **(
                {'valor': regla['valor'], 'acto': regla['acto'], 'articulo': regla.get('articulo', '')} if regla else
                {'valor': None, 'falta': f'la biblioteca normativa no trae la regla {clave} vigente'})})
        else:
            valor = _del_perfil(perfil, clave)
            filas.append({'parametro': parametro, 'de': 'perfil', 'clave': clave, **(
                {'valor': valor} if valor is not None else
                {'valor': None, 'falta': f'el perfil de la empresa no trae {clave.replace(".", " de ")}'})})
    return filas


def camino_de(lista: Mapping[str, Any], datos: Mapping[str, Any], *, norma: Callable[[str], dict | None] | None = None,
              perfil: Mapping[str, Any] | None = None, etapas: tuple[Etapa, ...] = ETAPAS) -> dict[str, Any]:
    """026:RF-48: el camino entero que propone el asistente, sobre la lista que verá el operador (067:RF-37).

    Para cada etapa: con qué entradas del espacio va, con qué parámetros según la norma y el perfil y por qué va (o por
    qué no); cuál sigue, y qué confirma el operador (lo que escribe, gasta la licencia o sale a la red) frente a lo que
    el asistente hace solo. No calcula ni ejecuta nada: solo lee la lista, los datos, la norma y el perfil.
    """
    from .tareas import requiere_confirmacion

    por_nombre = {e.nombre: e for e in etapas}
    datos = {**dict(datos), **(lista.get('conocidos') or {})}
    filas: list[dict[str, Any]] = []
    siguiente: dict[str, Any] | None = None
    for f in lista['etapas']:
        e = por_nombre[f['nombre']]
        entradas = {k: datos.get(k) or '(lo deja una etapa anterior)' for k in e.requiere
                    if datos.get(k) or k in LOS_DEJA_UNA_ETAPA}
        confirma = bool(f['escribe'] or requiere_confirmacion(e.tarea))
        if f['estado'] == 'pendiente':
            motivo = ('es la primera sin hacer' if siguiente is None else 'sigue a la anterior') + (
                f" con {', '.join(sorted(entradas))}" if entradas else '') + (
                f"; {f['condicion']}" if f.get('condicion') else '')
        else:
            falta = ', '.join(f['falta'])
            motivo = _MOTIVO_DEL_ESTADO[f['estado']].format(falta=falta, motivo=f.get('motivo') or f'falta {falta}')
        fila = {'etapa': f['nombre'], 'tarea': e.tarea, 'estado': f['estado'], 'entradas': entradas,
                'parametros': _parametros(f['nombre'], norma, perfil), 'motivo': motivo,
                'confirma_el_operador': confirma, 'lo_hace_el_asistente_solo': not confirma}
        filas.append(fila)
        if siguiente is None and f['estado'] in ('pendiente', 'falta_dato'):
            siguiente = fila
    pendientes = [f for f in filas if f['estado'] == 'pendiente']
    if siguiente is None:
        texto = 'Nada que hacer: todas las etapas están hechas o se saltan con su motivo.'
    elif siguiente['estado'] == 'falta_dato':
        texto = f"Siguiente etapa: {siguiente['etapa'].replace('_', ' ')}; {siguiente['motivo']}."
    else:
        texto = f"Siguiente etapa: {siguiente['etapa'].replace('_', ' ')}, porque {siguiente['motivo']}."
    return {'siguiente': siguiente['etapa'] if siguiente else None, 'motivo': texto, 'etapas': filas,
            'confirma_el_operador': [f['etapa'] for f in pendientes if f['confirma_el_operador']],
            'lo_hace_el_asistente_solo': [f['etapa'] for f in pendientes if f['lo_hace_el_asistente_solo']],
            'parametros_que_faltan': [f"{f['etapa']}: {p['falta']}" for f in filas for p in f['parametros']
                                      if p.get('falta')],
            'confirmacion': lista.get('confirmacion'), 'calcula': False}


def _resumen(resultado: Any) -> Any:
    """Lo que se guarda de una etapa: lo pequeño, no las curvas ni las tablas."""
    if isinstance(resultado, dict):
        pequeno = {k: v for k, v in resultado.items() if isinstance(v, (str, int, float, bool, type(None)))}
        # 063:RF-8: lo que decide es la conclusión de los tres casos, no el resumen del Word.
        conclusion = resultado.get('conclusion_conexion')
        if isinstance(conclusion, dict) and 'factible' in conclusion:
            pequeno.update(factible=conclusion['factible'], conclusion=conclusion.get('clave'))
        return pequeno
    return resultado if isinstance(resultado, (str, int, float, bool, type(None))) else None


def _factible(resumen: Any) -> Any:
    return resumen.get('factible') if isinstance(resumen, Mapping) else None


def _motivo_para_omitir(e: Etapa, cliente: ClienteWeb, datos: Mapping[str, Any], control: PuntoDeControl) -> str:
    """Por qué esta etapa no hace falta ahora; vacío si hace falta (070:RF-53, RF-54)."""
    if e.condicion == 'sin_calibracion':
        respuesta = cliente.pedir('GET', f"/demanda/ajuste/ultimo?project={quote(str(datos.get('proyecto') or ''))}") or {}
        return f"{datos.get('proyecto')} ya tiene calibración aplicada." if respuesta.get('ajuste') else ''
    previa = control.estado['etapas'].get('evaluacion') or {}
    if e.condicion == 'si_no_factible':
        # Solo un «no» explícito lleva a obras: sin conclusión no se construye nada por si acaso (063:RF-8).
        return '' if _factible(previa.get('resultado')) is False else 'la evaluación concluye que se conecta sin obras.'
    if e.condicion == 'si_hubo_obras':
        return '' if (control.estado['etapas'].get('obras') or {}).get('estado') == 'hecha' else 'no hubo obras: vale el informe de la evaluación.'
    return ''


def _extras_de_etapa(e: Etapa, datos: Mapping[str, Any]) -> dict[str, Any]:
    formulario = dict(datos.get('formulario') or {})
    if e.tarea == 'informe_factibilidad':
        formulario['preparar_casos'] = True                                   # 063:RF-1: en un paso
    extras: dict[str, Any] = {'formulario': formulario}
    if e.tarea == 'carga_nueva_sola':
        extras['nueva'] = datos.get('nueva')
    if e.tarea == 'optimizar_con_proyecto' and datos.get('sed'):
        extras['cargas'] = [datos['sed']]                                     # 063:RF-23: la de esta evaluación
    if datos.get('tipo_cambio'):
        extras['tipo_cambio'] = datos['tipo_cambio']
    if e.nombre in REQUISITOS_MODULO:
        extras[e.nombre] = dict(datos[e.nombre])                              # 027:RF-72: su dato, a sus pasos
    return extras


#: Las etapas cuya ``ruta`` es el libro CAPEX con que se costean las obras (070:RF-13).
_RUTA_ES_CAPEX = ('obras_escalera', 'optimizar_con_proyecto')


def _ruta_de_la_etapa(e: Etapa, datos: Mapping[str, Any]) -> Any:
    """El fichero de cada etapa: el libro de cargas, el CAPEX de las obras o, en las demás, los libros de demanda.

    La de las obras era la carpeta de los libros de demanda que añade la lista (070:RF-6), y la escalera la mandaba
    como su libro CAPEX (072:RF-33): ahora va el CAPEX que nombra la orden y, sin él, ninguno, como desde la web.
    """
    if e.tarea == 'cargas_nuevas':
        return datos.get('ruta_cargas')
    if e.tarea in _RUTA_ES_CAPEX:
        return datos.get('capex')
    return datos.get('ruta')


def _datos_tras(etapa: Etapa, datos: dict[str, Any], cliente: ClienteWeb) -> dict[str, Any]:
    """Lo que una etapa deja para las siguientes: tras el sistema, su proyecto y alimentadores."""
    if etapa.tarea != 'sistema_completo':
        return datos
    estado = cliente.pedir('GET', '') or {}
    grupo = f"SISTEMA_{str(datos['sistema']).upper()}"
    proyecto = (estado.get('pf_projects') or {}).get(grupo)
    if not proyecto:
        raise RuntimeError(f'tras el sistema {datos["sistema"]} no hay proyecto de DIgSILENT ({grupo})')
    sistema = (cliente.pedir('GET', f'/demanda/sistema?project={proyecto}') or {}).get('sistema') or {}
    return {**datos, 'proyecto': proyecto,
            'alimentadores': list(sistema.get('alimentadores') or datos.get('alimentadores') or [])}


def ejecutar_proyecto(datos: Mapping[str, Any], *, cliente: ClienteWeb, control: PuntoDeControl,
                      proceso: Callable[[str, Mapping[str, Any]], Any],
                      log: Callable[[str], None] = lambda _m: None,
                      etapas: tuple[Etapa, ...] = ETAPAS,
                      gobierno_etapa: Callable | None = None,
                      avance: Callable[[int,int,str],None] = lambda *_a:None) -> dict[str, Any]:
    """Las etapas que faltan, en orden, con su punto de control (RF-43, RF-44)."""
    datos = {**control.estado.get('datos', {}), **dict(datos)}
    # 070:RF-8: lo que no va a aparecer por el camino se dice antes de empezar: se cargaba la fuente y
    # la etapa siguiente moría por una opción obligatoria de ``sistema_web.py``.
    previos = sorted({k for e in etapas if not e.opcional and not e.condicion and not control.hecha(e.nombre)
                      for k in e.requiere if k not in LOS_DEJA_UNA_ETAPA and not datos.get(k)})
    if previos:
        raise ValueError(f'el proyecto necesita {", ".join(previos)} antes de empezar')
    for i, e in enumerate(etapas, 1):
        control.validar_identidad()
        avance(i-1,len(etapas),e.nombre)
        if control.hecha(e.nombre):
            log(f'Agente: etapa {i} de {len(etapas)}, {e.nombre}: ya hecha, no se repite (027:RF-44)')
            avance(i,len(etapas),e.nombre)
            continue
        if cliente.cancelado():
            return {'completo': False, 'cancelado': True, 'etapas': control.estado['etapas']}
        if e.condicion and (motivo := _motivo_para_omitir(e, cliente, datos, control)):
            log(f'Agente: etapa {e.nombre} omitida: {motivo}')
            control.marcar(e.nombre, 'omitida', {'motivo': motivo}, datos)
            avance(i,len(etapas),e.nombre)
            continue
        if e.nombre in REQUISITOS_MODULO and (motivo := falta_del_modulo(e.nombre, datos.get(e.nombre))):
            # 027:RF-72: un módulo sin su dato se salta con su motivo, nunca con un error, y se sigue con los demás.
            log(f'Agente: etapa {e.nombre} omitida: {motivo}')
            control.marcar(e.nombre, 'omitida', {'motivo': motivo}, datos)
            avance(i,len(etapas),e.nombre)
            continue
        faltan = [k for k in e.requiere if not datos.get(k)]
        if not faltan and e.tarea == 'obras' and not (cliente.pedir('GET', '/obras') or []):
            log('Agente: etapa obras omitida: no hay obras pendientes en el espacio')
            control.marcar(e.nombre, 'omitida', {'falta': ['obras pendientes']}, datos)
            avance(i,len(etapas),e.nombre)
            continue
        if faltan:
            if not e.opcional:
                raise ValueError(f'la etapa {e.nombre} necesita {", ".join(faltan)}')
            log(f'Agente: etapa {e.nombre} omitida: falta {", ".join(faltan)}')
            control.marcar(e.nombre, 'omitida', {'falta': faltan}, datos)
            avance(i,len(etapas),e.nombre)
            continue
        log(f'Agente: etapa {i} de {len(etapas)}, {e.nombre}…')
        datos_tarea = {**datos, 'ruta': _ruta_de_la_etapa(e, datos)}
        extras = _extras_de_etapa(e, datos)
        gobierno = gobierno_etapa(e.tarea, datos_tarea, extras) if gobierno_etapa is not None else None
        cliente.gobierno = gobierno
        if e.proceso:
            resultado = (gobierno.ejecutar_proceso(lambda: proceso(e.tarea, datos_tarea),
                                                  cancelado=cliente.cancelado) if gobierno is not None
                         else proceso(e.tarea, datos_tarea))
            if isinstance(resultado,dict) and resultado.get('codigo',0)!=0:
                raise RuntimeError(f'la etapa {e.nombre} terminó con código {resultado["codigo"]}; no se marca hecha')
        else:
            resultado = ejecutar(pasos(e.tarea, datos_tarea, extras), cliente, log)
        if e.tarea == 'verificar_convergencia':
            final = resultado.get('resultado') if isinstance(resultado, Mapping) else None
            if isinstance(final, Mapping) and final.get('returncode', 0) != 0:
                # 070:RF-50: nada se conecta sobre una red que no converge: se dice y se para.
                raise RuntimeError(f"{datos.get('proyecto')} no converge en el diagnóstico (informe {final.get('report')}): "
                                   'corrija la causa antes de evaluar la carga')
        datos = _datos_tras(e, datos, cliente)
        control.marcar(e.nombre, 'hecha', _resumen(resultado if not isinstance(resultado, dict)
                                                     else resultado.get('resultado', resultado)), datos)
        avance(i,len(etapas),e.nombre)
    return {'completo': True, 'etapas': control.estado['etapas'], 'datos': datos}
