"""Spec 033: cada RF con un número único, su tarea y su prueba; el estado, en un solo sitio.

La revisión del 2026-10-29 encontró la suite en verde con RF repetidos, saltos sin
explicar, tareas repetidas o sin «Hecho cuando:», specs implementadas que decían
«aprobada» y RF sin prueba porque una sola prueba de DIgSILENT abierta apagaba 009:RF-11.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter

from apoyo import cargar_herramienta

ES = cargar_herramienta('estado_specs.py')
RAIZ = ES.RAIZ
SPECS = ES.leer_specs()
CITAS = ES.citas_de_pruebas()


def _fallos(pares):
    return {k: v for k, v in pares if v}


# ----------------------------------------------------------------- numeración

def test_cada_rf_se_define_una_vez():
    """033:RF-1 — una sola línea ``- RF-n:`` por requisito; las aclaraciones son otra forma."""
    malos = _fallos((s.numero, sorted(r for r, c in Counter(s.definiciones).items() if c > 1))
                    for s in SPECS)
    assert not malos, f'RF definidos más de una vez: {malos}'


def test_los_huecos_de_numeracion_se_declaran():
    """033:RF-2 — un número sin usar se declara con «no se usa(n)» y su motivo."""
    malos = _fallos((s.numero, s.huecos()) for s in SPECS)
    assert not malos, f'Huecos sin declarar: {malos}'


def test_cada_numero_de_spec_tiene_carpeta():
    """033:RF-3 — 001 al mayor, sin huecos; los no usados, «reservada» o «retirada»."""
    numeros = {int(s.numero) for s in SPECS}
    faltan = [f'{n:03d}' for n in range(1, max(numeros) + 1) if n not in numeros]
    assert not faltan, f'Números de spec sin carpeta: {faltan}'
    for s in SPECS:
        if s.estado in ('reservada', 'retirada'):
            texto = (s.carpeta / 'spec.md').read_text(encoding='utf-8')
            assert re.search(r'^## Motivo', texto, re.M), f'spec {s.numero} {s.estado} sin motivo'


def test_tareas_con_forma_y_sin_repetir():
    """033:RF-4 — ``Tn`` o ``Tn`` más una letra, una vez por ``tasks.md``."""
    for s in SPECS:
        ids = [t.id for t in s.tareas]
        assert all(re.fullmatch(r'T\d+[a-z]?', i) for i in ids), (s.numero, ids)
        assert len(ids) == len(set(ids)), (s.numero, [i for i, c in Counter(ids).items() if c > 1])


# ----------------------------------------------------------------- tareas

def test_cada_tarea_dice_cuando_esta_hecha():
    """033:RF-5 — «Hecho cuando:» en cada tarea."""
    malos = _fallos((s.numero, [t.id for t in s.tareas if 'Hecho cuando' not in t.texto]) for s in SPECS)
    assert not malos, f'Tareas sin «Hecho cuando:»: {malos}'


def test_cada_rf_tiene_su_tarea():
    """033:RF-6 — cada RF lo nombra una tarea, suelto o en un rango."""
    malos = _fallos((s.numero, sorted(s.rf - s.rf_de_tareas(), key=ES.clave_rf))
                    for s in SPECS if s.tareas)
    assert not malos, f'RF sin tarea: {malos}'


def test_marca_de_digsilent():
    """033:RF-7 — la marca ``[DIgSILENT]`` reconoce las tareas que solo se hacen allí."""
    t = ES.Tarea('T9', False, '[DIgSILENT] Prueba con CA101.\nHecho cuando: informe válido.')
    assert t.digsilent and not ES.Tarea('T1', False, 'Código.\nHecho cuando: x').digsilent
    # La marca vale solo en el título: una evidencia que nombre DIgSILENT no la vuelve una.
    assert not ES.Tarea('T2', True, 'Código.\n   probado en [DIgSILENT]').digsilent


# ----------------------------------------------------------------- estado

def test_estado_con_vocabulario_cerrado():
    """033:RF-8 — la primera palabra de ``Estado:`` es una de seis."""
    malos = {s.numero: s.estado for s in SPECS if s.estado not in ES.ESTADOS}
    assert not malos, f'Estados fuera del vocabulario {ES.ESTADOS}: {malos}'


def test_cumplida_sin_tareas_abiertas():
    """033:RF-9 — «cumplida» con una tarea abierta es mentira."""
    malos = _fallos((s.numero, [t.id for t in s.abiertas]) for s in SPECS if s.estado == 'cumplida')
    assert not malos, malos


def test_implementada_solo_le_falta_digsilent():
    """033:RF-10 — «implementada»: abiertas solo las ``[DIgSILENT]``, y alguna."""
    for s in SPECS:
        if s.estado == 'implementada':
            assert s.abiertas, f'spec {s.numero} «implementada» sin nada abierto: es «cumplida»'
            codigo = [t.id for t in s.abiertas if not t.digsilent]
            assert not codigo, f'spec {s.numero} «implementada» con código abierto: {codigo}'


def test_aprobada_tiene_codigo_pendiente():
    """033:RF-11 — «aprobada» con tareas: queda al menos una de código."""
    malos = [s.numero for s in SPECS if s.estado == 'aprobada' and s.tareas
             and not [t for t in s.abiertas if not t.digsilent]]
    assert not malos, f'«aprobada» sin código pendiente (es implementada o cumplida): {malos}'


def test_borrador_sin_tareas_hechas():
    """033:RF-12 — borrador, reservada o retirada no tienen tareas marcadas."""
    malos = [s.numero for s in SPECS if s.estado in ('borrador', 'reservada', 'retirada')
             and any(t.hecha for t in s.tareas)]
    assert not malos, malos


def test_aprobada_o_mas_tiene_plan_y_tareas():
    """033:RF-13 — desde «aprobada», ``plan.md`` y ``tasks.md``."""
    malos = [s.numero for s in SPECS if s.estado in ('aprobada', 'implementada', 'cumplida')
             and not ((s.carpeta / 'plan.md').is_file() and (s.carpeta / 'tasks.md').is_file())]
    assert not malos, f'Sin plan.md o tasks.md: {malos}'


def test_readme_de_specs_al_dia():
    """033:RF-14 — ``specs/README.md`` es lo que genera ``tools/estado_specs.py``."""
    actual = (RAIZ / 'specs' / 'README.md').read_text(encoding='utf-8')
    assert actual == ES.tabla(), 'python tools/estado_specs.py --escribir'


def test_claude_md_dice_el_mismo_estado():
    """033:RF-15 — la tabla de ``CLAUDE.md``, una fila por spec con su estado."""
    texto = (RAIZ / 'CLAUDE.md').read_text(encoding='utf-8')
    filas = dict(re.findall(r'^\s*\| (\d{3}) [^|]*\| (\w+)', texto, re.M))
    for s in SPECS:
        assert filas.get(s.numero) == s.estado, (s.numero, filas.get(s.numero), s.estado)


# ----------------------------------------------------------------- pruebas

def test_rf_probados_al_cerrar_el_codigo():
    """033:RF-16 — con las tareas de código cerradas, cada RF (también de letra) citado."""
    malos = {}
    for s in SPECS:
        if s.tareas and not [t for t in s.abiertas if not t.digsilent]:
            sin = sorted(s.rf - CITAS.get(s.numero, set()), key=ES.clave_rf)
            if sin:
                malos[s.numero] = sin
    assert not malos, f'RF sin prueba: {malos}'


def test_citas_a_rf_que_existen():
    """033:RF-17 — una cita apunta a un RF definido, también de letra."""
    por_numero = {s.numero: s.rf for s in SPECS}
    malos = _fallos((n, sorted(c - por_numero.get(n, set()), key=ES.clave_rf)) for n, c in CITAS.items()
                    if n in por_numero)
    assert not malos, f'Citas a RF que no existen: {malos}'
    # Las pruebas del asistente usan «099» como dato inventado dentro de una cadena: solo se
    # exige que exista una spec dentro de la numeración.
    tope = max(por_numero)
    desconocidas = sorted(n for n in set(CITAS) - set(por_numero) if n <= tope)
    assert not desconocidas, f'Citas a specs que no existen: {desconocidas}'


def test_cada_fichero_de_pruebas_cita_una_spec():
    """033:RF-18 — ninguna prueba sin spec: el docstring del módulo o de una prueba la cita."""
    sueltos = [p.name for p in sorted((RAIZ / 'tests').glob('test_*.py'))
               if not re.search(r'\b\d{3}:RF-\d', p.read_text(encoding='utf-8', errors='replace'))]
    assert not sueltos, f'Ficheros de pruebas sin ninguna spec: {sueltos}'


# ----------------------------------------------------------------- código

def test_cada_spec_hecha_tiene_codigo_en_el_indice():
    """033:RF-19 — implementada o cumplida: al menos un fichero en ``CODIGO_FUENTE.md``."""
    indice = (RAIZ / 'CODIGO_FUENTE.md').read_text(encoding='utf-8')
    columnas = ' '.join(re.findall(r'^\| `[^`]+` \| .* \| ([^|]*) \|\s*$', indice, re.M))
    malos = [s.numero for s in SPECS if s.estado in ('implementada', 'cumplida')
             and s.numero not in ('009', '033') and not re.search(rf'\b{s.numero}\b', columnas)]
    assert not malos, f'Specs sin ningún fichero en el índice: {malos}'


def test_ningun_fichero_de_src_solo_con_base():
    """033:RF-20 — el código anterior a las specs lo rige la 034."""
    indice = (RAIZ / 'CODIGO_FUENTE.md').read_text(encoding='utf-8')
    solo_base = re.findall(r'^\| `((?:src|tools)/[^`]+)` \| .* \| base \|\s*$', indice, re.M)
    assert not solo_base, f'Solo «base», sin spec: {solo_base}'


def test_commits_feat_nombran_su_spec():
    """033:RF-21 — desde el 2026-10-30, cada ``feat`` nombra su spec."""
    log = subprocess.run(['git', 'log', '--since=2026-10-30', '--format=%h %s'], cwd=RAIZ,
                         capture_output=True, text=True, encoding='utf-8', check=True).stdout
    malos = [l for l in log.splitlines() if re.match(r'\w+ feat', l)
             and not re.search(r'\b\d{3}:RF-\d|spec \d{3}|\b\d{3} T\d', l)]
    assert not malos, f'Commits feat sin spec: {malos}'


def test_skill_con_las_reglas_del_flujo():
    """033:RF-22 — el skill dice cómo crece una spec, la marca y el vocabulario."""
    skill = (RAIZ / '.claude' / 'skills' / 'igea-dgs-spec' / 'SKILL.md').read_text(encoding='utf-8')
    for regla in ('cumplida no crece', 'con su tarea', '[DIgSILENT]', 'implementada', 'reservada'):
        assert regla in skill, regla
