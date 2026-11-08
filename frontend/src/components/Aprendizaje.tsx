import { useState } from 'react';
import { api } from '../api';
import type { EstadoAprendizaje } from '../types';

const FASES = [
  ['preparacion', 'Preparación'], ['entrenamiento', 'Entrenamiento'], ['seleccion', 'Selección'],
  ['evaluacion', 'Evaluación'], ['publicacion', 'Publicación'], ['activacion', 'Activación'],
  ['aceptacion_nativa', 'Validación en PowerFactory'],
] as const;
const ESTADOS: Record<string, string> = { pendiente: 'Pendiente', hecho: 'Completado',
  en_curso: 'En curso', rechazado: 'Rechazado', bloqueado: 'Bloqueado',
  anterior: 'Conjunto anterior', cancelado: 'Cancelado', ilegible: 'Ilegible' };

/** 050:RF-10: solo representa las fases y motivos que constan en el diario. */
export function VistaAprendizaje({ estado }: { estado: EstadoAprendizaje }) {
  const avisos = estado.bloqueos.flatMap((b) => Array.isArray(b.motivos)
    ? b.motivos.filter((m): m is string => typeof m === 'string') : []);
  return <>
    <table className="small" aria-label="Fases del ciclo de aprendizaje">
      <thead><tr><th>Fase</th><th>Estado</th><th>Motivo y versiones</th></tr></thead>
      <tbody>{FASES.map(([clave, nombre]) => {
        const fase = estado.fases[clave];
        return <tr key={clave}><td>{nombre}</td>
          <td>{fase ? ESTADOS[fase.estado] ?? fase.estado : 'Pendiente'}</td>
          <td>{fase?.motivo || 'Sin evidencia registrada'}
            {Object.entries(fase?.versiones ?? {}).map(([familia, version]) =>
              <div key={familia}>{familia}: {version}</div>)}
          </td></tr>;
      })}</tbody>
    </table>
    {avisos.length > 0 && <ul className="small">{avisos.map((aviso, i) => <li key={i}>{aviso}</li>)}</ul>}
  </>;
}

export function Aprendizaje() {
  const [estado, setEstado] = useState<EstadoAprendizaje | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const consultar = async () => {
    setOcupado(true); setError(null);
    try { setEstado(await api.asistenteAprendizaje()); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setOcupado(false); }
  };
  return <details>
    <summary className="small">Ciclo de aprendizaje y validación</summary>
    <p className="small muted">Un entrenamiento individual no acredita la publicación ni la validación del conjunto.</p>
    <button type="button" disabled={ocupado} onClick={() => void consultar()}>
      {ocupado ? 'Consultando…' : 'Consultar aprendizaje'}
    </button>
    <div aria-live="polite" aria-busy={ocupado}>
      {error && <p role="alert">{error}</p>}
      {estado && <VistaAprendizaje estado={estado} />}
    </div>
  </details>;
}
