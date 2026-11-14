"""Las entradas que les faltan a los estudios de «4.2 Estudios», leídas de lo que sube el operador
(spec 012, RF-73 a RF-86).

Usuario, 2026-11-13: «haz disponibles todos» los estudios; «lo que falta se ingresará en TXT o
en imagen (JPG o similares)» y «todo tiene que ser cargado desde la web». Una sonda de ese día en
CA101_CHN102 mostró por qué no se ofrecían: la red externa con los valores por defecto de
DIgSILENT (``snss`` = 10 000 MVA, ``rntxn`` = 0,1, ``snssmin`` = 8 000), ninguna característica de
tiempo en sus 204 cargas, ninguna tasa de falla en líneas ni tipos y ningún espectro armónico.
Ninguna fuente (TXT, MDB, VNR-GIS) trae esos datos, y rellenarlos con valores típicos daría
corrientes de falla iguales en toda la red o un SAIDI de cero que nadie dio (constitución P13).

Así que cada dato lo da la empresa: el operador suelta un TXT, un CSV, un PDF o una imagen, el
texto se lee (OCR si es imagen o PDF escaneado), se convierte aquí en filas con las columnas de su
esquema, el operador las confirma o corrige en una tabla de la web y solo entonces se guardan. Este
módulo no sabe de la web ni de DIgSILENT: lee texto, valida filas y dice lo que falta, sin
completar nada por su cuenta.

Una tabla de texto se reconoce sola: separada por tabuladores, «;», «|», «,» o, la que sale del
OCR, por dos o más espacios. La primera fila con nombres de columna conocidos es la cabecera; las
columnas se buscan por sus nombres (sin tildes ni mayúsculas), y una que no se reconoce se nombra
en los avisos en vez de leerse con otro sentido.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .studies import ESTUDIOS


class EntradasError(ValueError):
    """Entrada que no se puede usar; ``errores`` dice cada fila y columna."""

    def __init__(self, errores: list[str]):
        self.errores = list(errores)
        super().__init__('Los datos no se pueden usar:\n' + '\n'.join(self.errores))


@dataclass(frozen=True)
class Campo:
    """Una columna del esquema de una entrada."""

    clave: str
    titulo: str
    unidad: str = '-'
    alias: tuple[str, ...] = ()
    obligatoria: bool = False
    numero: bool = True


@dataclass(frozen=True)
class Esquema:
    """Qué se carga para una entrada del catálogo de ``studies.py`` y cómo se escribe."""

    clave: str
    nombre: str
    """El ``Entrada.nombre`` de ``studies.py``: la misma frase que el catálogo dice que falta."""
    titulo: str
    campos: tuple[Campo, ...]
    ayuda: str


def _c(clave, titulo, unidad='-', *alias, obligatoria=False, numero=True) -> Campo:
    return Campo(clave, titulo, unidad, tuple(alias), obligatoria, numero)


#: Una entrada por dato que falta. El nombre es el de ``studies._entradas``: el catálogo la da por
#: cumplida cuando está guardada (RF-79). Las protecciones no están: las lee el lector de ajustes
#: de la hoja «Protecciones» (spec 049), no esta vía.
ESQUEMAS: dict[str, Esquema] = {e.clave: e for e in (
    Esquema('impedancia', 'Potencia e impedancia de cortocircuito de cada subestación de cabecera',
            'Potencia de cortocircuito por subestación de cabecera', (
                _c('barra', 'SET o barra de cabecera', '-', 'set', 'subestacion', 'barra', 'cabecera', 'nodo',
                   'red externa', 'xnet', obligatoria=True, numero=False),
                _c('tension_kv', 'Tensión', 'kV', 'tension', 'un', 'kv', 'tension nominal'),
                _c('scc_max_mva', 'Pcc máxima', 'MVA', 'pcc max', 'scc max', 'skss max', 'mva max', 'pcc maxima',
                   'potencia de cortocircuito maxima', 'sk max', 'pcc'),
                _c('rx_max', 'R/X máxima', '-', 'r/x max', 'rx max', 'r/x', 'rx', 'r/x maxima'),
                _c('scc_min_mva', 'Pcc mínima', 'MVA', 'pcc min', 'scc min', 'skss min', 'mva min', 'pcc minima',
                   'sk min'),
                _c('rx_min', 'R/X mínima', '-', 'r/x min', 'rx min', 'r/x minima'),
                _c('ik_max_ka', 'Ik" máxima', 'kA', 'ik max', 'ikss max', "ik'' max", 'icc max', 'ik"max'),
                _c('ik_min_ka', 'Ik" mínima', 'kA', 'ik min', 'ikss min', "ik'' min", 'icc min', 'ik"min'),
                _c('x0x1', 'X0/X1', '-', 'x0/x1', 'x0x1'),
                _c('r0x0', 'R0/X0', '-', 'r0/x0', 'r0x0'),
                _c('fuente', 'Fuente', '-', 'origen', 'documento', numero=False),
            ), 'Una fila por SET o barra de cabecera, con la Pcc en MVA (o la Ik" en kA con la tensión) y la '
               'R/X, máximas y, si se tienen, mínimas. Sale del estudio de cortocircuito del sistema de '
               'transmisión o del COES.'),
    Esquema('perfiles', 'Perfiles de carga horarios o curvas típicas por tipo de cliente',
            'Perfiles de carga (horarios o de 15 minutos)', (
                _c('perfil', 'Perfil', '-', 'alimentador', 'tipo', 'tipo de cliente', 'curva', 'nombre',
                   'sector', numero=False),
                _c('instante', 'Instante', '-', 'hora', 'fecha', 'fecha hora', 'tiempo', 'h', 'periodo',
                   numero=False),
                _c('valor', 'Valor', 'p.u. o kW', 'p', 'potencia', 'demanda', 'kw', 'pu', 'p.u.'),
                _c('unidad', 'Unidad', '-', numero=False),
            ), 'Una serie por alimentador (su nombre) o por tipo de cliente (el tipo de carga del proyecto), '
               'cada hora o cada 15 minutos. Puede ir en columnas (instante y una columna por perfil) o en '
               'filas (perfil, instante, valor). La unidad, «p.u.» o «kW», va en su columna o en la cabecera '
               '(«Valor (kW)»).'),
    Esquema('tasas', 'Tasa de falla (λ) y tiempo de reparación por tipo de elemento',
            'Tasas de falla y tiempos de reparación', (
                _c('clase', 'Clase', '-', 'elemento', 'clase de elemento', obligatoria=True, numero=False),
                _c('tipo', 'Tipo del proyecto', '-', 'tipo', numero=False),
                _c('permanente', 'Falla permanente', '1/año (por km en líneas y cables)', 'lambda', 'λ',
                   'tasa de falla', 'falla permanente', 'tasa permanente', obligatoria=True),
                _c('transitoria', 'Falla transitoria', '1/año (por km en líneas y cables)', 'falla transitoria',
                   'tasa transitoria'),
                _c('reparacion', 'Tiempo de reparación', 'h', 'reparacion', 'mttr', 'tiempo de reparacion',
                   obligatoria=True),
            ), 'Una fila por clase de elemento (Línea aérea de media tensión, Cable subterráneo de media '
               'tensión, Transformador de distribución, Barra, Interruptor, Reconectador, Fusible, '
               'Seccionador), del histórico de interrupciones de la empresa.'),
    Esquema('maniobra', 'Tiempo de maniobra y de localización de falla', 'Tiempos de maniobra y localización', (
                _c('concepto', 'Concepto', '-', obligatoria=True, numero=False),
                _c('valor', 'Valor', 'min', 'minutos', 'tiempo', obligatoria=True),
            ), 'Tres filas: «Localización de la falla», «Maniobra manual» y, si hay equipos telemandados, '
               '«Maniobra telemandada», en minutos.'),
    Esquema('precios', 'Precios unitarios de conductor, estructura, SED y equipos de maniobra',
            'Precios unitarios', (
                _c('elemento', 'Elemento', '-', 'concepto', 'partida', 'descripcion', obligatoria=True,
                   numero=False),
                _c('unidad', 'Unidad', '-', 'und', 'unidad de medida', obligatoria=True, numero=False),
                _c('precio', 'Precio unitario', 'moneda', 'precio', 'costo', 'coste', 'precio unitario',
                   obligatoria=True),
                _c('moneda', 'Moneda', '-', obligatoria=True, numero=False),
            ), 'Una fila por partida (conductor por sección, estructura, SED por potencia, equipo de '
               'maniobra), con su unidad («km», «und») y la moneda de la empresa.'),
    Esquema('coste_energia', 'Coste de la energía (moneda/kWh) y tasa de actualización',
            'Coste de la energía y tasa de actualización', (
                _c('concepto', 'Concepto', '-', obligatoria=True, numero=False),
                _c('valor', 'Valor', '-', obligatoria=True),
                _c('unidad', 'Unidad', '-', obligatoria=True, numero=False),
            ), 'Dos filas: «Energía de pérdidas» con «<moneda>/kWh» y «Tasa de descuento» en «%».'),
    Esquema('etapas', 'Alternativas de inversión con sus etapas por año', 'Alternativas por etapa', (
                _c('alternativa', 'Alternativa', '-', 'opcion', 'estrategia', obligatoria=True, numero=False),
                _c('anio', 'Año', '-', 'ano', 'etapa', 'year', obligatoria=True),
                _c('obra', 'Obra', '-', 'proyecto', 'descripcion', 'partida', obligatoria=True, numero=False),
                _c('inversion', 'Inversión', 'moneda', 'monto', 'costo', 'coste', obligatoria=True),
                _c('moneda', 'Moneda', '-', obligatoria=True, numero=False),
            ), 'Una fila por obra de cada alternativa, con el año en que entra y su inversión.'),
    Esquema('proyeccion', 'Proyección de demanda por SED y por alimentador', 'Proyección de la demanda', (
                _c('elemento', 'Alimentador o SED', '-', 'alimentador', 'sed', 'nombre', obligatoria=True,
                   numero=False),
                _c('anio', 'Año', '-', 'ano', 'year', obligatoria=True),
                _c('demanda_kw', 'Demanda', 'kW', 'demanda', 'kw', 'potencia', 'p', obligatoria=True),
            ), 'Una fila por alimentador o SED y año, con la demanda máxima en kW.'),
    Esquema('espectros', 'Espectros armónicos de las cargas no lineales', 'Espectros armónicos', (
                _c('tipo_carga', 'Tipo de carga', '-', 'tipo', 'carga', 'espectro', obligatoria=True,
                   numero=False),
                _c('orden', 'Orden armónico', '-', 'h', 'armonico', 'orden', 'n', obligatoria=True),
                _c('magnitud_pct', 'Magnitud', '% de la fundamental', 'magnitud', '%', 'ih', 'i%',
                   obligatoria=True),
                _c('angulo_grados', 'Ángulo', 'grados', 'angulo', 'fase', 'deg'),
            ), 'Una fila por tipo de carga y orden armónico, con la corriente en % de la fundamental, de '
               'las campañas de medición de calidad de producto.'),
)}

#: Estudios que el conversor ya ejecuta en DIgSILENT con lo cargado (RF-83, RF-84).
CON_GUION = ('cortocircuito', 'cuasi_dinamica')
#: Pasos admitidos de un perfil, en minutos: horario, media hora o 15 minutos (RF-76).
PASOS_PERFIL_MIN = (15, 30, 60)
#: Unidades que se comprueban en la cabecera («Pcc (kVA)» no se lee como MVA).
UNIDADES_FISICAS = ('MVA', 'kV', 'kA', 'h', 'min', 'kW', 'grados')
UNIDADES_PERFIL = {'pu': 'pu', 'p.u.': 'pu', 'p.u': 'pu', 'kw': 'kW'}


def _norm(texto: Any) -> str:
    """Sin tildes, mayúsculas ni espacios de más: «R/X Máxima» = «r/x maxima»."""
    s = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode()
    return ' '.join(s.lower().replace('_', ' ').split())


def _sin_unidad(titulo: str) -> tuple[str, str]:
    """«Pcc máx (MVA)» → («pcc max», «mva»): la unidad entre paréntesis o corchetes se aparta."""
    m = re.match(r'^(.*?)[\s]*[\(\[]([^\)\]]*)[\)\]]\s*$', str(titulo or ''))
    if m:
        return _norm(m.group(1)).rstrip('.'), _norm(m.group(2))
    return _norm(titulo).rstrip('.'), ''


def _abreviar(t: str) -> str:
    """«máxima», «máx.», «max» se escriben igual para buscar la columna."""
    return re.sub(r'\b(maxima|maximo|max\.?)\b', 'max', re.sub(r'\b(minima|minimo|min\.?)\b', 'min', t))


def numero(texto: Any) -> float | None:
    """Un número escrito como lo escribe una empresa o como lo lee el OCR: «1.234,5», «1,5», «12 %».

    Sin adivinar el separador cuando es ambiguo: «1.234» con un solo punto y tres decimales se lee
    como 1,234 (el punto decimal del TXT de CYMDIST), y «1,234» como 1,234 también; los miles solo
    se reconocen cuando hay los dos separadores («1.234,5» o «1,234.5»).
    """
    if isinstance(texto, bool) or texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto) if math.isfinite(float(texto)) else None
    s = str(texto).strip().replace('−', '-').replace(' ', '').replace('%', '')
    if not s:
        return None
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        if s.count(',') > 1:
            return None
        s = s.replace(',', '.')
    try:
        x = float(s)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


# --------------------------------------------------------------------------- texto
def texto_de(ruta: Path | str) -> tuple[str, str, list[str]]:
    """(texto, método, avisos) de un TXT, CSV, PDF o imagen (RF-73, RF-74), con
    :func:`documentos_solicitud.texto_de_fichero`. Lo leído por OCR se revisa siempre: lo dice.
    """
    from .documentos_solicitud import texto_de_fichero

    texto, metodo, avisos = texto_de_fichero(Path(ruta))
    avisos = list(avisos)
    if metodo == 'ocr' and texto.strip() and not avisos:
        avisos.append(f'{Path(ruta).name}: leído por OCR; revise cada valor antes de guardar.')
    return texto, metodo, avisos


def _partir(linea: str, sep: str | None) -> list[str]:
    if sep is None:
        return [x.strip() for x in re.split(r'\s{2,}|\t', linea.strip()) if x.strip()]
    return [x.strip() for x in linea.split(sep)]


def leer_tabla(texto: str) -> tuple[list[str], list[list[str]], str | None]:
    """Las celdas de una tabla de texto: (líneas útiles partidas, separador elegido).

    El separador es el que parte en el mismo número de celdas (más de una) la mayoría de las
    líneas: «,» solo gana si da más columnas que «;» o el tabulador, porque en español la coma es el
    separador decimal. Una tabla del OCR no trae separador: se parte por dos o más espacios.
    """
    lineas = [ln for ln in (texto or '').splitlines()
              if ln.strip() and not ln.lstrip().startswith('#') and not set(ln.strip()) <= set('-=_|+ ')]
    mejor, puntos = None, (0, 0)
    for sep in ('\t', ';', '|', ','):
        cuentas = [len(_partir(ln, sep)) for ln in lineas if sep in ln]
        if not cuentas:
            continue
        moda = max(set(cuentas), key=cuentas.count)
        # La coma decimal de «22,9   7,5» no es un separador: el de verdad parte casi todas las líneas.
        if moda < 2 or cuentas.count(moda) < 0.6 * len(lineas):
            continue
        p = (cuentas.count(moda), moda)
        if p > puntos:
            mejor, puntos = sep, p
    filas = [_partir(ln, mejor) for ln in lineas]
    if mejor is None and filas:
        cuentas = [len(f) for f in filas]
        if max(set(cuentas), key=cuentas.count) < 2:
            # El OCR sin «preserve_interword_spaces» deja un solo espacio entre columnas.
            filas = [ln.split() for ln in lineas]
        # Las rayas de la tabla fotografiada salen como «=», «|» o «_» sueltos entre columnas
        # (OCR de una tabla de Pcc, 2026-11-13: «BARRA2 320 = 0.25»): no son celdas. El «-» sí
        # se queda: es la celda vacía que escribe quien rellena la tabla.
        filas = [[c for c in f if not re.fullmatch(r'[=|_~¦]+', c)] for f in filas]
    if mejor == '|':
        filas = [f[1:] if f and f[0] == '' else f for f in filas]
        filas = [f[:-1] if f and f[-1] == '' else f for f in filas]
    return lineas, filas, mejor


def _unidad_comentada(texto: str) -> str | None:
    """«# unidad: kW» en el TXT: la unidad declarada de toda la tabla."""
    m = re.search(r'^\s*#\s*unidad\s*[:=]\s*(\S+)', texto or '', re.I | re.M)
    return m.group(1) if m else None


@dataclass
class Lectura:
    """Lo leído de un fichero, para la tabla editable de la web (RF-75)."""

    clave: str
    filas: list[dict[str, Any]] = field(default_factory=list)
    columnas: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    faltan: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    metodo: str = 'texto'
    fichero: str = ''

    def a_dict(self) -> dict[str, Any]:
        return {'clave': self.clave, 'filas': self.filas, 'columnas': self.columnas, 'errores': self.errores,
                'faltan': self.faltan, 'avisos': self.avisos, 'metodo': self.metodo, 'fichero': self.fichero}


def _campo_de(titulo: str, esquema: Esquema) -> tuple[Campo | None, str]:
    nombre, unidad = _sin_unidad(titulo)
    nombre = _abreviar(nombre)
    for campo in esquema.campos:
        candidatos = {_abreviar(_norm(x)) for x in (campo.clave, campo.titulo, *campo.alias)}
        if nombre in candidatos:
            return campo, unidad
    return None, unidad


def _cabecera(filas: list[list[str]], esquema: Esquema) -> int | None:
    """La primera fila con al menos un campo obligatorio (o dos cualesquiera) reconocidos."""
    obligatorios = {c.clave for c in esquema.campos if c.obligatoria}
    for i, fila in enumerate(filas[:20]):
        campos = [c for c in (_campo_de(t, esquema)[0] for t in fila) if c is not None]
        claves = {c.clave for c in campos}
        if (obligatorios and claves & obligatorios and len(claves) >= 2) or (not obligatorios and len(claves) >= 2):
            return i
    return None


def leer_entrada(clave: str, texto: str, *, fichero: str = '', metodo: str = 'texto',
                 avisos: Iterable[str] = ()) -> Lectura:
    """Del texto de un fichero a las filas de la entrada ``clave``, validadas (RF-74, RF-75, RF-78).

    Nunca completa una celda: una columna obligatoria que no está queda vacía y dicha en
    ``errores``, y lo que la entrada necesita y no trae, en ``faltan``.
    """
    esquema = ESQUEMAS.get(clave)
    if esquema is None:
        raise EntradasError([f'«{clave}» no es una entrada de los estudios; las que hay son '
                             + ', '.join(ESQUEMAS) + '.'])
    lec = Lectura(clave, metodo=metodo, fichero=fichero, avisos=list(avisos),
                  columnas=[c.clave for c in esquema.campos])
    _lineas, filas, _sep = leer_tabla(texto)
    if not filas:
        lec.errores.append(f'{fichero or "El fichero"}: no tiene ninguna tabla que leer.')
        lec.faltan = faltan(clave, [])
        return lec
    i = _cabecera(filas, esquema)
    if clave == 'perfiles' and i is None:
        i = _cabecera_ancha(filas)
    if i is None:
        lec.errores.append(f'{fichero or "El fichero"}: ninguna fila tiene los nombres de columna de '
                           f'«{esquema.titulo}» (' + ', '.join(c.titulo for c in esquema.campos) + ').')
        lec.faltan = faltan(clave, [])
        return lec
    if clave == 'perfiles':
        lec.filas = _filas_perfiles(filas[i], filas[i + 1:], esquema, lec, _unidad_comentada(texto))
    else:
        posicion, unidades = {}, {}
        for k, titulo in enumerate(filas[i]):
            campo, unidad = _campo_de(titulo, esquema)
            if campo is None:
                lec.avisos.append(f'La columna «{titulo}» no es de «{esquema.titulo}»: no se lee.')
            elif campo.clave in posicion:
                lec.avisos.append(f'La columna «{titulo}» repite «{campo.titulo}»: se lee solo la primera.')
            else:
                posicion[campo.clave], unidades[campo.clave] = k, unidad
        for campo in esquema.campos:
            u = unidades.get(campo.clave)
            # Solo las unidades físicas: una «moneda» entre paréntesis es «S/», «USD»…, la de la empresa.
            if u and campo.unidad in UNIDADES_FISICAS and _norm(campo.unidad) not in u.replace('.', ''):
                lec.errores.append(f'La columna «{campo.titulo}» viene en «{u}» y se pide «{campo.unidad}»; '
                                   'no se convierte sola.')
        for fila in filas[i + 1:]:
            d = {c.clave: (fila[posicion[c.clave]] if c.clave in posicion and posicion[c.clave] < len(fila)
                           else None) for c in esquema.campos}
            lec.filas.append({k: (v if v not in ('', '-') else None) for k, v in d.items()})
    _registro, errores, falta = validar(clave, lec.filas)
    lec.errores += errores
    lec.faltan = falta
    return lec


def _cabecera_ancha(filas: list[list[str]]) -> int | None:
    """Perfiles en columnas: una cabecera cuya primera celda es el instante y las demás, nombres."""
    for i, fila in enumerate(filas[:20]):
        if len(fila) >= 2 and _sin_unidad(fila[0])[0] in ('hora', 'instante', 'fecha', 'fecha hora', 'tiempo', 'h',
                                                         'periodo') \
                and all(numero(x) is None for x in fila[1:]):
            return i
    return None


def _filas_perfiles(cab: list[str], datos: list[list[str]], esquema: Esquema, lec: Lectura,
                    unidad_tabla: str | None) -> list[dict[str, Any]]:
    """Las filas largas (perfil, instante, valor, unidad), vengan en filas o en columnas."""
    campos = [_campo_de(t, esquema) for t in cab]
    claves = [c.clave if c else None for c, _u in campos]
    if 'perfil' in claves and 'valor' in claves:
        pos = {k: claves.index(k) for k in ('perfil', 'instante', 'valor', 'unidad') if k in claves}
        u_cab = campos[pos['valor']][1] or unidad_tabla
        if not u_cab and _sin_unidad(cab[pos['valor']])[0] in ('kw', 'pu', 'p.u'):
            u_cab = _sin_unidad(cab[pos['valor']])[0]     # la columna se llama «kW» o «p.u.»
        out = []
        for f in datos:
            g = lambda k: f[pos[k]] if k in pos and pos[k] < len(f) else None  # noqa: E731
            out.append({'perfil': g('perfil'), 'instante': g('instante'), 'valor': g('valor'),
                        'unidad': g('unidad') or u_cab})
        return out
    # En columnas: la primera es el instante; cada una de las demás, un perfil con su unidad.
    out = []
    nombres = [_sin_unidad(t) for t in cab[1:]]
    for f in datos:
        for k, (nombre_norm, u) in enumerate(nombres, start=1):
            titulo = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]\s*$', '', cab[k]).strip()
            out.append({'perfil': titulo, 'instante': f[0] if f else None,
                        'valor': f[k] if k < len(f) else None, 'unidad': u or unidad_tabla})
    return out


# --------------------------------------------------------------------------- validación
def _minutos(instante: Any) -> float | None:
    """Minutos de un instante: «13» (hora), «13:15», «2026-07-01 13:15» (desde el año 1)."""
    if instante is None:
        return None
    s = str(instante).strip()
    m = re.fullmatch(r'(\d{1,2}):(\d{2})(?::\d{2})?', s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    for formato in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M', '%d/%m/%Y %H:%M:%S',
                    '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S'):
        try:
            t = datetime.strptime(s, formato)
            return (t - datetime(2000, 1, 1)).total_seconds() / 60.0
        except ValueError:
            continue
    x = numero(s)
    if x is not None and x == int(x) and 0 <= x <= 8784:
        return x * 60.0
    return None


def validar(clave: str, filas: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], list[str], list[str]]:
    """(registro, errores, faltan) de las filas de una entrada (RF-75, RF-78).

    ``registro`` es lo que usan el catálogo y los guiones; ``errores``, cada celda que no vale con
    su fila; ``faltan``, lo que la entrada necesita y no trae. Las filas son las de la tabla
    editable: lo que el operador ve es lo que se valida, celda por celda.
    """
    filas = [dict(f) for f in filas if any(v not in (None, '') for v in dict(f).values())]
    esquema = ESQUEMAS[clave]
    errores: list[str] = []
    limpias = []
    for n, f in enumerate(filas, start=1):
        d = {}
        for campo in esquema.campos:
            v = f.get(campo.clave)
            v = v.strip() if isinstance(v, str) else v
            if v in (None, ''):
                if campo.obligatoria:
                    errores.append(f'Fila {n}, «{campo.titulo}»: está vacía y es obligatoria.')
                d[campo.clave] = None
                continue
            if campo.numero and clave != 'perfiles':
                x = numero(v)
                if x is None:
                    errores.append(f'Fila {n}, «{campo.titulo}»: «{v}» no es un número.')
                elif x < 0 and campo.clave not in ('angulo_grados',):
                    errores.append(f'Fila {n}, «{campo.titulo}»: {x:g} es negativo.')
                    x = None
                d[campo.clave] = x
            else:
                d[campo.clave] = v
        limpias.append((n, d))
    registro = _REGISTROS[clave](limpias, errores)
    return registro, errores, faltan(clave, limpias, registro)


def _registro_impedancia(filas, errores) -> dict[str, Any]:
    barras: dict[str, dict[str, Any]] = {}
    for n, d in filas:
        if not d.get('barra'):
            continue
        scc = d.get('scc_max_mva')
        if scc is None and d.get('ik_max_ka') is not None and d.get('tension_kv'):
            # Pcc = √3 · U · Ik": una conversión de unidades, no un valor supuesto.
            scc = math.sqrt(3) * d['tension_kv'] * d['ik_max_ka']
        scc_min = d.get('scc_min_mva')
        if scc_min is None and d.get('ik_min_ka') is not None and d.get('tension_kv'):
            scc_min = math.sqrt(3) * d['tension_kv'] * d['ik_min_ka']
        if scc is None:
            errores.append(f'Fila {n}, {d["barra"]}: falta la Pcc máxima (en MVA, o la Ik" máxima con la tensión).')
            continue
        if d.get('rx_max') is None:
            errores.append(f'Fila {n}, {d["barra"]}: falta la R/X máxima.')
            continue
        if scc <= 0:
            errores.append(f'Fila {n}, {d["barra"]}: la Pcc máxima tiene que ser mayor que cero.')
            continue
        if scc_min is not None and scc_min > scc:
            errores.append(f'Fila {n}, {d["barra"]}: la Pcc mínima ({scc_min:g} MVA) supera a la máxima ({scc:g} MVA).')
            continue
        clave = _norm(d['barra'])
        if clave in barras:
            errores.append(f'Fila {n}: {d["barra"]} ya tiene otra fila.')
            continue
        barras[clave] = {'barra': d['barra'], 'tension_kv': d.get('tension_kv'), 'scc_max_mva': round(scc, 6),
                         'rx_max': d['rx_max'], 'scc_min_mva': None if scc_min is None else round(scc_min, 6),
                         'rx_min': d.get('rx_min'), 'x0x1': d.get('x0x1'), 'r0x0': d.get('r0x0'),
                         'fuente': d.get('fuente') or '', 'fila': n}
    return {'barras': barras}


def _registro_perfiles(filas, errores) -> dict[str, Any]:
    series: dict[str, list[tuple[float, float]]] = {}
    unidades: dict[str, set[str]] = {}
    nombres: dict[str, str] = {}
    for n, d in filas:
        perfil = d.get('perfil')
        if not perfil:
            errores.append(f'Fila {n}: falta el perfil (alimentador o tipo de cliente).')
            continue
        t = _minutos(d.get('instante'))
        if t is None:
            errores.append(f'Fila {n}, {perfil}: «{d.get("instante")}» no es un instante (hora, «HH:MM» o fecha y hora).')
            continue
        x = numero(d.get('valor'))
        if x is None or x < 0:
            errores.append(f'Fila {n}, {perfil}: «{d.get("valor")}» no es un valor de potencia (≥ 0).')
            continue
        u = UNIDADES_PERFIL.get(_norm(d.get('unidad')).replace(' ', ''))
        if u is None:
            errores.append(f'Fila {n}, {perfil}: falta la unidad («p.u.» o «kW»), o «{d.get("unidad")}» no es una de '
                           'ellas; no se supone.')
            continue
        k = _norm(perfil)
        nombres.setdefault(k, str(perfil).strip())
        series.setdefault(k, []).append((t, x))
        unidades.setdefault(k, set()).add(u)
    perfiles = {}
    for k, puntos in series.items():
        nombre = nombres[k]
        if len(unidades[k]) > 1:
            errores.append(f'{nombre}: mezcla p.u. y kW en la misma serie.')
            continue
        puntos.sort()
        instantes = [t for t, _ in puntos]
        if len(set(instantes)) != len(instantes):
            errores.append(f'{nombre}: tiene instantes repetidos.')
            continue
        if len(puntos) < 2:
            errores.append(f'{nombre}: una serie necesita al menos dos instantes.')
            continue
        pasos = {round(b - a, 6) for a, b in zip(instantes, instantes[1:])}
        if len(pasos) != 1 or next(iter(pasos)) not in PASOS_PERFIL_MIN:
            errores.append(f'{nombre}: el paso entre instantes tiene que ser uno solo de '
                           + ', '.join(f'{p} min' for p in PASOS_PERFIL_MIN)
                           + f'; trae {", ".join(f"{p:g} min" for p in sorted(pasos))}.')
            continue
        paso = int(next(iter(pasos)))
        valores = [v for _, v in puntos]
        maximo = max(valores)
        if maximo <= 0:
            errores.append(f'{nombre}: todos los valores son cero.')
            continue
        unidad = next(iter(unidades[k]))
        perfiles[k] = {'perfil': nombre, 'paso_min': paso, 'unidad': unidad, 'valores': valores,
                       # La característica de DIgSILENT multiplica la potencia de la carga: la serie
                       # en p.u. de su propio máximo deja la punta igual a la calibrada.
                       'pu': [round(v / maximo, 6) for v in valores], 'maximo': maximo,
                       'horas': len(valores) * paso / 60.0}
    return {'perfiles': perfiles}


def _registro_libro(hoja: str):
    """Tasas, tiempos y costes con las mismas reglas del libro de la empresa (012:RF-8 a RF-16)."""
    def registro(filas, errores) -> dict[str, Any]:
        from . import datos_empresa as de

        libro = de.Libro(nombre='entradas')
        propios: list[str] = []
        {'tasas': de._tasas, 'tiempos': de._tiempos, 'costes': de._costes}[hoja](filas, libro, propios)
        # Los mensajes del libro nombran su hoja; aquí no hay hoja, hay filas de la tabla.
        errores += [re.sub(r'^Hoja «[^»]*»,?\s*', '', e).replace('fila ', 'Fila ', 1) for e in propios]
        d = libro.a_dict()
        return {k: d[k] for k in {'tasas': ('tasas', 'tasas_por_tipo'), 'tiempos': ('tiempos_min',),
                                  'costes': ('coste_energia_kwh', 'moneda', 'tasa_descuento')}[hoja]}
    return registro


def _registro_precios(filas, errores) -> dict[str, Any]:
    precios, monedas = [], set()
    for n, d in filas:
        if None in (d.get('elemento'), d.get('unidad'), d.get('precio'), d.get('moneda')):
            continue
        precios.append({'elemento': d['elemento'], 'unidad': d['unidad'], 'precio': d['precio'],
                        'moneda': d['moneda'], 'fila': n})
        monedas.add(_norm(d['moneda']))
    if len(monedas) > 1:
        errores.append('Los precios vienen en más de una moneda (' + ', '.join(sorted(monedas)) + '); van en una.')
    return {'precios': precios}


def _registro_etapas(filas, errores) -> dict[str, Any]:
    alternativas: dict[str, list[dict[str, Any]]] = {}
    for n, d in filas:
        if None in (d.get('alternativa'), d.get('anio'), d.get('obra'), d.get('inversion'), d.get('moneda')):
            continue
        if d['anio'] != int(d['anio']) or not 1900 <= d['anio'] <= 2200:
            errores.append(f'Fila {n}, «Año»: {d["anio"]:g} no es un año.')
            continue
        alternativas.setdefault(str(d['alternativa']), []).append(
            {'anio': int(d['anio']), 'obra': d['obra'], 'inversion': d['inversion'], 'moneda': d['moneda'], 'fila': n})
    return {'alternativas': {k: sorted(v, key=lambda x: (x['anio'], x['fila'])) for k, v in sorted(alternativas.items())}}


def _registro_proyeccion(filas, errores) -> dict[str, Any]:
    series: dict[str, dict[int, float]] = {}
    for n, d in filas:
        if None in (d.get('elemento'), d.get('anio'), d.get('demanda_kw')):
            continue
        if d['anio'] != int(d['anio']) or not 1900 <= d['anio'] <= 2200:
            errores.append(f'Fila {n}, «Año»: {d["anio"]:g} no es un año.')
            continue
        s = series.setdefault(str(d['elemento']), {})
        if int(d['anio']) in s:
            errores.append(f'Fila {n}: {d["elemento"]} ya tiene el año {int(d["anio"])}.')
            continue
        s[int(d['anio'])] = d['demanda_kw']
    return {'proyeccion': {k: {str(a): v for a, v in sorted(s.items())} for k, s in sorted(series.items())}}


def _registro_espectros(filas, errores) -> dict[str, Any]:
    espectros: dict[str, dict[str, dict[str, float | None]]] = {}
    for n, d in filas:
        if None in (d.get('tipo_carga'), d.get('orden'), d.get('magnitud_pct')):
            continue
        if d['orden'] != int(d['orden']) or d['orden'] < 1:
            errores.append(f'Fila {n}, «Orden armónico»: {d["orden"]:g} no es un orden entero ≥ 1.')
            continue
        e = espectros.setdefault(str(d['tipo_carga']), {})
        if str(int(d['orden'])) in e:
            errores.append(f'Fila {n}: {d["tipo_carga"]} ya tiene el orden {int(d["orden"])}.')
            continue
        e[str(int(d['orden']))] = {'magnitud_pct': d['magnitud_pct'], 'angulo_grados': d.get('angulo_grados')}
    return {'espectros': espectros}


_REGISTROS = {
    'impedancia': _registro_impedancia, 'perfiles': _registro_perfiles, 'tasas': _registro_libro('tasas'),
    'maniobra': _registro_libro('tiempos'), 'coste_energia': _registro_libro('costes'),
    'precios': _registro_precios, 'etapas': _registro_etapas, 'proyeccion': _registro_proyeccion,
    'espectros': _registro_espectros,
}


def faltan(clave: str, filas, registro: Mapping[str, Any] | None = None) -> list[str]:
    """Lo que la entrada necesita y no trae (RF-78): vacío cuando está completa."""
    r = registro or {}
    vacio = {'impedancia': 'ninguna SET o barra de cabecera con su Pcc y su R/X',
             'perfiles': 'ninguna serie completa con su unidad',
             'tasas': 'ninguna clase de elemento con su tasa y su tiempo de reparación',
             'maniobra': 'los tiempos de localización de la falla y de maniobra manual',
             'precios': 'ningún precio unitario con su unidad y su moneda',
             'coste_energia': 'el coste de la energía de pérdidas y la tasa de descuento',
             'etapas': 'ninguna alternativa con sus obras por año',
             'proyeccion': 'ningún alimentador o SED con su demanda por año',
             'espectros': 'ningún tipo de carga con su espectro'}[clave]
    datos = {'impedancia': r.get('barras'), 'perfiles': r.get('perfiles'), 'tasas': r.get('tasas'),
             'precios': r.get('precios'), 'etapas': r.get('alternativas'), 'proyeccion': r.get('proyeccion'),
             'espectros': r.get('espectros')}
    if clave == 'maniobra':
        t = r.get('tiempos_min') or {}
        out = [f'«{x}»' for k, x in (('localizacion', 'Localización de la falla'), ('manual', 'Maniobra manual'))
               if k not in t]
        return out
    if clave == 'coste_energia':
        out = []
        if r.get('coste_energia_kwh') is None:
            out.append('el coste de la «Energía de pérdidas»')
        if r.get('tasa_descuento') is None:
            out.append('la «Tasa de descuento»')
        return out
    if clave == 'impedancia' and r.get('barras'):
        sin_min = sorted(b['barra'] for b in r['barras'].values() if b.get('scc_min_mva') is None)
        # La mínima no bloquea el cortocircuito máximo; se dice porque el ajuste de protecciones la pide.
        return [f'la Pcc mínima de {", ".join(sin_min)} (solo para el cortocircuito mínimo)'] if sin_min else []
    if clave == 'etapas' and r.get('alternativas') and len(r['alternativas']) < 2:
        return ['una segunda alternativa: la comparación de alternativas necesita al menos dos']
    return [] if datos.get(clave) else [vacio]


#: ``faltan`` que no impiden dar la entrada por cumplida (la Pcc mínima, la segunda alternativa).
def _bloquea(clave: str, falta: list[str]) -> bool:
    if clave == 'impedancia':
        return any('mínima' not in f for f in falta)
    if clave == 'etapas':
        return any('segunda alternativa' not in f for f in falta)
    return bool(falta)


def guardable(clave: str, filas) -> dict[str, Any]:
    """Registro listo para guardar (RF-77); ``EntradasError`` si una celda no vale.

    Se guarda lo que el operador confirmó en la tabla: si una sola fila tiene un error no se
    guarda nada, porque una tabla a medias dejaría el estudio con unas SET reales y otras por
    defecto sin que nadie lo note.
    """
    registro, errores, falta = validar(clave, filas)
    if errores:
        raise EntradasError(errores)
    return {'clave': clave, 'nombre': ESQUEMAS[clave].nombre, 'registro': registro, 'faltan': falta,
            'completa': not _bloquea(clave, falta)}


def cumplidas(guardadas: Mapping[str, Mapping[str, Any]]) -> set[str]:
    """Los ``Entrada.nombre`` del catálogo que lo guardado cumple (RF-79)."""
    return {ESQUEMAS[k].nombre for k, g in (guardadas or {}).items()
            if k in ESQUEMAS and g.get('completa')}


def que_estudios_desbloquea(clave: str) -> list[str]:
    """Los estudios del catálogo que piden la entrada ``clave`` (para la web, RF-80)."""
    nombre = ESQUEMAS[clave].nombre
    return [e.clave for e in ESTUDIOS if any(x.nombre == nombre for x in e.entradas)]


def esquemas_publicos() -> list[dict[str, Any]]:
    """Lo que la web necesita de cada entrada: columnas, unidades, ayuda y estudios (RF-80)."""
    return [{'clave': e.clave, 'nombre': e.nombre, 'titulo': e.titulo, 'ayuda': e.ayuda,
             'columnas': [{'clave': c.clave, 'titulo': c.titulo, 'unidad': c.unidad,
                           'obligatoria': c.obligatoria, 'numero': c.numero} for c in e.campos],
             'estudios': que_estudios_desbloquea(e.clave)} for e in ESQUEMAS.values()]


def combinar_con_libro(libro, guardadas: Mapping[str, Mapping[str, Any]]):
    """El libro de la empresa con las tasas, tiempos y costes cargados por la web (RF-81).

    Lo cargado por la web es lo último que confirmó el operador y pisa lo del libro en lo que
    trae; lo que no trae, sigue del libro. Sin libro y sin nada cargado, ``None``, como hasta ahora.
    """
    from . import datos_empresa as de

    propias = {k: (guardadas or {}).get(k) for k in ('tasas', 'maniobra', 'coste_energia')}
    propias = {k: g for k, g in propias.items() if g and g.get('completa')}
    if not propias:
        return libro
    nuevo = de.Libro.desde_dict(libro.a_dict()) if libro is not None else de.Libro(
        nombre='entradas cargadas en la web', hojas_que_faltan=[h.titulo for h in de.HOJAS])
    hojas = {'tasas': de.POR_CLAVE['tasas'].titulo, 'maniobra': de.POR_CLAVE['tiempos'].titulo,
             'coste_energia': de.POR_CLAVE['costes'].titulo}
    for k, g in propias.items():
        r = g['registro']
        if k == 'tasas':
            nuevo.tasas.update({c: de.Tasa(**v) for c, v in (r.get('tasas') or {}).items()})
            nuevo.tasas_por_tipo.update({c: de.Tasa(**v) for c, v in (r.get('tasas_por_tipo') or {}).items()})
        elif k == 'maniobra':
            nuevo.tiempos_min.update({c: float(v) for c, v in (r.get('tiempos_min') or {}).items()})
        else:
            nuevo.coste_energia_kwh, nuevo.moneda = r.get('coste_energia_kwh'), r.get('moneda') or ''
            nuevo.tasa_descuento = r.get('tasa_descuento')
        nuevo.hojas_que_faltan = [h for h in nuevo.hojas_que_faltan if h != hojas[k]]
    return nuevo


# --------------------------------------------------------------------------- para los guiones
def impedancia_para(registro: Mapping[str, Any], nombres: Iterable[str]) -> dict[str, Any] | None:
    """Los datos de la primera de ``nombres`` (red externa, su barra, su SET) que está cargada."""
    barras = (registro or {}).get('barras') or {}
    for nombre in nombres:
        if nombre and _norm(nombre) in barras:
            return barras[_norm(nombre)]
    return None


def atributos_xnet(d: Mapping[str, Any]) -> dict[str, float]:
    """Los atributos de ``ElmXnet`` que se escriben (datascheme.db de PF 2024): solo los dados."""
    out = {'snss': d['scc_max_mva'], 'rntxn': d['rx_max']}
    for atributo, clave in (('snssmin', 'scc_min_mva'), ('rntxnmin', 'rx_min'), ('x0tx1', 'x0x1'),
                            ('r0tx0', 'r0x0')):
        if d.get(clave) is not None:
            out[atributo] = d[clave]
    return out


def perfil_para(registro: Mapping[str, Any], nombres: Iterable[str]) -> dict[str, Any] | None:
    """El perfil del alimentador o del tipo de carga, en ese orden de ``nombres``."""
    perfiles = (registro or {}).get('perfiles') or {}
    for nombre in nombres:
        if nombre and _norm(nombre) in perfiles:
            return perfiles[_norm(nombre)]
    return None
