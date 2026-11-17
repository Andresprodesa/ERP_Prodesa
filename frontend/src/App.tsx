import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import LoginPage from "./pages/Login";
import InsumosPage from "./pages/maestros/Insumos";
import ProyectosPage from "./pages/maestros/Proyectos";
import EdtPage from "./pages/maestros/Edt";
import ApuPage from "./pages/apu/ApuPage";
import PresupuestosPage from "./pages/presupuestos/PresupuestosPage";
import VersionPage from "./pages/presupuestos/VersionPage";
import ComparativoPage from "./pages/control/Comparativo";
import TableroPage from "./pages/control/Tablero";
import AvancePage from "./pages/control/Avance";
import ExcelPage from "./pages/control/Excel";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const loc = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/presupuestos" replace />} />
        <Route path="maestros" element={<Navigate to="/maestros/insumos" replace />} />
        <Route path="maestros/insumos" element={<InsumosPage />} />
        <Route path="maestros/proyectos" element={<ProyectosPage />} />
        <Route path="maestros/edt" element={<EdtPage />} />
        <Route path="apu" element={<ApuPage />} />
        <Route path="apu/item/:itemId" element={<ApuPage />} />
        <Route path="presupuestos" element={<PresupuestosPage />} />
        <Route path="presupuestos/:presupuestoId" element={<PresupuestosPage />} />
        <Route path="presupuestos/versiones/:versionId" element={<VersionPage />} />
        <Route path="control" element={<Navigate to="/control/tablero" replace />} />
        <Route path="control/comparativo" element={<ComparativoPage />} />
        <Route path="control/tablero" element={<TableroPage />} />
        <Route path="control/avance" element={<AvancePage />} />
        <Route path="control/excel" element={<ExcelPage />} />
        <Route path="*" element={<Navigate to="/presupuestos" replace />} />
      </Route>
    </Routes>
  );
}
