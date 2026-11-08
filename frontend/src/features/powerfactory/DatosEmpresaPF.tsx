import { api } from '../../api/client';
import { useApp } from '../../shared/context';
import type { DatosEmpresa } from '../../api/types';
import { AvisoBeta, MarcaBeta } from '../../shared/MarcaBeta';
import { FileDrop } from '../../shared/ui';

/**
 * Libro de la empresa de la spec 012 (RF-6, RF-7, RF-16, RF-20, RF-21).
 *
 * Se valida al subirlo, sin abrir DIgSILENT: un error dice hoja, fila y columna y el libro
 * anterior sigue. «Aplicar en DIgSILENT» lo escribe en la variación «Datos de
 * confiabilidad» como trabajo del carril de DIgSILENT.
 */
export function DatosEmpresaPF({ project, feeders, libro, onCambio }: {
  project: string; feeders: string[]; libro: DatosEmpresa | null | undefined; onCambio: () => void;
}) {
  const { ws, run, startJob, active } = useApp();
  const pfBusy = Boolean(active.powerfactory);

  const subir = async (file: File) => {
    if (await run(() => api.datosEmpresaSubir(ws.id, project, file))) onCambio();
  };
  const aplicar = async () => {
    await startJob(() => api.datosEmpresaAplicar(ws.id, { project, feeders }));
    onCambio();
  };

  return (
    <div className="card">
      <p className="strong">Libro de la empresa: tasas de falla, tiempos y costes <MarcaBeta clave="confiabilidad" /></p>
      <AvisoBeta clave="confiabilidad" />
      <p className="muted small">La confiabilidad, los reconectadores y los condensadores solo se ejecutan con las cifras de
        la empresa; no se rellenan con valores típicos. <a href={api.datosEmpresaPlantillaUrl(ws.id)}>Descargar la
        plantilla</a>.</p>
      <FileDrop compact accept=".xlsx" disabled={!project} onFiles={([f]) => void subir(f)}>
        <span>{libro
          ? <><strong>{libro.nombre}</strong> · cargado el {libro.cargado.replace('T', ' ')} · reemplazar: soltar otro o <u>elegir</u></>
          : <>Libro de la empresa (.xlsx): soltar o <u>elegir</u></>}</span>
      </FileDrop>
      {libro && (
        <>
          <ul className="small">
            <li>Clases: {libro.clases.join(', ') || 'ninguna'}{libro.tipos.length > 0 && ` · ${libro.tipos.length} tipo(s) con fila propia`}</li>
            <li>Equipos telemandados: {libro.telemandados} · bancos de condensadores: {libro.bancos.length}</li>
            <li>Energía de pérdidas: {libro.coste_energia_kwh ?? '—'} {libro.moneda && `${libro.moneda}/kWh`} · tasa de descuento:{' '}
              {libro.tasa_descuento == null ? '—' : `${(libro.tasa_descuento * 100).toFixed(2)} %`}</li>
          </ul>
          {libro.avisos.map((a) => <p key={a} className="alert alert-warn">{a}</p>)}
          <div className="row">
            <button className="btn btn-pf" disabled={pfBusy || !feeders.length} onClick={aplicar}>
              Aplicar en DIgSILENT ({feeders.length} alim.)</button>
            <small className="muted">{libro.aplicado
              ? `Aplicado el ${libro.aplicado.replace('T', ' ')} en «Sin proyecto» y «Con proyecto».`
              : 'Aún no aplicado: la confiabilidad necesita la variación «Datos de confiabilidad».'}</small>
          </div>
        </>
      )}
    </div>
  );
}
