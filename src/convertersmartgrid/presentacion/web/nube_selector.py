"""La página del selector de ficheros de la nube, con su propia CSP (109:RF-1, RF-3; aclaración de RF-2).

Con el permiso ``drive.file``, Google solo deja ver lo que el operador elige en su selector (Google Picker) y lo que
la aplicación crea; OneDrive tiene el suyo (File Picker v8). Los dos corren en el navegador y necesitan un token de
acceso: esta página lo pide a ``POST …/nube/{proveedor}/selector/token`` al abrirse, lo deja en una variable local
del script y no lo guarda en ningún sitio (ni ``localStorage`` ni ``sessionStorage`` ni la URL). Al elegir, devuelve
los ids a la ventana que la abrió con ``postMessage`` y el origen propio, y se cierra.

La CSP es propia de esta página: solo admite el script del selector del proveedor y un script en línea con nonce.
La de la web no se relaja (plan de la 109, «Selector del proveedor en una página propia»).
Referencias: https://developers.google.com/workspace/drive/picker/guides/overview y
https://learn.microsoft.com/onedrive/developer/controls/file-pickers/
"""
from __future__ import annotations

import html
import json

MENSAJE = 'csg-nube-seleccion'
#: OneDrive personal; para OneDrive de empresa, la de SharePoint del inquilino (``url_selector`` en config/nube.json).
SELECTOR_ONEDRIVE = 'https://onedrive.live.com/picker'

_CSP = {
    'google': ("default-src 'none'; script-src 'nonce-{n}' https://apis.google.com https://www.gstatic.com; "
               "frame-src https://docs.google.com https://drive.google.com https://accounts.google.com "
               "https://content.googleapis.com; connect-src 'self' https://www.googleapis.com; "
               "img-src https: data:; style-src 'unsafe-inline' https://www.gstatic.com; base-uri 'none'; "
               "form-action 'none'; frame-ancestors 'none'"),
    'microsoft': ("default-src 'none'; script-src 'nonce-{n}'; "
                  "frame-src https://onedrive.live.com https://*.sharepoint.com https://login.live.com "
                  "https://login.microsoftonline.com; form-action https://onedrive.live.com https://*.sharepoint.com; "
                  "connect-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"),
}

_COMUN = """
const ESPACIO = {espacio}, PROVEEDOR = {proveedor}, MODO = {modo}, ORIGEN = location.origin;
const estado = document.getElementById('estado');
async function pedirToken() {{
  // Cada vez que se abre: el token vive solo en esta variable local, y caduca en menos de una hora.
  const r = await fetch(`/api/workspaces/${{ESPACIO}}/nube/${{PROVEEDOR}}/selector/token`,
                        {{method: 'POST', credentials: 'same-origin', cache: 'no-store'}});
  if (!r.ok) {{ estado.textContent = 'No se pudo abrir el selector.'; throw new Error(String(r.status)); }}
  return r.json();
}}
function devolver(ids) {{
  if (window.opener) window.opener.postMessage({{tipo: {mensaje}, proveedor: PROVEEDOR, modo: MODO, ids}}, ORIGEN);
  window.close();
}}
"""

_GOOGLE = """
<script nonce="{n}" src="https://apis.google.com/js/api.js"></script>
<script nonce="{n}">{comun}
gapi.load('picker', async () => {{
  const t = await pedirToken();
  const vista = MODO === 'carpeta'
    ? new google.picker.DocsView(google.picker.ViewId.FOLDERS).setSelectFolderEnabled(true)
    : new google.picker.DocsView().setIncludeFolders(true);
  const constructor = new google.picker.PickerBuilder().setOAuthToken(t.token_acceso).addView(vista)
    .setCallback((d) => {{
      if (d.action === google.picker.Action.PICKED) devolver(d.docs.map((x) => x.id));
      else if (d.action === google.picker.Action.CANCEL) devolver([]);
    }});
  if (t.clave_api) constructor.setDeveloperKey(t.clave_api);
  if (t.id_aplicacion) constructor.setAppId(t.id_aplicacion);
  if (MODO !== 'carpeta') constructor.enableFeature(google.picker.Feature.MULTISELECT_ENABLED);
  constructor.build().setVisible(true);
  estado.textContent = '';
}});
</script>"""

_MICROSOFT = """
<iframe name="selector" title="OneDrive" style="border:0;width:100%;height:96vh"></iframe>
<form id="abrir" method="post" target="selector"><input type="hidden" name="access_token"></form>
<script nonce="{n}">{comun}
const CANAL = crypto.randomUUID();
const URL_SELECTOR = {url};
const opciones = {{sdk: '8.0', entry: {{oneDrive: {{files: {{}}}}}}, authentication: {{}},
  messaging: {{origin: ORIGEN, channelId: CANAL}},
  selection: {{mode: MODO === 'carpeta' ? 'single' : 'multiple'}},
  typesAndSources: {{mode: MODO === 'carpeta' ? 'folders' : 'files'}}}};
let puerto = null;
async function alComando(ev) {{
  const m = ev.data;
  if (m.type !== 'command') return;
  puerto.postMessage({{type: 'acknowledge', id: m.id}});
  const c = m.data;
  if (c.command === 'authenticate') {{
    const t = await pedirToken();
    puerto.postMessage({{type: 'result', id: m.id, data: {{result: 'token', token: t.token_acceso}}}});
  }} else if (c.command === 'pick') {{
    puerto.postMessage({{type: 'result', id: m.id, data: {{result: 'success'}}}});
    devolver((c.items || []).map((i) => i.id));
  }} else if (c.command === 'close') {{
    devolver([]);
  }}
}}
window.addEventListener('message', (ev) => {{
  if (ev.source !== window.frames.selector || !ev.data || ev.data.channelId !== CANAL) return;
  if (ev.data.type === 'initialize') {{
    puerto = ev.ports[0];
    puerto.addEventListener('message', alComando);
    puerto.start();
    puerto.postMessage({{type: 'activate'}});
  }}
}});
(async () => {{
  const t = await pedirToken();
  const formulario = document.getElementById('abrir');
  formulario.action = URL_SELECTOR + '?' + new URLSearchParams({{filePicker: JSON.stringify(opciones)}});
  formulario.access_token.value = t.token_acceso;
  formulario.submit();
  formulario.access_token.value = '';
  estado.textContent = '';
}})();
</script>"""


def pagina_selector(proveedor: str, espacio: str, modo: str, nonce: str, url_onedrive: str = '') -> tuple[str, str]:
    """El HTML del selector y su CSP. Ningún token va en la página: lo pide el script al abrirse."""
    comun = _COMUN.format(espacio=json.dumps(espacio), proveedor=json.dumps(proveedor), modo=json.dumps(modo),
                          mensaje=json.dumps(MENSAJE))
    cuerpo = (_GOOGLE.format(n=nonce, comun=comun) if proveedor == 'google'
              else _MICROSOFT.format(n=nonce, comun=comun, url=json.dumps(url_onedrive or SELECTOR_ONEDRIVE)))
    titulo = 'Elegir carpeta' if modo == 'carpeta' else 'Elegir ficheros'
    pagina = (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{html.escape(titulo)}</title>'
              f'</head><body><p id="estado">Abriendo el selector…</p>{cuerpo}</body></html>')
    return pagina, _CSP[proveedor].format(n=nonce)
