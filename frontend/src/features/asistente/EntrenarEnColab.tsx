import { useState } from 'react';
import { api } from '../../api/client';
import { useApp } from '../../shared/context';
import type { ColabEstado, ColabPaquete, ColabPrevia, ColabTraer } from '../../api/types';

/** 113: entrenar en Colab Pro como opción; entrenar en este equipo sigue igual sin Drive (RF-16). */
export function EntrenarEnColab() {
  const { run } = useApp();
  const [estado, setEstado] = useState<ColabEstado | null>(null);
  const [familia, setFamilia] = useState('asistente_redaccion');
  const [dataset, setDataset] = useState('');
  const [previa, setPrevia] = useState<ColabPrevia | null>(null);
  const [paquete, setPaquete] = useState<ColabPaquete | null>(null);
  const [traidos, setTraidos] = useState<ColabTraer | null>(null);
  const leer = () => void run(api.colabEstado).then((r) => r && setEstado(r));
  const colab = estado?.opciones.find((o) => o.donde === 'colab');
  return (
    <details onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) leer(); }}>
      <summary className="small">Entrenar en Colab Pro</summary>
      {estado?.reentrenar.map((r) => <p key={String(r.familia)} className="small">
        <strong>{String(r.familia)}: {String(r.nuevos)} ejemplos nuevos</strong> desde el último paquete
        ({String(r.ejemplos_al_preparar)} → {String(r.ejemplos)}). Conviene reentrenarla, aquí o en Colab.</p>)}
      {estado && !colab?.disponible && <p className="muted small">Sin Google Drive para escritorio: se entrena en este
        equipo.</p>}
      {estado && colab?.disponible && <div className="stack">
        <label className="small">Familia{' '}
          <select value={familia} onChange={(e) => { setFamilia(e.target.value); setPrevia(null); }}>
            {estado.familias.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </label>
        <label className="small">Carpeta del dataset{' '}
          <input value={dataset} onChange={(e) => { setDataset(e.target.value); setPrevia(null); }} />
        </label>
        <button className="btn btn-ghost" disabled={!dataset.trim()}
          onClick={() => void run(() => api.colabPrevia(familia, dataset.trim())).then((r) => r && setPrevia(r))}>
          Revisar qué sube</button>
        {previa && <p className="small">
          {previa.ficheros} ficheros, {(previa.bytes / 2 ** 20).toFixed(1)} MiB, revisión {previa.revision.slice(0, 8)};
          {' '}{previa.anonimizacion}.
          {!previa.en_github && <strong> La revisión no está en GitHub: súbela antes.</strong>}
          {previa.cambios_sin_commit.length > 0 &&
            <strong> {previa.cambios_sin_commit.length} cambios sin commit: Colab no los verá.</strong>}
          {previa.prohibidos.map((x) => <span key={x} className="error"> No sale: {x}.</span>)}
        </p>}
        {previa?.confirmacion && <button className="btn btn-primary"
          onClick={() => void run(() => api.colabPreparar(familia, dataset.trim(), previa.confirmacion ?? ''))
            .then((r) => { if (r) { setPaquete(r); setPrevia(null); } })}>Subir a Drive</button>}
        {paquete && <p className="small">Paquete {paquete.paquete} en Drive.{' '}
          <a href={paquete.colab} target="_blank" rel="noreferrer">Abrir Colab</a></p>}
        <button className="btn btn-ghost"
          onClick={() => void run(api.colabTraer).then((r) => r && setTraidos(r))}>Traer los candidatos</button>
        {traidos && <ul className="small">
          {traidos.candidatos.length === 0 && <li>No hay candidatos en Drive.</li>}
          {traidos.candidatos.map((c) => <li key={String(c.candidato)}>{String(c.candidato)}:{' '}
            {c.aceptado ? `traído sin activar; su puerta: ${String(c.puerta)}` : String(c.motivo)}</li>)}
        </ul>}
      </div>}
    </details>
  );
}
