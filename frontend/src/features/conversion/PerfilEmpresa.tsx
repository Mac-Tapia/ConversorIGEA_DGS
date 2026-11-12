import { useEffect, useState } from 'react';
import { api, type PerfilEstado } from '../../api/client';
import { useApp } from '../../shared/context';

/**
 * 086:RF-59: un perfil guardado vuelve a leer el estado del servidor, que es de donde el resto de la página lee el
 * perfil. rc5 (2026-11-12): tras «Cargar perfil», el CRS de origen seguía diciendo «Sin perfil de empresa…» hasta
 * recargar, aunque la conversión ya usaba el CRS del perfil. Un perfil rechazado no cambia nada que releer.
 */
export async function guardarPerfil(
  guardar: () => Promise<PerfilEstado | undefined>, ponerAlDia: () => void,
): Promise<PerfilEstado | undefined> {
  const r = await guardar();
  if (r) ponerAlDia();
  return r;
}

/**
 * 086:RF-56: el perfil de la empresa se carga desde la web, no a mano en la carpeta de datos.
 * Se valida antes de guardar (como «validar-perfil»): con errores no se toca el que hay.
 */
export function PerfilEmpresa() {
  const { run, refreshHealth } = useApp();
  const [estado, setEstado] = useState<PerfilEstado | null>(null);
  const [perfil, setPerfil] = useState<File | null>(null);
  const [estructura, setEstructura] = useState<File | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    void run(() => api.perfilEstado()).then((r) => r && setEstado(r));
  }, [run]);

  const guardar = async () => {
    if (!perfil) return;
    setOcupado(true);
    const r = await guardarPerfil(() => run(() => api.perfilGuardar(perfil, estructura)), refreshHealth);
    setOcupado(false);
    if (r) {
      setEstado(r);
      setPerfil(null);
      setEstructura(null);
    }
  };

  const necesarias = estado?.faltan.filter((f) => !f.opcional) ?? [];
  return (
    <section className="card">
      <header className="card-head"><h2>Perfil de la empresa</h2></header>
      <p className="muted">
        Las convenciones de su empresa: sistema de coordenadas, bancos por tensión, fichas propias, estructura de
        zonales y SET, informes. Se comprueba antes de guardar; si tiene errores, se queda el que hay.
      </p>
      {estado && (
        <p>
          {estado.existe ? <>Perfil activo en <code>{estado.ruta}</code>.</> : <>Todavía no hay perfil: el programa no supone nada.</>}
          {estado.errores.length > 0 && (
            <small className="alert alert-error">Errores: {estado.errores.join('; ')}</small>
          )}
        </p>
      )}
      <div className="options-grid">
        <label className="field">
          <span>Perfil (JSON)</span>
          <input type="file" accept=".json,application/json" disabled={ocupado}
            onChange={(e) => setPerfil(e.target.files?.[0] ?? null)} />
        </label>
        <label className="field">
          <span>Estructura de la empresa (JSON, si el perfil la nombra)</span>
          <input type="file" accept=".json,application/json" disabled={ocupado}
            onChange={(e) => setEstructura(e.target.files?.[0] ?? null)} />
        </label>
      </div>
      <button className="btn" disabled={!perfil || ocupado} onClick={() => void guardar()}>
        {ocupado ? 'Comprobando…' : 'Cargar perfil'}
      </button>
      {necesarias.length > 0 && (
        <details>
          <summary>Faltan {necesarias.length} dato(s) que conviene dar</summary>
          <ul>
            {necesarias.map((f) => <li key={f.clave}><code>{f.clave}</code>: {f.funcion}. Sin él: {f.si_falta}</li>)}
          </ul>
        </details>
      )}
    </section>
  );
}
