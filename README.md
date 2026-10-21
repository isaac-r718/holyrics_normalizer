# Holyrics Normalizer

Herramienta en Python para limpiar y dar formato a letras de canciones para
**Holyrics**. La aplicación puede ejecutarse con una interfaz gráfica simple o
desde la línea de comandos, desarrollado de manera asistida con IA (Claude code & Gemini).

## Características

- GUI simple: ofrece acciones para limpiar letras, corregir títulos y ajustar
  los parámetros del formato.
- Copia de seguridad automática: crea una carpeta de respaldo con fecha antes de
  cada operación.
- Edición directa: modifica los archivos originales sin generar una carpeta de
  salida duplicada.
- Normalización de letras: convierte el contenido a mayúsculas, corrige
  palabras frecuentes, normaliza espacios y signos, conserva marcas de repetición
  y divide estrofas largas.
- Detección de título y autor: primero intenta obtenerlos del nombre
  `TÍTULO (AUTOR).txt`; si no coincide, revisa las cabeceras iniciales (`Title:`
  y `Artist:`). En modo interactivo, solicita los datos faltantes.
- Nombres compatibles con Windows: elimina caracteres no permitidos al generar
  nombres normalizados.

## Requisitos

- Python **3.10 o posterior**.
- Tkinter para la interfaz gráfica. Suele venir incluido con Python; en algunas
  distribuciones de Linux se instala por separado, por ejemplo con
  `python3-tk`.
- No se requieren dependencias externas de Python. `requirements.txt` refleja ese
  estado.

## Instalación

1. Instala Python desde [python.org](https://www.python.org/downloads/) o desde
   el gestor de paquetes de tu sistema.
2. Clona el repositorio o descarga sus archivos.
3. Coloca las canciones `.txt` en la carpeta `songs/`.
4. Ejecuta el programa desde la raíz del proyecto:

   ```bash
   python lyrics_normalizer.py
   ```

   En Windows, también puedes usar:

   ```powershell
   py lyrics_normalizer.py
   ```

   No es necesario instalar dependencias con `pip`. Si usas Linux y Tkinter no
   está disponible, instálalo con el gestor de paquetes de tu distribución.

## Uso

### Exportación

Exporta las canciones en masa desde Holyrics en formato `.txt` a la carpeta
`songs/`.

### Interfaz gráfica

Ejecuta el programa sin argumentos:

```bash
python lyrics_normalizer.py
```

La ventana permite elegir:

- **Corregir la letra:** limpia el contenido de cada archivo y mantiene su
  nombre actual.
- **Corregir títulos:** busca los datos del título y autor, solicita los que
  faltan y renombra los archivos sin alterar el contenido de las letras.
- **Cambiar parámetros:** ajusta el máximo de líneas por estrofa y el ancho
  usado para advertir líneas largas.

### Consola

Limpia las canciones y pregunta interactivamente por metadatos faltantes:

```bash
python lyrics_normalizer.py -i
```

Procesa otra carpeta:

```bash
python lyrics_normalizer.py -e "mis canciones" -i
```

Mantén los nombres originales durante la limpieza:

```bash
python lyrics_normalizer.py --nombre-original
```

Conserva las cabeceras `Title:` y `Artist:` dentro del archivo limpio:

```bash
python lyrics_normalizer.py --con-cabecera
```

Configura el formato:

```bash
python lyrics_normalizer.py --max-lineas 4 --max-ancho 40
```

Consulta todas las opciones disponibles:

```bash
python lyrics_normalizer.py --help
```

`--max-lineas` divide estrofas que superan ese número de líneas.
`--max-ancho` sirve para detectar y reportar líneas que exceden el ancho
indicado; no las recorta automáticamente.

## Detección de título y autor

La aplicación sigue este orden:

1. Si el nombre tiene el formato `TÍTULO (AUTOR).txt`, utiliza esos datos.
2. Si no tiene ese formato, busca cabeceras consecutivas al inicio del archivo,
   como `Title:`, `Título:`, `Artist:`, `Artista:`, `Author:` o `Autor:`.
3. Si todavía faltan datos, los solicita cuando se usa `-i` o la acción
   **Corregir títulos** de la interfaz gráfica.

Sin modo interactivo, si no se pueden obtener los datos, se usa el nombre del
archivo como sugerencia de título y `DESCONOCIDO` como autor. En la consola, la
limpieza renombra por defecto los archivos según los metadatos detectados;
`--nombre-original` desactiva ese renombrado. La acción de limpieza de la GUI
mantiene los nombres actuales.

## Respaldos y archivos locales

Antes de cada operación, se crea una copia fechada en `songs_backup/`.
Cuando se indica una carpeta con `-e`, el respaldo se crea en una carpeta con el
sufijo `_backup` junto a la carpeta seleccionada.

La limpieza modifica los archivos originales. Verifica que el respaldo se haya
creado correctamente y conserva copias adicionales en otra ubicación si los
archivos son importantes.

Los archivos `.txt` de `songs/` se excluyen de Git por defecto para evitar
publicar letras sin autorización. Añádelos al repositorio únicamente si tienes
los derechos necesarios y modificas conscientemente la regla correspondiente en
`.gitignore`.

## Estructura del proyecto

```text
holyrics_normalizer/
├── lyrics_normalizer.py
├── README.md
├── LICENSE
├── requirements.txt
├── .gitignore
├── songs/
│   └── .gitkeep
└── songs_backup/          # se crea al ejecutar; no se versiona
```

## Licencia

Este proyecto se distribuye bajo la licencia indicada en el archivo
[LICENSE](LICENSE).
