import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, TIPOS_VERSION, type TipoVersion, type VersionCopy, type VersionOut } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { SidePanel } from "../../components/Layout";
import { Cargando, ErrorBox, Kpi, mensajeError, PillEstado, Vacio } from "../../components/ui";
import { cop, copCompacto, fecha, hoyISO, pctAFraccion } from "../../lib/format";

interface FormVersion {
  tipo: TipoVersion;
  nombre: string;
  fecha_precios: string;
  adm: string;
  imp: string;
  uti: string;
  iva: string;
}

const FORM_VERSION_INICIAL: FormVersion = {
  tipo: "BASE",
  nombre: "",
  fecha_precios: hoyISO(),
  adm: "0",
  imp: "0",
  uti: "0",
  iva: "19",
};

function FormCopia(props: { origen: VersionOut; onCerrar: () => void; onCopiada: (v: VersionOut) => void }) {
  const { origen } = props;
  const [f, setF] = useState<VersionCopy>({
    tipo: origen.tipo === "BASE" ? "FIC" : origen.tipo,
    nombre: `${origen.nombre} (copia)`,
    recalcular_precios: false,
    fecha_precios: hoyISO(),
  });
  const copiar = useMutation({
    mutationFn: () =>
      api.presupuestos.copiar(origen.id, {
        ...f,
        fecha_precios: f.recalcular_precios ? f.fecha_precios : undefined,
      }),
    onSuccess: props.onCopiada,
  });
  return (
    <div className="det">
      <div className="dh">
        <b>Copiar versión {origen.numero} · {origen.nombre}</b>
        <span className="m">crea un nuevo BORRADOR con AIU, líneas y snapshot de insumos</span>
        <button className="x" type="button" onClick={props.onCerrar}>✕ cerrar</button>
      </div>
      <ErrorBox error={copiar.error} />
      <div className="frm">
        <div>
          <label>Tipo</label>
          <select value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value as TipoVersion })}>
            {TIPOS_VERSION.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <div>
          <label>Nombre</label>
          <input value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} />
        </div>
        <div>
          <label>Recalcular precios</label>
          <select
            value={f.recalcular_precios ? "si" : "no"}
            onChange={(e) => setF({ ...f, recalcular_precios: e.target.value === "si" })}
          >
            <option value="no">No (conservar unitarios)</option>
            <option value="si">Sí, a una nueva fecha</option>
          </select>
        </div>
        <div>
          <label>Nueva fecha de precios</label>
          <input
            type="date"
            disabled={!f.recalcular_precios}
            value={f.fecha_precios ?? ""}
            onChange={(e) => setF({ ...f, fecha_precios: e.target.value })}
          />
        </div>
      </div>
      <button className="btn-s" type="button" disabled={copiar.isPending || !f.nombre} onClick={() => copiar.mutate()}>
        ⧉ Copiar versión
      </button>
    </div>
  );
}

export default function PresupuestosPage() {
  const { presupuestoId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { puede } = useAuth();
  const qc = useQueryClient();
  const pid = presupuestoId ? Number(presupuestoId) : null;

  const [proyectoId, setProyectoId] = useState<number | null>(params.get("proyecto") ? Number(params.get("proyecto")) : null);
  const [nuevoP, setNuevoP] = useState({ codigo: "", nombre: "", etapa_id: "" });
  const [fv, setFv] = useState<FormVersion>(FORM_VERSION_INICIAL);
  const [copiando, setCopiando] = useState<VersionOut | null>(null);
  const [errAccion, setErrAccion] = useState<unknown>(null);

  const proyectos = useQuery({ queryKey: ["proyectos"], queryFn: () => api.maestros.proyectos() });
  const presupuestos = useQuery({
    queryKey: ["presupuestos", proyectoId],
    queryFn: () => api.presupuestos.lista({ proyecto_id: proyectoId ?? undefined }),
  });
  const detalle = useQuery({ queryKey: ["presupuesto", pid], queryFn: () => api.presupuestos.detalle(pid as number), enabled: pid !== null });
  const proyecto = useQuery({
    queryKey: ["proyecto", proyectoId],
    queryFn: () => api.maestros.proyecto(proyectoId as number),
    enabled: proyectoId !== null,
  });

  // Al abrir un presupuesto, sincroniza el proyecto del filtro.
  useEffect(() => {
    if (detalle.data && detalle.data.proyecto_id !== proyectoId) setProyectoId(detalle.data.proyecto_id);
  }, [detalle.data, proyectoId]);

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ["presupuesto", pid] });
    qc.invalidateQueries({ queryKey: ["presupuestos"] });
  };

  const crearPresupuesto = useMutation({
    mutationFn: () =>
      api.presupuestos.crear({
        proyecto_id: proyectoId as number,
        etapa_id: nuevoP.etapa_id ? Number(nuevoP.etapa_id) : null,
        codigo: nuevoP.codigo,
        nombre: nuevoP.nombre,
      }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["presupuestos"] });
      setNuevoP({ codigo: "", nombre: "", etapa_id: "" });
      navigate(`/presupuestos/${p.id}`);
    },
  });

  const crearVersion = useMutation({
    mutationFn: () =>
      api.presupuestos.crearVersion(pid as number, {
        tipo: fv.tipo,
        nombre: fv.nombre,
        fecha_precios: fv.fecha_precios,
        administracion_pct: pctAFraccion(fv.adm),
        imprevistos_pct: pctAFraccion(fv.imp),
        utilidad_pct: pctAFraccion(fv.uti),
        iva_utilidad_pct: pctAFraccion(fv.iva),
      }),
    onSuccess: (v) => {
      refrescar();
      setFv(FORM_VERSION_INICIAL);
      navigate(`/presupuestos/versiones/${v.id}`);
    },
  });

  const accion = useMutation({
    mutationFn: async (a: { tipo: "aprobar" | "cerrar" | "eliminar"; v: VersionOut }) => {
      if (a.tipo === "aprobar") return api.presupuestos.aprobar(a.v.id);
      if (a.tipo === "cerrar") return api.presupuestos.cerrar(a.v.id);
      return api.presupuestos.eliminarVersion(a.v.id);
    },
    onMutate: () => setErrAccion(null),
    onError: (e) => setErrAccion(e),
    onSuccess: refrescar,
  });

  function ejecutar(tipo: "aprobar" | "cerrar" | "eliminar", v: VersionOut) {
    const msg = {
      aprobar: `¿Aprobar la versión ${v.numero} "${v.nombre}"? Quedará inmutable y congelará sus precios.`,
      cerrar: `¿Cerrar la versión ${v.numero} "${v.nombre}"?`,
      eliminar: `¿Eliminar el borrador ${v.numero} "${v.nombre}"? Esta acción no se puede deshacer.`,
    }[tipo];
    if (window.confirm(msg)) accion.mutate({ tipo, v });
  }

  const p = detalle.data;
  const versiones = p?.versiones ?? [];
  const aprobadas = versiones.filter((v) => v.estado !== "BORRADOR");
  const ultimaAprobada = aprobadas[aprobadas.length - 1];

  return (
    <>
      <SidePanel>
        <h2><span className="chev">&gt;</span>Presupuestos</h2>
        <p className="sub">Elige el proyecto y el presupuesto (por proyecto o etapa).</p>
        <label className="lbl">Proyecto</label>
        <select
          value={proyectoId ?? ""}
          onChange={(e) => {
            const id = e.target.value ? Number(e.target.value) : null;
            setProyectoId(id);
            setParams(id ? { proyecto: String(id) } : {});
            if (pid !== null) navigate(id ? `/presupuestos?proyecto=${id}` : "/presupuestos");
          }}
        >
          <option value="">Todos los proyectos</option>
          {proyectos.data?.map((pr) => (
            <option key={pr.id} value={pr.id}>{pr.codigo} · {pr.nombre}</option>
          ))}
        </select>
        <ul className="lst">
          {presupuestos.data?.map((pp) => (
            <li key={pp.id} className={pp.id === pid ? "on" : ""} onClick={() => navigate(`/presupuestos/${pp.id}`)}>
              {pp.codigo} · {pp.nombre}
              <small>{pp.proyecto_codigo}{pp.etapa_codigo ? ` · etapa ${pp.etapa_codigo}` : ""} · {pp.num_versiones} versiones</small>
            </li>
          ))}
          {presupuestos.data?.length === 0 && <li>Sin presupuestos</li>}
        </ul>

        {puede.presupuesto && pid === null && (
          <>
            <hr className="sep" />
            <h2><span className="chev">&gt;</span>Nuevo presupuesto</h2>
            {proyectoId === null ? (
              <p className="sub">Selecciona primero un proyecto.</p>
            ) : (
              <>
                <input type="text" placeholder="Código (ej. PPTO-01)" value={nuevoP.codigo} onChange={(e) => setNuevoP({ ...nuevoP, codigo: e.target.value })} />
                <input type="text" placeholder="Nombre" value={nuevoP.nombre} onChange={(e) => setNuevoP({ ...nuevoP, nombre: e.target.value })} />
                <select value={nuevoP.etapa_id} onChange={(e) => setNuevoP({ ...nuevoP, etapa_id: e.target.value })}>
                  <option value="">Todo el proyecto (sin etapa)</option>
                  {proyecto.data?.etapas.map((et) => (
                    <option key={et.id} value={et.id}>{et.codigo} · {et.nombre}</option>
                  ))}
                </select>
                <button
                  className="btn"
                  type="button"
                  disabled={crearPresupuesto.isPending || !nuevoP.codigo || !nuevoP.nombre}
                  onClick={() => crearPresupuesto.mutate()}
                >
                  + Crear presupuesto
                </button>
                {crearPresupuesto.error && <p className="hint">⚠ {mensajeError(crearPresupuesto.error)}</p>}
              </>
            )}
          </>
        )}

        {puede.presupuesto && pid !== null && (
          <>
            <hr className="sep" />
            <h2><span className="chev">&gt;</span>Nueva versión</h2>
            <p className="sub">Se crea en BORRADOR con número consecutivo.</p>
            <div className="row2">
              <select value={fv.tipo} onChange={(e) => setFv({ ...fv, tipo: e.target.value as TipoVersion })}>
                {TIPOS_VERSION.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <input type="date" value={fv.fecha_precios} onChange={(e) => setFv({ ...fv, fecha_precios: e.target.value })} />
            </div>
            <input type="text" placeholder="Nombre de la versión" value={fv.nombre} onChange={(e) => setFv({ ...fv, nombre: e.target.value })} />
            <label className="lbl">AIU e IVA (%)</label>
            <div className="row2">
              <input type="number" step="0.01" title="Administración %" placeholder="Adm %" value={fv.adm} onChange={(e) => setFv({ ...fv, adm: e.target.value })} />
              <input type="number" step="0.01" title="Imprevistos %" placeholder="Imp %" value={fv.imp} onChange={(e) => setFv({ ...fv, imp: e.target.value })} />
              <input type="number" step="0.01" title="Utilidad %" placeholder="Util %" value={fv.uti} onChange={(e) => setFv({ ...fv, uti: e.target.value })} />
              <input type="number" step="0.01" title="IVA sobre utilidad %" placeholder="IVA util %" value={fv.iva} onChange={(e) => setFv({ ...fv, iva: e.target.value })} />
            </div>
            <button className="btn" type="button" disabled={crearVersion.isPending || !fv.nombre} onClick={() => crearVersion.mutate()}>
              {crearVersion.isPending && <span className="spin" />}+ Crear versión
            </button>
            {crearVersion.error && <p className="hint">⚠ {mensajeError(crearVersion.error)}</p>}
          </>
        )}
      </SidePanel>

      {pid === null ? (
        <div className="card">
          <h3>Presupuestos <span className="tag">{presupuestos.data?.length ?? 0} encontrados</span></h3>
          <ErrorBox error={presupuestos.error} />
          {presupuestos.isLoading ? (
            <Cargando />
          ) : !presupuestos.data?.length ? (
            <Vacio>No hay presupuestos para este filtro.</Vacio>
          ) : (
            <div className="tw">
              <table>
                <thead>
                  <tr><th>Proyecto</th><th>Código</th><th>Nombre</th><th>Etapa</th><th>Versiones</th></tr>
                </thead>
                <tbody>
                  {presupuestos.data.map((pp) => (
                    <tr key={pp.id} onClick={() => navigate(`/presupuestos/${pp.id}`)}>
                      <td>{pp.proyecto_codigo} · {pp.proyecto_nombre}</td>
                      <td>{pp.codigo}</td>
                      <td>{pp.nombre}</td>
                      <td className="c">{pp.etapa_codigo ?? "—"}</td>
                      <td className="n">{pp.num_versiones}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <>
          <ErrorBox error={detalle.error} />
          {detalle.isLoading && <Cargando />}
          {p && (
            <>
              <div className="kpis">
                <Kpi k="Presupuesto" v={p.codigo} s={`${p.proyecto_codigo} · ${p.proyecto_nombre}`} tono="b" />
                <Kpi k="Versiones" v={versiones.length} s={`${aprobadas.length} aprobadas/cerradas`} tono="b" />
                <Kpi
                  k="Última aprobada"
                  v={ultimaAprobada ? copCompacto(ultimaAprobada.total_presupuesto) : "—"}
                  s={ultimaAprobada ? `v${ultimaAprobada.numero} ${ultimaAprobada.tipo} · total con AIU` : "sin versiones aprobadas"}
                />
              </div>

              <div className="card">
                <h3>{p.nombre} <span className="tag">{p.descripcion ?? ""}</span></h3>
                <ErrorBox error={errAccion} />
                {versiones.length === 0 ? (
                  <Vacio>Este presupuesto aún no tiene versiones. Créala desde el panel izquierdo.</Vacio>
                ) : (
                  <div className="tw">
                    <table>
                      <thead>
                        <tr>
                          <th>N°</th><th>Tipo</th><th>Nombre</th><th>Estado</th><th>Precios a</th><th>Ciudad</th>
                          <th>Líneas</th><th>Costo directo</th><th>Total</th><th>Origen</th><th>Acciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        {versiones.map((v) => (
                          <tr key={v.id} className={copiando?.id === v.id ? "sel" : ""}>
                            <td className="c">{v.numero}</td>
                            <td className="c"><span className="pill ap">{v.tipo}</span></td>
                            <td>
                              <Link to={`/presupuestos/versiones/${v.id}`}>{v.nombre}</Link>
                            </td>
                            <td className="c"><PillEstado estado={v.estado} /></td>
                            <td className="c">{fecha(v.fecha_precios)}</td>
                            <td className="c">{v.ciudad_precios_codigo}</td>
                            <td className="n">{v.num_lineas}</td>
                            <td className="n">{cop(v.total_costo_directo)}</td>
                            <td className="n">{cop(v.total_presupuesto)}</td>
                            <td className="c">{v.version_origen_id ? `de v${versiones.find((o) => o.id === v.version_origen_id)?.numero ?? "?"}` : "—"}</td>
                            <td>
                              <div className="acciones">
                                <Link className="btn-s gh" to={`/presupuestos/versiones/${v.id}`}>Abrir</Link>
                                {puede.presupuesto && (
                                  <button className="btn-s gh" type="button" onClick={() => setCopiando(v)}>⧉ Copiar</button>
                                )}
                                {puede.aprobacion && v.estado === "BORRADOR" && (
                                  <button className="btn-s gh" type="button" disabled={accion.isPending} onClick={() => ejecutar("aprobar", v)}>
                                    ✔ Aprobar
                                  </button>
                                )}
                                {puede.aprobacion && v.estado === "APROBADO" && (
                                  <button className="btn-s gh" type="button" disabled={accion.isPending} onClick={() => ejecutar("cerrar", v)}>
                                    🔒 Cerrar
                                  </button>
                                )}
                                {puede.presupuesto && v.estado === "BORRADOR" && (
                                  <button className="btn-s gh" type="button" disabled={accion.isPending} onClick={() => ejecutar("eliminar", v)}>
                                    🗑
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {copiando && (
                  <FormCopia
                    origen={copiando}
                    onCerrar={() => setCopiando(null)}
                    onCopiada={(nv) => {
                      setCopiando(null);
                      refrescar();
                      navigate(`/presupuestos/versiones/${nv.id}`);
                    }}
                  />
                )}
                <p className="note">
                  Las versiones APROBADAS y CERRADAS son inmutables y conservan el snapshot de precios con que se aprobaron.
                </p>
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}
