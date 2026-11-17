import { createContext, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { NavLink, Outlet } from "react-router-dom";
import logo from "../assets/logo-prodesa.png";
import { useAuth } from "../auth/AuthContext";

/** Header estándar css-pro: logo + hbar + eyebrow/h1 + eslogan (nunca cambia). */
export function Header({ titulo = "ADPRO · Presupuesto y control de obra" }: { titulo?: string }) {
  return (
    <header>
      <img className="logo" src={logo} alt="Prodesa" />
      <div className="hbar" />
      <div className="htxt">
        <div className="eyebrow">ERP Prodesa · Prototipo</div>
        <h1>{titulo}</h1>
      </div>
      <div className="tagline">¡Contigo, adonde quieres llegar!</div>
    </header>
  );
}

/**
 * El sidebar es único (estructura css-pro: entradas a la izquierda, resultados en el main).
 * Cada pantalla inyecta sus entradas en el sidebar con <SidePanel>, mediante un portal.
 */
const SideSlotCtx = createContext<HTMLElement | null>(null);

export function SidePanel({ children }: { children: ReactNode }) {
  const slot = useContext(SideSlotCtx);
  return slot ? createPortal(children, slot) : null;
}

const NAV = [
  { sec: "Maestros" },
  { to: "/maestros/insumos", label: "📦 Insumos y precios" },
  { to: "/maestros/proyectos", label: "🏗 Proyectos" },
  { to: "/maestros/edt", label: "🗂 EDT presupuestal" },
  { sec: "Costos" },
  { to: "/apu", label: "🧮 APU" },
  { to: "/presupuestos", label: "📑 Presupuestos" },
  { sec: "Control" },
  { to: "/control/comparativo", label: "⚖ Comparativo" },
  { to: "/control/tablero", label: "📊 Tablero" },
  { to: "/control/avance", label: "📈 Registro de avance" },
  { to: "/control/excel", label: "📥 Excel" },
] as const;

export function Layout() {
  const { user, logout } = useAuth();
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  return (
    <>
      <Header />
      <div className="wrap">
        <aside className="side">
          <div className="usr">
            👤 <b>{user?.nombre ?? user?.username}</b> · {user?.rol}
            <button type="button" onClick={logout}>Salir</button>
          </div>
          <nav>
            <ul className="nav">
              {NAV.map((n, i) =>
                "sec" in n ? (
                  <li key={i} className="sec">{n.sec}</li>
                ) : (
                  <li key={n.to}>
                    <NavLink to={n.to}>{n.label}</NavLink>
                  </li>
                ),
              )}
            </ul>
          </nav>
          <div ref={setSlot} />
        </aside>
        <main className="main">
          <SideSlotCtx.Provider value={slot}>
            <Outlet />
          </SideSlotCtx.Provider>
        </main>
      </div>
    </>
  );
}
