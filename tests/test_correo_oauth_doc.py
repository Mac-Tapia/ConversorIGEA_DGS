"""Spec 110: el instructivo del registro OAuth existe, lo enlaza el manual y no lleva identificadores ni secretos."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DOC = RAIZ / 'docs' / 'CORREO_OAUTH.md'

#: Lo que delataría un identificador o un secreto real pegado en el documento.
_REALES = (
    re.compile(r'\d{6,}-[a-z0-9]{20,}\.apps\.googleusercontent\.com'),  # identificador de cliente de Google
    re.compile(r'GOCSPX-[A-Za-z0-9_\-]{10,}'),                            # secreto de cliente de Google
    re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I),  # GUID de Azure
    re.compile(r'\b[A-Za-z0-9_~.\-]{3}8Q~[A-Za-z0-9_~.\-]{30,}'),         # secreto de Entra ID
    re.compile(r'ya29\.[A-Za-z0-9_\-]{20,}'),                             # token de acceso de Google
    re.compile(r'[A-Za-z0-9._%+\-]+@(?!example\.)[A-Za-z0-9\-]+\.[A-Za-z]{2,}'),  # una dirección de alguien
)


def _texto() -> str:
    """El instructivo; una aserción, y no un FileNotFoundError, si todavía no existe (rojo por caso)."""
    assert DOC.is_file(), f'falta {DOC.relative_to(RAIZ)}'
    return DOC.read_text(encoding='utf-8')


def test_el_instructivo_existe_y_pide_solo_enviar():
    """110:RF-2 — Google con gmail.send y Microsoft con Mail.Send; ningún permiso de lectura del buzón."""
    texto = _texto()
    assert 'https://www.googleapis.com/auth/gmail.send' in texto and 'Mail.Send' in texto
    assert 'fuera de git' in texto


def test_el_manual_lo_enlaza():
    """110:RF-2 — el manual de órdenes nombra el instructivo."""
    assert 'docs/CORREO_OAUTH.md' in (RAIZ / 'docs' / 'MANUAL_COMANDOS.md').read_text(encoding='utf-8')


def test_sin_identificadores_ni_secretos_reales():
    """110:RF-2 — el instructivo no trae ni un identificador, ni un secreto, ni un token, ni una dirección."""
    texto = _texto()
    for patron in _REALES:
        assert not patron.search(texto), patron.pattern


def test_version_de_prueba_sin_verificacion():
    """110:RF-2 — decisión del usuario: Google en «Testing» (hasta 100 usuarios de prueba, sin verificación) y Azure con
    cuentas personales; la prueba real con una cuenta es opcional y la validación es con el simulado."""
    texto = _texto()
    assert 'Testing' in texto and '100 usuarios de prueba' in texto and 'cuentas personales' in texto
    assert 'tests/correo_simulado.py' in texto and 'opcional' in texto
    assert 'Sin cuenta conectada: configure config/nube.json' in texto


def test_no_pide_leer_el_buzon():
    """110:RF-2 — los permisos de lectura solo aparecen para decir que no se añaden."""
    texto = _texto()
    for linea in texto.splitlines():
        if any(p in linea for p in ('gmail.readonly', 'Mail.Read', 'gmail.modify')):
            assert 'No añada' in linea or 'ni `Mail.Read`' in linea, linea
