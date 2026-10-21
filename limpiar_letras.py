#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Limpia letras de Holyrics y actualiza los archivos originales con respaldo.

Sin argumentos abre la GUI. En modo CLI, por ejemplo:
    python limpiar_letras.py -i
    python limpiar_letras.py -e mis_canciones --max-lineas 4 --max-ancho 40

Cada operación crea un respaldo fechado en ``canciones_backup`` (o junto a la
carpeta indicada con ``-e``). Los nombres solo se extraen del formato
«TÍTULO (AUTOR).txt»; si no coincide, se consultan las cabeceras iniciales y,
con ``-i``, se pregunta por los datos que falten.
"""

import argparse
import math
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


@dataclass
class Configuracion:
    max_lineas: int = 4
    max_ancho: int = 40


CONFIGURACION = Configuracion()

# ----------------------------------------------------------------------------
# 1) EXPRESIONES REGULARES
# ----------------------------------------------------------------------------

# Varios espacios/tabs/espacios duros -> un solo espacio
RE_ESPACIOS = re.compile(r"[ \t\u00A0]+")

# Espacio antes de , . ; : ! ?   ("DIOS ," -> "DIOS,")
RE_ESPACIO_ANTES_PUNTUACION = re.compile(r"\s+([,.;:!?])")

# Cabecera: "Title: ...", "Artist: ...", "Título: ...", "Autor: ...", "Author: ..."
RE_CABECERA = re.compile(
    r"^\s*(title|t[ií]tulo|artist|artista|author|autor)\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)

# Una o más líneas en blanco = separador de estrofas
RE_SEPARADOR_ESTROFA = re.compile(r"\n\s*\n+")

# Marcas de repetición "/ /": normalizan "//" -> "/ /" y "/ /¿A" -> "/ / ¿A"
RE_BARRA_PEGADA = re.compile(r"/(?=/)")            # barra seguida de barra -> "/ "
RE_ESPACIO_TRAS_BARRA = re.compile(r"/(?=[^\s/])")  # barra pegada a texto  -> "/ "
RE_ESPACIO_ANTES_BARRA = re.compile(r"(?<=[^\s/])/")  # texto pegado a barra -> " /"

# Nombre de archivo tipo "TÍTULO (ARTISTA)"
RE_NOMBRE_ARCHIVO = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")

# --- Limpieza de títulos -----------------------------------------------------
# Marcador de duplicado al final: "(1)", " (2)"  (típico de archivos copiados)
RE_DUPLICADO = re.compile(r"\s*\(\d+\)\s*$")
# Numeración al inicio: "01. ", "3 - ", "12) "  (exige separador, así "1000 AÑOS" no se toca)
RE_NUMERACION_INICIO = re.compile(r"^\s*\d{1,3}\s*[.\-–)]\s*")
# Cualquier cosa entre (), [] o {} -> autor, "(Live)", "(1)", etc.
RE_ENTRE_BRACKETS = re.compile(r"\s*[\(\[\{][^\)\]\}]*[\)\]\}]")
# Sufijo tras guion CON espacios: "TÍTULO - AUTOR" -> "TÍTULO"
RE_SUFIJO_GUION = re.compile(r"\s+[-–—]\s+.*$")
# Dos o más puntos seguidos ("..", "...") y puntos/espacios sobrantes en los bordes
RE_PUNTOS_REPETIDOS = re.compile(r"\.{2,}")
RE_BORDES_SUCIOS = re.compile(r"^[\s.\-_,;:]+|[\s.\-_,;:]+$")
# Caracteres que Windows no permite en nombres de archivo
RE_CARACTERES_INVALIDOS = re.compile(r'[<>:"/\\|?*]')

# Windows NO permite "?" en nombres de archivo, así que en el NOMBRE se omite
# (dentro del programa el título sí conserva su "?"). Si prefieres un símbolo
# parecido que sí es válido, cambia "" por "？" (signo de interrogación de ancho completo).
SIGNO_INTERROGACION_EN_NOMBRE = ""

# ----------------------------------------------------------------------------
# 2) DICCIONARIO DE TILDES / ERRORES COMUNES (palabras sin ambigüedad)
#    Clave: sin tilde, minúscula  ->  valor: correcta. Agrega las tuyas.
# ----------------------------------------------------------------------------
CORRECCIONES = {
    "senor": "señor", "jesus": "jesús", "jehova": "jehová", "corazon": "corazón",
    "salvacion": "salvación", "adoracion": "adoración", "oracion": "oración",
    "cancion": "canción", "bendicion": "bendición", "perdon": "perdón",
    "espiritu": "espíritu", "tambien": "también", "aqui": "aquí",
    "alli": "allí", "ahi": "ahí", "asi": "así", "despues": "después",
    "ademas": "además", "jamas": "jamás", "dia": "día", "dias": "días",
    "unico": "único", "angel": "ángel", "angeles": "ángeles",
    "ningun": "ningún", "algun": "algún", "mio": "mío", "mia": "mía",
    "mesias": "mesías", "maria": "maría", "rios": "ríos",
    "murio": "murió", "nacio": "nació", "resucito": "resucitó",
    "sufrio": "sufrió", "sere": "seré", "estare": "estaré",
    "amare": "amaré", "alabare": "alabaré", "cantare": "cantaré",
    "adorare": "adoraré", "sera": "será", "vendra": "vendrá",
    "volvera": "volverá", "reinara": "reinará", "santisimo": "santísimo",
    "sanacion": "sanación", "ayudame": "ayúdame", "dame": "dame",
    "ire": "iré", "vivire": "viviré",
}

RE_CORRECCIONES = re.compile(
    r"\b(" + "|".join(map(re.escape, CORRECCIONES)) + r")\b", re.IGNORECASE
)


# ----------------------------------------------------------------------------
# 3) FUNCIONES
# ----------------------------------------------------------------------------

def leer_archivo(ruta: Path) -> str:
    """Lee un .txt probando varias codificaciones."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return ruta.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"No pude decodificar {ruta.name}")


def separar_cabecera(texto: str):
    """Extrae Title/Artist del inicio. Devuelve (titulo, artista, cuerpo)."""
    titulo = artista = None
    lineas = texto.splitlines()
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        if not linea.strip():
            i += 1
            continue
        m = RE_CABECERA.match(linea)
        if not m:
            break
        clave = m.group(1).lower()
        valor = m.group(2) or None
        if clave in ("title", "titulo", "título"):
            titulo = valor
        else:
            artista = valor
        i += 1
    return titulo, artista, "\n".join(lineas[i:])


def corregir_palabras(texto: str) -> str:
    """Aplica el diccionario de tildes (insensible a mayúsculas)."""
    return RE_CORRECCIONES.sub(lambda m: CORRECCIONES[m.group(0).lower()], texto)


def normalizar_marcas(linea: str) -> str:
    """Deja las marcas de repetición como '/ /' con espacios consistentes."""
    linea = RE_BARRA_PEGADA.sub("/ ", linea)
    linea = RE_ESPACIO_TRAS_BARRA.sub("/ ", linea)
    linea = RE_ESPACIO_ANTES_BARRA.sub(" /", linea)
    return linea


def limpiar_linea(linea: str) -> str:
    linea = normalizar_marcas(linea)
    linea = RE_ESPACIOS.sub(" ", linea)
    linea = RE_ESPACIO_ANTES_PUNTUACION.sub(r"\1", linea)
    return linea.strip()


def dividir_estrofa(lineas, max_lineas):
    """Parte estrofas largas en bloques equilibrados (6 -> 3+3, 9 -> 3+3+3)."""
    n = len(lineas)
    if n <= max_lineas:
        return [lineas]
    partes = math.ceil(n / max_lineas)
    tam = math.ceil(n / partes)
    return [lineas[i:i + tam] for i in range(0, n, tam)]


def datos_desde_nombre(ruta: Path):
    """Extrae título y autor solo del formato «TÍTULO (AUTOR).txt»."""
    stem = re.sub(r"[_]+", " ", ruta.stem).strip()
    while RE_DUPLICADO.search(stem):
        stem = RE_DUPLICADO.sub("", stem)
    m = RE_NOMBRE_ARCHIVO.match(stem)
    if m and m.group(1).strip() and m.group(2).strip():
        return m.group(1).strip(), m.group(2).strip()
    return None, None


class InteraccionCancelada(Exception):
    """Indica que el usuario canceló una solicitud de datos."""


def resolver_datos(ruta: Path, titulo_cabecera: Optional[str],
                   artista_cabecera: Optional[str], interactivo: bool,
                   solicitar: Optional[Callable[[str, str, str], Optional[str]]] = None):
    """Aplica la precedencia: nombre formal, cabecera inicial y, por último, usuario."""
    titulo_nombre, artista_nombre = datos_desde_nombre(ruta)
    if titulo_nombre and artista_nombre:
        return titulo_nombre, artista_nombre

    titulo = titulo_cabecera
    artista = artista_cabecera
    stem_sugerido = re.sub(r"[_]+", " ", ruta.stem).strip()
    stem_sugerido = RE_DUPLICADO.sub("", stem_sugerido).strip() or ruta.stem

    if interactivo:
        def pedir(campo: str, sugerencia: str) -> str:
            mensaje = f"[{ruta.name}] {campo} (Enter = '{sugerencia}'): "
            valor = solicitar(ruta.name, campo, sugerencia) if solicitar else input(mensaje)
            if valor is None:
                raise InteraccionCancelada()
            return valor.strip() or sugerencia

        if not titulo:
            titulo = pedir("Título", stem_sugerido)
        if not artista:
            artista = pedir("Autor", "DESCONOCIDO")
    else:
        titulo = titulo or stem_sugerido
        artista = artista or "DESCONOCIDO"

    return titulo, artista or "DESCONOCIDO"


def limpiar_titulo(titulo: str, artista: str = None) -> str:
    """
    Deja solo el nombre de la canción. Quita, en este orden:
      1. numeración inicial          "01. Cuán grande es Él"  -> "Cuán grande es Él"
      2. texto entre (), [] o {}     "Título (Chris Tomlin) (1)" -> "Título"
      3. sufijo tras " - "           "Título - Chris Tomlin"  -> "Título"
      4. el artista pegado al final  "Título Chris Tomlin"    -> "Título"
      5. puntos repetidos/sobrantes  "Título..."              -> "Título"
    """
    t = titulo.replace("_", " ")
    t = RE_NUMERACION_INICIO.sub("", t)
    t = RE_ENTRE_BRACKETS.sub("", t)
    t = RE_SUFIJO_GUION.sub("", t)
    if artista and artista.upper() != "DESCONOCIDO":
        # artista al final del título (sin distinguir mayúsculas)
        t = re.sub(r"\s+" + re.escape(artista.strip()) + r"\s*$", "", t, flags=re.IGNORECASE)
    t = RE_PUNTOS_REPETIDOS.sub(" ", t)
    t = RE_ESPACIOS.sub(" ", t)
    t = RE_BORDES_SUCIOS.sub("", t)
    return t.strip()


def cerrar_interrogacion(titulo: str) -> str:
    """Si el título empieza con '¿' y no termina con '?', agrega el '?' final."""
    if titulo.startswith("¿") and not titulo.endswith("?"):
        return titulo + "?"
    return titulo


def _parte_segura(texto: str) -> str:
    """Convierte un texto en algo válido para un nombre de archivo de Windows."""
    texto = texto.replace("?", SIGNO_INTERROGACION_EN_NOMBRE)
    texto = RE_CARACTERES_INVALIDOS.sub("", texto)
    texto = RE_ESPACIOS.sub(" ", texto)
    return texto.strip(" .")                  # Windows no admite punto/espacio al final


def nombre_archivo(titulo: str, artista: str, numero: int = 1) -> str:
    """
    Arma el nombre que Holyrics reconoce: 'TÍTULO (AUTOR)'.
    Sin autor conocido queda solo 'TÍTULO'. Si el nombre ya existe (numero > 1)
    se agrega el número al título: 'TÍTULO 2 (AUTOR)'.
    """
    t = _parte_segura(titulo)
    if numero > 1:
        t = f"{t} {numero}"
    a = _parte_segura(artista)
    return f"{t} ({a})" if a and a.upper() != "DESCONOCIDO" else t


def procesar(ruta: Path, interactivo: bool, max_lineas: int, max_ancho: int,
             con_cabecera: bool = False,
             solicitar: Optional[Callable[[str, str, str], Optional[str]]] = None):
    """Procesa un archivo. Devuelve (texto_final, avisos, titulo, artista)."""
    if max_lineas < 1 or max_ancho < 1:
        raise ValueError("max_lineas y max_ancho deben ser mayores que cero")
    avisos = []
    texto = leer_archivo(ruta).replace("\r\n", "\n").replace("\r", "\n")
    titulo_cabecera, artista_cabecera, cuerpo = separar_cabecera(texto)
    titulo, artista = resolver_datos(
        ruta, titulo_cabecera, artista_cabecera, interactivo, solicitar)
    if not interactivo and not titulo_cabecera and not datos_desde_nombre(ruta)[0]:
        avisos.append("título tomado del nombre del archivo")
    if artista.upper() == "DESCONOCIDO":
        avisos.append("falta artista")

    # --- Cuerpo: tildes sobre minúsculas -> MAYÚSCULAS -> limpieza ---
    cuerpo = corregir_palabras(cuerpo.lower()).upper()

    estrofas = []
    for bloque in RE_SEPARADOR_ESTROFA.split(cuerpo.strip()):
        lineas = [limpiar_linea(l) for l in bloque.split("\n")]
        lineas = [l for l in lineas if l]
        if lineas:
            estrofas.extend(dividir_estrofa(lineas, max_lineas))

    for est in estrofas:
        for l in est:
            if len(l) > max_ancho:
                avisos.append(f"línea ancha ({len(l)} car.): {l[:40]}...")

    # --- Título final: limpio (sin autor, "(1)", puntos extra), con tildes y en MAYÚSCULAS ---
    titulo_limpio = limpiar_titulo(titulo, artista)
    if not titulo_limpio:                       # por si la limpieza lo dejó vacío
        titulo_limpio = titulo.strip()
    if titulo_limpio != titulo.strip():
        avisos.append(f"título limpiado: '{titulo.strip()}' -> '{titulo_limpio}'")
    titulo = corregir_palabras(titulo_limpio.lower()).upper()
    artista = artista.upper()

    # Si el título abre con ¿, debe cerrar con ?
    cerrado = cerrar_interrogacion(titulo)
    if cerrado != titulo:
        avisos.append(f"título con ¿ sin cierre: se agregó '?' -> '{cerrado}'")
        titulo = cerrado

    # Por defecto NO se escribe la cabecera Title:/Artist: (Holyrics usa el nombre del archivo)
    salida = f"Title: {titulo}\nArtist: {artista}\n\n" if con_cabecera else ""
    salida += "\n\n".join("\n".join(e) for e in estrofas) + "\n"
    return salida, avisos, titulo, artista


def crear_respaldo(carpeta: Path) -> Path:
    """Guarda una copia fechada junto a la carpeta original sin pisar respaldos previos."""
    origen = carpeta.resolve()
    if not origen.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de canciones: {carpeta}")
    raiz_respaldo = origen.parent / f"{origen.name}_backup"
    raiz_respaldo.mkdir(parents=True, exist_ok=True)
    instante = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = raiz_respaldo / instante
    shutil.copytree(origen, destino)
    return destino


def escribir_atomico(ruta: Path, contenido: str) -> None:
    """Reemplaza el archivo completo evitando dejarlo truncado ante un fallo."""
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\r\n", dir=ruta.parent,
                prefix=f".{ruta.name}.", suffix=".tmp", delete=False) as archivo:
            temporal = Path(archivo.name)
            archivo.write(contenido)
        os.replace(temporal, ruta)
    finally:
        if temporal and temporal.exists():
            temporal.unlink()


def ruta_con_nombre_unico(ruta: Path, titulo: str, artista: str) -> Path:
    """Genera un nombre Holyrics disponible, sin reemplazar otro archivo existente."""
    numero = 1
    while True:
        nombre = f"{nombre_archivo(titulo, artista, numero)}.txt"
        destino = ruta.with_name(nombre)
        misma_ruta = os.path.normcase(str(destino.resolve())) == os.path.normcase(
            str(ruta.resolve()))
        if misma_ruta or not destino.exists():
            return destino
        numero += 1


def archivos_txt(carpeta: Path):
    if not carpeta.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de canciones: {carpeta}")
    archivos = sorted(carpeta.glob("*.txt"))
    if not archivos:
        raise FileNotFoundError(f"No hay archivos .txt en la carpeta: {carpeta}")
    return archivos


def ejecutar_limpieza(carpeta: Path, max_lineas: int, max_ancho: int,
                      interactivo: bool = False, con_cabecera: bool = False,
                      renombrar: bool = True,
                      solicitar: Optional[Callable[[str, str, str], Optional[str]]] = None):
    """Limpia las letras en sus archivos originales y opcionalmente normaliza nombres."""
    respaldo = crear_respaldo(carpeta)
    archivos = archivos_txt(carpeta)
    avisos_totales = []
    errores = []
    for ruta in archivos:
        try:
            salida, avisos, titulo, artista = procesar(
                ruta, interactivo, max_lineas, max_ancho, con_cabecera, solicitar)
            escribir_atomico(ruta, salida)
            destino = ruta_con_nombre_unico(ruta, titulo, artista) if renombrar else ruta
            if destino != ruta:
                ruta.rename(destino)
                print(f"OK {ruta.name} -> {destino.name}")
            else:
                print(f"OK {ruta.name}")
            avisos_totales.extend(f"{ruta.name}: {aviso}" for aviso in avisos)
        except Exception as error:
            errores.append(f"{ruta.name}: {error}")
            print(f"ERROR {ruta.name}: {error}")
    return respaldo, len(archivos), avisos_totales, errores


def ejecutar_correccion_titulos(carpeta: Path,
                                solicitar: Callable[[str, str, str], Optional[str]]):
    """Revisa metadatos y renombra, preservando intacto el contenido de cada canción."""
    respaldo = crear_respaldo(carpeta)
    archivos = archivos_txt(carpeta)
    avisos = []
    errores = []
    for ruta in archivos:
        try:
            titulo_cabecera, artista_cabecera, _ = separar_cabecera(leer_archivo(ruta))
            titulo, artista = resolver_datos(
                ruta, titulo_cabecera, artista_cabecera, True, solicitar)
            titulo = limpiar_titulo(titulo, artista) or titulo.strip()
            titulo = corregir_palabras(titulo.lower()).upper()
            artista = artista.upper()
            titulo = cerrar_interrogacion(titulo)
            destino = ruta_con_nombre_unico(ruta, titulo, artista)
            if destino != ruta:
                ruta.rename(destino)
                print(f"OK {ruta.name} -> {destino.name}")
            else:
                print(f"OK {ruta.name}")
        except InteraccionCancelada:
            avisos.append(f"{ruta.name}: se omitió por cancelación")
        except Exception as error:
            errores.append(f"{ruta.name}: {error}")
            print(f"ERROR {ruta.name}: {error}")
    return respaldo, len(archivos), avisos, errores


def _mostrar_resumen(parent, resultado):
    from tkinter import messagebox

    respaldo, total, avisos, errores = resultado
    mensaje = f"Archivos revisados: {total}\nRespaldo creado en:\n{respaldo}"
    if avisos:
        mensaje += f"\n\nAvisos: {len(avisos)}\n" + "\n".join(avisos[:8])
    if errores:
        mensaje += f"\n\nErrores: {len(errores)}\n" + "\n".join(errores[:8])
        messagebox.showwarning("Proceso terminado con errores", mensaje, parent=parent)
    else:
        messagebox.showinfo("Proceso terminado", mensaje, parent=parent)


def abrir_interfaz(carpeta: Path):
    """Abre la ventana sencilla de acciones y preferencias."""
    import tkinter as tk
    from tkinter import messagebox, simpledialog

    ventana = tk.Tk()
    ventana.title("Limpieza de canciones")
    ventana.resizable(False, False)
    ventana.attributes("-topmost", True)

    respaldo_inicial = crear_respaldo(carpeta)
    tk.Label(ventana, text=f"Carpeta: {carpeta.resolve()}",
             wraplength=420, justify="left").pack(padx=16, pady=(16, 8))
    estado = tk.Label(ventana, text=f"Respaldo inicial: {respaldo_inicial.name}",
                      anchor="w", wraplength=420)
    estado.pack(fill="x", padx=16, pady=(0, 8))

    def solicitar(nombre: str, campo: str, sugerencia: str):
        return simpledialog.askstring(
            f"Completar {campo.lower()}",
            f"Archivo: {nombre}\n{campo} (sugerencia: {sugerencia}):",
            initialvalue=sugerencia, parent=ventana)

    def correr_limpieza():
        try:
            resultado = ejecutar_limpieza(
                carpeta, CONFIGURACION.max_lineas, CONFIGURACION.max_ancho,
                renombrar=False)
            _mostrar_resumen(ventana, resultado)
        except Exception as error:
            messagebox.showerror("No se pudo completar", str(error), parent=ventana)

    def correr_titulos():
        try:
            resultado = ejecutar_correccion_titulos(carpeta, solicitar)
            _mostrar_resumen(ventana, resultado)
        except Exception as error:
            messagebox.showerror("No se pudo completar", str(error), parent=ventana)

    def cambiar_parametros():
        lineas = simpledialog.askinteger(
            "Parámetros", "Máximo de líneas por estrofa:",
            initialvalue=CONFIGURACION.max_lineas, minvalue=1, parent=ventana)
        if lineas is None:
            return
        ancho = simpledialog.askinteger(
            "Parámetros", "Ancho máximo de línea (caracteres):",
            initialvalue=CONFIGURACION.max_ancho, minvalue=1, parent=ventana)
        if ancho is None:
            return
        CONFIGURACION.max_lineas = lineas
        CONFIGURACION.max_ancho = ancho
        estado.config(text=f"Parámetros: {lineas} líneas / {ancho} caracteres")

    tk.Button(ventana, text="Corregir la letra", command=correr_limpieza,
              width=32).pack(padx=16, pady=5)
    tk.Button(ventana, text="Corregir títulos", command=correr_titulos,
              width=32).pack(padx=16, pady=5)
    tk.Button(ventana, text="Cambiar parámetros", command=cambiar_parametros,
              width=32).pack(padx=16, pady=5)
    tk.Button(ventana, text="Cerrar", command=ventana.destroy,
              width=32).pack(padx=16, pady=(5, 16))
    ventana.mainloop()


def crear_parser():
    parser = argparse.ArgumentParser(description="Limpia letras de Holyrics (.txt)")
    parser.add_argument("-e", "--entrada", default="canciones", help="carpeta de canciones")
    parser.add_argument("-i", "--interactivo", action="store_true",
                        help="preguntar título/autor cuando falten")
    parser.add_argument("--con-cabecera", action="store_true",
                        help="conservar Title:/Artist: dentro del archivo")
    parser.add_argument("--nombre-original", action="store_true",
                        help="no renombrar los archivos después de limpiarlos")
    parser.add_argument("--max-lineas", type=int, default=CONFIGURACION.max_lineas,
                        help="máximo de líneas por estrofa")
    parser.add_argument("--max-ancho", type=int, default=CONFIGURACION.max_ancho,
                        help="aviso si una línea supera N caracteres")
    return parser


def main(argv=None):
    argumentos = sys.argv[1:] if argv is None else argv
    if not argumentos:
        try:
            abrir_interfaz(Path("canciones"))
        except Exception as error:
            print(f"No se pudo iniciar la interfaz: {error}")
            return 1
        return 0

    args = crear_parser().parse_args(argumentos)
    try:
        resultado = ejecutar_limpieza(
            Path(args.entrada), args.max_lineas, args.max_ancho,
            interactivo=args.interactivo, con_cabecera=args.con_cabecera,
            renombrar=not args.nombre_original)
    except Exception as error:
        print(f"No se pudo completar el proceso: {error}")
        return 1
    respaldo, total, avisos, errores = resultado
    print(f"\nListo: {total} archivo(s) procesado(s). Respaldo: '{respaldo}'.")
    for aviso in avisos:
        print(f"AVISO: {aviso}")
    for error in errores:
        print(f"ERROR: {error}")
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())