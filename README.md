# Holyrics Normalizer

Herramienta en Python para limpiar y dar formato a letras de canciones de texto
para **Holyrics**. La aplicación puede ejecutarse desde una interfaz gráfica
sencilla o desde la consola.

## Características

- **GUI flotante:** ofrece acciones para corregir letras, corregir títulos y
  cambiar los parámetros de formato.
- **Respaldo automático:** crea una copia fechada de la carpeta de canciones
  antes de cada operación.
- **Edición directa:** actualiza los archivos originales, sin crear una
  carpeta de salida duplicada.
- **Normalización de letras:** convierte el contenido a mayúsculas, corrige
  palabras configuradas, normaliza espacios y signos, conserva las marcas de
  repetición y divide estrofas largas.
- **Detección de título y autor:** primero intenta obtenerlos del nombre
  `TÍTULO (AUTOR).txt`; si no coincide, revisa las cabeceras iniciales, como
  `Title:` y `Artist:`. En modo interactivo solicita los datos que falten.
- **Nombres compatibles con Windows:** elimina los caracteres no permitidos
  al generar nombres normalizados.

## Requisitos

- Python **3.10 o posterior**.
- Tkinter para utilizar la interfaz gráfica. Suele incluirse con Python; en
  algunas distribuciones de Linux se instala por separado, por ejemplo con el
  paquete del sistema `python3-tk`.
- No se necesitan paquetes externos de Python. `requirements.txt` documenta
  esta condición.

## Instalación

1. Instala Python desde [python.org](https://www.python.org/downloads/) o desde
   el gestor de paquetes de tu sistema.
2. Clona el repositorio o descarga sus archivos.
3. Coloca las canciones `.txt` en la carpeta `canciones/`.
4. Ejecuta el programa desde la raíz del proyecto:

   ```bash
   python limpiar_letras.py
   ```

   En Windows también puedes utilizar:

   ```powershell
   py limpiar_letras.py
   ```

No es necesario instalar dependencias con `pip`. Si usas Linux y Tkinter no
está disponible, instálalo con el gestor de paquetes de tu distribución.

## Uso

### Interfaz gráfica

Ejecuta el programa sin argumentos:

```bash
python limpiar_letras.py
```

La ventana permite elegir:

- **Corregir la letra:** limpia el contenido de cada archivo y mantiene su
  nombre actual.
- **Corregir títulos:** busca los datos del título y autor, solicita los que
  falten y renombra los archivos sin alterar el contenido de las letras.
- **Cambiar parámetros:** ajusta el máximo de líneas por estrofa y el ancho
  usado para avisar de líneas largas.

### Consola

Limpiar las canciones y preguntar interactivamente por metadatos faltantes:

```bash
python limpiar_letras.py -i
```

Procesar otra carpeta:

```bash
python limpiar_letras.py -e "mis canciones" -i
```

Mantener los nombres originales durante la limpieza:

```bash
python limpiar_letras.py --nombre-original
```

Conservar las cabeceras `Title:` y `Artist:` dentro del archivo limpio:

```bash
python limpiar_letras.py --con-cabecera
```

Configurar formato:

```bash
python limpiar_letras.py --max-lineas 4 --max-ancho 40
```

Ver todas las opciones disponibles:

```bash
python limpiar_letras.py --help
```

`--max-lineas` divide estrofas que superan ese número de líneas.
`--max-ancho` sirve para detectar y reportar líneas que exceden el ancho
indicado; no las recorta automáticamente.

## Detección de título y autor

La aplicación sigue este orden:

1. Si el nombre tiene el formato `TÍTULO (AUTOR).txt`, utiliza esos datos.
2. Si no tiene ese formato, busca cabeceras consecutivas al inicio del archivo,
   como `Title:`, `Título:`, `Artist:`, `Artista:`, `Author:` o `Autor:`.
3. Si todavía faltan datos, los solicita cuando se utiliza `-i` en consola o la
   acción **Corregir títulos** de la GUI.

Sin modo interactivo, si no se pueden obtener los datos, se usa el nombre del
archivo como sugerencia de título y `DESCONOCIDO` como autor. En la consola, la
limpieza renombra por defecto los archivos según los metadatos detectados;
`--nombre-original` desactiva ese renombrado. La acción de limpieza de la GUI
conserva los nombres actuales.

## Respaldos y archivos locales

Antes de cada operación, se crea una copia fechada en `canciones_backup/`.
Cuando se indica una carpeta con `-e`, el respaldo se crea en una carpeta con
sufijo `_backup` junto a la carpeta seleccionada.

La limpieza modifica los archivos originales. Verifica que el respaldo se haya
creado correctamente y conserva copias adicionales en otra ubicación si los
archivos son importantes.

Los archivos `.txt` de `canciones/` se excluyen de Git por defecto para evitar
publicar letras sin autorización. Añádelos al repositorio únicamente si tienes
los derechos necesarios y modificas conscientemente la regla correspondiente
de `.gitignore`.

## Estructura del proyecto

```text
holyrics_normalizer/
├── limpiar_letras.py
├── README.md
├── LICENSE
├── requirements.txt
├── .gitignore
├── canciones/
│   └── .gitkeep
└── canciones_backup/  # Se crea al ejecutar; no se versiona
```

## Licencia

Este proyecto se distribuye bajo la licencia indicada en el archivo
[LICENSE](LICENSE).
