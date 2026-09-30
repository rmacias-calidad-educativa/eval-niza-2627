import html
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Resultados académicos | NIZA", page_icon="📊", layout="wide")

GRADE_MAP = {3:"TERCERO",4:"CUARTO",5:"QUINTO",6:"SEXTO",7:"SEPTIMO",8:"OCTAVO",9:"NOVENO",10:"DECIMO",11:"UNDECIMO"}
DEFAULT_FILE = Path(__file__).parent / "data" / "base_resultados.xlsx"

@st.cache_data(show_spinner=False)
def load_data(source):
    df = pd.read_excel(source)
    for c in ["Sede","Grado","AULA","Nombre","Apellido","QuizName","Pregunta","RespuestaEst","Descriptor"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).map(lambda x: html.unescape(html.unescape(x)).replace("\xa0", " ").strip())
    df["IsCorrect"] = pd.to_numeric(df["IsCorrect"], errors="coerce")
    df["AttemptId"] = df["AttemptId"].astype(str)
    if "IdentiEstudiante" in df.columns:
        df["IdentiEstudiante"] = df["IdentiEstudiante"].astype(str)
    if "TimeCompleted" in df.columns:
        df["TimeCompleted"] = pd.to_datetime(df["TimeCompleted"], errors="coerce", utc=True)

    # Duplicados generados por joins: mismos datos de respuesta con distinto grado/aula.
    dedup_cols = [c for c in ["AttemptId","QuizName","Pregunta","RespuestaEst","IsCorrect","Descriptor"] if c in df.columns]
    df["_duplicado_join"] = df.duplicated(dedup_cols, keep="first")
    clean = df.drop_duplicates(dedup_cols, keep="first").copy()

    # Grado inferido desde el nombre de la prueba, más estable que el campo Grado en intentos inconsistentes.
    def infer_grade(q):
        m = re.search(r"(\d{1,2})\s*°", str(q))
        return GRADE_MAP.get(int(m.group(1))) if m else None
    clean["Grado_prueba"] = clean["QuizName"].map(infer_grade)
    clean["Grado_analisis"] = clean["Grado_prueba"].fillna(clean["Grado"])

    # Aula canónica: solo se conserva cuando el AttemptId tiene una única aula.
    aula_n = clean.groupby("AttemptId")["AULA"].nunique(dropna=True)
    aula_first = clean.groupby("AttemptId")["AULA"].first()
    aula_map = pd.Series(np.where(aula_n.eq(1), aula_first, "AMBIGUA"), index=aula_n.index)
    clean["AULA_analisis"] = clean["AttemptId"].map(aula_map)

    # Diagnóstico de inconsistencias del intento.
    for col in ["Grado","AULA"]:
        nuniq = clean.groupby("AttemptId")[col].nunique(dropna=True)
        clean[f"{col}_inconsistente"] = clean["AttemptId"].map(nuniq.gt(1))
    return df, clean


def attempt_table(df):
    agg = df.groupby(["AttemptId","QuizName","Grado_analisis","AULA_analisis"], dropna=False).agg(
        Puntaje=("IsCorrect","mean"),
        Respuestas=("IsCorrect","count"),
        Correctas=("IsCorrect","sum"),
        Estudiante=("IdentiEstudiante","first"),
        Sede=("Sede","first")
    ).reset_index()
    agg["Puntaje"] *= 100
    return agg


def cronbach_alpha(wide):
    x = wide.dropna(axis=0, how="any")
    if x.shape[0] < 3 or x.shape[1] < 2:
        return np.nan, x.shape[0]
    item_var = x.var(axis=0, ddof=1).sum()
    total = x.sum(axis=1)
    total_var = total.var(ddof=1)
    if not np.isfinite(total_var) or total_var <= 0:
        return np.nan, x.shape[0]
    k = x.shape[1]
    return float(k/(k-1) * (1-item_var/total_var)), x.shape[0]


def psychometrics_for_quiz(dfq):
    # Pregunta se usa como identificador cuando es suficientemente única.
    # En pruebas con rótulos repetidos (p. ej. “Espacio 1”), se advierte y los resultados deben interpretarse con cautela.
    d = dfq.dropna(subset=["IsCorrect"]).copy()
    d["Pregunta"] = d["Pregunta"].fillna("").astype(str)
    dup_within = d.duplicated(["AttemptId","Pregunta"], keep=False)
    repeated_rate = dup_within.mean() if len(d) else 0
    # Para matrices, conserva una observación por intento-pregunta.
    dm = d.drop_duplicates(["AttemptId","Pregunta"], keep="first")
    wide = dm.pivot(index="AttemptId", columns="Pregunta", values="IsCorrect")
    alpha, n_complete = cronbach_alpha(wide)

    rows = []
    for q, g in dm.groupby("Pregunta", dropna=False):
        p = g["IsCorrect"].mean()
        aids = g["AttemptId"]
        rest = dm[dm["AttemptId"].isin(aids) & (dm["Pregunta"] != q)].groupby("AttemptId")["IsCorrect"].mean()
        xy = g.set_index("AttemptId")[["IsCorrect"]].join(rest.rename("rest"), how="inner").dropna()
        disc = xy["IsCorrect"].corr(xy["rest"]) if len(xy) >= 3 and xy["IsCorrect"].nunique() > 1 and xy["rest"].nunique() > 1 else np.nan
        descriptor = g["Descriptor"].mode().iloc[0] if len(g["Descriptor"].mode()) else ""
        rows.append({"Pregunta":q, "Descriptor":descriptor, "n":len(g), "Dificultad_p":p, "Discriminacion":disc})
    return pd.DataFrame(rows), alpha, n_complete, repeated_rate

uploaded = st.sidebar.file_uploader("Usar otro archivo XLSX", type=["xlsx"])
source = uploaded if uploaded is not None else DEFAULT_FILE
raw, df = load_data(source)

st.title("📊 Visualizador de resultados académicos")
st.caption("Rendimiento, calidad de datos y análisis psicométrico en un mismo tablero.")

# Filtros
st.sidebar.header("Filtros")
filters = {}
for col, label in [("Sede","Sede"),("Grado_analisis","Grado"),("AULA_analisis","Aula"),("QuizName","Prueba"),("Descriptor","Descriptor")]:
    opts = sorted([x for x in df[col].dropna().astype(str).unique() if x != ""])
    sel = st.sidebar.multiselect(label, opts)
    filters[col] = sel

f = df.copy()
for col, sel in filters.items():
    if sel:
        f = f[f[col].astype(str).isin(sel)]

att = attempt_table(f)

# KPIs
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Respuestas analizadas", f"{len(f):,}".replace(",","."))
c2.metric("Intentos", f"{att['AttemptId'].nunique():,}".replace(",","."))
c3.metric("Estudiantes", f"{f['IdentiEstudiante'].nunique():,}".replace(",","."))
c4.metric("Acierto global", f"{f['IsCorrect'].mean()*100:.1f}%" if len(f) else "–")
c5.metric("Puntaje medio", f"{att['Puntaje'].mean():.1f}%" if len(att) else "–")

pages = st.tabs(["Panorama","Competencias","Estudiantes","Psicometría","Calidad de datos","Datos"])

with pages[0]:
    st.subheader("Panorama de desempeño")
    left,right = st.columns([1.15,1])
    with left:
        g = att.groupby("Grado_analisis", as_index=False).agg(Puntaje=("Puntaje","mean"), Intentos=("AttemptId","nunique"))
        order = [GRADE_MAP[i] for i in sorted(GRADE_MAP) if GRADE_MAP[i] in set(g["Grado_analisis"])]
        fig = px.bar(g, x="Grado_analisis", y="Puntaje", text_auto=".1f", category_orders={"Grado_analisis":order},
                     labels={"Grado_analisis":"Grado","Puntaje":"Puntaje medio (%)"}, title="Puntaje medio por grado")
        fig.update_yaxes(range=[0,100])
        st.plotly_chart(fig, use_container_width=True)
    with right:
        fig = px.histogram(att, x="Puntaje", nbins=20, labels={"Puntaje":"Puntaje (%)"}, title="Distribución de puntajes por intento")
        fig.update_xaxes(range=[0,100])
        st.plotly_chart(fig, use_container_width=True)

    q = att.groupby("QuizName", as_index=False).agg(Puntaje=("Puntaje","mean"), Intentos=("AttemptId","nunique")).sort_values("Puntaje")
    fig = px.bar(q, y="QuizName", x="Puntaje", orientation="h", text_auto=".1f",
                 labels={"QuizName":"Prueba","Puntaje":"Puntaje medio (%)"}, title="Desempeño por prueba")
    fig.update_xaxes(range=[0,100])
    fig.update_layout(height=max(450, 25*len(q)))
    st.plotly_chart(fig, use_container_width=True)

with pages[1]:
    st.subheader("Resultados por descriptor / competencia")
    desc = f.groupby("Descriptor", as_index=False).agg(Acierto=("IsCorrect","mean"), Respuestas=("IsCorrect","count"))
    desc["Acierto"] *= 100
    desc = desc.sort_values("Acierto")
    fig = px.bar(desc, y="Descriptor", x="Acierto", orientation="h", text_auto=".1f",
                 labels={"Acierto":"Acierto (%)"}, title="Acierto por descriptor")
    fig.update_xaxes(range=[0,100])
    fig.update_layout(height=max(450, 26*len(desc)))
    st.plotly_chart(fig, use_container_width=True)

    heat = f.groupby(["Grado_analisis","Descriptor"], as_index=False)["IsCorrect"].mean()
    heat["Acierto"] = heat["IsCorrect"]*100
    piv = heat.pivot(index="Descriptor", columns="Grado_analisis", values="Acierto")
    if not piv.empty:
        fig = px.imshow(piv, text_auto=".0f", aspect="auto", zmin=0, zmax=100,
                        labels={"color":"Acierto %"}, title="Mapa de desempeño por grado y descriptor")
        st.plotly_chart(fig, use_container_width=True)

with pages[2]:
    st.subheader("Resultados por estudiante")
    student = f.groupby(["IdentiEstudiante","Nombre","Apellido"], as_index=False).agg(
        Puntaje=("IsCorrect","mean"), Respuestas=("IsCorrect","count"), Pruebas=("QuizName","nunique"))
    student["Puntaje"] *= 100
    st.dataframe(student.sort_values("Puntaje", ascending=False), use_container_width=True, hide_index=True)
    st.download_button("Descargar tabla de estudiantes", student.to_csv(index=False).encode("utf-8-sig"), "resultados_estudiantes.csv", "text/csv")

with pages[3]:
    st.subheader("Análisis psicométrico")
    quizzes = sorted(f["QuizName"].dropna().unique())
    if quizzes:
        quiz = st.selectbox("Selecciona una prueba", quizzes)
        qdf = f[f["QuizName"] == quiz]
        items, alpha, n_complete, repeated_rate = psychometrics_for_quiz(qdf)
        a,b,c,d = st.columns(4)
        a.metric("Intentos", qdf["AttemptId"].nunique())
        b.metric("Ítems identificados", items.shape[0])
        c.metric("Alfa de Cronbach", "–" if pd.isna(alpha) else f"{alpha:.3f}")
        d.metric("Casos completos para α", n_complete)
        if repeated_rate > 0.05:
            st.warning(f"{repeated_rate:.1%} de las filas repiten el texto de pregunta dentro del mismo intento. La base no trae un ID de ítem; por eso la psicometría de esta prueba debe interpretarse con cautela.")
        st.caption("Dificultad p = proporción de respuestas correctas. Discriminación = correlación ítem-resto; valores negativos o cercanos a cero requieren revisión.")
        if not items.empty:
            fig = px.scatter(items, x="Dificultad_p", y="Discriminacion", hover_data=["Descriptor","Pregunta","n"],
                             labels={"Dificultad_p":"Proporción correcta (p)","Discriminacion":"Correlación ítem-resto"},
                             title="Mapa de dificultad y discriminación de ítems")
            fig.add_vline(x=0.2, line_dash="dot"); fig.add_vline(x=0.8, line_dash="dot"); fig.add_hline(y=0.2, line_dash="dot")
            fig.update_xaxes(range=[0,1])
            st.plotly_chart(fig, use_container_width=True)
            show = items.copy()
            show["Dificultad_p"] = (show["Dificultad_p"]*100).round(1)
            show["Discriminacion"] = show["Discriminacion"].round(3)
            st.dataframe(show.sort_values(["Discriminacion","Dificultad_p"]), use_container_width=True, hide_index=True)

with pages[4]:
    st.subheader("Calidad de datos")
    removed = int(raw["_duplicado_join"].sum())
    inconsistent_grade = df.loc[df["Grado_inconsistente"], "AttemptId"].nunique()
    inconsistent_aula = df.loc[df["AULA_inconsistente"], "AttemptId"].nunique()
    a,b,c,d = st.columns(4)
    a.metric("Filas originales", f"{len(raw):,}".replace(",","."))
    b.metric("Duplicados removidos", f"{removed:,}".replace(",","."), f"{removed/max(len(raw),1):.1%}")
    c.metric("Intentos con grado inconsistente", inconsistent_grade)
    d.metric("Intentos con aula inconsistente", inconsistent_aula)

    missing = pd.DataFrame({"Variable":raw.columns, "Faltantes":raw.isna().sum().values})
    missing["Porcentaje"] = missing["Faltantes"] / max(len(raw),1) * 100
    st.dataframe(missing[missing["Faltantes"]>0].sort_values("Porcentaje", ascending=False), use_container_width=True, hide_index=True)
    st.info("Para el análisis se eliminan duplicados de respuesta que parecen provenir de joins. El grado se infiere prioritariamente desde el nombre de la prueba y los intentos con más de un aula se marcan como AMBIGUA.")

with pages[5]:
    st.subheader("Datos filtrados")
    cols = [c for c in ["AttemptId","Sede","Grado_analisis","AULA_analisis","IdentiEstudiante","Nombre","Apellido","QuizName","Descriptor","Pregunta","RespuestaEst","IsCorrect","TimeCompleted"] if c in f.columns]
    st.dataframe(f[cols], use_container_width=True, hide_index=True)
    st.download_button("Descargar datos filtrados", f[cols].to_csv(index=False).encode("utf-8-sig"), "datos_filtrados.csv", "text/csv")
