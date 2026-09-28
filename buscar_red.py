#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
buscar_red.py - Buscador de archivos en la red local Windows (varios segmentos)

Descubre los equipos encendidos de uno o varios segmentos de red, enumera sus
carpetas compartidas y busca archivos por nombre (2 o 3 a la vez) y/o extension,
mostrando en tiempo real la ruta, el tamano y la fecha de modificacion.

Modo asistente (pregunta todo por pantalla):
    python buscar_red.py

Modo directo:
    python buscar_red.py -n factura -n presupuesto -e pdf,xlsx -r 192.1.1 -r 192.1.2 -r 192.1.3
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import ipaddress
import os
import re
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
PUERTOS_SMB = (445, 139)

RECURSOS_OMITIDOS = {"IPC$", "ADMIN$", "PRINT$", "FAX$", "NETLOGON", "SYSVOL"}

CARPETAS_OMITIDAS = {
    "windows", "winsxs", "$recycle.bin", "system volume information",
    "program files", "program files (x86)", "programdata", "appdata",
    "msocache", "recovery", "perflogs", "node_modules", ".git", ".svn",
    "$windows.~bt", "$windows.~ws", "config.msi", "onedrivetemp",
}

# --------------------------------------------------------------------------- #
# Consola
# --------------------------------------------------------------------------- #

_lock = threading.Lock()
COLOR = True

_C = {
    "reset": "\033[0m", "gris": "\033[90m", "verde": "\033[92m",
    "amarillo": "\033[93m", "cian": "\033[96m", "rojo": "\033[91m",
    "blanco": "\033[97m", "magenta": "\033[95m",
}


def init_consola() -> None:
    global COLOR
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            COLOR = False


def col(texto: str, color: str | None) -> str:
    if not COLOR or not color:
        return texto
    return f"{_C.get(color, '')}{texto}{_C['reset']}"


def hora() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(mensaje: str, color: str | None = None) -> None:
    with _lock:
        print(f"{col('[' + hora() + ']', 'gris')} {col(mensaje, color)}", flush=True)


def humano(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:,.0f} {u}" if u == "B" else f"{n:,.1f} {u}"
        n /= 1024.0
    return f"{n:,.1f} TB"


# --------------------------------------------------------------------------- #
# Redes
# --------------------------------------------------------------------------- #

def decodificar(datos: bytes) -> str:
    for cod in ("utf-8", "cp850", "cp1252", "latin-1"):
        try:
            return datos.decode(cod)
        except UnicodeDecodeError:
            continue
    return datos.decode("utf-8", errors="replace")


def expandir_red(txt: str) -> list[str]:
    """Acepta: 192.1.1 | 192.1.1.0/24 | 192.1.1.10-90 | 192.1.1.55"""
    txt = txt.strip()
    if not txt:
        return []
    if "/" in txt:
        return [str(h) for h in ipaddress.ip_network(txt, strict=False).hosts()]
    m = re.match(r"^(\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d{1,3})-(\d{1,3})$", txt)
    if m:
        base, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        return [f"{base}.{i}" for i in range(min(a, b), max(a, b) + 1)]
    partes = txt.split(".")
    if len(partes) == 3 and all(p.isdigit() for p in partes):
        return [f"{txt}.{i}" for i in range(1, 255)]
    if len(partes) == 4 and all(p.isdigit() for p in partes):
        return [txt]
    raise ValueError(f"Segmento no reconocido: '{txt}'")


def redes_locales() -> list[str]:
    """Detecta los segmentos /24 a los que pertenece este equipo."""
    encontrados: list[str] = []
    try:
        s = subprocess.run(["ipconfig"], capture_output=True, timeout=15,
                           creationflags=CREATE_NO_WINDOW)
        texto = decodificar(s.stdout)
        for ip in re.findall(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", texto):
            if ip.startswith(("127.", "255.", "0.")) or ip.endswith((".255", ".0")):
                continue
            seg = ".".join(ip.split(".")[:3])
            if seg not in encontrados:
                encontrados.append(seg)
    except Exception:
        pass
    return encontrados


# --------------------------------------------------------------------------- #
# Descubrimiento de equipos
# --------------------------------------------------------------------------- #

def puerto_abierto(ip: str, puerto: int, espera: float) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(espera)
    try:
        return s.connect_ex((ip, puerto)) == 0
    except OSError:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


def responde_ping(ip: str, ms: int) -> bool:
    if os.name == "nt":
        cmd = ["ping", "-n", "1", "-w", str(ms), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, ms // 1000)), ip]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=(ms / 1000.0) + 3, creationflags=CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception:
        return False


def nombre_equipo(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0].split(".")[0]
    except Exception:
        return ""


def sondear(ip: str, espera: float, usar_ping: bool) -> tuple[str, bool, bool]:
    """Devuelve (ip, encendido, tiene_smb)."""
    for p in PUERTOS_SMB:
        if puerto_abierto(ip, p, espera):
            return ip, True, True
    if usar_ping and responde_ping(ip, int(espera * 1000)):
        return ip, True, False
    return ip, False, False


# --------------------------------------------------------------------------- #
# Recursos compartidos
# --------------------------------------------------------------------------- #

def conectar_credenciales(ip: str, usuario: str, clave: str) -> None:
    try:
        subprocess.run(["net", "use", f"\\\\{ip}\\IPC$", clave, f"/user:{usuario}"],
                       capture_output=True, timeout=25, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass


def desconectar(ip: str) -> None:
    try:
        subprocess.run(["net", "use", f"\\\\{ip}\\IPC$", "/delete", "/y"],
                       capture_output=True, timeout=15, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass


def listar_recursos(ip: str, extra: list[str], espera: int = 25) -> list[str]:
    """Enumera los recursos compartidos accesibles de un equipo."""
    candidatos: list[str] = list(extra)

    for args in (["net", "view", f"\\\\{ip}", "/all"], ["net", "view", f"\\\\{ip}"]):
        try:
            p = subprocess.run(args, capture_output=True, timeout=espera,
                               creationflags=CREATE_NO_WINDOW)
        except Exception:
            continue
        salida = decodificar(p.stdout)
        if "---" not in salida:
            continue
        nuevos = 0
        for linea in salida.split("---", 1)[1].splitlines():
            if not linea.strip() or linea.lstrip().startswith("-"):
                continue
            if re.search(r"(completed|complet|correctamente|xito|exito)", linea, re.I):
                continue
            nombre = re.split(r"\s{2,}|\t", linea.strip())[0].strip()
            if not nombre or nombre.upper() in RECURSOS_OMITIDOS:
                continue
            if nombre not in candidatos:
                candidatos.append(nombre)
                nuevos += 1
        if nuevos:
            break

    validos = []
    for nombre in candidatos:
        try:
            if os.path.isdir(f"\\\\{ip}\\{nombre}"):
                validos.append(nombre)
        except OSError:
            continue
    return validos


# --------------------------------------------------------------------------- #
# Criterios de busqueda
# --------------------------------------------------------------------------- #

class Criterio:
    __slots__ = ("original", "patron", "es_glob")

    def __init__(self, texto: str):
        self.original = texto.strip()
        self.patron = self.original.lower()
        self.es_glob = any(ch in self.patron for ch in "*?[")


def normalizar_extensiones(valores: list[str]) -> list[str]:
    exts: list[str] = []
    for v in valores:
        for parte in re.split(r"[,;\s]+", v):
            parte = parte.strip().lower().lstrip("*")
            if not parte:
                continue
            if not parte.startswith("."):
                parte = "." + parte
            if parte not in exts:
                exts.append(parte)
    return exts


def coincide(nombre: str, criterios: list[Criterio], exts: list[str]) -> str | None:
    n = nombre.lower()
    if exts and not any(n.endswith(x) for x in exts):
        return None
    if not criterios:
        return "(solo extension)" if exts else None
    for c in criterios:
        if c.es_glob:
            if fnmatch.fnmatch(n, c.patron):
                return c.original
        elif c.patron in n:
            return c.original
    return None


# --------------------------------------------------------------------------- #
# Estado compartido
# --------------------------------------------------------------------------- #

class Estado:
    def __init__(self, cfg):
        self.cfg = cfg
        self.detener = threading.Event()
        self.lock = threading.Lock()
        self.hosts_totales = 0
        self.hosts_hechos = 0
        self.host_actual: dict[int, str] = {}
        self.carpetas = 0
        self.archivos = 0
        self.errores = 0
        self.hallazgos: list[dict] = []
        self.csv_writer = None
        self.csv_file = None
        self.inicio = time.time()

    def sumar(self, carpetas=0, archivos=0, errores=0):
        with self.lock:
            self.carpetas += carpetas
            self.archivos += archivos
            self.errores += errores

    def registrar(self, fila: dict) -> None:
        with self.lock:
            self.hallazgos.append(fila)
            if self.csv_writer:
                self.csv_writer.writerow(fila)
                self.csv_file.flush()


def hilo_progreso(est: Estado, intervalo: float) -> None:
    while not est.detener.wait(intervalo):
        with est.lock:
            hechos, tot = est.hosts_hechos, est.hosts_totales
            carp, arch, hall = est.carpetas, est.archivos, len(est.hallazgos)
            activos = [v for v in est.host_actual.values() if v]
        transcurrido = int(time.time() - est.inicio)
        mm, ss = divmod(transcurrido, 60)
        detalle = (", ".join(sorted(activos)[:3])) or "-"
        log(f".. equipos {hechos}/{tot} | carpetas {carp:,} | archivos {arch:,} "
            f"| hallazgos {hall} | {mm:02d}:{ss:02d} | en curso: {detalle}", "cian")


# --------------------------------------------------------------------------- #
# Busqueda
# --------------------------------------------------------------------------- #

def recorrer(raiz: str, etiqueta: str, criterios: list[Criterio], exts: list[str],
             est: Estado, limite: float) -> None:
    """Recorrido iterativo de un recurso compartido."""
    cfg = est.cfg
    pila: list[tuple[str, int]] = [(raiz, 0)]
    carpetas = archivos = errores = 0

    while pila:
        if est.detener.is_set() or time.time() > limite:
            if time.time() > limite:
                log(f"   ~ tiempo agotado en {etiqueta}, se pasa al siguiente", "amarillo")
            break

        ruta, prof = pila.pop()
        carpetas += 1
        try:
            with os.scandir(ruta) as it:
                for e in it:
                    if est.detener.is_set():
                        break
                    try:
                        es_dir = e.is_dir(follow_symlinks=False)
                    except OSError:
                        errores += 1
                        continue

                    if es_dir:
                        if cfg.profundidad and prof + 1 > cfg.profundidad:
                            continue
                        if not cfg.todo and e.name.lower() in CARPETAS_OMITIDAS:
                            continue
                        pila.append((e.path, prof + 1))
                        continue

                    archivos += 1
                    patron = coincide(e.name, criterios, exts)
                    if not patron:
                        continue
                    try:
                        st = e.stat(follow_symlinks=False)
                        tam, mod = st.st_size, st.st_mtime
                    except OSError:
                        tam, mod = 0, 0
                    fecha = (datetime.fromtimestamp(mod).strftime("%Y-%m-%d %H:%M:%S")
                             if mod else "?")
                    est.registrar({
                        "coincidencia": patron,
                        "archivo": e.name,
                        "ruta": e.path,
                        "tamano": tam,
                        "tamano_legible": humano(tam),
                        "modificado": fecha,
                        "equipo": etiqueta.split("\\")[0] if "\\" in etiqueta else etiqueta,
                        "encontrado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    log(f"  >> [{patron}] {e.path}", "verde")
                    log(f"     {humano(tam):>12}  |  modificado: {fecha}", "blanco")
                    if cfg.max_hallazgos and len(est.hallazgos) >= cfg.max_hallazgos:
                        log(f"!! limite de {cfg.max_hallazgos} hallazgos alcanzado", "amarillo")
                        est.detener.set()
                        break
        except (PermissionError, OSError):
            errores += 1
            continue

        if carpetas % 200 == 0:
            est.sumar(carpetas=carpetas, archivos=archivos, errores=errores)
            carpetas = archivos = errores = 0

    est.sumar(carpetas=carpetas, archivos=archivos, errores=errores)


def procesar_equipo(ip: str, nombre: str, criterios: list[Criterio], exts: list[str],
                    est: Estado) -> None:
    cfg = est.cfg
    ident = threading.get_ident()
    etiqueta_eq = f"{ip}" + (f" ({nombre})" if nombre else "")
    with est.lock:
        est.host_actual[ident] = ip
    try:
        if est.detener.is_set():
            return

        if cfg.usuario:
            conectar_credenciales(ip, cfg.usuario, cfg.clave or "")

        recursos = listar_recursos(ip, cfg.recursos)
        if not recursos:
            log(f"-- {etiqueta_eq}: sin carpetas compartidas accesibles", "gris")
            return

        log(f"== {etiqueta_eq}: {len(recursos)} recurso(s) -> {', '.join(recursos)}", "magenta")
        for r in recursos:
            if est.detener.is_set():
                return
            raiz = f"\\\\{ip}\\{r}"
            log(f"   escaneando {raiz}", "gris")
            limite = time.time() + cfg.tiempo_recurso
            recorrer(raiz, f"{ip}\\{r}", criterios, exts, est, limite)
    finally:
        if cfg.usuario:
            desconectar(ip)
        with est.lock:
            est.host_actual[ident] = ""
            est.hosts_hechos += 1


# --------------------------------------------------------------------------- #
# Flujo principal
# --------------------------------------------------------------------------- #

def descubrir(ips: list[str], est: Estado) -> list[tuple[str, str]]:
    cfg = est.cfg
    log(f"Fase 1/2 - buscando equipos encendidos en {len(ips)} direcciones "
        f"({cfg.hilos_descubrimiento} sondas en paralelo)...", "amarillo")

    vivos: list[tuple[str, str]] = []
    revisados = 0
    total = len(ips)

    def tarea(ip):
        return sondear(ip, cfg.espera, cfg.ping)

    with ThreadPoolExecutor(max_workers=cfg.hilos_descubrimiento) as pool:
        for ip, encendido, smb in pool.map(tarea, ips):
            revisados += 1
            if est.detener.is_set():
                break
            if encendido:
                nom = nombre_equipo(ip) if cfg.resolver else ""
                marca = "SMB" if smb else "sin SMB"
                log(f"++ encendido {ip:<15} {('(' + nom + ')') if nom else '':<18} [{marca}]",
                    "verde" if smb else "gris")
                if smb or not cfg.solo_smb:
                    vivos.append((ip, nom))
            if revisados % 64 == 0 or revisados == total:
                log(f".. sondeadas {revisados}/{total} direcciones, {len(vivos)} utiles", "cian")

    return vivos


def ejecutar(cfg) -> int:
    est = Estado(cfg)
    criterios = [Criterio(n) for n in cfg.nombres if n.strip()]
    exts = normalizar_extensiones(cfg.extensiones)

    if not criterios and not exts and not cfg.solo_listar:
        log("Debes indicar al menos un nombre (-n) o una extension (-e).", "rojo")
        return 2

    ips: list[str] = []
    for r in cfg.redes:
        for ip in expandir_red(r):
            if ip not in ips:
                ips.append(ip)

    print()
    log("=" * 78, "gris")
    log("BUSCADOR DE ARCHIVOS EN RED LOCAL", "blanco")
    log(f"Nombres    : {', '.join(c.original for c in criterios) or '(cualquiera)'}", "blanco")
    log(f"Extensiones: {', '.join(exts) or '(cualquiera)'}", "blanco")
    log(f"Segmentos  : {', '.join(cfg.redes)}  ->  {len(ips)} direcciones", "blanco")
    log(f"Inicio     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "blanco")
    log("=" * 78, "gris")
    print()

    if cfg.csv:
        campos = ["coincidencia", "archivo", "ruta", "tamano", "tamano_legible",
                  "modificado", "equipo", "encontrado"]
        est.csv_file = open(cfg.csv, "w", newline="", encoding="utf-8-sig")
        est.csv_writer = csv.DictWriter(est.csv_file, fieldnames=campos, delimiter=";")
        est.csv_writer.writeheader()
        log(f"Los resultados se guardan en: {os.path.abspath(cfg.csv)}", "amarillo")

    codigo = 0
    try:
        vivos = descubrir(ips, est)
        print()
        log(f"Equipos utiles encontrados: {len(vivos)}", "amarillo")
        if not vivos:
            log("No hay equipos con carpetas compartidas accesibles.", "rojo")
            return 1

        if cfg.solo_listar:
            for ip, nom in vivos:
                recursos = listar_recursos(ip, cfg.recursos)
                log(f"{ip:<15} {nom:<18} -> {', '.join(recursos) or '(sin acceso)'}", "cian")
            return 0

        est.hosts_totales = len(vivos)
        est.inicio = time.time()
        print()
        log(f"Fase 2/2 - buscando archivos ({cfg.hilos_equipos} equipos a la vez)...",
            "amarillo")
        print()

        prog = threading.Thread(target=hilo_progreso, args=(est, cfg.progreso), daemon=True)
        prog.start()

        with ThreadPoolExecutor(max_workers=cfg.hilos_equipos) as pool:
            futuros = [pool.submit(procesar_equipo, ip, nom, criterios, exts, est)
                       for ip, nom in vivos]
            for f in futuros:
                f.result()

    except KeyboardInterrupt:
        est.detener.set()
        print()
        log("Interrumpido por el usuario (Ctrl+C). Mostrando lo encontrado hasta ahora.",
            "rojo")
        codigo = 130
    finally:
        est.detener.set()

    resumen(est, criterios, exts)
    if est.csv_file:
        est.csv_file.close()
    return codigo


def resumen(est: Estado, criterios: list[Criterio], exts: list[str]) -> None:
    dur = int(time.time() - est.inicio)
    mm, ss = divmod(dur, 60)
    print()
    log("=" * 78, "gris")
    log("RESUMEN", "blanco")
    log(f"Duracion de la busqueda : {mm:02d}:{ss:02d}", "blanco")
    log(f"Equipos revisados       : {est.hosts_hechos}/{est.hosts_totales}", "blanco")
    log(f"Carpetas recorridas     : {est.carpetas:,}", "blanco")
    log(f"Archivos examinados     : {est.archivos:,}", "blanco")
    log(f"Accesos denegados/error : {est.errores:,}", "blanco")
    log(f"Coincidencias           : {len(est.hallazgos)}", "verde" if est.hallazgos else "rojo")
    log("=" * 78, "gris")

    if not est.hallazgos:
        log("No se encontro ningun archivo con esos criterios.", "rojo")
        return

    por_patron: dict[str, list[dict]] = {}
    for h in est.hallazgos:
        por_patron.setdefault(h["coincidencia"], []).append(h)

    for patron, filas in por_patron.items():
        print()
        log(f"[{patron}] -> {len(filas)} archivo(s)", "amarillo")
        for h in sorted(filas, key=lambda x: x["modificado"], reverse=True):
            log(f"   {h['modificado']}  {h['tamano_legible']:>12}  {h['ruta']}", "verde")

    if est.csv_file:
        print()
        log(f"CSV guardado en: {os.path.abspath(est.cfg.csv)}", "amarillo")


# --------------------------------------------------------------------------- #
# Asistente interactivo
# --------------------------------------------------------------------------- #

def preguntar(texto: str, defecto: str = "") -> str:
    sufijo = f" [{defecto}]" if defecto else ""
    try:
        r = input(f"{col('?', 'amarillo')} {texto}{sufijo}: ").strip()
    except EOFError:
        return defecto
    return r or defecto


def asistente(cfg) -> None:
    print()
    print(col("=" * 78, "gris"))
    print(col("  BUSCADOR DE ARCHIVOS EN RED LOCAL - asistente", "blanco"))
    print(col("=" * 78, "gris"))
    print(col("  Puedes buscar 1, 2 o 3 nombres a la vez. Deja vacio para terminar.", "gris"))
    print(col("  Se acepta texto parcial (factura) o comodines (fact*2024*).", "gris"))
    print()

    nombres = []
    for i in range(1, 4):
        v = preguntar(f"Nombre del archivo {i} (vacio = fin)")
        if not v:
            break
        nombres.append(v)

    ext = preguntar("Extensiones separadas por coma (pdf,xlsx,docx) o vacio para todas")

    detectadas = redes_locales()
    sugerencia = ",".join(detectadas) if detectadas else "192.1.1,192.1.2,192.1.3"
    redes = preguntar("Segmentos de red separados por coma", sugerencia)

    guardar = preguntar("Guardar resultados en CSV? (s/n)", "s").lower().startswith("s")

    cfg.nombres = nombres
    cfg.extensiones = [ext] if ext else []
    cfg.redes = [r.strip() for r in redes.split(",") if r.strip()]
    if guardar and not cfg.csv:
        cfg.csv = f"resultados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    avanzado = preguntar("Ajustar opciones avanzadas (hilos, tiempos)? (s/n)", "n")
    if avanzado.lower().startswith("s"):
        cfg.hilos_equipos = int(preguntar("Equipos a escanear a la vez", str(cfg.hilos_equipos)))
        cfg.tiempo_recurso = int(preguntar("Segundos maximos por carpeta compartida",
                                           str(cfg.tiempo_recurso)))
        cfg.profundidad = int(preguntar("Profundidad maxima de subcarpetas (0 = sin limite)",
                                        str(cfg.profundidad)))
        u = preguntar("Usuario para equipos protegidos (vacio = sesion actual)")
        if u:
            cfg.usuario = u
            import getpass
            cfg.clave = getpass.getpass("  Contrasena: ")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="buscar_red.py",
        description="Busca archivos por nombre y/o extension en los equipos "
                    "encendidos de varios segmentos de la red local.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Ejemplos:
  python buscar_red.py
  python buscar_red.py -n factura -e pdf -r 192.1.1
  python buscar_red.py -n factura -n nomina -n contrato -e pdf,docx -r 192.1.1 -r 192.1.2 -r 192.1.3
  python buscar_red.py -n "*2024*" -e xlsx -r 192.1.1.10-60 --csv salida.csv
  python buscar_red.py --listar -r 192.1.1
""")
    p.add_argument("-n", "--nombre", dest="nombres", action="append", default=[],
                   help="Nombre o parte del nombre. Repetir hasta 3 veces.")
    p.add_argument("-e", "--ext", dest="extensiones", action="append", default=[],
                   help="Extensiones separadas por coma: pdf,xlsx,docx")
    p.add_argument("-r", "--red", dest="redes", action="append", default=[],
                   help="Segmento: 192.1.1 | 192.1.1.0/24 | 192.1.1.10-90 | 192.1.1.5")
    p.add_argument("--auto-redes", action="store_true",
                   help="Detecta automaticamente los segmentos de este equipo.")
    p.add_argument("--csv", default="", help="Archivo CSV donde guardar los resultados.")
    p.add_argument("--recurso", dest="recursos", action="append", default=[],
                   help="Forzar nombres de carpetas compartidas a probar (ej: Datos, C$).")
    p.add_argument("--usuario", default="", help="Usuario para autenticarse (DOMINIO\\usuario).")
    p.add_argument("--clave", default="", help="Contrasena del usuario.")
    p.add_argument("--hilos-equipos", type=int, default=6,
                   help="Equipos escaneados a la vez (por defecto 6).")
    p.add_argument("--hilos-descubrimiento", type=int, default=128,
                   help="Sondas simultaneas al buscar equipos encendidos (128).")
    p.add_argument("--espera", type=float, default=0.4,
                   help="Segundos de espera por sonda de puerto (0.4).")
    p.add_argument("--tiempo-recurso", type=int, default=300,
                   help="Segundos maximos por carpeta compartida (300).")
    p.add_argument("--profundidad", type=int, default=0,
                   help="Profundidad maxima de subcarpetas, 0 = sin limite.")
    p.add_argument("--max-hallazgos", type=int, default=0,
                   help="Detener al alcanzar N coincidencias, 0 = sin limite.")
    p.add_argument("--progreso", type=float, default=10.0,
                   help="Segundos entre lineas de progreso (10).")
    p.add_argument("--todo", action="store_true",
                   help="No omitir carpetas de sistema (Windows, ProgramData...).")
    p.add_argument("--ping", action="store_true",
                   help="Tambien detectar equipos que solo responden a ping.")
    p.add_argument("--todos-los-equipos", dest="solo_smb", action="store_false",
                   help="Intentar escanear tambien equipos sin SMB detectado.")
    p.add_argument("--sin-nombres", dest="resolver", action="store_false",
                   help="No resolver el nombre de cada equipo (mas rapido).")
    p.add_argument("--listar", dest="solo_listar", action="store_true",
                   help="Solo listar equipos y sus carpetas compartidas.")
    p.set_defaults(solo_smb=True, resolver=True, solo_listar=False)
    return p


def main(argv: list[str]) -> int:
    init_consola()
    socket.setdefaulttimeout(2.0)
    cfg = construir_parser().parse_args(argv)

    if cfg.auto_redes and not cfg.redes:
        cfg.redes = redes_locales()

    interactivo = not cfg.nombres and not cfg.extensiones and not cfg.solo_listar
    if interactivo:
        asistente(cfg)

    if not cfg.redes:
        cfg.redes = redes_locales() or ["192.1.1", "192.1.2", "192.1.3"]

    if len(cfg.nombres) > 3:
        log("Aviso: se recomiendan como maximo 3 nombres a la vez.", "amarillo")

    try:
        codigo = ejecutar(cfg)
    except ValueError as e:
        log(str(e), "rojo")
        return 2

    if interactivo:
        try:
            input("\nPulsa ENTER para salir...")
        except EOFError:
            pass
    return codigo


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
