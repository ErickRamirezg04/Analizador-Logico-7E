# Analizador lógico — Sistemas Expertos

Aplicación de escritorio en Python con **CustomTkinter**, parser recursivo de lógica proposicional, tablas de verdad, tableau semántico, persistencia SQLite y un motor explicable de encadenamiento hacia adelante para reglas y hechos introducidos tanto en el modo manual como en el análisis de texto.

## Características

- Dos modos de entrada: texto completo y base de conocimiento manual.
- Tokenización, átomos únicos e identificadores persistentes `x[id]`.
- Extracción recursiva de reglas para negación, conjunción, disyunción, condicional y bicondicional.
- Normalización de conectores discursivos frecuentes: «pero al mismo tiempo» como conjunción y «siempre y cuando» como condición adicional del antecedente de un condicional.
- Reconocimiento de negación gramatical en frases como «el proceso principal no se ejecuta de forma fluida», conservando el mismo átomo negado que en su versión afirmativa.
- Tabla de verdad, tableau semántico, modelos de ramas abiertas e interpretación de resultados.
- Historial recuperable: se conserva el texto original, la fórmula, el objetivo semántico, las advertencias, los tokens, las reglas asociadas y los vínculos con las proposiciones atómicas. Al abrir el historial se reconstruyen las tablas y el árbol sin volver a capturar el texto.
- Modo manual que analiza **todas** las premisas y reglas almacenadas cada vez que agregas o eliminas una entrada.
- Encadenamiento hacia adelante disponible tanto en el modo manual como en el modo de texto completo para reglas con forma `A → B`, incluyendo antecedentes conjuntivos como `(p ∧ q) → r`, consecuentes atómicos o conjunciones de literales, negación literal y cadenas de varias reglas.
- Traza de inferencia: regla aplicada, antecedente demostrado, hechos usados y conclusión derivada.
- Control de duplicidad para átomos y fórmulas manuales.
- Botón **Limpieza completa de datos**, con confirmación, para borrar átomos, reglas asociadas, premisas/reglas manuales, historial e informes CSV generados.
- Exportación de tablas a CSV.
- Configuraciones de VS Code para iniciar, instalar dependencias y ejecutar pruebas.

## Requisitos

- Windows 10/11 (puede funcionar también en macOS/Linux con Python y Tk instalados).
- Visual Studio Code y extensión Python de Microsoft.
- Python 3.10 o posterior.
- CustomTkinter, instalado desde `requirements.txt`.
- Internet durante la instalación inicial de dependencias, salvo que ya estén disponibles localmente. Después, el programa se ejecuta sin Internet.

## Instalación y ejecución desde VS Code

1. Descomprime el proyecto y abre **la carpeta `analizador_logico`** en VS Code. Debes ver `app.py`, `logic_engine.py`, `inference_engine.py`, `storage.py`, `requirements.txt` y `.vscode`.
2. Pulsa `Ctrl + Shift + P`, ejecuta `Python: Select Interpreter` y selecciona Python 3.10 o posterior.
3. Abre **Terminal → Run Task…** (en VS Code en español puede aparecer como **Terminal → Ejecutar tarea…**).
4. Ejecuta **Analizador lógico: instalar dependencias**. Solo es necesario al configurar el entorno o actualizar las dependencias.
5. Ejecuta **Analizador lógico: iniciar**. Se abrirá la ventana gráfica del programa.

También puedes abrir **Run and Debug** y elegir `Analizador lógico (escritorio CustomTkinter)`; pulsa `F5` para iniciarlo bajo el depurador.

## Modo 1: analizar texto completo

Escribe una oración, un conjunto de enunciados o una fórmula. El programa normaliza el texto, muestra su tokenización, registra los átomos, extrae las reglas, calcula una tabla de verdad cuando es viable y construye el tableau semántico para el objetivo seleccionado (satisfacibilidad o validez).

Para condicionales en español se recomienda usar una forma delimitada, por ejemplo:

```text
Si nos dejan, entonces nos vamos a querer toda la vida
```

La formalización esperada es `x[1] → x[2]`. El lenguaje natural puede ser ambiguo; revisa las advertencias y confirma los límites entre antecedente y consecuente. Para una oración como «Si P, entonces Q, siempre y cuando R», el programa usa la convención `(P ∧ R) → Q`. La negación española colocada después de un sujeto («el proceso no se ejecuta») se normaliza como la negación de la proposición completa.

## Modo 2: base de conocimiento manual

Agrega cada **hecho** y cada **regla** como una entrada independiente. El sistema conserva las entradas en SQLite y después de cada alta analiza toda la base, no únicamente la última entrada. Si se elimina una premisa, vuelve a analizar el sistema restante.

### Ejemplo de encadenamiento

Introduce estas tres entradas, una por una:

```text
Regla 1: Si tengo dolor de garganta y tengo tos seca entonces tengo faringitis
Tengo dolor de garganta
Tengo tos seca
```

Puedes incluir el prefijo `Regla 1:`; el programa lo ignora para la formalización, pero conserva el texto original en el registro. También puedes escribir la regla sin prefijo:

```text
Si tengo dolor de garganta y tengo tos seca entonces tengo faringitis
```

Al contar con ambos hechos, el motor aplica la regla `(tengo dolor de garganta ∧ tengo tos seca) → tengo faringitis` y deriva `tengo faringitis`. La pestaña **Encadenamiento** muestra la regla aplicada, el antecedente demostrado y los hechos usados en cada paso. El motor repite el proceso hasta que no haya reglas nuevas aplicables, por lo que permite cadenas como `p → q`, `q → r`, `r → s`.

El encadenamiento busca consecuencias literales justificadas a partir de los hechos presentes. En ambos modos se utiliza el mismo motor y la misma traza explicable. Soporta reglas de tipo Horn con antecedentes demostrables (por ejemplo, conjunciones) y consecuentes que sean átomos, negaciones de átomos o conjunciones de esos literales. Si una regla tiene un consecuente más complejo, el programa lo indica como advertencia en vez de afirmar una conclusión no soportada por este motor.

**Importante para casos clínicos:** las salidas son inferencias lógicas condicionadas a las premisas y a su formalización; no son un diagnóstico médico ni sustituyen la evaluación profesional. Datos incompletos o reglas mal definidas pueden producir conclusiones incorrectas.

## Persistencia y recuperación del historial

La base `analizador_logico.db` se crea en la carpeta del proyecto. SQLite conserva las proposiciones únicas, cada texto original, el árbol de fórmula, el objetivo, los tokens, las advertencias, las reglas extraídas y la relación del análisis con sus átomos. El esquema se migra automáticamente al iniciar versiones nuevas, sin que tengas que borrar una base existente.

Para recuperar resultados guardados:

1. Abre la sección **Historial**.
2. Selecciona el análisis que te interesa.
3. Pulsa **Abrir análisis seleccionado** o haz doble clic en la fila.

El programa vuelve a generar la tabla de verdad, el tableau y el árbol a partir de la fórmula almacenada, y utiliza las reglas, tokens y advertencias persistidos cuando están disponibles. No necesitas volver a escribir el texto original.

En el modo manual, la lista de premisas/reglas también se conserva. Al volver a abrir el programa puedes ir a **Modo manual** y pulsar **Reanalizar sistema completo**.

## Limpieza completa

El botón rojo **Limpieza completa de datos** aparece en la barra lateral. Tras una confirmación explícita, elimina todos los átomos, relaciones y reglas asociadas a los análisis, entradas manuales, historial e informes CSV dentro de `exports/`. Esta operación es irreversible. Copia `analizador_logico.db` antes de ejecutarla si quieres conservar una copia.

La limpieza total está diseñada para empezar un caso independiente. El uso normal del programa no elimina automáticamente los registros históricos.

## Conectores admitidos

| Operación | Formas reconocidas | Símbolo |
|---|---|---|
| Negación | `no p`, `not p`, `¬p`, `~p` | `¬` |
| Conjunción | `p y q`, `p and q`, `p ∧ q`, `p & q` | `∧` |
| Disyunción inclusiva | `p o q`, `p or q`, `p ∨ q`, `p \| q` | `∨` |
| Condicional | `si p entonces q`, `if p then q`, `p -> q`, `p => q`, `p → q` | `→` |
| Bicondicional | `p si y solo si q`, `p iff q`, `p <-> q`, `p ↔ q` | `↔` |
| Contraste discursivo | `p, pero al mismo tiempo q`, `p, sin embargo, q` | `∧` (aproximación proposicional) |
| Condición adicional | `si p entonces q, siempre y cuando r` | `(p ∧ r) → q` |

Precedencia, de mayor a menor: `¬`, `∧`, `∨`, `→`, `↔`. Usa paréntesis cuando el alcance pueda ser ambiguo.

## Pruebas

En **Terminal → Run Task…**, ejecuta **Analizador lógico: ejecutar pruebas**. La suite `unittest` verifica el parser, conectores, tablas de verdad, tableau, deduplicación, persistencia de reglas/vínculos, limpieza total, la inferencia del ejemplo clínico y cadenas de dos o más reglas. Incluye regresiones para «siempre y cuando» y para la negación después del sujeto en «el proceso principal no se ejecuta de forma fluida».

## Límites conocidos

- La aplicación implementa lógica proposicional clásica y encadenamiento hacia adelante explicable; no intenta comprender cualquier texto natural sin ambigüedad.
- El análisis lingüístico no maneja todos los fenómenos de lenguaje natural, correferencia, cuantificadores ni lógica de predicados. «Pero», «sin embargo» y frases similares se aproximan como conjunción; los matices discursivos no se formalizan aparte. «Siempre y cuando R» se interpreta como una condición añadida al antecedente, por lo que conviene revisar la advertencia del análisis.
- Las tablas de verdad están limitadas a 12 átomos y el tableau tiene un límite de nodos para prevenir explosión combinatoria.
- El razonador manual deriva literales de reglas cuyo antecedente puede justificarse con hechos conocidos; no equivale a un motor general de prueba para todas las fórmulas de lógica proposicional.
