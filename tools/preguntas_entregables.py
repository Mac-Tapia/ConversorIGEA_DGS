"""Preguntas de metodología y criterios por entregable: comprueba, reparte, exporta, importa y sortea (spec 076).

Subórdenes: `verificar` (fuentes, cifras, nombres y hechos), `exportar` (hoja de revisión en `output/`), `importar`
(marcas del operador), `informe` (por entregable), `generar` (preguntas estocásticas de la web) y `cobertura`.
Una fila, marcada o no, nunca es una orden confirmada del operador (068:RF-30). Sin DIgSILENT, sin GPU y sin datos
de la distribuidora.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
DOCS = RAIZ / 'docs' / 'asistente'
DATASET = DOCS / 'preguntas_entregables.jsonl'
HECHOS = DOCS / 'hechos_web.jsonl'
REGLAS = DOCS / 'reglas_operador_sin_codigo.jsonl'
HUECOS = DOCS / 'preguntas_entregables_huecos.json'
INFORME = DOCS / 'preguntas_entregables_informe.md'
HOJA = RAIZ / 'output' / 'preguntas_entregables_revision.xlsx'
#: Todas las líneas citadas son de esta revisión: el árbol se mueve y la cita no (076:RF-4).
REVISION = '10fd3e1d29822d326be088e38c5a90f438e76d5e'
SAL_REPARTO = '076-reparto'
FRACCION_SELLADO = 0.25
#: Campos del operador: revisar no cambia lo sellado (076:RF-9).
CAMPOS_REVISION = ('revisado_por_operador', 'revision', 'revisado_por_maestro')
#: 076:RF-28: quién marcó la hoja; el maestro hace el rol del revisor por orden del usuario (2026-11-03), y no es humano.
REVISORES = ('operador', 'maestro')

ENTREGABLES = ('informe_estudio', 'factibilidad_conexion', 'libro_excel_informe', 'planos_informe', 'formatos_pide',
               'planeamiento_pide', 'dgs_manifiesto', 'calibracion_alcance', 'estudios_resultados', 'transferencias',
               'escalera_obras', 'set_nueva', 'pronostico', 'catalogo_parametros', 'salidas_auxiliares')
TEMAS = ('flujo_conversor', 'arquitectura', 'estudios', 'tipos_de_informe', 'operacion_web')
ASPECTOS = ('metodologia', 'criterio', 'dato_entrada', 'limite', 'cuando_no_aplica',
            'que_hace', 'requisito', 'escribe_digsilent', 'entrega', 'formato', 'si_falta', 'cancelar', 'orden')
ESTADOS = ('cumplida', 'implementada', 'aprobada', 'solo_especificada')
TIPOS = ('con_respuesta', 'sin_respuesta')
#: Cómo escribe el operador: abreviaturas y muletillas, para medir que no todo está en registro formal.
FALTAS = re.compile(r'\b(q|xq|pq|porfa|nomas|pe|ps|oe|oye|ahorita|tb|tmb|k|aki|pa)\b')
#: Códigos con forma de alimentador; los de las SED de medición dependen del perfil (P13) y no se suponen.
PATRONES_REALES = (re.compile(r'\b[A-Za-z]{2}\d{3}\b'), re.compile(r'\b[Ee]lectro ?[A-Z][a-z]+'))
MARCADORES = {'alimentador': ('ALIM-A', 'ALIM-B', 'ALIM-C'), 'set': ('SET-A', 'SET-B'), 'proyecto': ('PROYECTO-X', 'PROYECTO-Y')}
REGISTROS = (('formal', 0.0), ('corto', 0.05), ('coloquial', 0.12))
VERIFICACION = 'sin_comprobar_en_navegador'


class HojaError(ValueError):
    """Una hoja de revisión que no se puede aplicar: nombra la fila y no se escribe nada (076:RF-27)."""


def normalizar(texto: Any) -> str:
    plano = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9.,%+-]+', ' ', plano)).strip()


def leer_jsonl(ruta: Path | str) -> list[dict[str, Any]]:
    return [json.loads(x) for x in Path(ruta).read_text(encoding='utf-8').splitlines() if x.strip()]


def _linea_jsonl(fila: Mapping[str, Any]) -> str:
    return json.dumps(fila, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def escribir_jsonl(ruta: Path | str, filas: Iterable[Mapping[str, Any]]) -> None:
    """Con `\\n` siempre y por reemplazo, para que nunca quede a medias."""
    ruta = Path(ruta)
    tmp = ruta.with_name(ruta.name + '.tmp')
    tmp.write_bytes(''.join(_linea_jsonl(f) + '\n' for f in filas).encode('utf-8'))
    tmp.replace(ruta)


def huella(filas: Iterable[Mapping[str, Any]]) -> str:
    """SHA-256 del contenido canónico, ordenado por id, sin las marcas de revisión ni los finales de línea (076:RF-7, RF-9)."""
    h = hashlib.sha256()
    for f in sorted(filas, key=lambda x: x['id']):
        h.update(_linea_jsonl({k: v for k, v in f.items() if k not in CAMPOS_REVISION}).encode('utf-8') + b'\n')
    return h.hexdigest()


def repartir(filas: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Reparto en `corpus` y `sellado` por grupos de paráfrasis (076:RF-8).

    Método, declarado antes de medir nada. Dentro de cada par (entregable, tipo), los grupos se ordenan por
    sha256(«076-reparto|» + grupo), y el primer 25 % redondeado hacia arriba va a `sellado`, y el resto a `corpus`.
    No interviene lo que dice la fila ni quién la escribió, un grupo cae entero a un lado y añadir una fila no
    reordena las demás. Lo sellado no orienta nada después de medir: se mide una vez, con su huella.
    """
    por_estrato: dict[tuple[str, str], set[str]] = defaultdict(set)
    for f in filas:
        por_estrato[(f['entregable'], f['tipo'])].add(f['grupo_parafrasis'])
    # Un grupo con filas de dos tipos no se parte: manda el primer estrato en que sale.
    sellados: set[str] = set()
    for _estrato, grupos in sorted(por_estrato.items()):
        orden = sorted(grupos, key=lambda g: hashlib.sha256(f'{SAL_REPARTO}|{g}'.encode()).hexdigest())
        sellados.update(orden[:math.ceil(FRACCION_SELLADO * len(orden))])
    return {f['id']: 'sellado' if f['grupo_parafrasis'] in sellados else 'corpus' for f in filas}


# ----------------------------------------------------------------------- comprobaciones
_CACHE: dict[str, list[str] | None] = {}


def _en_revision(fichero: str) -> list[str] | None:
    """Las líneas del fichero en la revisión fijada, o `None` si allí no estaba."""
    if fichero not in _CACHE:
        r = subprocess.run(['git', 'show', f'{REVISION}:{fichero}'], cwd=RAIZ, capture_output=True, check=False)
        _CACHE[fichero] = r.stdout.decode('utf-8', 'replace').splitlines() if r.returncode == 0 else None
    return _CACHE[fichero]


def _rf_definido(rf: str) -> bool:
    m = re.fullmatch(r'(\d{3}):RF-(\d+[a-z]?)', rf)
    if not m:
        return False
    carpetas = list((RAIZ / 'specs').glob(f'{m.group(1)}-*'))
    if not carpetas:
        return False
    return bool(re.search(rf'^- RF-{m.group(2)}:', (carpetas[0] / 'spec.md').read_text(encoding='utf-8'), re.M))


def errores_de_fuentes(filas: Iterable[Mapping[str, Any]]) -> list[str]:
    """Cada fuente: en la revisión, su línea con su ancla; en el árbol, el ancla sigue; su RF, definido (076:RF-4)."""
    errores = []
    for f in filas:
        fuentes = f.get('fuentes') or []
        # Sin respuesta puede no tener fuente: lo que se pregunta no está en el repositorio (076:RF-3).
        if not fuentes and f.get('tipo') != 'sin_respuesta':
            errores.append(f"{f['id']}: sin fuentes")
        for s in fuentes:
            donde = f"{f['id']}: {s.get('fichero')}:{s.get('linea')}"
            lineas = _en_revision(s['fichero'])
            if lineas is None:
                errores.append(f'{donde} no está en la revisión')
                continue
            if not 1 <= s['linea'] <= len(lineas):
                errores.append(f'{donde} fuera del fichero')
            elif s['ancla'] not in lineas[s['linea'] - 1]:
                errores.append(f'{donde} no contiene «{s["ancla"]}»')
            actual = RAIZ / s['fichero']
            if not actual.is_file():
                errores.append(f'{donde} ya no existe')
            elif s['ancla'] not in actual.read_text(encoding='utf-8', errors='replace'):
                errores.append(f'{donde}: «{s["ancla"]}» ya no está en el árbol: hay que revisar la fila')
            if s.get('rf') and not _rf_definido(s['rf']):
                errores.append(f'{donde} cita {s["rf"]}, que no está definido')
    return errores


_CIFRA = re.compile(r'(?<![\w.,-])\d+(?:[.,]\d+)?(?![\w])')
VENTANA_CIFRAS = 12


def _canonica(cifra: str) -> str:
    """«04» es el año 4 y «85,0» es 85: la cifra se compara por su valor, no por cómo se escribe."""
    v = float(cifra.replace(',', '.'))
    return str(int(v)) if v.is_integer() else repr(v)


def errores_de_cifras(filas: Iterable[Mapping[str, Any]]) -> list[str]:
    """Cada cifra de una respuesta esperada aparece cerca de una línea citada: lo demás sería inventado (076:RF-5)."""
    errores = []
    for f in filas:
        cifras = _CIFRA.findall(f.get('respuesta_esperada') or '')
        if not cifras:
            continue
        texto = ''
        for s in f.get('fuentes') or []:
            lineas = _en_revision(s['fichero']) or []
            texto += '\n'.join(lineas[max(0, s['linea'] - 2):s['linea'] + VENTANA_CIFRAS]) + '\n'
        presentes = {_canonica(c) for c in re.findall(r'\d+(?:[.,]\d+)?', texto)}
        for c in cifras:
            if _canonica(c) not in presentes:
                errores.append(f"{f['id']}: la cifra {c} no está en sus fuentes")
    return errores


def nombres_del_perfil() -> set[str]:
    """Empresa, zonales, SET, sistemas y alimentadores del perfil público, normalizados (076:RF-6)."""
    nombres: set[str] = set()
    for ruta in sorted((RAIZ / 'config' / 'perfiles').glob('*.json')):
        datos = json.loads(ruta.read_text(encoding='utf-8'))
        if isinstance(datos, dict) and datos.get('empresa'):
            nombres.add(normalizar(datos['empresa']))

        if not ruta.name.endswith('.estructura.json'):
            continue

        def recorrer(x: Any, clave: str = '') -> None:
            # Los nombres y códigos son valores de «nombre», «codigo» y «sistema», y las claves de «sistemas»;
            # los demás campos son la forma del fichero, no nombres propios.
            if isinstance(x, dict):
                for k, v in x.items():
                    if k.startswith('_'):
                        continue
                    if clave == 'sistemas':
                        nombres.add(normalizar(k))
                    recorrer(v, k)
            elif isinstance(x, list):
                for v in x:
                    recorrer(v, clave)
            elif isinstance(x, str) and clave in ('nombre', 'codigo', 'sistema'):
                nombres.add(normalizar(x))

        recorrer(datos)
    # Una sigla corta o un número no identifican a nadie y darían falsos positivos en cualquier frase.
    return {n for n in nombres if len(n) >= 4 and not n.isdigit() and n not in _PALABRAS_COMUNES}


_PALABRAS_COMUNES = {'norte', 'sur', 'este', 'oeste', 'centro', 'nueva', 'rural', 'urbano', 'urbana', 'barra', 'sistema',
                     'sein', 'otros', 'todos'}
_CAMPOS_DE_NOMBRE = ('pregunta', 'respuesta_esperada', 'motivo_sin_respuesta', 'nota', 'nombre', 'hace', 'requisito_texto',
                     'requisito', 'entrega', 'si_falta', 'formatos', 'cancelar', 'orden_uso', 'escribe')


def errores_de_nombres(filas: Iterable[Mapping[str, Any]], nombres: set[str], patrones: Sequence[re.Pattern],
                       privados: frozenset[str]) -> list[str]:
    """Ningún nombre real en el texto ni en las anclas de las fuentes (076:RF-6)."""
    errores = []
    for f in filas:
        partes = [str(f.get(c) or '') for c in _CAMPOS_DE_NOMBRE]
        partes += [str(s.get('ancla') or '') for s in f.get('fuentes') or []]
        for texto in partes:
            for p in patrones:
                if p.search(texto):
                    errores.append(f"{f['id']}: patrón {p.pattern} en «{texto[:60]}»")
            palabras = normalizar(texto).split()
            for n in range(1, 5):
                for i in range(len(palabras) - n + 1):
                    trozo = ' '.join(palabras[i:i + n]).strip('.,%+-')
                    if trozo in nombres:
                        errores.append(f"{f['id']}: nombre del perfil «{trozo}»")
                    if hashlib.sha256(f'076:{trozo}'.encode()).hexdigest()[:16] in privados:
                        errores.append(f"{f['id']}: nombre privado en «{texto[:40]}»")
    return errores


def errores_de_forma(f: Mapping[str, Any]) -> list[str]:
    """Los campos de una fila (076:RF-1)."""
    e = []
    for c in ('id', 'entregable', 'aspecto', 'pregunta', 'tipo', 'respuesta_esperada', 'fuentes', 'estado_fuente',
              'origen', 'revisado_por_operador', 'grupo_parafrasis', 'reparto'):
        if c not in f or f[c] in (None, '') and c != 'revisado_por_operador':
            e.append(f'falta {c}')
    if f.get('aspecto') not in ASPECTOS:
        e.append(f"aspecto {f.get('aspecto')}")
    if f.get('tipo') not in TIPOS:
        e.append(f"tipo {f.get('tipo')}")
    if f.get('estado_fuente') not in ESTADOS:
        e.append(f"estado {f.get('estado_fuente')}")
    if f.get('origen') != 'sintetico_maestro':
        e.append(f"origen {f.get('origen')}")
    if f.get('reparto') not in ('corpus', 'sellado'):
        e.append(f"reparto {f.get('reparto')}")
    if len(f.get('respuesta_esperada') or '') > 320:
        e.append('respuesta larga')
    return e


# ----------------------------------------------------------------------- web
def _rutas_de_la_api() -> set[str]:
    texto = (RAIZ / 'src' / 'convertersmartgrid' / 'web' / 'app.py').read_text(encoding='utf-8')
    return {f'{m.upper()} {r}' for m, r in re.findall(r"@app\.(get|post|put|delete)\('([^']+)'", texto)}


def _funciones_de_api() -> set[str]:
    return set(re.findall(r'^  (\w+): ?\(', (RAIZ / 'frontend' / 'src' / 'api.ts').read_text(encoding='utf-8'), re.M))


def errores_de_hechos(hechos: Iterable[Mapping[str, Any]]) -> list[str]:
    """Ruta en `web/app.py`, función en `api.ts` y citada en el componente: no se supone un botón por su nombre (076:RF-19)."""
    rutas, funciones, errores = _rutas_de_la_api(), _funciones_de_api(), []
    for h in hechos:
        if h.get('ruta') and h['ruta'] not in rutas:
            errores.append(f"{h['id']}: la ruta {h['ruta']} no está en web/app.py")
        if h.get('api'):
            if h['api'] not in funciones:
                errores.append(f"{h['id']}: api.{h['api']} no está en api.ts")
            elif h['api'] not in (RAIZ / h['fuentes'][0]['fichero']).read_text(encoding='utf-8'):
                errores.append(f"{h['id']}: {h['fuentes'][0]['fichero']} no llama a api.{h['api']}")
        if h.get('clase') not in ('boton', 'casilla'):
            errores.append(f"{h['id']}: clase {h.get('clase')}")
        if not h.get('hace'):
            errores.append(f"{h['id']}: sin «hace»")
        if h.get('requisito') and h.get('verificacion') != VERIFICACION:
            errores.append(f"{h['id']}: lo de pantalla va marcado {VERIFICACION}")
    return errores


#: Botones sin acción propia que preguntar: cierres, listas de chips, orden de tablas (076:RF-19).
_SIN_ACCION = re.compile(r'chip|th-btn|toast-close|icon-btn|curva-serie-btn|onClick=\{\(\) => setPlan\(null\)\}'
                         r'|setTramo\(null\)|close\(|setSelected\(\[\]\)|setOrder|setPathMode|onClear|setValues\(vacio')


def botones_del_front() -> list[tuple[str, int]]:
    """Cada `<button>` y `<FileDrop>` con acción propia de los componentes, como (componente, línea), en la revisión fijada."""
    salida = []
    carpeta = 'frontend/src/components'
    listado = subprocess.run(['git', 'ls-tree', '--name-only', f'{REVISION}:{carpeta}'], cwd=RAIZ, capture_output=True,
                             check=True, text=True).stdout.split()
    for nombre in sorted(listado):
        if not nombre.endswith('.tsx') or nombre == 'ui.tsx':
            continue
        texto = '\n'.join(_en_revision(f'{carpeta}/{nombre}') or [])
        for m in re.finditer(r'<(button|FileDrop)\b', texto):
            fin = texto.find('>', m.start())
            cabeza = re.sub(r'\s+', ' ', texto[m.start():texto.find('</', m.start()) if m.group(1) == 'button' else fin])
            if m.group(1) == 'button' and _SIN_ACCION.search(cabeza):
                continue
            salida.append((nombre, texto[:m.start()].count('\n') + 1))
    return salida


def excluidos_del_catalogo() -> set[tuple[str, int]]:
    """Botones declarados fuera del catálogo con su motivo en `preguntas_entregables_huecos.json` (076:RF-19)."""
    h = json.loads(HUECOS.read_text(encoding='utf-8'))
    return {(x['componente'], x['linea']) for x in h.get('botones_excluidos', [])}


# ----------------------------------------------------------------------- generador
#: Plantillas por aspecto y registro; `{n}` es el nombre del botón o la casilla. Los corchetes, variantes de `expandir`.
PLANTILLAS: dict[str, dict[str, tuple[str, ...]]] = {
    'que_hace': {'formal': ('¿Qué hace [el botón|la opción] «{n}»?', '¿Para qué sirve «{n}» en la web?'),
                 'corto': ('«{n}», ¿qué hace?', '¿q hace «{n}»?'),
                 'coloquial': ('oe y [ese|el] «{n}» [para que es|q hace]', 'explicame nomas que hace «{n}»')},
    'requisito': {'formal': ('¿Qué necesita «{n}» para poder usarse?', '¿Cuándo se habilita «{n}»?'),
                  'corto': ('«{n}» no me deja, ¿q falta?', '¿cuando se activa «{n}»?'),
                  'coloquial': ('[oye|oe] no me prende «{n}», que le falta', 'q tengo q hacer antes de «{n}» pe')},
    'escribe_digsilent': {'formal': ('¿«{n}» escribe en DIgSILENT?', '¿«{n}» cambia algo en el proyecto de DIgSILENT?'),
                          'corto': ('«{n}» toca digsilent?', '¿«{n}» graba en el proyecto?'),
                          'coloquial': ('si le doy a «{n}» me cambia algo en digsilent o no', 'oe «{n}» escribe en power factory?')},
    'entrega': {'formal': ('¿Qué entrega «{n}»?', '¿Qué resultado deja «{n}»?'),
                'corto': ('¿q sale de «{n}»?', '«{n}», ¿qué devuelve?'),
                'coloquial': ('y despues de «{n}» que me queda', 'cuando acaba «{n}» q me da')},
    'ruta': {'formal': ('¿Qué ruta de la API llama «{n}»?',), 'corto': ('¿ruta de «{n}»?',),
             'coloquial': ('a q ruta le pega «{n}»',)},
    'formato': {'formal': ('¿Qué formatos acepta la casilla «{n}»?',), 'corto': ('¿q archivos entran en «{n}»?',),
                'coloquial': ('q tipo de archivo le meto a «{n}»', 'oe en «{n}» q extension va')},
    'si_falta': {'formal': ('¿Qué pasa si falta «{n}»?', '¿Qué ocurre si «{n}» viene mal?'),
                 'corto': ('¿y si no pongo «{n}»?',), 'coloquial': ('y si no tengo «{n}» que pasa pe', 'si le meto mal «{n}» q me dice')},
    'cancelar': {'formal': ('¿Cómo se cancela «{n}»?',), 'corto': ('¿se puede parar «{n}»?',),
                 'coloquial': ('como paro «{n}» si me equivoque',)},
    'orden': {'formal': ('¿En qué orden se usa «{n}»?', '¿Qué va antes de «{n}»?'), 'corto': ('¿q va antes de «{n}»?',),
              'coloquial': ('primero q y luego «{n}»?',)},
}
_CAMPO_DE_ASPECTO = {'que_hace': 'hace', 'requisito': 'requisito', 'escribe_digsilent': 'escribe', 'entrega': 'entrega',
                     'ruta': 'ruta', 'formato': 'formatos', 'si_falta': 'si_falta', 'cancelar': 'cancelar', 'orden': 'orden_uso'}


def aspectos_del_hecho(h: Mapping[str, Any]) -> list[str]:
    return [a for a in PLANTILLAS if h.get(_CAMPO_DE_ASPECTO[a])]


def respuesta_de(h: Mapping[str, Any], aspecto: str) -> str:
    """La respuesta sale del hecho, nunca del azar (076:RF-21)."""
    valor = h[_CAMPO_DE_ASPECTO[aspecto]]
    if aspecto == 'ruta':
        return f'Llama a {valor}.'
    return str(valor)


def muestras_para_cubrir(hechos: Sequence[Mapping[str, Any]]) -> int:
    """Número declarado de muestras con que sale cada hecho al menos una vez (076:RF-22)."""
    return len(hechos)


def generar(hechos: Sequence[Mapping[str, Any]], *, semilla: int, cuantas: int, para: str = 'medida',
            sellados: Iterable[str] = (), vistos: Iterable[str] = (), excluir_vistos: bool = False) -> list[dict[str, Any]]:
    """Preguntas sorteadas; misma semilla, misma salida, sin `hash()` salado (076:RF-20).

    Una permutación de los hechos se recorre en ciclos: con tantas muestras como hechos sale cada uno, sea cual sea la
    semilla (076:RF-22). Con `para='corpus'` se apartan los hechos de una fila sellada: enseñarían lo que se va a medir
    (076:RF-23). Los marcadores son de forma `ALIM-A`: `expandir` inventa códigos con forma de alimentador real.
    """
    from convertersmartgrid.asistente.sinteticos import expandir

    if para not in ('corpus', 'medida'):
        raise ValueError(f'«para» es corpus o medida, no {para}')
    rnd = random.Random(semilla)
    vistos = set(vistos)
    fuera = set(sellados) if para == 'corpus' else set()
    if excluir_vistos:
        fuera |= vistos
    elegibles = sorted((h for h in hechos if h['id'] not in fuera and aspectos_del_hecho(h)), key=lambda h: h['id'])
    filas: list[dict[str, Any]] = []
    orden: list[Mapping[str, Any]] = []
    for i in range(cuantas):
        if not elegibles:
            break
        if not orden:
            orden = rnd.sample(elegibles, len(elegibles))
        h = orden.pop()
        aspecto = rnd.choice(aspectos_del_hecho(h))
        registro, ruido = rnd.choice(REGISTROS)
        plantilla = rnd.choice(PLANTILLAS[aspecto][registro]).replace('{n}', h['nombre'].replace('[', '(').replace(']', ')'))
        frase = expandir(plantilla, h['id'], rnd, {}, ruido).texto
        if rnd.random() < 0.4:
            tipo = rnd.choice(sorted(MARCADORES))
            frase = f"{frase.rstrip('?¿ ')} en {rnd.choice(MARCADORES[tipo])}" + ('?' if frase.endswith('?') else '')
        fila = {'id': f'est-{semilla}-{i:05d}', 'entregable': 'operacion_web', 'hecho': h['id'], 'aspecto': aspecto, 'pregunta': frase,
                'tipo': 'con_respuesta', 'respuesta_esperada': respuesta_de(h, aspecto), 'fuentes': h['fuentes'],
                'origen': 'sintetico_estocastico', 'revisado_por_operador': False, 'semilla': semilla, 'registro': registro,
                'ruido': ruido, 'para': para, 'hecho_visto_al_ensenar': h['id'] in vistos}
        if aspecto == 'requisito':
            fila['verificacion'] = VERIFICACION
        filas.append(fila)
    return filas


def generar_texto(hechos: Sequence[Mapping[str, Any]], **opciones: Any) -> str:
    return ''.join(_linea_jsonl(f) + '\n' for f in generar(hechos, **opciones))


def cobertura(filas: Iterable[Mapping[str, Any]], hechos: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Cuántos botones y casillas del catálogo salen en una muestra, y cuáles no (076:RF-22)."""
    salen = Counter(f['hecho'] for f in filas)
    faltan = sorted(h['id'] for h in hechos if not salen[h['id']])
    return {'catalogo': len(hechos), 'cubiertos': len(hechos) - len(faltan), 'faltan': faltan, 'muestras': sum(salen.values())}


# ----------------------------------------------------------------------- hoja de revisión
COLUMNAS_HOJA = ('id', 'pregunta', 'respuesta esperada', 'fuente', '¿correcta? s/n', 'corrección')
_MARCAS = {'s': 'correcta', 'si': 'correcta', 'n': 'incorrecta', 'no': 'incorrecta'}


def _fuente_corta(f: Mapping[str, Any]) -> str:
    partes = []
    for s in f.get('fuentes') or []:
        donde = f"{s['fichero']}:{s['linea']}" if s.get('linea') else str(s.get('fichero'))
        partes.append(f"{donde} ({s['rf']})" if s.get('rf') else donde)
    return '; '.join(partes) or str(f.get('memoria') or '')


def exportar(filas: Iterable[Mapping[str, Any]], reglas: Iterable[Mapping[str, Any]], destino: Path | str = HOJA) -> Path:
    """La hoja para el operador, con una lista s/n; va a `output/`, fuera de git (076:RF-10)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.worksheet.datavalidation import DataValidation

    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Revisión'
    hoja.append(list(COLUMNAS_HOJA))
    for f in list(filas) + list(reglas):
        hoja.append([f['id'], f['pregunta'], f['respuesta_esperada'], _fuente_corta(f), None, None])
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    for col, ancho in zip('ABCDEF', (22, 60, 70, 50, 12, 50), strict=True):
        hoja.column_dimensions[col].width = ancho
    for fila in hoja.iter_rows(min_row=2):
        for celda in fila:
            celda.alignment = Alignment(wrap_text=True, vertical='top')
    lista = DataValidation(type='list', formula1='"s,n"', allow_blank=True)
    hoja.add_data_validation(lista)
    if hoja.max_row > 1:
        lista.add(f'E2:E{hoja.max_row}')
    hoja.freeze_panes = 'B2'
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    libro.save(destino)
    return destino


def importar(hoja: Path | str, dataset: Path | str = DATASET, revisor: str = 'operador') -> dict[str, int]:
    """Marca solo lo marcado; toda la hoja o nada (076:RF-11, RF-12, RF-27). La corrección no pisa la respuesta esperada.

    Con ``revisor='maestro'`` la marca queda como del maestro: no pone ``revisado_por_operador`` y no cuenta como humana (RF-28).
    """
    from openpyxl import load_workbook

    if revisor not in REVISORES:
        raise HojaError(f'revisor {revisor}: use {" o ".join(REVISORES)}')

    filas = leer_jsonl(dataset)
    por_id = {f['id']: f for f in filas}
    libro = load_workbook(hoja, read_only=True, data_only=True)
    filas_hoja = libro.worksheets[0].iter_rows(values_only=True)
    cabecera = [str(c or '').strip() for c in next(filas_hoja)]
    if not {'id', '¿correcta? s/n', 'corrección'} <= set(cabecera):
        raise HojaError(f'La hoja no tiene las columnas de revisión: {cabecera}')
    ci, cm, cc = cabecera.index('id'), cabecera.index('¿correcta? s/n'), cabecera.index('corrección')
    vistos, marcas, sin_marca = set(), {}, 0
    for valores in filas_hoja:
        i = str(valores[ci] or '').strip()
        if not i:
            continue
        if i in vistos:
            raise HojaError(f'La fila {i} está repetida en la hoja.')
        vistos.add(i)
        if i not in por_id and not i.startswith('regla-'):
            raise HojaError(f'La fila {i} no es de este conjunto.')
        marca = normalizar(valores[cm])
        if not marca:
            sin_marca += 1
            continue
        if marca not in _MARCAS:
            raise HojaError(f'La fila {i} tiene la marca «{valores[cm]}»: use s o n.')
        if i in por_id:
            marcas[i] = {'veredicto': _MARCAS[marca], 'correccion': str(valores[cc] or '').strip()}
    libro.close()
    for i, revision in marcas.items():
        if revisor == 'maestro':
            por_id[i]['revisado_por_maestro'] = True
            por_id[i]['revision'] = {**revision, 'revisor': 'maestro'}
        else:
            por_id[i]['revisado_por_operador'] = True
            por_id[i]['revision'] = revision
    if marcas:
        escribir_jsonl(dataset, filas)
    veredictos = Counter(r['veredicto'] for r in marcas.values())
    return {'correctas': veredictos['correcta'], 'incorrectas': veredictos['incorrecta'], 'sin_marca': sin_marca}


def humanas(filas: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Solo lo que el operador marcó; sin marca no cuenta como humano (076:RF-12, RF-24)."""
    return [f for f in filas if f.get('revisado_por_operador') is True]


def ordenes_confirmadas(_filas: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Siempre vacía: una pregunta revisada no es una orden del operador (068:RF-30, 076:RF-12)."""
    return []


# ----------------------------------------------------------------------- informe
def informe_md(filas: Sequence[Mapping[str, Any]], datos: Mapping[str, Any]) -> str:
    """Un informe por entregable: filas, con y sin respuesta, reparto, huecos; y las contradicciones (076:RF-13, RF-15)."""
    n = len(filas)
    t = ['# Preguntas por entregable: informe', '',
         f'Generado con `tools/preguntas_entregables.py informe` (spec 076), sobre la revisión `{REVISION[:8]}`. No editar a mano.', '',
         f'Filas: {n}. Huella del contenido: `{huella(filas)}`.',
         f'Huella de lo sellado: `{huella([f for f in filas if f["reparto"] == "sellado"])}`.', '',
         '| Entregable o tema | Filas | Con respuesta | Sin respuesta | Corpus | Sellado | Revisadas |',
         '| --- | --- | --- | --- | --- | --- | --- |']
    for e in ENTREGABLES + TEMAS:
        de_e = [f for f in filas if f['entregable'] == e]
        c = Counter(f['tipo'] for f in de_e)
        r = Counter(f['reparto'] for f in de_e)
        t.append(f"| {e} | {len(de_e)} | {c['con_respuesta']} | {c['sin_respuesta']} | {r['corpus']} | {r['sellado']} | "
                 f"{sum(1 for f in de_e if f['revisado_por_operador'])} |")
    t += ['', '## Pendientes', ''] + [f'- {p}' for p in datos['pendientes']] + ['']
    for e in ENTREGABLES + TEMAS:
        de_e = [f for f in filas if f['entregable'] == e]
        c = Counter(f['tipo'] for f in de_e)
        estados = Counter(f['estado_fuente'] for f in de_e)
        t += [f'## {e}', '', f"Filas: {len(de_e)}; con respuesta {c['con_respuesta']}, sin respuesta {c['sin_respuesta']}. Fuentes: "
              + ', '.join(f'{k} {v}' for k, v in sorted(estados.items())) + '.', '', 'Huecos encontrados:', '']
        t += [f'- {h}' for h in datos['huecos'].get(e, [])] + ['']
    t += ['## Contradicciones entre la documentación y el código', '', 'Manda el código; se anotan y no se corrigen aquí.', '']
    for c in datos['contradicciones']:
        doc, cod = c['documento'], c['codigo']
        t.append(f"- {c['nota']} Documento: `{doc['fichero']}:{doc['linea']}`. Código: `{cod['fichero']}:{cod['linea']}`.")
    t.append('')
    return '\n'.join(t)


# ----------------------------------------------------------------------- órdenes
def _verificar() -> int:
    filas, hechos, reglas = leer_jsonl(DATASET), leer_jsonl(HECHOS), leer_jsonl(REGLAS)
    errores = [f"{f['id']}: {x}" for f in filas for x in errores_de_forma(f)]
    errores += errores_de_fuentes(filas) + errores_de_fuentes(hechos) + errores_de_cifras(filas) + errores_de_hechos(hechos)
    errores += errores_de_nombres(filas + hechos + reglas, nombres_del_perfil(), PATRONES_REALES, frozenset())
    reparto = repartir(filas)
    errores += [f"{f['id']}: reparto" for f in filas if reparto[f['id']] != f['reparto']]
    for e in errores:
        print(e)
    print(f'{len(filas)} filas, {len(hechos)} hechos, {len(reglas)} reglas sin código: {len(errores)} error(es).')
    print(f'huella {huella(filas)}')
    print(f"sellado {huella([f for f in filas if f['reparto'] == 'sellado'])}")
    print(f'hechos {huella(hechos)}')
    return 1 if errores else 0


def _cargar_src() -> None:
    src = str(RAIZ / 'src')
    if src not in sys.path:
        sys.path.insert(0, src)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='orden', required=True)
    sub.add_parser('verificar', help='comprueba fuentes, cifras, nombres, hechos y reparto')
    e = sub.add_parser('exportar', help='hoja de revisión para el operador, en output/')
    e.add_argument('--salida', type=Path, default=HOJA)
    i = sub.add_parser('importar', help='marca lo que el operador marcó en la hoja')
    i.add_argument('hoja', type=Path)
    i.add_argument('--dataset', type=Path, default=DATASET)
    i.add_argument('--revisor', choices=REVISORES, default='operador', help='quién marcó la hoja (076:RF-28)')
    sub.add_parser('informe', help='reescribe el informe por entregable')
    g = sub.add_parser('generar', help='preguntas estocásticas de la web, deterministas con la semilla')
    g.add_argument('--semilla', type=int, required=True)
    g.add_argument('--cuantas', type=int, required=True)
    g.add_argument('--para', choices=('corpus', 'medida'), default='medida')
    g.add_argument('--vistos', type=Path, help='JSONL de una generación anterior usada para enseñar')
    g.add_argument('--excluir-vistos', action='store_true')
    g.add_argument('--salida', default='-', help='fichero en output/, o - para la salida estándar')
    c = sub.add_parser('cobertura', help='botones y casillas que salen con esa semilla y ese número de muestras')
    c.add_argument('--semilla', type=int, required=True)
    c.add_argument('--cuantas', type=int, default=None)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    if a.orden == 'verificar':
        return _verificar()
    if a.orden == 'exportar':
        print(exportar(leer_jsonl(DATASET), leer_jsonl(REGLAS), a.salida))
        return 0
    if a.orden == 'importar':
        try:
            print(json.dumps(importar(a.hoja, a.dataset, a.revisor), ensure_ascii=False))
        except HojaError as exc:
            print(f'Hoja rechazada, no se escribió nada: {exc}', file=sys.stderr)
            return 1
        return 0
    if a.orden == 'informe':
        texto = informe_md(leer_jsonl(DATASET), json.loads(HUECOS.read_text(encoding='utf-8')))
        INFORME.write_bytes(texto.encode('utf-8'))
        print(INFORME)
        return 0
    _cargar_src()
    hechos = leer_jsonl(HECHOS)
    if a.orden == 'cobertura':
        n = a.cuantas if a.cuantas is not None else muestras_para_cubrir(hechos)
        print(json.dumps(cobertura(generar(hechos, semilla=a.semilla, cuantas=n), hechos), ensure_ascii=False, indent=1))
        return 0
    sellados = {f['hecho'] for f in leer_jsonl(DATASET) if f.get('hecho') and f['reparto'] == 'sellado'}
    vistos = {f['hecho'] for f in leer_jsonl(a.vistos)} if a.vistos else set()
    texto = generar_texto(hechos, semilla=a.semilla, cuantas=a.cuantas, para=a.para, sellados=sellados, vistos=vistos,
                          excluir_vistos=a.excluir_vistos)
    if a.salida == '-':
        sys.stdout.buffer.write(texto.encode('utf-8'))
    else:
        destino = Path(a.salida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(texto.encode('utf-8'))
    return 0


# El módulo se puede importar sin instalar el paquete: `generar` necesita `sinteticos`.
_cargar_src()
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')

if __name__ == '__main__':
    raise SystemExit(main())
