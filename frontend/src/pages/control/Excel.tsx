import { useRef, useState, type DragEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type ImportResultado } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { SidePanel } from "../../components/Layout";
import { SelectorPresupuesto, SelectorVersion } from "../../components/Selectores";
import { ErrorBox, Kpi } from "../../components/ui";

type Modo = "agregar" | "reemplazar";

export default function ExcelPage() {
  const { puede } = useAuth();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [pid, setPid] = useState<number | null>(null);
  const [vid, setVid] = useState<number | null>(null);
  const [vidExp, setVidExp] = useState<number | null>(null);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [modo, setModo] = useState<Modo>("agregar");
  const [over, setOver] = useState(false);
  const [res, setRes] = useState<ImportResultado | null>(null);
  const [errDescarga, setErrDescarga] = useState<unknown>(null);

  const importar = useMutation({
    mutationFn: () => api.control.excel.importar(vid as number, archivo as File, modo),
    onMutate: () => setRes(null),
    onSuccess: (r) => {
      setRes(r);
      if (r.aplicado) {
        for (const k of ["version", "lineas", "resumen", "explosion"]) qc.invalidateQueries({ queryKey: [k, vid] });
        qc.invalidateQueries({ queryKey: ["presupuesto"] });
      }
    },
  });

  const descargar = (fn: () => Promise<void>) => {
    setErrDescarga(null);
    fn().catch(setErrDescarga);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setArchivo(f);
  };

  return (
    <>
      <SidePanel>
        <h2><span className="chev">&gt;</span>Importar presupuesto</h2>
        <p className="sub">Carga líneas desde la plantilla Excel a una versión en BORRADOR. Todo o nada.</p>
        <SelectorPresupuesto label="Presupuesto" value={pid} onChange={(id) => { setPid(id); setVid(null); setVidExp(null); }} />
        <label className="lbl">Versión destino (borrador)</label>
        <SelectorVersion presupuestoId={pid} value={vid} onChange={(id) => setVid(id)} soloBorrador vacio="Selecciona borrador…" />
        <div
          className={`drop ${over ? "over" : ""} ${archivo ? "has" : ""}`}
          onClick={() => input.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
          role="button"
          tabIndex={0}
        >
          <div className="ic">📄</div>
          <div className="txt">{archivo ? archivo.name : "Arrastra aquí el .xlsx o haz clic"}</div>
        </div>
        <input
          ref={input}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          hidden
          onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
        />
        <div className={`opt ${modo === "agregar" ? "on" : ""}`} onClick={() => setModo("agregar")}>
          <span className="dot" />
          <div><div className="t">Agregar / actualizar</div><div className="d">Crea líneas nuevas y actualiza las existentes.</div></div>
        </div>
        <div className={`opt ${modo === "reemplazar" ? "on" : ""}`} onClick={() => setModo("reemplazar")}>
          <span className="dot" />
          <div><div className="t">Reemplazar</div><div className="d">Borra todas las líneas de la versión y carga el archivo.</div></div>
        </div>
        <button
          className="btn"
          type="button"
          disabled={!puede.presupuesto || !vid || !archivo || importar.isPending}
          onClick={() => {
            if (modo === "reemplazar" && !window.confirm("Se eliminarán todas las líneas actuales de la versión. ¿Continuar?")) return;
            importar.mutate();
          }}
        >
          {importar.isPending && <span className="spin" />}📥 Importar
        </button>
        <p className="hint">
          {!puede.presupuesto ? "Tu rol no permite importar." : !vid ? "Elige una versión en borrador." : !archivo ? "Falta el archivo." : "Listo para importar."}
        </p>
      </SidePanel>

      <div className="card intro">
        <p><span className="badge">EXCEL</span>Plantilla: hoja <b>Presupuesto</b>, encabezados en la fila 1:</p>
        <p><code>codigo_item | descripcion | unidad | cantidad | valor_unitario | observacion</code></p>
        <p className="note">
          descripción y unidad son informativas · valor_unitario vacío = se toma del APU del ítem; con valor = origen IMPORTADO.
        </p>
        <div className="toolbar">
          <button className="btn-s gh" type="button" onClick={() => descargar(() => api.control.excel.plantilla())}>📄 Descargar plantilla</button>
        </div>
        <ErrorBox error={errDescarga} />
      </div>

      {(importar.error || res) && (
        <div className="card">
          <h3>Resultado de la importación</h3>
          <ErrorBox error={importar.error} />
          {res && (
            <>
              <div className="kpis">
                <Kpi k="Aplicado" v={res.aplicado ? "Sí" : "No"} s={res.aplicado ? "cambios guardados" : "no se aplicó ningún cambio"} tono={res.aplicado ? "g" : "r"} />
                <Kpi k="Creadas" v={res.lineas_creadas} tono="b" />
                <Kpi k="Actualizadas" v={res.lineas_actualizadas} tono="b" />
                <Kpi k="Eliminadas" v={res.lineas_eliminadas} tono="b" />
              </div>
              {res.errores.length > 0 && (
                <div className="tw">
                  <table>
                    <thead><tr><th>Fila</th><th>Columna</th><th>Error</th></tr></thead>
                    <tbody>
                      {res.errores.map((e, i) => (
                        <tr key={i}>
                          <td className="n">{e.fila ?? "—"}</td>
                          <td>{e.columna ?? "—"}</td>
                          <td className="pos">{e.mensaje}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {res.advertencias.length > 0 && <div className="tdesc">⚠ {res.advertencias.join(" · ")}</div>}
              {res.aplicado && vid && (
                <div className="toolbar"><Link className="btn-s gh" to={`/presupuestos/versiones/${vid}`}>Ver versión</Link></div>
              )}
            </>
          )}
        </div>
      )}

      <div className="card">
        <h3>Exportar a Excel</h3>
        <div className="frm">
          <div>
            <label>Versión a exportar</label>
            <SelectorVersion presupuestoId={pid} value={vidExp} onChange={(id) => setVidExp(id)} />
          </div>
        </div>
        <div className="acciones">
          <button className="btn-s gh" type="button" disabled={!vidExp} onClick={() => descargar(() => api.control.excel.presupuesto(vidExp as number))}>
            📤 Presupuesto (Resumen + líneas)
          </button>
          <button className="btn-s gh" type="button" disabled={!vidExp} onClick={() => descargar(() => api.control.excel.explosion(vidExp as number))}>
            📤 Explosión de insumos
          </button>
          <Link className="btn-s gh" to="/control/comparativo">⚖ Comparativo → exportar desde su pantalla</Link>
        </div>
      </div>
    </>
  );
}
