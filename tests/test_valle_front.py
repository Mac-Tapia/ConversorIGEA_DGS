"""Spec 073, T10: la web muestra la frase del valle de cada alternativa (contrato de la fuente del front).

Como en las demás pruebas de contrato del front, la web no se ejecuta en la suite: se comprueba en la
fuente que lo que pinta `CargasTab.tsx` es el campo que devuelve la API (`valle_texto`, de
`valle.frase_valle`), sin inventar otro ni reconstruir la frase en el navegador. La frase la decide el
servidor: sin valle medido dice «no comprobado en valle», nunca «cumple» (073:RF-31), y si el front la
rehiciera con sus propios campos podría contradecir al informe.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / 'frontend' / 'src'
CARGAS = (SRC / 'components' / 'CargasTab.tsx').read_text(encoding='utf-8')
TIPOS = (SRC / 'types.ts').read_text(encoding='utf-8')
SERVICIOS = (RAIZ / 'src' / 'convertersmartgrid' / 'web' / 'services.py').read_text(encoding='utf-8')


def _bloque(texto: str, inicio: str, fin: str) -> str:
    """El trozo de `texto` entre `inicio` y el primer `fin` que le sigue."""
    a = texto.index(inicio)
    return texto[a:texto.index(fin, a + len(inicio))]


def test_la_escalera_devuelve_la_frase_del_valle_por_variante():
    """073:RF-30 — cada fila de la tabla de variantes que da la API lleva `valle_texto`, la frase de
    `frase_valle`, la misma del informe."""
    assert "| {'valle_texto': frase_valle(t)}" in SERVICIOS
    tipo = _bloque(TIPOS, 'export interface EscaleraVariante {', '\n}')
    assert re.search(r'^\s*valle_texto\?: string \| null;', tipo, re.M)


def test_la_tabla_de_variantes_tiene_la_columna_en_valle():
    """073:RF-30 — la tabla de variantes de la escalera tiene la columna «En valle» y la celda pinta
    `valle_texto` tal cual, en la misma posición que su cabecera."""
    escalera = _bloque(CARGAS, 'function Escalera(', '\n}\n')
    cabecera = _bloque(escalera, '<thead>', '</thead>')
    cuerpo = _bloque(escalera, '<tbody>', '</tbody>')
    columnas = re.findall(r'<th[^>]*>([^<]*)</th>', cabecera)
    assert 'En valle' in columnas
    # Una celda por cabecera: si se descuadra, la frase del valle saldría bajo «Inversión».
    celdas = re.findall(r'<td[\s>]', cuerpo)
    assert len(celdas) == len(columnas), (columnas, len(celdas))
    orden_celdas = re.findall(r'<td[^>]*>\{?([^<\n]*)', cuerpo)
    assert 'v.valle_texto' in orden_celdas[columnas.index('En valle')]


def test_el_front_no_rehace_ni_endulza_la_frase():
    """073:RF-30, 073:RF-31 — el front no reconstruye la frase con los campos sueltos del valle ni
    escribe «cumple en valle»: sin valle medido, el servidor ya dice «no comprobado en valle»."""
    for campo in ('valle_u_max', 'valle_nodo', 'valle_fecha', 'valle_casos', 'valle_sin_comprobar'):
        assert campo not in CARGAS, campo
    assert 'cumple en valle' not in CARGAS.lower()


def test_la_set_nueva_muestra_su_frase_del_valle():
    """073:RF-30 — la SET nueva es otra alternativa (073:RF-40): el oráculo devuelve su `valle_texto` y
    el resultado de «Con proyecto» lo enseña junto al veredicto."""
    oraculo = _bloque(SERVICIOS, 'def _set_nueva_en_el_oraculo(', '\n\n\n')
    assert "'valle_texto': frase_valle(e)" in oraculo
    tipo = _bloque(TIPOS, 'export interface ConProyectoResultado {', '\n}')
    assert re.search(r'oraculo\?: \{[^}]*valle_texto\?: string \| null', tipo)
    # La vista de la SET nueva vive en su componente desde que hay una por zona; «Con proyecto» la usa.
    con_proyecto = _bloque(CARGAS, 'function ConProyecto(', '\n}\n')
    vista = _bloque(CARGAS, 'function SetNuevaVista(', '\n}\n')
    assert '<SetNuevaVista s={s} />' in con_proyecto
    assert 's.oraculo?.valle_texto' in vista
