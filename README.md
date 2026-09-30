# Dashboard de resultados académicos en Streamlit

Aplicación para explorar resultados de evaluación a nivel de grado, prueba, descriptor, estudiante e ítem.

## Qué incluye

- Filtros por sede, grado, aula, prueba y descriptor.
- KPIs de respuestas, intentos, estudiantes, acierto y puntaje medio.
- Comparaciones por grado y prueba.
- Heatmap de grado × descriptor.
- Tabla y descarga de resultados por estudiante.
- Análisis psicométrico por prueba: dificultad, correlación ítem-resto y alfa de Cronbach.
- Página explícita de calidad de datos.
- Descarga de datos filtrados.

## Decisiones de limpieza incorporadas

La base contiene indicios de duplicación por joins: algunas respuestas del mismo `AttemptId` aparecen repetidas con distinto valor de `AULA` o `Grado`. La app:

1. Elimina duplicados usando `AttemptId + QuizName + Pregunta + RespuestaEst + IsCorrect + Descriptor`.
2. Infiere el grado desde `QuizName` cuando aparece el grado con el símbolo `°`.
3. Marca como `AMBIGUA` el aula de intentos asociados a más de un aula.
4. Advierte cuando una prueba repite textos de pregunta y, por tanto, el análisis psicométrico carece de un identificador de ítem perfecto.

## Ejecutar localmente

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Subir a GitHub

```bash
git init
git add .
git commit -m "Dashboard de resultados académicos"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git
git push -u origin main
```

## Publicar en Streamlit Community Cloud

1. Entra a https://share.streamlit.io/.
2. Conecta tu cuenta de GitHub.
3. Selecciona el repositorio y la rama `main`.
4. Usa `app.py` como archivo principal.
5. Pulsa **Deploy**.

El archivo incluido por defecto está en `data/base_resultados.xlsx`. También puedes cargar otro XLSX desde la barra lateral.

## Nota psicométrica

Para un análisis de ítems plenamente defendible conviene que la fuente incluya un `ItemId` único y estable. `Pregunta` funciona razonablemente en muchas pruebas, pero no en aquellas que reutilizan etiquetas como “Espacio 1”, “Espacio 2”, etc.
