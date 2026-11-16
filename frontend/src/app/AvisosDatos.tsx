import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import { useApp } from '../shared/context';
import type { CopiaExistente, Health, PreviaCopiaDatos, ResumenEspacio } from '../api/types';
import { avisosDeTrabajos, esGeneral } from '../shared/pasoDeTrabajo';
import { AvisoTrabajo, useVistos } from '../shared/AvisosTrabajo';
import { abrirEspacio } from '../shared/useWorkspace';
import { Modal, useToast } from '../shared/ui';
import { fmtBytes } from '../shared/formato';

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
  // 086:RF-109: la copia más nueva que la previa encontró en la carpeta escrita, aunque el servidor no la recuerde.
  const [vista, setVista] = useState<number | null>(null);
  const generales = avisosDeTrabajos(jobs, ws.id, vistos).filter((a) => esGeneral(a, pestanas));
  return (
    <>
      {copia.vencida && (
        // 086:RF-74: una línea; el «cómo» al desplegarla, con el botón de la copia (RF-85).
        <details className="alert alert-warn aviso-linea" role="status">
          <summary>{resumenCopia(copia, vista)}{' '}<span className="mas">más</span></summary>
          <p>Haga una copia en otro disco o en una carpeta en la nube, por si falla el equipo.</p>
          <CopiaAhora onCopias={(copias) => setVista(ultimaBuena(copias))} />
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

/** 086:RF-110: vale para cualquier carpeta (otro disco, Drive, OneDrive…); antes suponía «G:/Mi unidad». */
export const MARCADOR_CARPETA_COPIA = 'Una carpeta de otro disco, de Drive o de OneDrive';

/** 086:RF-109: la fecha de la copia buena más nueva de la lista, o ninguna. */
export function ultimaBuena(copias: readonly CopiaExistente[]): number | null {
  const fechas = copias.filter((c) => c.estado === 'buena' && c.creada != null).map((c) => c.creada as number);
  return fechas.length ? Math.max(...fechas) : null;
}

/**
 * 086:RF-109: la línea del aviso. Nunca dice que no hay copias: el servidor solo sabe de su registro y de la carpeta
 * que recuerda; sin ellas, «no consta». La copia que la previa vio en la carpeta escrita también cuenta.
 */
export function resumenCopia(copia: Health['copia_datos'], vista: number | null = null,
  ahora: number = Date.now() / 1000): string {
  const masNueva = vista != null && (copia.ultima == null || vista > copia.ultima);
  const edad = masNueva ? (ahora - (vista as number)) / 86400 : copia.edad_dias;
  if (edad == null) return 'No consta ninguna copia de sus datos.';
  const dias = Math.max(0, Math.round(edad));
  if (dias === 0) return 'La última copia de sus datos es de hoy.';
  const texto = `La última copia de sus datos tiene ${dias} ${dias === 1 ? 'día' : 'días'}`;
  return edad > copia.maxima_dias ? `${texto} (el máximo es ${copia.maxima_dias}).` : `${texto}.`;
}

const ESTADO_COPIA: Record<CopiaExistente['estado'], string> = {
  buena: 'Completa', con_errores: 'Con errores', no_valida: 'No válida', a_medias: 'A medias',
};

function fechaCopia(creada: number | null): string {
  return creada == null ? 'Sin fecha'
    : new Date(creada * 1000).toLocaleString('es', { dateStyle: 'short', timeStyle: 'short' });
}

/**
 * Aclaración de 086:RF-82 y RF-83, RF-108: antes de escribir nada, lo que ocupará, lo libre, lo que se copia y las
 * copias que ya hay en la carpeta. Solo «Copiar» la empieza; si no cabe, no se ofrece y se dicen las dos cifras.
 */
export function PreviaCopia({ previa, onCopiar, onCancelar }: {
  previa: PreviaCopiaDatos; onCopiar: () => void; onCancelar: () => void;
}) {
  return (
    <Modal title="Copia de sus datos" onClose={onCancelar} actions={<>
      <button className="btn" onClick={onCancelar}>Cancelar</button>
      {previa.cabe && <button className="btn btn-primary" autoFocus onClick={onCopiar}>Copiar</button>}
    </>}>
      <p className="small">En <span className="mono">{previa.destino}</span></p>
      <p>Ocupará <strong>{fmtBytes(previa.bytes_fisicos)}</strong>. Libre: <strong>{fmtBytes(previa.libre)}</strong>.</p>
      {!previa.cabe && (
        <p className="alert alert-error" role="alert">No cabe: ocupará {fmtBytes(previa.bytes_fisicos)} y hay
          {' '}{fmtBytes(previa.libre)} libres. No se copia nada.</p>)}
      <h3>Qué se copia</h3>
      <ul className="small">
        {previa.raices.map((r) => <li key={r.nombre}>{r.etiqueta}: {fmtBytes(r.bytes)}</li>)}
      </ul>
      <h3>Copias en esta carpeta</h3>
      {previa.copias.length === 0 ? <p className="small muted">Ninguna.</p> : (
        <ul className="small lista-copias">
          {previa.copias.map((c) => (
            <li key={c.nombre} title={c.motivo ?? undefined}>
              {fechaCopia(c.creada)} · {c.bytes == null ? '—' : fmtBytes(c.bytes)} · <strong>{ESTADO_COPIA[c.estado]}</strong>
              {c.errores > 0 && ` · ${c.errores} ${c.errores === 1 ? 'error' : 'errores'}`}
            </li>))}
        </ul>)}
    </Modal>
  );
}

/**
 * 086:RF-85, RF-86: la carpeta de la copia, recordada en el equipo, y el botón que abre su previa. Aclaración de RF-82
 * (prueba con la cuenta local, 2026-11-16): el botón escribía unos 20 GB en Drive en un clic. Ahora pide la previa y la
 * copia solo se encola con «Copiar»; el progreso y su «Cancelar» salen en la barra de trabajos, como los de cualquier
 * otro.
 */
function CopiaAhora({ onCopias }: { onCopias: (copias: CopiaExistente[]) => void }) {
  const { ws, health, jobs, run, startJob, refreshHealth } = useApp();
  const [carpeta, setCarpeta] = useState('');
  const [previa, setPrevia] = useState<PreviaCopiaDatos | null>(null);
  const [mirando, setMirando] = useState(false);
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
  const ver = async () => {
    setMirando(true);
    try {
      const r = await run(() => api.previaCopia(texto));
      if (r) {
        setPrevia(r);
        onCopias(r.copias);
      }
    } finally {
      setMirando(false);
    }
  };
  const copiar = (vista: PreviaCopiaDatos) => {
    setPrevia(null);
    void startJob(() => api.copiarDatos(ws.id, vista));
  };
  return (
    <div className="row">
      <input className="search" value={carpeta} placeholder={MARCADOR_CARPETA_COPIA} disabled={!rutasLocales || copiando}
        aria-label="Carpeta de la copia" onChange={(e) => setCarpeta(e.target.value)} />
      <button className="btn btn-sm btn-primary" disabled={!rutasLocales || copiando || mirando || !texto}
        onClick={() => void ver()}>
        {copiando ? 'Copiando…' : mirando ? 'Calculando…' : 'Hacer una copia ahora'}</button>
      {!rutasLocales && <small className="muted">Este servidor no admite rutas locales: use la orden del manual.</small>}
      {previa && <PreviaCopia previa={previa} onCancelar={() => setPrevia(null)} onCopiar={() => copiar(previa)} />}
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
