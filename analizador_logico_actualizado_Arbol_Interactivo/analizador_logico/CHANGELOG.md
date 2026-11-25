# Historial de cambios

## Actualización: persistencia relacional e inferencia explicable

- Cada análisis conserva texto original, fórmula serializada, objetivo, tokens, advertencias y datos de inferencia.
- Se almacenan reglas extraídas en `analysis_rules` y vínculos entre análisis y proposiciones atómicas en `analysis_propositions`.
- Las bases SQLite existentes se migran de forma idempotente. Se preservan textos, fórmulas, entradas manuales e historial.
- El modo manual reanaliza automáticamente todas las entradas al agregar una nueva; al eliminar una entrada, recalcula la base restante.
- Se añadió encadenamiento hacia adelante para reglas con antecedentes demostrables (incluidas conjunciones) y consecuentes atómicos, literales negados o conjunciones de literales.
- La vista de resultados incluye una traza explicable con la regla disparada, los hechos utilizados y las conclusiones.
- Se añadió limpieza completa confirmada para la base de datos y los CSV de `exports/`.
- Se añadieron pruebas para la inferencia de faringitis, cadenas de reglas, hechos faltantes, persistencia, migración y limpieza.


## Corrección: conectores subordinados y negación en lenguaje natural

- Se normaliza «siempre y cuando R» en un condicional como condición adicional del antecedente: `(P ∧ R) → Q`, con una advertencia visible sobre esta convención.
- «Pero al mismo tiempo», «pero», «sin embargo» y «no obstante» se aproximan como conjunción lógica antes de tokenizar, evitando que sus palabras queden absorbidas dentro de un átomo.
- Se admite negación gramatical después del sujeto, como «el proceso principal no se ejecuta de forma fluida», y se representa como `¬(el proceso principal se ejecuta de forma fluida)`.
- La tabla de tokenización etiqueta las frases compuestas «siempre y cuando» y «pero al mismo tiempo» como unidades discursivas, en vez de marcar la «y» interna como conjunción normal.
- Se añadieron pruebas de regresión para ambos textos reportados, incluida la contradicción de la segunda oración.


## Encadenamiento en modo de texto completo

- El modo **Analizar texto** ahora ejecuta el motor de encadenamiento hacia adelante con las reglas y hechos del propio texto, además del análisis de verdad/tableau.
- Los enunciados pueden separarse por líneas, puntos finales o punto y coma; se admiten numeración y etiquetas como `Regla 1:`.
- Se permite extraer reglas condicionales que estén dentro de una conjunción afirmada para el razonamiento.
- Los resultados y la traza de inferencia se guardan con el análisis y pueden recuperarse desde el historial.
- Se agregaron pruebas para inferencia en texto, cadenas de reglas, condiciones faltantes y premisas separadas por líneas.


## Visualización gráfica del tableau semántico

- Se reemplazó la vista textual del árbol semántico por un diagrama de nodos conectados en un `tkinter.Canvas` integrado en CustomTkinter.
- Los nodos muestran identificador, rama, fórmula con signo, regla aplicada y estado. Las ramas cerradas se resaltan en rojo con ×; las abiertas en verde; las bifurcaciones en violeta.
- Se añadieron zoom, ajuste general, barras de desplazamiento y diálogo de detalle al seleccionar cualquier nodo.
- Se incorporó exportación SVG vectorial y PNG; las imágenes PNG de gran tamaño se reducen automáticamente para limitar el uso de memoria.
- Se añadió `tableau_visualizer.py`, se incorporó Pillow a `requirements.txt` y se agregaron pruebas para estructura del árbol y exportación de los formatos.
