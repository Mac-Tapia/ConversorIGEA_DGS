"""086:RF-38: el ensayo no registra accesos/ruta con identidad del producto.

Lectura de las directivas ISPP simples usadas por este .iss, sin ejecutar setup.
La compilación real sigue siendo una comprobación independiente del candidato.
"""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _directivas(qa):
    source = (ROOT / 'instalador/ConverterSmartGrid.iss').read_text(encoding='utf-8')
    macros = {'Candidato': 'fixture', 'SourcePath': 'fixture'}
    if qa:
        macros['EnsayoQA'] = '1'
    return _analizar(source, macros)


def _analizar(source, macros):
    """Las directivas ISPP de este .iss, sin compilarlo (086:RF-38, 086:RF-92).

    Desde la versión única (086:RF-92) el .iss calcula la versión con expresiones del preprocesador (``#define Version
    Copy(...)``, ``#if Version == ""``…) que solo ISCC puede evaluar. Un ``#define`` con expresión queda como
    «calculado por ISPP», un ``#if`` con expresión es una comprobación del compilador que con un candidato válido no se
    cumple, y ``#expr``, ``#pragma`` y ``#error`` no son contenido. Lo que esta prueba comprueba (identidad, ruta y
    accesos del QA frente al producto) son ``#define`` literales y se leen como siempre. 2026-11-13: el analizador
    exigía que todo ``#define`` fuera literal y la puerta de ese commit no eligió esta prueba.
    """
    macros = dict(macros)
    active = [True]
    lines = []
    de_expresion = [False]          # cada bloque abierto: ¿es un «#if <expresión>»?
    for line in source.splitlines():
        if line.startswith(('#ifdef ', '#ifndef ')):
            cmd, name = line.split()
            condition = name in macros
            active.append(active[-1] and (condition if cmd == '#ifdef' else not condition))
            de_expresion.append(False)
        elif line.startswith('#if '):
            active.append(False)
            de_expresion.append(True)
        elif line == '#else':
            active[-1] = active[-2] and not active[-1]
        elif line == '#endif':
            active.pop()
            de_expresion.pop()
        elif line.lstrip().startswith(('#expr ', '#pragma ', '#error')):     # también sangradas, como en el .iss
            continue
        elif de_expresion[-1]:
            # Falla cerrado: un «#if <expresión>» no se evalúa aquí, así que solo puede envolver comprobaciones del
            # compilador. Un AppId, un acceso o una ruta dentro dejaría de verse y la prueba seguiría en verde.
            assert not line.strip() or line.lstrip().startswith(';'), f'contenido dentro de un #if de expresión: {line}'
        elif active[-1] and line.startswith('#define '):
            literal = re.fullmatch(r'#define (\w+) "([^"]*)"', line)
            if literal:
                macros[literal[1]] = literal[2]
            else:
                nombre = re.fullmatch(r'#define (\w+) .+', line)
                assert nombre, line
                macros.setdefault(nombre[1], f'<{nombre[1]} calculado por ISPP>')
        elif active[-1]:
            lines.append(re.sub(r'\{#(\w+)\}', lambda m: macros[m[1]], line))
    assert len(active) == 1
    return lines


def test_086_rf92_el_analizador_entiende_las_expresiones_del_preprocesador():
    """086:RF-92 — un ``#define`` con expresión, un ``#if`` y un ``#expr`` no hacen fallar la lectura; los literales se
    sustituyen como siempre y lo calculado queda señalado, sin inventar su valor."""
    source = '\n'.join([
        '#define Prefijo "programa-"',
        '#define Busqueda FindFirst(AddBackslash(Candidato) + Prefijo + "*.whl", 0)',
        '#if Busqueda == 0',
        '#error falta la rueda',
        '#endif',
        '#expr FindClose(Busqueda)',
        '#define Version Copy(Busqueda, 1, 3)',
        '#pragma message "versión: " + Version',
        'AppVersion={#Version}',
        'Nombre={#Prefijo}',
    ])
    lineas = _analizar(source, {'Candidato': 'fixture'})
    assert lineas == ['AppVersion=<Version calculado por ISPP>', 'Nombre=programa-']
    # Falla cerrado: contenido dentro de un «#if <expresión>» no se descarta en silencio.
    import pytest

    with pytest.raises(AssertionError, match='dentro de un #if de expresión'):
        _analizar('\n'.join(['#if Version == ""', 'AppId={{FALSO}', '#endif']), {})


def _valor(lines, name):
    return next(line.split('=', 1)[1] for line in lines if line.startswith(name+'='))


def test_qa_y_producto_no_comparten_appid_ruta_ni_accesos():
    product, qa = _directivas(False), _directivas(True)
    assert _valor(product, 'AppId') == '{{6F0B1C52-8A3E-4C57-9B0E-6F4C2D7A1E86}'
    assert _valor(product, 'DefaultDirName') == r'{localappdata}\Programs\ConverterSmartGrid'
    assert _valor(qa, 'AppId') == '{{A377620D-88D7-4C7E-8358-202611080003}'
    assert _valor(qa, 'DefaultDirName') == r'D:\converter\auditorias\csg_qa_1108'
    footprints = []
    for lines in (product, qa):
        icons = {line.split(';', 1)[0] for line in lines if line.startswith('Name: "{auto')}
        # Escritorio, menú Inicio, diagnóstico y, desde la 1.0 (086:RF-89 a RF-91, decisión del usuario del
        # 2026-11-13), el manual de instalación en el menú Inicio.
        assert len(icons) == 4
        footprints.append(icons)
    # Por nombre, no solo por número: un acceso equivocado también daría 4.
    assert 'Name: "{autoprograms}\\ConverterSmartGrid - manual de instalacion"' in footprints[0]
    assert any(i.startswith('Name: "{autoprograms}\\') and 'manual de instalacion' in i and 'QA' in i
               for i in footprints[1])
    assert footprints[0].isdisjoint(footprints[1]), 'QA pisa accesos de producto'
    assert all('QA' in icon for icon in footprints[1])
    assert '-qa-setup' in _valor(qa, 'OutputBaseFilename')
    assert '-qa-' not in _valor(product, 'OutputBaseFilename')


def test_qa_conserva_instalacion_verificada_y_no_borra_datos():
    for qa in (False, True):
        lines = _directivas(qa)
        assert _valor(lines, 'PrivilegesRequired') == 'lowest'
        assert _valor(lines, 'CloseApplications') == 'no'
        deletes = [line for line in lines if line.startswith('Type:')]
        assert deletes and all('{app}' in line for line in deletes)
        assert not any('CSG_DATOS_HOME' in line for line in deletes)
        assert any('ewWaitUntilTerminated' in line for line in lines)
        assert any('CodigoProceso = 0' in line for line in lines)
