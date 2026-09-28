# 🔍 Buscador de Archivos en Red Local

> Encuentra rápidamente archivos por **nombre** y/o **extensión** en todos los equipos encendidos de tu red local Windows, con resultados en tiempo real y exportación a CSV.

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.7%2B-blue?logo=python&logoColor=white">
  <img alt="Plataforma" src="https://img.shields.io/badge/Windows-10%2F11-0078D6?logo=windows&logoColor=white">
  <img alt="Sin dependencias" src="https://img.shields.io/badge/Dependencias-0%20externas-brightgreen">
  <img alt="Licencia" src="https://img.shields.io/badge/Uso-Red%20local%20autorizada-orange">
</p>

---

## ✨ Características

- 🖥️ **Descubrimiento automático** de equipos encendidos en uno o varios segmentos de red.
- 📂 **Enumeración de carpetas compartidas** accesibles de cada equipo.
- 🔎 **Búsqueda simultánea** de hasta **3 nombres** a la vez, con soporte para texto parcial y comodines (`fact*2024*`).
- 🧩 **Filtro por extensión** (`pdf`, `xlsx`, `docx`, …).
- ⚡ **Resultados en tiempo real** con ruta, tamaño y fecha de modificación.
- 📊 **Exportación a CSV** lista para abrir en Excel.
- 🧵 **Multihilo** para descubrimiento y escaneo rápidos.
- 🎨 **Salida en color** y **asistente interactivo** para quienes no usan la línea de comandos.
- 🚀 **Cero dependencias externas** — solo Python estándar.

---

## 📦 Requisitos

- **Python 3.7 o superior** (marca *"Add Python to PATH"* durante la instalación).
- **Windows 10 / 11** (usa `net view`, SMB y `ipconfig`).
- Acceso autorizado a la red y a las carpetas compartidas que quieras explorar.

---

## 🚀 Inicio rápido

### Opción A — Doble clic (recomendado)

Ejecuta **`Buscar en red.bat`** y usa el menú:

```
============================================================================
               BUSCADOR DE ARCHIVOS EN LA RED LOCAL
============================================================================

  1. Buscar archivos  (asistente: nombres, extension y segmentos)
  2. Busqueda rapida en 192.1.1 , 192.1.2 y 192.1.3
  3. Ver que equipos estan encendidos y sus carpetas compartidas
  4. Ayuda / todas las opciones
  5. Salir
```

### Opción B — Asistente interactivo

```bash
python buscar_red.py
```

Te preguntará los nombres, extensiones, segmentos y si deseas guardar en CSV.

### Opción C — Línea de comandos

```bash
python buscar_red.py -n factura -e pdf -r 192.1.1
```

---

## 💡 Ejemplos

```bash
# Buscar "factura" en PDF dentro del segmento 192.1.1
python buscar_red.py -n factura -e pdf -r 192.1.1

# Tres nombres a la vez, varias extensiones, tres segmentos
python buscar_red.py -n factura -n nomina -n contrato -e pdf,docx -r 192.1.1 -r 192.1.2 -r 192.1.3

# Comodines y rango de IP, guardando resultados en CSV
python buscar_red.py -n "*2024*" -e xlsx -r 192.1.1.10-60 --csv salida.csv

# Solo listar equipos encendidos y sus carpetas compartidas
python buscar_red.py --listar -r 192.1.1
```

---

## ⚙️ Opciones principales

| Opción | Descripción |
| --- | --- |
| `-n`, `--nombre` | Nombre o parte del nombre (repetir hasta 3 veces). |
| `-e`, `--ext` | Extensiones separadas por coma: `pdf,xlsx,docx`. |
| `-r`, `--red` | Segmento: `192.1.1` · `192.1.1.0/24` · `192.1.1.10-90` · `192.1.1.5`. |
| `--auto-redes` | Detecta automáticamente los segmentos de este equipo. |
| `--csv` | Archivo CSV donde guardar los resultados. |
| `--listar` | Solo listar equipos y sus carpetas compartidas. |
| `--usuario` / `--clave` | Credenciales para equipos protegidos (`DOMINIO\usuario`). |
| `--profundidad` | Profundidad máxima de subcarpetas (`0` = sin límite). |
| `--max-hallazgos` | Detener al alcanzar N coincidencias. |
| `--ping` | También detectar equipos que solo responden a ping. |

> 💬 Consulta todas las opciones con `python buscar_red.py --help`.

---

## 🎯 Formatos de segmento aceptados

| Formato | Significado |
| --- | --- |
| `192.1.1` | Todo el rango `.1` a `.254` |
| `192.1.1.0/24` | Notación CIDR |
| `192.1.1.10-90` | Rango de IPs |
| `192.1.1.55` | Una IP concreta |

---

## 📄 Resultados en CSV

Los resultados se guardan con codificación `UTF-8` y separador `;` (compatible con Excel en español):

| coincidencia | archivo | ruta | tamano | tamano_legible | modificado | equipo | encontrado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| factura | factura_marzo.pdf | `\\192.1.2.208\C$\...\factura_marzo.pdf` | 934348 | 912.4 KB | 2025-07-08 10:40:28 | 192.1.2.208 | 2026-09-03 09:37:31 |

---

## 🗂️ Estructura del proyecto

```
scan-archive/
├── buscar_red.py        # Motor de búsqueda (CLI + asistente)
├── Buscar en red.bat    # Lanzador con menú para Windows
└── README.md            # Este archivo
```

---

## ⚠️ Uso responsable

Esta herramienta está pensada para **administrar y localizar archivos en redes locales sobre las que tienes autorización**. Úsala únicamente en equipos y recursos compartidos a los que tengas permiso legítimo de acceso.

---

<p align="center">
  Hecho con 🐍 Python · Sin dependencias externas
</p>
