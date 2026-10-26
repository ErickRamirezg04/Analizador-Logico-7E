
## Instalación y ejecución

### 1. Descripción general

El Analizador de Lógica Proposicional es una aplicación de escritorio desarrollada en Python con CustomTkinter. Permite analizar textos en lenguaje natural, construir fórmulas de lógica proposicional, generar tablas de verdad y tableaux semánticos, y ejecutar un motor de inferencia mediante encadenamiento de reglas.

La aplicación utiliza SQLite para conservar las proposiciones, las reglas y el historial de análisis entre ejecuciones.

### 2. Requisitos previos

Antes de comenzar, asegúrate de contar con los siguientes componentes:

- **Sistema operativo:** Windows 10 u 11.
- **Python:** versión 3.10 o posterior.
- **Visual Studio Code:** instalado en el equipo.
- **Extensión Python:** extensión oficial de Microsoft para Visual Studio Code.
- **Git:** necesario si deseas clonar el repositorio directamente desde GitHub.

La dependencia gráfica CustomTkinter se instala desde el archivo `requirements.txt`. SQLite forma parte de la biblioteca estándar de Python, por lo que no necesita una instalación independiente.

Se requiere conexión a Internet durante la instalación inicial de las dependencias, salvo que ya estén disponibles en el entorno de Python seleccionado. Una vez configurado el entorno, la aplicación puede ejecutarse sin conexión.

### 3. Descargar o clonar el repositorio

Puedes obtener el código fuente directamente desde GitHub o descargarlo como archivo ZIP.

#### Opción A: clonar el repositorio desde VS Code

1. Abre Visual Studio Code.
2. Pulsa `Ctrl + Shift + P` para abrir la paleta de comandos.
3. Busca y selecciona `Git: Clone`.
4. Introduce la URL de este repositorio de GitHub.
5. Selecciona la carpeta local donde deseas guardar el proyecto.
6. Cuando VS Code pregunte si deseas abrir el repositorio clonado, selecciona **Open**.

#### Opción B: descargar el proyecto como ZIP

1. Abre la página del repositorio en GitHub.
2. Pulsa el botón `Code`.
3. Selecciona `Download ZIP`.
4. Descomprime el archivo en una carpeta de tu equipo.
5. En Visual Studio Code, selecciona **File → Open Folder...** y abre la carpeta del proyecto.

### 4. Abrir la carpeta correcta

Abre en VS Code la carpeta raíz que contiene directamente los archivos del programa.

La estructura principal del proyecto debe ser similar a la siguiente:

```text
analizador_logico/
├── .vscode/
│   └── tasks.json
├── tests/
│   └── test_logic_engine.py
├── app.py
├── logic_engine.py
├── inference_engine.py
├── storage.py
├── requirements.txt
├── README.md
└── CHANGELOG.md
```

Los archivos tienen las siguientes funciones:

| Archivo | Función |
|---|---|
| `app.py` | Interfaz gráfica y flujo de interacción con el usuario. |
| `logic_engine.py` | Tokenización, formalización, tablas de verdad y tableaux semánticos. |
| `inference_engine.py` | Motor de inferencia y encadenamiento de reglas. |
| `storage.py` | Persistencia, consultas e historial mediante SQLite. |
| `requirements.txt` | Dependencias externas del proyecto. |
| `.vscode/tasks.json` | Tareas para instalar dependencias, iniciar la aplicación y ejecutar pruebas. |
| `tests/` | Pruebas automatizadas del motor lógico. |

**Importante:** no abras únicamente `app.py`, ni una carpeta superior que contenga el proyecto como subcarpeta. La carpeta abierta en VS Code debe ser aquella en la que se encuentran directamente `app.py` y `.vscode`.

### 5. Seleccionar el intérprete de Python

Antes de instalar las dependencias, debes indicar a VS Code qué instalación de Python utilizará el proyecto.

1. Pulsa `Ctrl + Shift + P`.
2. Escribe `Python: Select Interpreter`.
3. Selecciona Python 3.10 o posterior.

Se recomienda crear un entorno virtual para mantener las dependencias aisladas de otros proyectos de Python.

Para crearlo desde la terminal integrada de VS Code:

```powershell
py -m venv .venv
```

A continuación, vuelve a ejecutar `Python: Select Interpreter` y selecciona el intérprete ubicado en:

```text
.venv\Scripts\python.exe
```

Si el comando `py` no está disponible, puedes utilizar `python -m venv .venv`, siempre que Python esté correctamente instalado y accesible.

No es necesario activar manualmente el entorno virtual si ya seleccionaste su intérprete en VS Code. Las tareas del proyecto utilizan el intérprete seleccionado.

### 6. Instalar las dependencias

La forma recomendada de instalar las dependencias es utilizar la tarea incluida en la configuración del proyecto.

1. En Visual Studio Code, abre el menú **Terminal → Run Task...**. En la interfaz en español puede aparecer como **Terminal → Ejecutar tarea...**.
2. Selecciona la tarea:

   `Analizador lógico: instalar dependencias`

3. Espera a que termine la instalación.
4. Comprueba que la terminal no muestre errores.

Esta tarea ejecuta la instalación definida en `requirements.txt`, cuyo contenido incluye CustomTkinter.

La instalación debe repetirse únicamente al configurar un entorno nuevo o cuando se incorporen o actualicen dependencias.

Como alternativa, desde la terminal integrada puedes ejecutar:

```powershell
python -m pip install -r requirements.txt
```

Este comando debe ejecutarse utilizando el mismo entorno de Python seleccionado para el proyecto.

### 7. Iniciar la aplicación

Una vez instaladas las dependencias, puedes iniciar el programa directamente desde Visual Studio Code.

1. Abre **Terminal → Run Task...**.
2. Selecciona:

   `Analizador lógico: iniciar`

3. Espera a que aparezca la ventana gráfica del analizador.

La interfaz de CustomTkinter se abrirá en una ventana de escritorio independiente. La terminal integrada de VS Code permanecerá disponible para mostrar mensajes y errores durante la ejecución.

Desde la interfaz puedes acceder a las distintas funciones del programa:

- **Analizar texto:** interpreta una oración o un conjunto de premisas, genera la representación lógica y permite consultar las tablas y el tableau semántico.
- **Modo manual:** permite introducir hechos y reglas de manera individual y analizar la base de conocimiento completa.
- **Encadenamiento:** aplica las reglas a los hechos conocidos para obtener conclusiones justificadas.
- **Historial:** recupera análisis anteriores y sus resultados guardados.
- **Registro de proposiciones:** consulta los átomos almacenados y sus identificadores persistentes.
- **Limpieza completa:** permite eliminar los datos locales del analizador después de una confirmación explícita.

Para cerrar el programa, utiliza la opción de salida de la aplicación o cierra su ventana.

### 8. Ejecutar las pruebas automatizadas

El proyecto incluye pruebas para verificar el comportamiento del parser, la persistencia y los motores de razonamiento.

Para ejecutarlas:

1. Abre **Terminal → Run Task...**.
2. Selecciona:

   `Analizador lógico: ejecutar pruebas`

3. Espera a que termine la ejecución.
4. Revisa los resultados que aparecen en la terminal.

También puedes ejecutar las pruebas desde la terminal integrada con:

```powershell
python -m unittest discover -s tests -v
```

Las pruebas permiten comprobar, entre otros aspectos:

- Reconocimiento de conectores y formalización de expresiones.
- Construcción de tablas de verdad y tableaux semánticos.
- Control de proposiciones duplicadas.
- Persistencia y recuperación de los análisis.
- Encadenamiento de reglas y derivación de conclusiones.
- Interpretación de expresiones de negación y condiciones en español.

Una prueba aprobada indica que el comportamiento cubierto por ella coincide con el resultado esperado; no garantiza una interpretación infalible de cualquier texto libre.

### 9. Persistencia y ubicación de los datos

La aplicación utiliza SQLite para conservar la información entre ejecuciones.

El archivo:

```text
analizador_logico.db
```

se crea automáticamente en la carpeta raíz del proyecto cuando se inicializa la base de datos.

Este archivo contiene información persistente como las proposiciones, las reglas asociadas, los análisis y el historial, según las funciones utilizadas.

Al cerrar VS Code o apagar el equipo, los datos guardados permanecen en la base de datos. Al volver a iniciar la aplicación, podrás consultar los registros existentes sin introducir nuevamente los textos.

**Precauciones:**

- No elimines `analizador_logico.db` si deseas conservar los datos.
- Antes de actualizar el proyecto, realiza una copia de seguridad de la base de datos.
- La limpieza completa elimina información local y no debe utilizarse si necesitas conservar los registros.
- Si deseas mantener una separación estricta entre los datos personales y el código fuente, evita subir la base de datos local al repositorio público.

### 10. Solución de problemas frecuentes

#### La tarea `Analizador lógico: iniciar` no aparece

Comprueba que abriste la carpeta raíz correcta y que dentro existe:

```text
.vscode/tasks.json
```

Si acabas de agregar o modificar la configuración, ejecuta `Developer: Reload Window` desde la paleta de comandos y vuelve a buscar la tarea.

#### Aparece `ModuleNotFoundError: No module named 'customtkinter'`

La dependencia no está instalada en el intérprete que utiliza el programa.

1. Ejecuta `Python: Select Interpreter`.
2. Selecciona el entorno correcto.
3. Ejecuta nuevamente `Analizador lógico: instalar dependencias`.
4. Vuelve a iniciar la aplicación.

#### La terminal indica que no encuentra el ejecutable de Python

Comprueba que el intérprete seleccionado exista y que corresponda a una instalación de Python válida.

Vuelve a seleccionar el intérprete en VS Code y ejecuta de nuevo la tarea.

#### El programa no abre la ventana gráfica

Revisa los mensajes de la terminal integrada. Si aparece una excepción, comprueba primero la configuración del intérprete y la instalación de dependencias.

Si el problema persiste, conserva el mensaje completo del error para facilitar su diagnóstico.

#### No aparecen las proposiciones o el historial anteriores

Comprueba que estás ejecutando el programa desde la carpeta del proyecto que contiene tu archivo `analizador_logico.db`. Si abriste otra copia del repositorio, es posible que esa carpeta tenga una base de datos diferente.

### 11. Consideraciones sobre el razonamiento lógico

El proyecto implementa lógica proposicional clásica y un motor explicable de encadenamiento hacia adelante.

La generación de conclusiones depende de las reglas y hechos proporcionados por el usuario. El sistema no garantiza la formalización perfecta de cualquier expresión en lenguaje natural; por ello, es necesario revisar las advertencias y comprobar que la fórmula generada representa la intención original.

En el caso de aplicaciones clínicas, las conclusiones son inferencias lógicas condicionadas por las premisas y no constituyen diagnósticos médicos ni sustituyen una valoración profesional.
