"""086:RF-38: el ensayo no registra accesos/ruta con identidad del producto.

Lectura de las directivas ISPP simples usadas por este .iss, sin ejecutar setup.
La compilación real sigue siendo una comprobación independiente del candidato.
"""
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _directivas(qa):
    source = (ROOT / 'instalador/ConverterSmartGrid.iss').read_text(encoding='utf-8')
    macros = {'Candidato': 'fixture', 'Version': '1.0.0rc6', 'SourcePath': 'fixture'}
    if qa:
        macros['EnsayoQA'] = '1'
    active = [True]
    lines = []
    for line in source.splitlines():
        if line.startswith(('#ifdef ', '#ifndef ')):
            cmd, name = line.split()
            condition = name in macros
            active.append(active[-1] and (condition if cmd == '#ifdef' else not condition))
        elif line == '#else':
            active[-1] = active[-2] and not active[-1]
        elif line == '#endif':
            active.pop()
        elif active[-1] and line.startswith('#define '):
            match = re.fullmatch(r'#define (\w+) "([^"]*)"', line)
            assert match, line
            macros[match[1]] = match[2]
        elif active[-1]:
            lines.append(re.sub(r'\{#(\w+)\}', lambda m: macros[m[1]], line))
    assert len(active) == 1
    return lines


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
        assert len(icons) == 3
        footprints.append(icons)
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
