import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type EstadoProyecto, type TipoProyecto } from "../../api/client";
import { SidePanel } from "../../components/Layout";
import { Cargando, ErrorBox, Kpi, Vacio } from "../../components/ui";
import { fecha } from "../../lib/format";

const ESTADOS: EstadoProyecto[] = ["PLANEACION", "EN_EJECUCION", "TERMINADO", "SUSPENDIDO"];
const TIPOS: TipoProyecto[] = ["VIS", "VIP", "NO_VIS"];

export default function ProyectosPage() {
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState<EstadoProyecto | "">("");
  const [tipo, setTipo] = useState<TipoProyecto | "">("");
  const [sel, setSel] = useState<number | null>(null);

  const proyectos = useQuery({
    queryKey: ["proyectos", q, estado, tipo],
    queryFn: () => api.maestros.proyectos({ q, estado, tipo }),
  });
  const detalle = useQuery({
    queryKey: ["proyecto", sel],
    queryFn: () => api.maestros.proyecto(sel as number),
    enabled: sel !== null,
  });

  const lista = proyectos.data ?? [];
  const unidades = lista.reduce((s, p) => s + (p.numero_unidades ?? 0), 0);

  return (
    <>
      <SidePanel>
        <h2><span className="chev">&gt;</span>Proyectos</h2>
        <p className="sub">Filtra por nombre, estado o tipo de vivienda.</p>
        <input type="text" placeholder="Buscar proyecto…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={estado} onChange={(e) => setEstado(e.target.value as EstadoProyecto | "")}>
          <option value="">Todos los estados</option>
          {ESTADOS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select value={tipo} onChange={(e) => setTipo(e.target.value as TipoProyecto | "")}>
          <option value="">Todos los tipos</option>
          {TIPOS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </SidePanel>

      <div className="kpis">
        <Kpi k="Proyectos" v={lista.length} tono="b" />
        <Kpi k="Unidades de vivienda" v={unidades.toLocaleString("es-CO")} s="suma de los proyectos listados" tono="b" />
        <Kpi k="En ejecución" v={lista.filter((p) => p.estado === "EN_EJECUCION").length} />
      </div>

      <div className="card">
        <h3>Proyectos <span className="tag">clic para ver etapas y torres</span></h3>
        <ErrorBox error={proyectos.error} />
        {proyectos.isLoading ? (
          <Cargando />
        ) : lista.length === 0 ? (
          <Vacio>No hay proyectos.</Vacio>
        ) : (
          <div className="tw">
            <table>
              <thead>
                <tr>
                  <th>Código</th><th>Nombre</th><th>Ciudad</th><th>Tipo</th><th>Estado</th>
                  <th>Inicio</th><th>Fin estimado</th><th>Unidades</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((p) => (
                  <tr key={p.id} className={p.id === sel ? "sel" : ""} onClick={() => setSel(p.id)}>
                    <td>{p.codigo}</td>
                    <td>{p.nombre}</td>
                    <td>{p.ciudad_nombre}</td>
                    <td className="c"><span className="pill ap">{p.tipo}</span></td>
                    <td className="c">{p.estado}</td>
                    <td className="c">{fecha(p.fecha_inicio)}</td>
                    <td className="c">{fecha(p.fecha_fin_estimada)}</td>
                    <td className="n">{p.numero_unidades ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {sel !== null && (
          <div className="det">
            <ErrorBox error={detalle.error} />
            {detalle.isLoading || !detalle.data ? (
              <Cargando />
            ) : (
              <>
                <div className="dh">
                  <b>{detalle.data.codigo} · {detalle.data.nombre}</b>
                  <span className="m">{detalle.data.ciudad_nombre} · {detalle.data.tipo}</span>
                  <Link className="btn-s gh" to={`/presupuestos?proyecto=${detalle.data.id}`}>📑 Ver presupuestos</Link>
                  <button className="x" type="button" onClick={() => setSel(null)}>✕ cerrar</button>
                </div>
                {detalle.data.descripcion && <p className="note">{detalle.data.descripcion}</p>}
                <h4>Etapas y torres</h4>
                {detalle.data.etapas.length === 0 ? (
                  <Vacio>Sin etapas registradas.</Vacio>
                ) : (
                  <div className="tw">
                    <table>
                      <thead>
                        <tr><th>Etapa</th><th>Torre</th><th>Pisos</th><th>Unidades</th></tr>
                      </thead>
                      <tbody>
                        {detalle.data.etapas.flatMap((et) => [
                          <tr key={`e${et.id}`} className="tot">
                            <td>{et.codigo} · {et.nombre}</td>
                            <td>{et.torres.length} torre(s)</td>
                            <td className="n" />
                            <td className="n">{et.numero_unidades ?? "—"}</td>
                          </tr>,
                          ...et.torres.map((t) => (
                            <tr key={`t${t.id}`}>
                              <td />
                              <td>{t.codigo} · {t.nombre}</td>
                              <td className="n">{t.numero_pisos ?? "—"}</td>
                              <td className="n">{t.numero_unidades ?? "—"}</td>
                            </tr>
                          )),
                        ])}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}
