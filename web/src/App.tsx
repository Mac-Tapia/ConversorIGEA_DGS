const modules = [
  'Proyecto',
  'Diagnóstico G1–G4',
  'Unifilar',
  'Mapa',
  'PowerFactory G5–G6',
  'Evidencias',
]

export default function App() {
  return (
    <div className="cockpit">
      <aside className="sidebar">
        <strong>ELDICA GRID</strong>
        <nav aria-label="Módulos del proyecto">
          {modules.map((label) => <button key={label}>{label}</button>)}
        </nav>
      </aside>
      <main>
        <header><h1>Proyecto local</h1><span className="badge">G1–G6</span></header>
        <section className="welcome">
          <h2>Seleccione RED, CARGA y BD_Equipo</h2>
          <p>Los TXT originales se registrarán por hash y permanecerán inmutables.</p>
        </section>
      </main>
    </div>
  )
}
