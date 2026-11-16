"""Google Drive y OneDrive por su API, detrás de un contrato común (spec 109).

Hasta la 109, Drive solo entraba como una carpeta local más (086:RF-78, 105:RF-28). Aquí van el contrato
(``proveedor``), el único transporte HTTP (``http``), el OAuth (``oauth``) y un adaptador por proveedor. Ningún otro
fichero del paquete abre la red: lo comprueba ``tests/test_seguridad_web.py`` (086:RF-22, 109:RF-16).
"""
