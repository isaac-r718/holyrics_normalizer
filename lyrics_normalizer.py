#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Normalize Holyrics song text files and rename them consistently."""

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
class Configuration:
    max_lines: int = 4
    max_width: int = 40


CONFIGURATION = Configuration()

# ----------------------------------------------------------------------------
# 1) REGULAR EXPRESSIONS
# ----------------------------------------------------------------------------

# Several spaces/tabs/non-breaking spaces -> one single space
RE_SPACES = re.compile(r"[ \t\u00A0]+")

# Spaces before punctuation: "GOD ," -> "GOD,"
RE_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?])")

# Header: "Title: ...", "Artist: ...", "Título: ...", "Autor: ...", "Author: ..."
RE_HEADER = re.compile(
    r"^\s*(title|t[ií]tulo|artist|artista|author|autor)\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)

# One or more blank lines = stanza separator
RE_STANZA_SEPARATOR = re.compile(r"\n\s*\n+")

# Repetition marks "/ /": normalize "//" -> "/ /" and "/ /¿A" -> "/ / ¿A"
RE_STICKY_SLASH = re.compile(r"/(?=/)")
RE_SPACE_AFTER_SLASH = re.compile(r"/(?=[^\s/])")
RE_SPACE_BEFORE_SLASH = re.compile(r"(?<=[^\s/])/")

# Filename pattern: "TITLE (ARTIST)"
RE_FILENAME = re.compile(r"^(.*?)\s*\(([^()]*)\)\s*$")

# --- Title cleanup -----------------------------------------------------------
# Duplicate marker at the end: "(1)", " (2)" (typical copy files)
RE_DUPLICATE = re.compile(r"\s*\(\d+\)\s*$")
# Leading numbering: "01. ", "3 - ", "12) " (requires separator, so "1000 YEARS" stays untouched)
RE_LEADING_NUMBER = re.compile(r"^\s*\d{1,3}\s*[.\-–)]\s*")
# Anything between (), [] or {} -> artist, "(Live)", "(1)" etc.
RE_BETWEEN_BRACKETS = re.compile(r"\s*[\(\[\{][^\)\]\}]*[\)\]\}"]")
# Suffix after dash with spaces: "TITLE - ARTIST" -> "TITLE"
RE_DASH_SUFFIX = re.compile(r"\s+[-–—]\s+.*$")
# Two or more dots and extra punctuation at the edges
RE_REPEATED_DOTS = re.compile(r"\.{2,}")
RE_DIRTY_EDGES = re.compile(r"^[\s.\-_,;:]+|[\s.\-_,;:]+$")
# Characters invalid in Windows file names
RE_INVALID_CHARACTERS = re.compile(r'[<>:"/\\|?*]')

# Windows does not allow "?" in file names, so it is omitted from the name.
# Keep the question mark in the internal title if needed.
QUESTION_MARK_IN_NAME = ""

# ----------------------------------------------------------------------------
# 2) DICTIONARY OF ACCENTS / COMMON MISTAKES (unambiguous words)
#    Key: no accent, lowercase -> value: correct. Add your own.
# ----------------------------------------------------------------------------
CORRECTIONS = {
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

RE_CORRECTIONS = re.compile(
    r"\b(" + "|".join(map(re.escape, CORRECTIONS)) + r")\b", re.IGNORECASE
)


# ----------------------------------------------------------------------------
# 3) FUNCTIONS
# ----------------------------------------------------------------------------

def read_file(path: Path) -> str:
    """Read a .txt file trying several encodings."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {path.name}")


def split_header(text: str):
    """Extract the initial Title/Artist metadata. Returns (title, artist, body)."""
    title = artist = None
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        match = RE_HEADER.match(line)
        if not match:
            break
        key = match.group(1).lower()
        value = match.group(2) or None
        if key in ("title", "titulo", "título"):
            title = value
        else:
            artist = value
        index += 1
    return title, artist, "\n".join(lines[index:])


def fix_words(text: str) -> str:
    """Apply the accent correction dictionary (case-insensitive)."""
    return RE_CORRECTIONS.sub(lambda match: CORRECTIONS[match.group(0).lower()], text)


def normalize_markers(line: str) -> str:
    """Ensure repetition marks are formatted as '/ /' with consistent spacing."""
    line = RE_STICKY_SLASH.sub("/ ", line)
    line = RE_SPACE_AFTER_SLASH.sub("/ ", line)
    line = RE_SPACE_BEFORE_SLASH.sub(" /", line)
    return line


def clean_line(line: str) -> str:
    line = normalize_markers(line)
    line = RE_SPACES.sub(" ", line)
    line = RE_SPACE_BEFORE_PUNCTUATION.sub(r"\1", line)
    return line.strip()


def split_stanza(lines, max_lines):
    """Break large stanzas into balanced blocks (6 -> 3+3, 9 -> 3+3+3)."""
    count = len(lines)
    if count <= max_lines:
        return [lines]
    parts = math.ceil(count / max_lines)
    size = math.ceil(count / parts)
    return [lines[i:i + size] for i in range(0, count, size)]


def data_from_name(path: Path):
    """Extract title and artist only from the format 'TITLE (ARTIST).txt'."""
    stem = re.sub(r"[_]+", " ", path.stem).strip()
    while RE_DUPLICATE.search(stem):
        stem = RE_DUPLICATE.sub("", stem)
    match = RE_FILENAME.match(stem)
    if match and match.group(1).strip() and match.group(2).strip():
        return match.group(1).strip(), match.group(2).strip()
    return None, None


class InteractionCancelled(Exception):
    """Raised when the user cancels a requested value."""


def resolve_data(path: Path, title_header: Optional[str],
                artist_header: Optional[str], interactive: bool,
                request: Optional[Callable[[str, str, str], Optional[str]]] = None):
    """Apply precedence: formal name, header, and last user input."""
    title_name, artist_name = data_from_name(path)
    if title_name and artist_name:
        return title_name, artist_name

    title = title_header
    artist = artist_header
    stem_suggested = re.sub(r"[_]+", " ", path.stem).strip()
    stem_suggested = RE_DUPLICATE.sub("", stem_suggested).strip() or path.stem

    if interactive:
        def ask(field: str, suggestion: str) -> str:
            message = f"[{path.name}] {field} (Enter = '{suggestion}'): "
            value = request(path.name, field, suggestion) if request else input(message)
            if value is None:
                raise InteractionCancelled()
            return value.strip() or suggestion

        if not title:
            title = ask("Title", stem_suggested)
        if not artist:
            artist = ask("Artist", "UNKNOWN")
    else:
        title = title or stem_suggested
        artist = artist or "UNKNOWN"

    return title, artist or "UNKNOWN"


def clean_title(title: str, artist: str = None) -> str:
    """
    Keep only the song name. Remove, in this order:
      1. leading numbering          "01. Great is He" -> "Great is He"
      2. text inside (), [] or {}    "Title (Chris Tomlin) (1)" -> "Title"
      3. suffix after " - "         "Title - Chris Tomlin" -> "Title"
      4. artist appended at the end "Title Chris Tomlin" -> "Title"
      5. repeated dots/extras      "Title..." -> "Title"
    """
    t = title.replace("_", " ")
    t = RE_LEADING_NUMBER.sub("", t)
    t = RE_BETWEEN_BRACKETS.sub("", t)
    t = RE_DASH_SUFFIX.sub("", t)
    if artist and artist.upper() != "UNKNOWN":
        t = re.sub(r"\s+" + re.escape(artist.strip()) + r"\s*$", "", t, flags=re.IGNORECASE)
    t = RE_REPEATED_DOTS.sub(" ", t)
    t = RE_SPACES.sub(" ", t)
    t = RE_DIRTY_EDGES.sub("", t)
    return t.strip()


def close_question_mark(title: str) -> str:
    """If the title starts with '¿' and does not end with '?', add the closing '?'."""
    if title.startswith("¿") and not title.endswith("?"):
        return title + "?"
    return title


def safe_part(text: str) -> str:
    """Convert text to a valid Windows file name."""
    text = text.replace("?", QUESTION_MARK_IN_NAME)
    text = RE_INVALID_CHARACTERS.sub("", text)
    text = RE_SPACES.sub(" ", text)
    return text.strip(" .")


def file_name(title: str, artist: str, number: int = 1) -> str:
    """
    Build the file name Holyrics recognizes: 'TITLE (ARTIST)'.
    If the artist is unknown, it becomes just 'TITLE'. If the name already exists,
    the number is appended: 'TITLE 2 (ARTIST)'.
    """
    t = safe_part(title)
    if number > 1:
        t = f"{t} {number}"
    a = safe_part(artist)
    return f"{t} ({a})" if a and a.upper() != "UNKNOWN" else t


def process_file(path: Path, interactive: bool, max_lines: int, max_width: int,
                 with_header: bool = False,
                 request: Optional[Callable[[str, str, str], Optional[str]]] = None):
    """Process a file. Returns (final_text, warnings, title, artist)."""
    if max_lines < 1 or max_width < 1:
        raise ValueError("max_lines and max_width must be greater than zero")
    warnings = []
    text = read_file(path).replace("\r\n", "\n").replace("\r", "\n")
    title_header, artist_header, body = split_header(text)
    title, artist = resolve_data(path, title_header, artist_header, interactive, request)
    if not interactive and not title_header and not data_from_name(path)[0]:
        warnings.append("title taken from the file name")
    if artist.upper() == "UNKNOWN":
        warnings.append("missing artist")

    # --- Body: accents in lowercase -> uppercase -> cleanup ---
    body = fix_words(body.lower()).upper()

    stanzas = []
    for block in RE_STANZA_SEPARATOR.split(body.strip()):
        lines = [clean_line(line) for line in block.split("\n")]
        lines = [line for line in lines if line]
        if lines:
            stanzas.extend(split_stanza(lines, max_lines))

    for stanza in stanzas:
        for line in stanza:
            if len(line) > max_width:
                warnings.append(f"wide line ({len(line)} chars): {line[:40]}...")

    # --- Final title: clean (without author, "(1)", extra dots), with accents and uppercase ---
    clean_title_value = clean_title(title, artist)
    if not clean_title_value:
        clean_title_value = title.strip()
    if clean_title_value != title.strip():
        warnings.append(f"title cleaned: '{title.strip()}' -> '{clean_title_value}'")
    title = fix_words(clean_title_value.lower()).upper()
    artist = artist.upper()

    # If the title starts with '¿', it must close with '?'
    closed = close_question_mark(title)
    if closed != title:
        warnings.append(f"title began with '¿' and was closed: '{closed}'")
        title = closed

    # By default, DO NOT write a Title:/Artist: header; Holyrics uses the file name.
    output = f"Title: {title}\nArtist: {artist}\n\n" if with_header else ""
    output += "\n\n".join("\n".join(stanza) for stanza in stanzas) + "\n"
    return output, warnings, title, artist


def create_backup(folder: Path) -> Path:
    """Save a dated copy next to the original folder without overriding previous backups."""
    source = folder.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"The songs folder does not exist: {folder}")
    backup_root = source.parent / f"{source.name}_backup"
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = backup_root / timestamp
    shutil.copytree(source, destination)
    return destination


def atomic_write(path: Path, content: str) -> None:
    """Replace the full file without leaving it truncated if an error occurs."""
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\r\n", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False) as file:
            temp = Path(file.name)
            file.write(content)
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()


def unique_file_path(path: Path, title: str, artist: str) -> Path:
    """Generate a valid Holyrics filename without overwriting an existing file."""
    number = 1
    while True:
        filename = f"{file_name(title, artist, number)}.txt"
        destination = path.with_name(filename)
        same_path = os.path.normcase(str(destination.resolve())) == os.path.normcase(
            str(path.resolve()))
        if same_path or not destination.exists():
            return destination
        number += 1


def txt_files(folder: Path):
    if not folder.is_dir():
        raise FileNotFoundError(f"The songs folder does not exist: {folder}")
    files = sorted(folder.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No .txt files found in {folder}")
    return files


def run_cleanup(folder: Path, max_lines: int, max_width: int,
                interactive: bool = False, with_header: bool = False,
                rename: bool = True,
                request: Optional[Callable[[str, str, str], Optional[str]]] = None):
    """Clean lyrics in their original files and optionally normalize names."""
    backup = create_backup(folder)
    files = txt_files(folder)
    warnings_total = []
    errors = []
    for path in files:
        try:
            output, warnings, title, artist = process_file(
                path, interactive, max_lines, max_width, with_header, request)
            atomic_write(path, output)
            destination = unique_file_path(path, title, artist) if rename else path
            if destination != path:
                path.rename(destination)
                print(f"OK {path.name} -> {destination.name}")
            else:
                print(f"OK {path.name}")
            warnings_total.extend(f"{path.name}: {warning}" for warning in warnings)
        except Exception as error:
            errors.append(f"{path.name}: {error}")
            print(f"ERROR {path.name}: {error}")
    return backup, len(files), warnings_total, errors


def run_title_correction(folder: Path,
                        request: Callable[[str, str, str], Optional[str]]):
    """Review metadata and rename files while preserving the lyric content."""
    backup = create_backup(folder)
    files = txt_files(folder)
    warnings = []
    errors = []
    for path in files:
        try:
            title_header, artist_header, _ = split_header(read_file(path))
            title, artist = resolve_data(path, title_header, artist_header, True, request)
            title = clean_title(title, artist) or title.strip()
            title = fix_words(title.lower()).upper()
            artist = artist.upper()
            title = close_question_mark(title)
            destination = unique_file_path(path, title, artist)
            if destination != path:
                path.rename(destination)
                print(f"OK {path.name} -> {destination.name}")
            else:
                print(f"OK {path.name}")
        except InteractionCancelled:
            warnings.append(f"{path.name}: skipped by user cancellation")
        except Exception as error:
            errors.append(f"{path.name}: {error}")
            print(f"ERROR {path.name}: {error}")
    return backup, len(files), warnings, errors


def show_summary(parent, result):
    from tkinter import messagebox

    backup, total, warnings, errors = result
    message = f"Files processed: {total}\nBackup created in:\n{backup}"
    if warnings:
        message += f"\n\nWarnings: {len(warnings)}\n" + "\n".join(warnings[:8])
    if errors:
        message += f"\n\nErrors: {len(errors)}\n" + "\n".join(errors[:8])
        messagebox.showwarning("Process completed with errors", message, parent=parent)
    else:
        messagebox.showinfo("Process completed", message, parent=parent)


def open_interface(folder: Path):
    """Open a simple GUI for the available actions."""
    import tkinter as tk
    from tkinter import messagebox, simpledialog

    window = tk.Tk()
    window.title("Song cleanup")
    window.resizable(False, False)
    window.attributes("-topmost", True)

    backup_initial = create_backup(folder)
    tk.Label(window, text=f"Folder: {folder.resolve()}",
             wraplength=420, justify="left").pack(padx=16, pady=(16, 8))
    status = tk.Label(window, text=f"Initial backup: {backup_initial.name}",
                     anchor="w", wraplength=420)
    status.pack(fill="x", padx=16, pady=(0, 8))

    def request(name: str, field: str, suggestion: str):
        return simpledialog.askstring(
            f"Complete {field.lower()}",
            f"File: {name}\n{field} (suggested: {suggestion}):",
            initialvalue=suggestion, parent=window)

    def run_cleanup_gui():
        try:
            result = run_cleanup(folder, CONFIGURATION.max_lines, CONFIGURATION.max_width,
                                rename=False)
            show_summary(window, result)
        except Exception as error:
            messagebox.showerror("Could not complete the process", str(error), parent=window)

    def run_titles_gui():
        try:
            result = run_title_correction(folder, request)
            show_summary(window, result)
        except Exception as error:
            messagebox.showerror("Could not complete the process", str(error), parent=window)

    def change_parameters():
        lines = simpledialog.askinteger(
            "Parameters", "Maximum lines per stanza:",
            initialvalue=CONFIGURATION.max_lines, minvalue=1, parent=window)
        if lines is None:
            return
        width = simpledialog.askinteger(
            "Parameters", "Maximum line width (characters):",
            initialvalue=CONFIGURATION.max_width, minvalue=1, parent=window)
        if width is None:
            return
        CONFIGURATION.max_lines = lines
        CONFIGURATION.max_width = width
        status.config(text=f"Parameters: {lines} lines / {width} characters")

    tk.Button(window, text="Clean lyrics", command=run_cleanup_gui,
              width=32).pack(padx=16, pady=5)
    tk.Button(window, text="Fix titles", command=run_titles_gui,
              width=32).pack(padx=16, pady=5)
    tk.Button(window, text="Change parameters", command=change_parameters,
              width=32).pack(padx=16, pady=5)
    tk.Button(window, text="Close", command=window.destroy,
              width=32).pack(padx=16, pady=(5, 16))
    window.mainloop()


def create_parser():
    parser = argparse.ArgumentParser(description="Normalize Holyrics lyrics (.txt)")
    parser.add_argument("-e", "--input", "--entrada", default="songs",
                        help="songs folder")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="ask for missing title/artist data")
    parser.add_argument("--with-header", "--con-cabecera", action="store_true",
                        help="keep Title:/Artist: inside the file")
    parser.add_argument("--original-name", "--nombre-original", action="store_true",
                        help="do not rename files after cleaning")
    parser.add_argument("--max-lines", "--max-lineas", type=int,
                        default=CONFIGURATION.max_lines,
                        help="maximum lines per stanza")
    parser.add_argument("--max-width", "--max-ancho", type=int,
                        default=CONFIGURATION.max_width,
                        help="warn if a line exceeds N characters")
    return parser


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        try:
            open_interface(Path("songs"))
        except Exception as error:
            print(f"Could not start the interface: {error}")
            return 1
        return 0

    args = create_parser().parse_args(arguments)
    try:
        result = run_cleanup(
            Path(args.input), args.max_lines, args.max_width,
            interactive=args.interactive, with_header=args.with_header,
            rename=not args.original_name)
    except Exception as error:
        print(f"Could not complete the process: {error}")
        return 1
    backup, total, warnings, errors = result
    print(f"\nDone: {total} file(s) processed. Backup: '{backup}'.")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
