import { useCallback, useEffect, useMemo, useState } from 'react';
import { entradasEstudios, type EntradaBorrador, type EntradaEsquema, type EntradasEstado, type FilaEntrada } from '../../api/entradasEstudios';
import { useApp } from '../../shared/context';
import { FileDrop } from '../../shared/ui';
import {
  ACEPTA, conDatosSinEjecucion, editarCelda, entradasQueFaltan, filaVacia, filasConError, pagina, quitarFila, textoCelda,
  type EstudioNoOfrecido,
} from './entradasEstudiosLogica';

/**
 * 4.2 · «Datos que faltan a los estudios» (spec 012, RF-73 a RF-82).
 *
 * Por cada estudio no disponible, las entradas que le faltan: el operador suelta un TXT, CSV, PDF
 * o una imagen, el servidor lo lee (OCR si hace falta) en un trabajo del motor, y lo leído sale en
 * una tabla editable. Nada cuenta para el catálogo hasta «Guardar»: una cifra del OCR sin revisar
 * no puede volver «disponible» un cortocircuito. No se rellena ninguna celda con un valor típico.
 */
export function EntradasEstudios({ project, noOfrecidos, onCambio }: {
  project: string; noOfrecidos: EstudioNoOfrecido[]; onCambio: () => void;
}) {
  const { ws, run, startJob, jobs, active } = useApp();
  const [estado, setEstado] = useState<EntradasEstado | null>(null);
  const [leyendo, setLeyendo] = useState<Record<string, string>>({});
  const engineBusy = Boolean(active.engine);

  const cargar = useCallback(() => {
    if (!project) return;
    void run(() => entradasEstudios.estado(ws.id, project)).then((e) => { if (e) setEstado(e); });
  }, [run, ws.id, project]);
  useEffect(cargar, [cargar]);

  // Al terminar la lectura (el trabajo del motor), se relee el borrador que dejó.
  const terminados = Object.entries(leyendo).filter(([, id]) => {
    const j = jobs[id];
    return j && !['queued', 'running'].includes(j.status);
  }).map(([clave]) => clave).join(',');
  useEffect(() => {
    if (!terminados) return;
    setLeyendo((xs) => Object.fromEntries(Object.entries(xs).filter(([k]) => !terminados.split(',').includes(k))));
    cargar();
  }, [terminados, cargar]);

  const lista = useMemo(() => (estado ? entradasQueFaltan(noOfrecidos, estado) : []), [estado, noOfrecidos]);
  const sinEjecucion = conDatosSinEjecucion(noOfrecidos);
  if (!project || !estado || (!lista.length && !sinEjecucion.length)) return null;

  const leer = async (clave: string, files: File[]) => {
    const job = await startJob(() => entradasEstudios.leer(ws.id, project, clave, files));
    if (job) setLeyendo((xs) => ({ ...xs, [clave]: job.id }));
  };
  const guardar = async (clave: string, filas: FilaEntrada[]) => {
    const e = await run(() => entradasEstudios.guardar(ws.id, project, clave, filas));
    if (e) {
      setEstado(e);
      onCambio();                                        // 012:RF-79: el catálogo se relee
    }
  };
  const descartar = async (clave: string) => {
    const e = await run(() => entradasEstudios.descartar(ws.id, project, clave));
    if (e) setEstado(e);
  };

  return (
    <div className="card">
      <p className="strong">Datos que faltan a los estudios</p>
      <p className="muted small">Cada dato lo da la empresa: suelte un TXT, CSV, PDF o una foto (JPG, PNG) de la tabla, revise
        lo leído y guárdelo. No se rellena nada con valores típicos; lo guardado vale para este proyecto.</p>
      {sinEjecucion.length > 0 && (
        <p className="alert alert-info small">Con sus datos ya cargados, pendientes de ejecución en DIgSILENT:{' '}
          {sinEjecucion.map((e) => e.nombre).join(', ')}.</p>
      )}
      {lista.map(({ esquema, estudios, guardada }) => (
        <Entrada key={esquema.clave} esquema={esquema} estudios={estudios} guardada={guardada ? estado.guardadas[esquema.clave] : null}
          borrador={estado.borradores[esquema.clave] ?? null} ocupado={engineBusy || Boolean(leyendo[esquema.clave])}
          onLeer={(f) => void leer(esquema.clave, f)} onGuardar={(f) => void guardar(esquema.clave, f)}
          onDescartar={() => void descartar(esquema.clave)} />
      ))}
    </div>
  );
}

function Entrada({ esquema, estudios, guardada, borrador, ocupado, onLeer, onGuardar, onDescartar }: {
  esquema: EntradaEsquema; estudios: string[]; guardada: EntradasEstado['guardadas'][string] | null;
  borrador: EntradaBorrador | null; ocupado: boolean;
  onLeer: (f: File[]) => void; onGuardar: (f: FilaEntrada[]) => void; onDescartar: () => void;
}) {
  const [filas, setFilas] = useState<FilaEntrada[] | null>(null);
  const [num, setNum] = useState(0);
  // Un borrador nuevo (otra lectura) reemplaza lo que se estaba editando.
  useEffect(() => { setFilas(borrador ? borrador.filas : null); setNum(0); }, [borrador]);
  const editando = filas !== null;
  const errores = borrador?.errores ?? [];
  const marcadas = filasConError(errores);
  const vista = pagina(filas ?? [], num);

  return (
    <details open={editando}>
      <summary>
        <strong>{esquema.titulo}</strong>
        {guardada
          ? <span className="muted small"> · guardada el {guardada.confirmado?.replace('T', ' ')} ({guardada.fichero})
            {guardada.completa ? '' : ' · incompleta'}</span>
          : <span className="muted small"> · falta</span>}
        {estudios.length > 0 && <span className="muted small"> · la piden: {estudios.join(', ')}</span>}
      </summary>
      <p className="muted small">{esquema.ayuda}</p>
      {guardada && guardada.faltan.length > 0 && <p className="alert alert-warn small">Le falta: {guardada.faltan.join('; ')}.</p>}
      <FileDrop compact multiple accept={ACEPTA} disabled={ocupado} onFiles={onLeer}>
        <span>{ocupado ? 'Leyendo…' : <>TXT, CSV, PDF o imagen de «{esquema.titulo}»: soltar o <u>elegir</u> (varias fotos de la misma
          tabla, juntas)</>}</span>
      </FileDrop>
      {!editando && (
        <div className="row">
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => setFilas(guardada?.filas?.length ? guardada.filas : [filaVacia(esquema)])}>
            {guardada ? 'Revisar lo guardado' : 'Escribir a mano'}</button>
        </div>
      )}
      {borrador && (
        <>
          <p className="small muted">Leído de {borrador.ficheros.join(', ')} ({borrador.metodos.join(', ')}) el {borrador.leido.replace('T', ' ')}:
            revise cada cifra antes de guardar.</p>
          {borrador.avisos.map((a) => <p key={a} className="alert alert-warn small">{a}</p>)}
          {errores.length > 0 && (
            <ul className="alert alert-error small">{errores.slice(0, 30).map((e) => <li key={e}>{e}</li>)}
              {errores.length > 30 && <li>… y {errores.length - 30} más</li>}</ul>
          )}
          {borrador.faltan.length > 0 && <p className="alert alert-warn small">Le falta: {borrador.faltan.join('; ')}.</p>}
        </>
      )}
      {editando && (
        <>
          <div className="table-wrap">
            <table className="table table-ajustada">
              <thead><tr><th>#</th>{esquema.columnas.map((c) => (
                <th key={c.clave}>{c.titulo}{c.unidad !== '-' && <span className="muted"> ({c.unidad})</span>}{c.obligatoria && ' *'}</th>
              ))}<th /></tr></thead>
              <tbody>
                {vista.filas.map((f, k) => {
                  const i = vista.desde + k;
                  return (
                    <tr key={i} style={marcadas.has(i) ? { background: 'var(--error-soft)' } : undefined}>
                      <td className="muted">{i + 1}</td>
                      {esquema.columnas.map((c) => (
                        <td key={c.clave}>
                          <input size={10} value={textoCelda(f[c.clave])} aria-label={`${c.titulo}, fila ${i + 1}`}
                            inputMode={c.numero ? 'decimal' : undefined}
                            onChange={(ev) => setFilas((xs) => editarCelda(xs ?? [], i, c.clave, ev.target.value))} />
                        </td>
                      ))}
                      <td><button type="button" className="btn btn-sm btn-ghost" aria-label={`Quitar la fila ${i + 1}`}
                        onClick={() => setFilas((xs) => quitarFila(xs ?? [], i))}>×</button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {vista.paginas > 1 && (
            <div className="row small">
              <button type="button" className="btn btn-sm btn-ghost" disabled={num === 0} onClick={() => setNum(num - 1)}>‹</button>
              <span>Página {Math.min(num, vista.paginas - 1) + 1} de {vista.paginas} ({filas.length} filas)</span>
              <button type="button" className="btn btn-sm btn-ghost" disabled={num >= vista.paginas - 1} onClick={() => setNum(num + 1)}>›</button>
            </div>
          )}
          <div className="row">
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => setFilas((xs) => [...(xs ?? []), filaVacia(esquema)])}>
              Añadir fila</button>
            <button type="button" className="btn btn-sm btn-primary" disabled={!filas.length} onClick={() => onGuardar(filas)}>Guardar</button>
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => { setFilas(null); if (borrador) onDescartar(); }}>
              {borrador ? 'Descartar lo leído' : 'Cancelar'}</button>
          </div>
        </>
      )}
    </details>
  );
}
