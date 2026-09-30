import html
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Resultados académicos", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

GRADE_NUM_TO_NAME = {
    3: "TERCERO",
    4: "CUARTO",
    5: "QUINTO",
    6: "SEXTO",
    7: "SEPTIMO",
    8: "OCTAVO",
    9: "NOVENO",
    10: "DECIMO",
    11: "UNDECIMO",
}
GRADE_NAME_TO_NUM = {v: k for k, v in GRADE_NUM_TO_NAME.items()}
GRADE_ORDER_NUM = [3, 4, 5, 6, 7, 8, 9, 10, 11]
GRADE_LABEL = {g: f"{g}°" for g in GRADE_ORDER_NUM}
TEST_ORDER = ["Matemáticas", "Lectura", "Ciencias naturales", "Ciencias sociales", "Inglés"]
DEFAULT_FILE = Path(__file__).parent / "data" / "base_resultados.xlsx"

st.markdown(
    """
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
div[data-testid="stMetric"] {
    background: rgba(127,127,127,.06);
    border: 1px solid rgba(127,127,127,.16);
    padding: 14px 16px;
    border-radius: 14px;
}
div[data-testid="stMetricValue"] {font-size: 1.65rem;}
.small-note {font-size: .92rem; color: #5c5c5c;}
</style>
""",
    unsafe_allow_html=True,
)


def pct(x, digits=1):
    return "–" if pd.isna(x) else f"{x:.{digits}f}%"


def numfmt(x, digits=1):
    return "–" if pd.isna(x) else f"{x:.{digits}f}"


def performance_level(score):
    """Clasifica un puntaje 0-100 según los cortes definidos."""
    if pd.isna(score):
        return "Sin resultado"
    if score <= 25:
        return "Progreso limitado"
    if score <= 50:
        return "Emergente"
    if score <= 75:
        return "Aceleración"
    return "Avanzado"


PERFORMANCE_ORDER = ["Progreso limitado", "Emergente", "Aceleración", "Avanzado"]


def clean_text(x):
    if pd.isna(x):
        return ""
    x = str(x)
    x = html.unescape(html.unescape(x)).replace("\\xa0", " ")
    return x.strip()


def infer_grade_num_from_quiz(quiz_name: str):
    m = re.search(r"(\d{1,2})\s*°", str(quiz_name))
    return int(m.group(1)) if m else None


def infer_grade_num_from_grade(raw_grade: str):
    raw = clean_text(raw_grade).upper()
    return GRADE_NAME_TO_NUM.get(raw)


def normalize_test(quiz_name: str):
    q = clean_text(quiz_name).upper()
    if "MATEM" in q:
        return "Matemáticas"
    if "LENGUAJE" in q:
        return "Lectura"
    if "LECTURA CR" in q:
        return "Lectura"
    if "CIENCIAS" in q:
        return "Ciencias naturales"
    if "COMPETENCIAS CIUDADANAS" in q or "SOCIALES Y CIUDADANAS" in q:
        return "Ciencias sociales"
    if "INGL" in q:
        return "Inglés"
    return "Otra"


def normalize_subtest(quiz_name: str):
    q = clean_text(quiz_name).upper()
    grade_num = infer_grade_num_from_quiz(q)
    if "MATEM" in q:
        return "Matemáticas"
    if "LENGUAJE" in q:
        return "Competencias Comunicativas en Lenguaje: Lectura" if (grade_num is None or grade_num <= 9) else "Lectura crítica"
    if "LECTURA CR" in q:
        return "Lectura crítica"
    if "CIENCIAS" in q:
        return "Ciencias Naturales y Educación Ambiental" if (grade_num is not None and grade_num <= 9) else "Ciencias Naturales"
    if "COMPETENCIAS CIUDADANAS" in q:
        return "Competencias Ciudadanas: Pensamiento Ciudadano"
    if "SOCIALES Y CIUDADANAS" in q:
        return "Sociales y ciudadanas"
    if "INGL" in q:
        return "Inglés"
    return clean_text(quiz_name)


def is_applicable(grade_num: int, test_name: str):
    if grade_num is None:
        return False
    rules = {
        "Matemáticas": lambda g: 3 <= g <= 11,
        "Lectura": lambda g: 3 <= g <= 11,
        "Ciencias naturales": lambda g: 5 <= g <= 11,
        "Ciencias sociales": lambda g: 5 <= g <= 11,
        "Inglés": lambda g: 9 <= g <= 11,
    }
    return rules.get(test_name, lambda g: False)(grade_num)


@st.cache_data(show_spinner=False)
def load_data(source):
    df = pd.read_excel(source)
    for c in ["Sede", "Grado", "AULA", "Nombre", "Apellido", "QuizName", "Pregunta", "RespuestaEst", "Descriptor"]:
        if c in df.columns:
            df[c] = df[c].map(clean_text)

    if "IsCorrect" in df.columns:
        df["IsCorrect"] = pd.to_numeric(df["IsCorrect"], errors="coerce")
    df["AttemptId"] = df["AttemptId"].astype(str)
    if "IdentiEstudiante" in df.columns:
        df["IdentiEstudiante"] = df["IdentiEstudiante"].astype(str).map(clean_text)

    dedup_cols = [c for c in ["AttemptId", "QuizName", "Pregunta", "RespuestaEst", "IsCorrect", "Descriptor"] if c in df.columns]
    df = df.drop_duplicates(dedup_cols, keep="first").copy()

    # Construir el grado sin asignaciones parciales sobre una columna numérica.
    # Esto evita LossySetitemError en versiones recientes de pandas.
    grade_from_quiz = df["QuizName"].map(infer_grade_num_from_quiz)
    grade_from_column = df["Grado"].map(infer_grade_num_from_grade)
    df["Grado_num"] = (
        pd.to_numeric(grade_from_quiz, errors="coerce")
        .combine_first(pd.to_numeric(grade_from_column, errors="coerce"))
        .astype("Int64")
    )
    df["Grado_analisis"] = df["Grado_num"].map(
        lambda x: GRADE_LABEL.get(int(x)) if pd.notna(x) else None
    )

    df["Prueba_grupo"] = df["QuizName"].map(normalize_test)
    df["Subprueba"] = df["QuizName"].map(normalize_subtest)
    df["Curso"] = df["AULA"].replace("", np.nan)
    df = df[df["Prueba_grupo"].isin(TEST_ORDER)].copy()

    # Inferir el máximo de ítems esperado de forma empírica para cada grado × prueba.
    # Se cuenta el número de registros de respuesta por intento y se toma el máximo observado.
    attempt_counts = (
        df.groupby(["AttemptId", "Grado_num", "Prueba_grupo"], dropna=False)
        .size()
        .rename("Items_registrados")
        .reset_index()
    )
    expected = (
        attempt_counts.groupby(["Grado_num", "Prueba_grupo"], dropna=False)["Items_registrados"]
        .max()
        .rename("Items_esperados")
        .reset_index()
    )
    df = df.merge(expected, on=["Grado_num", "Prueba_grupo"], how="left")
    return df


@st.cache_data(show_spinner=False)
def attempt_table(df):
    cols = [c for c in ["AttemptId", "Prueba_grupo", "Subprueba", "QuizName", "Grado_num", "Grado_analisis", "Curso"] if c in df.columns]
    if df.empty:
        return pd.DataFrame(columns=cols + ["Puntaje", "Respuestas", "Correctas", "Items_esperados", "Faltantes", "Cobertura", "Nivel", "Estudiante", "Sede"])

    agg = (
        df.groupby(cols, dropna=False)
        .agg(
            Respuestas=("IsCorrect", "count"),
            Correctas=("IsCorrect", "sum"),
            Items_esperados=("Items_esperados", "max"),
            Estudiante=("IdentiEstudiante", "first"),
            Sede=("Sede", "first"),
        )
        .reset_index()
    )
    agg["Items_esperados"] = pd.to_numeric(agg["Items_esperados"], errors="coerce")
    agg["Faltantes"] = (agg["Items_esperados"] - agg["Respuestas"]).clip(lower=0)
    agg["Cobertura"] = np.where(
        agg["Items_esperados"] > 0,
        agg["Respuestas"] / agg["Items_esperados"] * 100,
        np.nan,
    )
    # El denominador es el total esperado, no solo lo contestado.
    agg["Puntaje"] = np.where(
        agg["Items_esperados"] > 0,
        agg["Correctas"] / agg["Items_esperados"] * 100,
        np.nan,
    )
    agg["Nivel"] = agg["Puntaje"].map(performance_level)
    return agg

def stats_table(att_df, group_cols):
    if att_df.empty:
        return pd.DataFrame(columns=group_cols + ["Promedio", "DE", "Estudiantes", "Intentos", "Items_esperados", "Respondidas_prom", "Faltantes_prom", "Cobertura_prom"])
    out = (
        att_df.groupby(group_cols, dropna=False)
        .agg(
            Promedio=("Puntaje", "mean"),
            DE=("Puntaje", "std"),
            Estudiantes=("Estudiante", pd.Series.nunique),
            Intentos=("AttemptId", pd.Series.nunique),
            Items_esperados=("Items_esperados", "max"),
            Respondidas_prom=("Respuestas", "mean"),
            Faltantes_prom=("Faltantes", "mean"),
            Cobertura_prom=("Cobertura", "mean"),
        )
        .reset_index()
    )
    out["DE"] = out["DE"].fillna(0)
    return out


def performance_distribution(att_df, group_cols):
    """Distribución porcentual de niveles de desempeño por grupos."""
    if att_df.empty:
        return pd.DataFrame(columns=group_cols + ["Nivel", "Estudiantes", "Porcentaje"])
    # Un intento representa la unidad de resultado.
    dist = (
        att_df.groupby(group_cols + ["Nivel"], dropna=False)
        .size()
        .rename("Estudiantes")
        .reset_index()
    )
    if group_cols:
        totals = dist.groupby(group_cols, dropna=False)["Estudiantes"].transform("sum")
    else:
        totals = pd.Series(dist["Estudiantes"].sum(), index=dist.index)
    dist["Porcentaje"] = np.where(totals > 0, dist["Estudiantes"] / totals * 100, 0)
    return dist

def build_grade_summary_matrix(summary_df):
    rows = []
    for grade_num in GRADE_ORDER_NUM:
        row = {"Grado": GRADE_LABEL[grade_num]}
        for test_name in TEST_ORDER:
            mask = (summary_df["Grado_num"] == grade_num) & (summary_df["Prueba_grupo"] == test_name)
            tmp = summary_df.loc[mask]
            if not is_applicable(grade_num, test_name):
                row[test_name] = "No aplica"
            elif tmp.empty:
                row[test_name] = "Sin datos"
            else:
                r = tmp.iloc[0]
                row[test_name] = f"Prom {r['Promedio']:.1f}% | DE {r['DE']:.1f} | n {int(r['Estudiantes'])}"
        rows.append(row)
    return pd.DataFrame(rows)


def ordered_grade_labels(values):
    found = [v for v in pd.Series(values).dropna().unique().tolist() if v in GRADE_LABEL.values()]
    return [GRADE_LABEL[g] for g in GRADE_ORDER_NUM if GRADE_LABEL[g] in found]


def build_grade_course_matrix(att_df):
    """Tabla consolidada: una fila por grado/curso y una columna por prueba."""
    if att_df.empty:
        return pd.DataFrame(columns=["Grado", "Curso"] + TEST_ORDER)

    valid = att_df.dropna(subset=["Grado_num", "Curso"]).copy()
    if valid.empty:
        return pd.DataFrame(columns=["Grado", "Curso"] + TEST_ORDER)

    summary = stats_table(valid, ["Grado_num", "Curso", "Prueba_grupo"])
    pairs = (
        valid[["Grado_num", "Curso"]]
        .drop_duplicates()
        .sort_values(["Grado_num", "Curso"])
    )

    rows = []
    for _, pair in pairs.iterrows():
        grade_num = int(pair["Grado_num"])
        course = pair["Curso"]
        row = {"Grado": GRADE_LABEL.get(grade_num, str(grade_num)), "Curso": course}

        for test_name in TEST_ORDER:
            if not is_applicable(grade_num, test_name):
                row[test_name] = "No aplica"
                continue

            tmp = summary[
                (summary["Grado_num"] == grade_num)
                & (summary["Curso"] == course)
                & (summary["Prueba_grupo"] == test_name)
            ]
            if tmp.empty:
                row[test_name] = "Sin datos"
            else:
                r = tmp.iloc[0]
                row[test_name] = (
                    f"Prom {r['Promedio']:.1f}% | DE {r['DE']:.1f} | n {int(r['Estudiantes'])}"
                )
        rows.append(row)

    return pd.DataFrame(rows)


uploaded = st.sidebar.file_uploader("Usar otro archivo XLSX", type=["xlsx"])
source = uploaded if uploaded is not None else DEFAULT_FILE

df = load_data(source)
att = attempt_table(df)

st.title("📊 Visualizador de resultados académicos")
st.caption("Resultados en escala 0–100, incorporando cobertura de respuesta, datos faltantes y niveles de desempeño.")

st.sidebar.header("Filtros")
sedes = sorted([x for x in df["Sede"].dropna().astype(str).unique() if x]) if "Sede" in df.columns else []
sede_sel = st.sidebar.multiselect("Sede", sedes)
base = df[df["Sede"].isin(sede_sel)].copy() if sede_sel else df.copy()
att_base = attempt_table(base)

main_tab, detail_tab = st.tabs(["🌐 Vista general", "🎯 Pruebas y dimensiones"])

with main_tab:
    st.subheader("Vista general por grado")
    st.write("Para cada grado se muestran las **5 pruebas agrupadas**: Matemáticas, Lectura, Ciencias naturales, Ciencias sociales e Inglés. El puntaje se calcula sobre el **máximo de ítems observado para cada grado × prueba**, de modo que los ítems faltantes no inflen artificialmente el resultado. Cuando una prueba no corresponde al grado, aparece como **No aplica**.")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Estudiantes", f"{base['IdentiEstudiante'].nunique():,}".replace(",", "."))
    c2.metric("Intentos", f"{att_base['AttemptId'].nunique():,}".replace(",", "."))
    c3.metric("Grados con datos", f"{att_base['Grado_analisis'].nunique():,}".replace(",", "."))
    c4.metric("Promedio general", pct(att_base["Puntaje"].mean()))
    c5.metric("Ítems faltantes promedio", numfmt(att_base["Faltantes"].mean()))

    grade_test_summary = stats_table(att_base, ["Grado_num", "Grado_analisis", "Prueba_grupo"])
    matrix_df = build_grade_summary_matrix(grade_test_summary)

    st.markdown("### Resumen general: grado × prueba")
    st.dataframe(matrix_df, use_container_width=True, hide_index=True)
    st.markdown("<div class='small-note'>Cada celda muestra: promedio, desviación estándar (DE) y cantidad de estudiantes únicos. El puntaje usa como denominador el máximo de ítems observado en cada grado × prueba.</div>", unsafe_allow_html=True)

    st.markdown("### Cobertura de respuesta y datos faltantes")
    coverage_general = grade_test_summary.copy()
    coverage_general["Grado"] = coverage_general["Grado_num"].map(GRADE_LABEL)
    coverage_display = coverage_general[["Grado", "Prueba_grupo", "Items_esperados", "Respondidas_prom", "Faltantes_prom", "Cobertura_prom"]].rename(
        columns={
            "Prueba_grupo": "Prueba",
            "Items_esperados": "Ítems esperados",
            "Respondidas_prom": "Respondidas promedio",
            "Faltantes_prom": "Faltantes promedio",
            "Cobertura_prom": "Cobertura promedio",
        }
    )
    coverage_display["Respondidas promedio"] = coverage_display["Respondidas promedio"].round(1)
    coverage_display["Faltantes promedio"] = coverage_display["Faltantes promedio"].round(1)
    coverage_display["Cobertura promedio"] = coverage_display["Cobertura promedio"].round(1).astype(str) + "%"
    st.dataframe(coverage_display, use_container_width=True, hide_index=True)

    st.markdown("### Resultado promedio por grado y prueba")
    chart_df = grade_test_summary.copy()
    chart_df["Grado"] = chart_df["Grado_num"].map(GRADE_LABEL)
    fig = px.bar(
        chart_df,
        x="Grado",
        y="Promedio",
        color="Prueba_grupo",
        barmode="group",
        text="Promedio",
        labels={"Promedio": "Puntaje promedio (%)", "Prueba_grupo": "Prueba"},
        category_orders={"Grado": [GRADE_LABEL[g] for g in GRADE_ORDER_NUM], "Prueba_grupo": TEST_ORDER},
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_yaxes(range=[0, 100])
    fig.update_layout(margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Desagregación por curso dentro del grado")
    grade_options = [GRADE_LABEL[g] for g in GRADE_ORDER_NUM]
    selected_grade_label = st.selectbox("Selecciona un grado", grade_options, index=0)
    selected_grade_num = int(selected_grade_label.replace("°", ""))

    grade_summary = grade_test_summary[grade_test_summary["Grado_num"] == selected_grade_num].copy()
    grade_rows = []
    for test_name in TEST_ORDER:
        row = {"Prueba": test_name}
        tmp = grade_summary[grade_summary["Prueba_grupo"] == test_name]
        if not is_applicable(selected_grade_num, test_name):
            row.update({"Aplicación": "No aplica", "Promedio": "–", "DE": "–", "Estudiantes": "–", "Intentos": "–", "Ítems esperados": "–", "Faltantes prom.": "–", "Cobertura": "–"})
        elif tmp.empty:
            row.update({"Aplicación": "Sin datos", "Promedio": "–", "DE": "–", "Estudiantes": "–", "Intentos": "–", "Ítems esperados": "–", "Faltantes prom.": "–", "Cobertura": "–"})
        else:
            r = tmp.iloc[0]
            row.update({
                "Aplicación": "Aplicada",
                "Promedio": f"{r['Promedio']:.1f}%",
                "DE": f"{r['DE']:.1f}",
                "Estudiantes": int(r["Estudiantes"]),
                "Intentos": int(r["Intentos"]),
                "Ítems esperados": int(r["Items_esperados"]),
                "Faltantes prom.": f"{r['Faltantes_prom']:.1f}",
                "Cobertura": f"{r['Cobertura_prom']:.1f}%",
            })
        grade_rows.append(row)
    st.dataframe(pd.DataFrame(grade_rows), use_container_width=True, hide_index=True)

    grade_att = att_base[att_base["Grado_num"] == selected_grade_num].copy()
    available_courses = sorted([x for x in grade_att["Curso"].dropna().astype(str).unique() if x])
    course_sel = st.multiselect("Curso(s)", available_courses, default=[])
    if course_sel:
        grade_att = grade_att[grade_att["Curso"].isin(course_sel)].copy()

    course_summary = stats_table(grade_att, ["Curso", "Prueba_grupo"]) if not grade_att.empty else pd.DataFrame()
    if course_summary.empty:
        st.info("No hay datos de cursos para el grado seleccionado con los filtros actuales.")
    else:
        course_summary["Promedio_fmt"] = course_summary["Promedio"].map(lambda x: f"{x:.1f}%")
        course_summary["DE_fmt"] = course_summary["DE"].map(lambda x: f"{x:.1f}")
        fig_course = px.bar(
            course_summary,
            x="Curso",
            y="Promedio",
            color="Prueba_grupo",
            barmode="group",
            text="Promedio",
            labels={"Promedio": "Puntaje promedio (%)", "Prueba_grupo": "Prueba"},
            category_orders={"Prueba_grupo": TEST_ORDER},
        )
        fig_course.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_course.update_yaxes(range=[0, 100])
        fig_course.update_layout(margin=dict(t=20, b=20))
        st.plotly_chart(fig_course, use_container_width=True)

        display_course = course_summary.rename(columns={"Prueba_grupo": "Prueba"}).copy()
        display_course["Promedio"] = display_course["Promedio"].round(1).astype(str) + "%"
        display_course["DE"] = display_course["DE"].round(1)
        display_course["Ítems esperados"] = display_course["Items_esperados"].astype(int)
        display_course["Faltantes prom."] = display_course["Faltantes_prom"].round(1)
        display_course["Cobertura"] = display_course["Cobertura_prom"].round(1).astype(str) + "%"
        st.dataframe(display_course[["Curso", "Prueba", "Promedio", "DE", "Estudiantes", "Ítems esperados", "Faltantes prom.", "Cobertura"]], use_container_width=True, hide_index=True)

        st.markdown("#### Niveles de desempeño del grado seleccionado")
        perf_grade = performance_distribution(grade_att, ["Prueba_grupo"])
        if not perf_grade.empty:
            perf_grade["Nivel"] = pd.Categorical(perf_grade["Nivel"], categories=PERFORMANCE_ORDER, ordered=True)
            fig_perf = px.bar(
                perf_grade.sort_values(["Prueba_grupo", "Nivel"]),
                x="Prueba_grupo", y="Porcentaje", color="Nivel", barmode="stack",
                labels={"Prueba_grupo": "Prueba", "Porcentaje": "% de intentos"},
                category_orders={"Prueba_grupo": TEST_ORDER, "Nivel": PERFORMANCE_ORDER},
            )
            fig_perf.update_yaxes(range=[0, 100])
            fig_perf.update_layout(margin=dict(t=20, b=20))
            st.plotly_chart(fig_perf, use_container_width=True)

    st.markdown("### Tabla consolidada final: grado × curso × prueba")
    st.write(
        "Esta tabla resume todos los cursos en una sola vista. Cada celda contiene "
        "**promedio, DE y número de estudiantes**; el promedio ya incorpora los ítems faltantes en el denominador. "
        "Cuando una prueba no corresponde al grado, se muestra **No aplica**."
    )
    final_course_matrix = build_grade_course_matrix(att_base)
    if final_course_matrix.empty:
        st.info("No hay información de cursos disponible con los filtros actuales.")
    else:
        st.dataframe(final_course_matrix, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar tabla consolidada en CSV",
            data=final_course_matrix.to_csv(index=False).encode("utf-8-sig"),
            file_name="resultados_por_grado_curso_prueba.csv",
            mime="text/csv",
        )

with detail_tab:
    st.subheader("Detalle por prueba y dimensiones")
    st.write("Las pruebas se agrupan sin el número final del grado. Luego puedes ver cómo cambian sus resultados por grado y, dentro de un grado, por dimensión y curso.")

    selected_test = st.selectbox("Prueba agrupada", TEST_ORDER)
    applicable_grades = [g for g in GRADE_ORDER_NUM if is_applicable(g, selected_test)]
    test_att = att_base[att_base["Prueba_grupo"] == selected_test].copy()

    test_summary = stats_table(test_att, ["Grado_num", "Grado_analisis", "Subprueba"]) if not test_att.empty else pd.DataFrame()

    rows = []
    for g in applicable_grades:
        tmp = test_summary[test_summary["Grado_num"] == g] if not test_summary.empty else pd.DataFrame()
        if tmp.empty:
            rows.append({
                "Grado": GRADE_LABEL[g],
                "Subprueba": "Sin datos",
                "Promedio": np.nan,
                "DE": np.nan,
                "Estudiantes": np.nan,
                "Intentos": np.nan,
                "Estado": "Sin datos",
                "Items_esperados": np.nan,
                "Faltantes_prom": np.nan,
                "Cobertura_prom": np.nan,
            })
        else:
            for _, r in tmp.iterrows():
                rows.append({
                    "Grado": GRADE_LABEL[g],
                    "Subprueba": r["Subprueba"],
                    "Promedio": r["Promedio"],
                    "DE": r["DE"],
                    "Estudiantes": int(r["Estudiantes"]),
                    "Intentos": int(r["Intentos"]),
                    "Estado": "Aplicada",
                    "Items_esperados": r["Items_esperados"],
                    "Faltantes_prom": r["Faltantes_prom"],
                    "Cobertura_prom": r["Cobertura_prom"],
                })
    test_grade_df = pd.DataFrame(rows)

    st.markdown("### Resultado de la prueba por grado")
    if test_grade_df.empty or test_grade_df["Promedio"].dropna().empty:
        st.info("No hay datos disponibles para esta prueba con los filtros actuales.")
    else:
        fig_test = px.bar(
            test_grade_df.dropna(subset=["Promedio"]),
            x="Grado",
            y="Promedio",
            color="Subprueba",
            barmode="group",
            text="Promedio",
            labels={"Promedio": "Puntaje promedio (%)", "Subprueba": "Tipo de prueba"},
            category_orders={"Grado": [GRADE_LABEL[g] for g in applicable_grades]},
        )
        fig_test.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_test.update_yaxes(range=[0, 100])
        fig_test.update_layout(margin=dict(t=20, b=20))
        st.plotly_chart(fig_test, use_container_width=True)

    display_test_grade = test_grade_df.copy()
    display_test_grade["Promedio"] = display_test_grade["Promedio"].map(lambda x: "–" if pd.isna(x) else f"{x:.1f}%")
    display_test_grade["DE"] = display_test_grade["DE"].map(lambda x: "–" if pd.isna(x) else f"{x:.1f}")
    display_test_grade["Ítems esperados"] = display_test_grade["Items_esperados"].map(lambda x: "–" if pd.isna(x) else int(x))
    display_test_grade["Faltantes prom."] = display_test_grade["Faltantes_prom"].map(lambda x: "–" if pd.isna(x) else round(x, 1))
    display_test_grade["Cobertura"] = display_test_grade["Cobertura_prom"].map(lambda x: "–" if pd.isna(x) else f"{x:.1f}%")
    st.dataframe(display_test_grade[["Grado", "Subprueba", "Estado", "Promedio", "DE", "Estudiantes", "Ítems esperados", "Faltantes prom.", "Cobertura"]], use_container_width=True, hide_index=True)

    selected_grade_for_test = st.selectbox("Grado para ver dimensiones", [GRADE_LABEL[g] for g in applicable_grades], index=0)
    selected_grade_num_for_test = int(selected_grade_for_test.replace("°", ""))

    test_df = base[(base["Prueba_grupo"] == selected_test) & (base["Grado_num"] == selected_grade_num_for_test)].copy()
    att_test_grade = test_att[test_att["Grado_num"] == selected_grade_num_for_test].copy()

    grade_courses = sorted([x for x in att_test_grade["Curso"].dropna().astype(str).unique() if x])
    selected_courses_test = st.multiselect("Curso(s) dentro del grado seleccionado", grade_courses, default=[])
    if selected_courses_test:
        att_test_grade = att_test_grade[att_test_grade["Curso"].isin(selected_courses_test)].copy()
        test_df = test_df[test_df["Curso"].isin(selected_courses_test)].copy()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Grado", selected_grade_for_test)
    c2.metric("Estudiantes", f"{att_test_grade['Estudiante'].nunique():,}".replace(",", "."))
    c3.metric("Promedio", pct(att_test_grade["Puntaje"].mean()))
    c4.metric("Ítems esperados", numfmt(att_test_grade["Items_esperados"].max(), 0))
    c5.metric("Faltantes promedio", numfmt(att_test_grade["Faltantes"].mean()))
    c6.metric("Cobertura", pct(att_test_grade["Cobertura"].mean()))

    st.markdown("### Niveles de desempeño")
    perf_test = performance_distribution(att_test_grade, [])
    if not perf_test.empty:
        perf_test["Nivel"] = pd.Categorical(perf_test["Nivel"], categories=PERFORMANCE_ORDER, ordered=True)
        perf_test = perf_test.sort_values("Nivel")
        fig_levels = px.bar(
            perf_test, x="Nivel", y="Porcentaje", text="Porcentaje",
            labels={"Porcentaje": "% de intentos"},
            category_orders={"Nivel": PERFORMANCE_ORDER},
        )
        fig_levels.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_levels.update_yaxes(range=[0, 100])
        fig_levels.update_layout(showlegend=False, margin=dict(t=20, b=20))
        st.plotly_chart(fig_levels, use_container_width=True)
    st.caption("Progreso limitado: ≤25 · Emergente: >25–50 · Aceleración: >50–75 · Avanzado: >75.")

    st.markdown("### Desempeño por dimensión")
    st.caption("La dimensión se calcula sobre los registros disponibles de sus ítems. El puntaje global de la prueba sí penaliza los ítems faltantes mediante el total esperado.")
    dim_df = test_df[test_df["Descriptor"].astype(str).str.strip().ne("")].copy()
    if dim_df.empty:
        st.info("No hay dimensiones registradas para esta combinación de prueba y grado.")
    else:
        dim_summary = (
            dim_df.groupby("Descriptor", dropna=False)
            .agg(
                Acierto=("IsCorrect", "mean"),
                Respuestas=("IsCorrect", "count"),
                Estudiantes=("IdentiEstudiante", pd.Series.nunique),
            )
            .reset_index()
        )
        dim_summary["Acierto"] = dim_summary["Acierto"] * 100
        dim_summary = dim_summary.sort_values("Acierto", ascending=False)

        fig_dim = px.bar(
            dim_summary.sort_values("Acierto"),
            y="Descriptor",
            x="Acierto",
            orientation="h",
            text="Acierto",
            labels={"Descriptor": "Dimensión", "Acierto": "Acierto (%)"},
        )
        fig_dim.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig_dim.update_xaxes(range=[0, 100])
        fig_dim.update_layout(height=max(360, 45 * len(dim_summary)), margin=dict(t=20, b=20))
        st.plotly_chart(fig_dim, use_container_width=True)

        dim_display = dim_summary.rename(columns={"Descriptor": "Dimensión"}).copy()
        dim_display["Acierto"] = dim_display["Acierto"].round(1).astype(str) + "%"
        st.dataframe(dim_display, use_container_width=True, hide_index=True)

    st.markdown("### Desagregación por curso en esta prueba")
    if att_test_grade.empty:
        st.info("No hay datos por curso para esta combinación.")
    else:
        course_test_summary = stats_table(att_test_grade, ["Curso"]) if not att_test_grade.empty else pd.DataFrame()
        if course_test_summary.empty:
            st.info("No hay datos por curso para esta combinación.")
        else:
            fig_ct = px.bar(
                course_test_summary,
                x="Curso",
                y="Promedio",
                text="Promedio",
                labels={"Promedio": "Puntaje promedio (%)"},
            )
            fig_ct.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig_ct.update_yaxes(range=[0, 100])
            fig_ct.update_layout(margin=dict(t=20, b=20))
            st.plotly_chart(fig_ct, use_container_width=True)

            course_test_display = course_test_summary.copy()
            course_test_display["Promedio"] = course_test_display["Promedio"].round(1).astype(str) + "%"
            course_test_display["DE"] = course_test_display["DE"].round(1)
            course_test_display["Ítems esperados"] = course_test_display["Items_esperados"].astype(int)
            course_test_display["Faltantes prom."] = course_test_display["Faltantes_prom"].round(1)
            course_test_display["Cobertura"] = course_test_display["Cobertura_prom"].round(1).astype(str) + "%"
            st.dataframe(course_test_display[["Curso", "Promedio", "DE", "Estudiantes", "Ítems esperados", "Faltantes prom.", "Cobertura"]], use_container_width=True, hide_index=True)

st.sidebar.markdown("---")
st.sidebar.caption("El tablero integra grado, prueba, dimensiones, curso, cobertura de respuesta, faltantes y niveles de desempeño.")
