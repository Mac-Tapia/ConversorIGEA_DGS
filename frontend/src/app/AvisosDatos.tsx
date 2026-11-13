import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { useApp } from '../shared/context';
import type { ResumenEspacio } from '../api/types';
import { avisosDeTrabajos, esGeneral } from '../shared/pasoDeTrabajo';
import { AvisoTrabajo, useVistos } from '../shared/AvisosTrabajo';
import { abrirEspacio } from '../shared/useWorkspace';
import { useToast } from '../shared/ui';

const QUE_ES: Record<string, string> = {
  inputs: 'Entrada', demanda: 'Libro de demanda', datos_empresa: 'Libro de la empresa',
  libro_perdidas: 'Libro de pérdidas', catalog_file: 'Catálogo corregido', active_run_id: 'Última carga de la fuente',
};

/**
 * Lo que le pasó a los datos y el operador tiene que saber (086:RF-2, RF-3, RF-47): ficheros que hoy no
 * están, otros espacios dañados y una copia vieja. El servidor ya lo decía por su API.
 *
 * 086:RF-74: arriba quedan solo los avisos generales del espacio, cada uno en una línea que se despliega. Los de un
 * trabajo van a su paso (RF-70); aquí, solo los que no tienen paso o cuyo paso no se ofrece hoy (RF-71, RF-75).
 * 086:RF-85: el de la copia lleva «Hacer una copia ahora»; antes solo remitía a la orden del manual.
 */
export function AvisosDatos({ pestanas }: { pestanas: readonly string[] }) {
  const { ws, setWs, health, jobs, run } = useApp();
  const [danados, setDanados] = useState<ResumenEspacio[]>([]);
  const vistos = useVistos();

  const leerEspacios = useCallback(() => run(api.espacios).then((filas) => {
    if (filas) setDanados(filas.filter((f) => f.estado !== 'ok'));
  }), [run]);
  // `health` cambia al volver a conectar: un corte que dañó otro espacio se ve sin recargar la pestaña.
  useEffect(() => { void leerEspacios(); }, [leerEspacios, ws.id, health]);

  const copia = health.copia_datos;
  const generales = avisosDeTrabajos(jobs, ws.id, vistos).filter((a) => esGeneral(a, pestanas));
  return (
    <>
      {copia.vencida && (
        // 086:RF-74: una línea; el «cómo» al desplegarla, con el botón de la copia (RF-85).
        <details className="alert alert-warn aviso-linea" role="status">
          <summary>{copia.edad_dias == null
            ? 'Aún no hay ninguna copia de sus datos.'
            : `La última copia de sus datos tiene ${Math.round(copia.edad_dias)} días (el máximo es ${copia.maxima_dias}).`}
            {' '}<span className="mas">más</span></summary>
          <p>Haga una copia para no perder trabajo si falla el equipo, en otro disco o en una carpeta de Google Drive.</p>
          <CopiaAhora />
        </details>
      )}
      {danados.map((d) => (
        <div key={d.id} className="alert alert-error stack">
          <p><strong>Otro espacio de trabajo no se puede abrir</strong> <span className="muted small">({d.id.slice(0, 6)})</span>.
            {' '}{d.estado === 'danado' ? 'Su fichero de estado está dañado.' : 'Es de una versión más nueva del programa.'}</p>
          {d.restaurable && (
            <div className="row">
              <button className="btn btn-sm" onClick={() => void run(() => api.restaurarCopia(d.id)).then((r) => r && leerEspacios())}>
                Restaurar su copia anterior</button>
            </div>
          )}
        </div>
      ))}
      {ws.no_disponibles.length > 0 && (
        <details className="alert alert-warn aviso-linea">
          <summary><strong>{ws.no_disponibles.length === 1 ? 'Un fichero no está ahora.' : `${ws.no_disponibles.length} ficheros no están ahora.`}</strong>
            {' '}<span className="mas">más</span></summary>
          <p>Se conservan: si la unidad vuelve, se recuperan solos.</p>
          <ul className="small">
            {ws.no_disponibles.map((n) => (
              <li key={`${n.campo}-${n.clave}`}>
                {QUE_ES[n.campo] ?? 'Fichero'}: <strong>{n.nombre}</strong>
                {n.campo !== 'active_run_id' && <span className="mono"> · {n.ruta}</span>}{' '}
                <button className="btn btn-sm btn-ghost"
                  onClick={() => void run(() => api.descartarNoDisponible(ws.id, n.campo, n.clave)).then((r) => r && setWs(r))}>
                  Descartar</button>
              </li>
            ))}
          </ul>
        </details>
      )}
      {ws.avisos_datos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
      {generales.map((a) => <AvisoTrabajo key={a.job.id} aviso={a} conPaso />)}
    </>
  );
}

/**
 * 086:RF-85, RF-86: la carpeta de la copia, recordada en el equipo, y el botón que la lanza como trabajo. El progreso y
 * «Cancelar» salen en la barra de trabajos, como los de cualquier otro; antes de copiar, su registro dice cuánto ocupará
 * (cada fichero una vez, RF-78) y cuánto hay libre, y si no cabe no empieza (RF-82, RF-83).
 */
function CopiaAhora() {
  const { ws, health, jobs, run, startJob, refreshHealth } = useApp();
  const [carpeta, setCarpeta] = useState('');
  useEffect(() => {
    void run(api.carpetaCopia).then((r) => { if (r?.carpeta) setCarpeta((actual) => actual || (r.carpeta ?? '')); });
  }, [run]);
  const deCopia = Object.values(jobs).filter((j) => j.kind === 'copia_datos');
  const copiando = deCopia.some((j) => j.status === 'queued' || j.status === 'running');
  const hecha = deCopia.find((j) => j.status === 'done')?.id;
  // Terminada, el aviso se vuelve a leer: con la copia hecha deja de salir.
  useEffect(() => { if (hecha) refreshHealth(); }, [hecha, refreshHealth]);
  const rutasLocales = health.server_paths;
  const texto = carpeta.trim();
  return (
    <div className="row">
      <input className="search" value={carpeta} placeholder="G:/Mi unidad/…/copias_de_datos" disabled={!rutasLocales || copiando}
        aria-label="Carpeta de la copia" onChange={(e) => setCarpeta(e.target.value)} />
      <button className="btn btn-sm btn-primary" disabled={!rutasLocales || copiando || !texto}
        onClick={() => void startJob(() => api.copiarDatos(ws.id, texto))}>
        {copiando ? 'Copiando…' : 'Hacer una copia ahora'}</button>
      {!rutasLocales && <small className="muted">Este servidor no admite rutas locales: use la orden del manual.</small>}
    </div>
  );
}

/**
 * 086:RF-2, RF-5: el espacio de este navegador no se abre. Antes solo salía el mensaje, sin nada que hacer con él,
 * y el botón de restaurar de la API no lo alcanzaba nadie.
 */
export function EspacioNoDisponible({ id, mensaje }: { id: string; mensaje: string }) {
  const toast = useToast();
  const [fila, setFila] = useState<ResumenEspacio | null>(null);
  const [ocupado, setOcupado] = useState(false);
  useEffect(() => {
    api.espacios().then((filas) => setFila(filas.find((f) => f.id === id) ?? null))
      .catch((e: Error) => toast('error', 'No se pudo leer la lista de espacios', e.message));
  }, [id, toast]);
  const accion = async (fn: () => Promise<{ id: string }>) => {
    setOcupado(true);
    try {
      abrirEspacio((await fn()).id);
    } catch (e) {
      toast('error', 'No se pudo completar', e instanceof Error ? e.message : String(e));
      setOcupado(false);
    }
  };
  const danado = fila?.estado !== 'version_futura';
  return (
    <div className="boot">
      <h1>{danado ? 'Este espacio de trabajo está dañado' : 'Este espacio es de una versión más nueva'}</h1>
      <p>{danado
        ? 'Su fichero de estado no se puede leer; puede pasar tras un corte de luz. Lo dañado no se borra: se aparta.'
        : mensaje}</p>
      {danado && fila && !fila.restaurable && <p className="alert alert-warn">No tiene una copia anterior que restaurar.</p>}
      <div className="row">
        {danado && fila?.restaurable && (
          <button className="btn btn-primary" disabled={ocupado} onClick={() => void accion(() => api.restaurarCopia(id))}>
            Restaurar la copia anterior</button>
        )}
        <button className="btn" disabled={ocupado} onClick={() => void accion(api.createWorkspace)}>
          Empezar en un espacio nuevo</button>
      </div>
    </div>
  );
}
