import html
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Resultados académicos", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

GRADE_MAP = {3:"TERCERO",4:"CUARTO",5:"QUINTO",6:"SEXTO",7:"SEPTIMO",8:"OCTAVO",9:"NOVENO",10:"DECIMO",11:"UNDECIMO"}
GRADE_ORDER = list(GRADE_MAP.values())
DEFAULT_FILE = Path(__file__).parent / "data" / "base_resultados.xlsx"

st.markdown("""
<style>
.block-container {padding-top: 1.7rem; padding-bottom: 2rem;}
div[data-testid="stMetric"] {background: rgba(127,127,127,.06); border: 1px solid rgba(127,127,127,.16); padding: 14px 16px; border-radius: 14px;}
div[data-testid="stMetricValue"] {font-size: 1.75rem;}
</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def load_data(source):
    df = pd.read_excel(source)
    for c in ["Sede","Grado","AULA","Nombre","Apellido","QuizName","Pregunta","RespuestaEst","Descriptor"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str).map(lambda x: html.unescape(html.unescape(x)).replace("\\xa0", " ").strip())
    df["IsCorrect"] = pd.to_numeric(df["IsCorrect"], errors="coerce")
    df["AttemptId"] = df["AttemptId"].astype(str)
    if "IdentiEstudiante" in df.columns:
        df["IdentiEstudiante"] = df["IdentiEstudiante"].astype(str)

    dedup_cols = [c for c in ["AttemptId","QuizName","Pregunta","RespuestaEst","IsCorrect","Descriptor"] if c in df.columns]
    df = df.drop_duplicates(dedup_cols, keep="first").copy()

    def infer_grade(q):
        m = re.search(r"(\\d{1,2})\\s*°", str(q))
        return GRADE_MAP.get(int(m.group(1))) if m else None
    df["Grado_prueba"] = df["QuizName"].map(infer_grade)
    df["Grado_analisis"] = df["Grado_prueba"].fillna(df["Grado"])
    return df

@st.cache_data(show_spinner=False)
def attempt_table(df):
    if df.empty:
        return pd.DataFrame(columns=["AttemptId","QuizName","Grado_analisis","Puntaje","Respuestas","Estudiante","Sede"])
    agg = df.groupby(["AttemptId","QuizName","Grado_analisis"], dropna=False).agg(
        Puntaje=("IsCorrect","mean"),
        Respuestas=("IsCorrect","count"),
        Estudiante=("IdentiEstudiante","first"),
        Sede=("Sede","first")
    ).reset_index()
    agg["Puntaje"] *= 100
    return agg

def pct(x):
    return "–" if pd.isna(x) else f"{x:.1f}%"

def ordered_grades(values):
    vals = list(pd.Series(values).dropna().astype(str).unique())
    return [g for g in GRADE_ORDER if g in vals] + sorted([g for g in vals if g not in GRADE_ORDER])

uploaded = st.sidebar.file_uploader("Usar otro archivo XLSX", type=["xlsx"])
source = uploaded if uploaded is not None else DEFAULT_FILE
df = load_data(source)

st.title("📊 Visualizador de resultados académicos")
st.caption("Panorama por grado y prueba, con detalle de dimensiones por prueba.")

st.sidebar.header("Filtros")
sedes = sorted([x for x in df["Sede"].dropna().astype(str).unique() if x]) if "Sede" in df.columns else []
sede_sel = st.sidebar.multiselect("Sede", sedes)
base = df[df["Sede"].isin(sede_sel)].copy() if sede_sel else df.copy()

tab_general, tab_prueba = st.tabs(["🌐 Vista general", "🎯 Detalle por prueba"])

with tab_general:
    st.subheader("Vista general por grado y prueba")
    st.write("Una lectura ejecutiva de cobertura y desempeño: **grado → prueba**.")
    att = attempt_table(base)

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Estudiantes", f"{base['IdentiEstudiante'].nunique():,}".replace(",","."))
    c2.metric("Intentos", f"{att['AttemptId'].nunique():,}".replace(",","."))
    c3.metric("Pruebas", f"{base['QuizName'].nunique():,}".replace(",","."))
    c4.metric("Puntaje promedio", pct(att["Puntaje"].mean()))

    st.markdown("### Resultados por grado")
    grade = att.groupby("Grado_analisis", as_index=False).agg(
        Puntaje=("Puntaje","mean"), Estudiantes=("Estudiante","nunique"), Intentos=("AttemptId","nunique"), Pruebas=("QuizName","nunique")
    )
    order = ordered_grades(grade["Grado_analisis"])
    left,right = st.columns([1.35,1])
    with left:
        fig = px.bar(grade, x="Grado_analisis", y="Puntaje", text="Puntaje",
                     category_orders={"Grado_analisis":order},
                     labels={"Grado_analisis":"Grado","Puntaje":"Puntaje promedio (%)"})
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_yaxes(range=[0,100]); fig.update_layout(showlegend=False, margin=dict(t=20,b=20))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        t = grade.copy().rename(columns={"Grado_analisis":"Grado"})
        t["Puntaje promedio"] = t["Puntaje"].round(1).astype(str) + "%"
        t["_orden"] = t["Grado"].map({g:i for i,g in enumerate(order)})
        st.dataframe(t.sort_values("_orden").drop(columns=["_orden","Puntaje"]), use_container_width=True, hide_index=True)

    st.markdown("### Mapa de desempeño: grado × prueba")
    mx = att.groupby(["Grado_analisis","QuizName"], as_index=False)["Puntaje"].mean()
    piv = mx.pivot(index="QuizName", columns="Grado_analisis", values="Puntaje")
    cols = [g for g in order if g in piv.columns]
    if cols: piv = piv[cols]
    if not piv.empty:
        fig = px.imshow(piv, text_auto=".0f", aspect="auto", zmin=0, zmax=100,
                        labels={"x":"Grado","y":"Prueba","color":"Puntaje %"})
        fig.update_layout(height=max(430, 33*len(piv)), margin=dict(t=15,b=20))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Resultados por prueba")
    quiz = att.groupby(["QuizName","Grado_analisis"], as_index=False).agg(
        Puntaje=("Puntaje","mean"), Estudiantes=("Estudiante","nunique"), Intentos=("AttemptId","nunique")
    )
    fig = px.bar(quiz.sort_values("Puntaje"), y="QuizName", x="Puntaje", color="Grado_analisis", orientation="h", text="Puntaje",
                 labels={"QuizName":"Prueba","Puntaje":"Puntaje promedio (%)","Grado_analisis":"Grado"},
                 category_orders={"Grado_analisis":order})
    fig.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
    fig.update_xaxes(range=[0,100]); fig.update_layout(height=max(500,30*len(quiz)), margin=dict(t=20,b=20))
    st.plotly_chart(fig, use_container_width=True)

    qt = quiz.rename(columns={"QuizName":"Prueba","Grado_analisis":"Grado"}).copy()
    qt["Puntaje promedio"] = qt["Puntaje"].round(1).astype(str) + "%"
    st.dataframe(qt.drop(columns="Puntaje"), use_container_width=True, hide_index=True)

with tab_prueba:
    st.subheader("Detalle de una prueba y sus dimensiones")
    st.write("Selecciona una prueba y revisa su resultado general junto con el comportamiento de cada dimensión.")
    quizzes = sorted([x for x in base["QuizName"].dropna().astype(str).unique() if x])
    if not quizzes:
        st.info("No hay pruebas disponibles con los filtros actuales.")
    else:
        selected = st.selectbox("Prueba", quizzes)
        qdf = base[base["QuizName"] == selected].copy()
        qatt = attempt_table(qdf)
        grades_q = ordered_grades(qdf["Grado_analisis"])

        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Grado", ", ".join(grades_q) if grades_q else "–")
        c2.metric("Estudiantes", f"{qdf['IdentiEstudiante'].nunique():,}".replace(",","."))
        c3.metric("Intentos", f"{qatt['AttemptId'].nunique():,}".replace(",","."))
        c4.metric("Puntaje promedio", pct(qatt["Puntaje"].mean()))

        dim = qdf[qdf["Descriptor"].astype(str).str.strip().ne("")].groupby("Descriptor", as_index=False).agg(
            Acierto=("IsCorrect","mean"), Respuestas=("IsCorrect","count"), Estudiantes=("IdentiEstudiante","nunique")
        )
        dim["Acierto"] *= 100

        st.markdown("### Desempeño por dimensión")
        if dim.empty:
            st.info("Esta prueba no tiene dimensiones registradas en la base.")
        else:
            ds = dim.sort_values("Acierto")
            fig = px.bar(ds, y="Descriptor", x="Acierto", orientation="h", text="Acierto",
                         labels={"Descriptor":"Dimensión","Acierto":"Acierto (%)"})
            fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig.update_xaxes(range=[0,100]); fig.update_layout(height=max(420,48*len(ds)), margin=dict(t=15,b=20))
            st.plotly_chart(fig, use_container_width=True)

            td = dim.sort_values("Acierto", ascending=False).copy()
            td["% de acierto"] = td["Acierto"].round(1).astype(str) + "%"
            st.dataframe(td.rename(columns={"Descriptor":"Dimensión"}).drop(columns="Acierto"), use_container_width=True, hide_index=True)

            best = dim.loc[dim["Acierto"].idxmax()]
            low = dim.loc[dim["Acierto"].idxmin()]
            b1,b2 = st.columns(2)
            b1.success(f"Mayor desempeño: **{best['Descriptor']}** · {best['Acierto']:.1f}%")
            b2.warning(f"Menor desempeño: **{low['Descriptor']}** · {low['Acierto']:.1f}%")

st.sidebar.markdown("---")
st.sidebar.caption("El tablero se concentra exclusivamente en grado, prueba y dimensiones.")
