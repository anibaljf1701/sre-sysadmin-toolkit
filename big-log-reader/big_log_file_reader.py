"""
Un servidor web escribe una línea en su registro de acceso por cada página
que sirve. En un sitio con mucho tráfico, ese archivo puede crecer hasta
ocupar varios gigabytes. Si guardas todas las líneas en una lista, Python
mantiene el archivo entero en memoria. En cambio, un generador entrega una
línea a la vez, por lo que la memoria no crece con el tamaño del archivo.
Los contadores sí ocupan memoria según la cantidad de rutas distintas.


EJECUCIÓN
    python3 big_log_file_reader.py access.log [opciones]
    --from/--to                  filtran por intervalo ISO-8601
    --route                      filtra por ruta exacta
    --format-regex/--timestamp-format configuran otro formato de log

No requiere paquetes externos: usa únicamente la biblioteca estándar de Python.
La generación de muestras y la lectura con listas quedan comentadas en el
código como material de prueba y comparación.
"""

import argparse
import re
import tracemalloc
from time import perf_counter
from collections import Counter
from datetime import datetime
from pathlib import Path

DEFAULT_LOG_PATTERN = (
    r'\[(?P<timestamp>[^\]]+)\]\s+'
    r'"\S+\s+(?P<route>\S+)\s+\S+"\s+'
    r'(?P<status>\d{3})(?:\s|$)'
)
DEFAULT_TIMESTAMP_FORMAT = "%d/%b/%Y:%H:%M:%S %z"

# Datos y dependencias usados solo por el generador de logs de prueba:
# import random
# import time
# PAGES = ["/", "/blog/python-generators", "/blog/decorators", "/about", "/pricing",
#          "/login", "/api/search", "/static/app.js", "/static/style.css", "/wp-login.php"]
# WEIGHTS = [18, 12, 9, 4, 5, 6, 10, 16, 16, 4]
# FAIL_RATE = {"/api/search": 0.04, "/login": 0.005}
# BROWSERS = [
#     "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
#     "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
#     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
#     "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
#     "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 "
#     "(KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1",
# ]


# Código de prueba, desactivado: genera logs sintéticos para comparar los
# modos de lectura. No forma parte del análisis de logs reales.
# def fake_lines(count):
#     """Genera `count` líneas de registro para pruebas, una por vez."""
#     rnd = random.Random(40)
#     t = 1792368000
#     for _ in range(count):
#         t += rnd.random() * 86400 * 2 / count
#         page = rnd.choices(PAGES, WEIGHTS)[0]
#         if page == "/wp-login.php":
#             status = 404
#         elif rnd.random() < FAIL_RATE.get(page, 0):
#             status = 500
#         else:
#             status = 304 if rnd.random() < 0.08 else 200
#         when = time.strftime("%d/%b/%Y:%H:%M:%S +0000", time.gmtime(t))
#         yield (f'203.0.113.{rnd.randrange(1, 255)} - - [{when}] "GET {page} HTTP/1.1" '
#                f'{status} {rnd.randrange(200, 60000)} "-" "{rnd.choice(BROWSERS)}"\n')


def parse(line, pattern, timestamp_format):
    """Extrae fecha, ruta y estado; devuelve None si la línea no coincide."""
    match = pattern.search(line)
    if match is None:
        return None

    fields = match.groupdict()
    if not all(fields.get(name) for name in ("timestamp", "route", "status")):
        return None
    if not fields["status"].isdigit() or len(fields["status"]) != 3:
        return None

    status_code = int(fields["status"])
    if not 100 <= status_code <= 599:
        return None

    try:
        timestamp = datetime.strptime(fields["timestamp"], timestamp_format)
    except ValueError:
        return None
    return timestamp, fields["route"], fields["status"]


def read_requests(path, pattern, timestamp_format):
    """Generador de solicitudes; entrega None para líneas malformadas."""
    with open(path) as f:
        for line in f:                  # lee el archivo una línea a la vez
            yield parse(line, pattern, timestamp_format)


# Código de comparación, desactivado: conserva todas las solicitudes en una
# lista para medir la diferencia de memoria frente a `read_requests`.
# def load_requests(path):
#     requests = []
#     with open(path) as f:
#         for line in f:
#             requests.append(parse(line))
#     return requests


def report(requests, start=None, end=None, route=None):
    """Resume solicitudes válidas e informa cuántas líneas se descartaron."""
    total, not_found, malformed, filtered = 0, 0, 0, 0
    pages, errors = Counter(), Counter()
    for request in requests:
        if request is None:
            malformed += 1
            continue
        timestamp, page, status = request
        if (start is not None and timestamp < start) or (end is not None and timestamp > end):
            filtered += 1
            continue
        if route is not None and page != route:
            filtered += 1
            continue
        total += 1
        pages[page] += 1
        if status.startswith("5"):
            errors[page] += 1
        elif status == "404":
            not_found += 1
    print(f"  Requests:      {total:>11,}")
    print(f"  Malformed lines:{malformed:>10,}   (skipped)")
    print(f"  Filtered out:  {filtered:>11,}")
    print(f"  Server errors: {sum(errors.values()):>11,}   (status 5xx)")
    print(f"  Not found:     {not_found:>11,}   (status 404)")
    print("  Busiest pages:")
    for page, count in pages.most_common(3):
        print(f"    {page:<22}{count:>10,}")
    if errors:
        page, count = errors.most_common(1)[0]
        print(f"  Most errors:   {page} ({count:,} of {sum(errors.values()):,})")


# Código de prueba, desactivado: crea un log sintético grande en el directorio
# actual. Para reactivarlo, descomentar el generador, sus datos/imports y esta
# función junto con la rama `--sample` de `main`.
# def make_sample(millions):
#     path = Path("access.log")
#     print(f"Writing {path} with {millions:g} million lines...")
#     with open(path, "w") as f:
#         f.writelines(fake_lines(int(millions * 1_000_000)))
#     print(f"Done: {path.stat().st_size / 1e9:.2f} GB")


def main():
    parser = argparse.ArgumentParser(
        description="Analiza access logs grandes sin cargarlos completos en memoria."
    )
    parser.add_argument("logfile", type=Path, help="archivo de log que se analizará")
    parser.add_argument(
        "--format-regex",
        default=DEFAULT_LOG_PATTERN,
        help=(
            "regex con grupos nombrados timestamp, route y status; el predeterminado "
            "cubre formatos access comunes/combinados de Apache y Nginx"
        ),
    )
    parser.add_argument(
        "--timestamp-format",
        default=DEFAULT_TIMESTAMP_FORMAT,
        help="formato strptime para el grupo timestamp (predeterminado: Apache/Nginx)",
    )
    parser.add_argument("--from", dest="start", type=parse_iso_datetime, help="inicio inclusivo ISO-8601")
    parser.add_argument("--to", dest="end", type=parse_iso_datetime, help="fin inclusivo ISO-8601")
    parser.add_argument("--route", help="filtrar por coincidencia exacta de ruta")
    parser.add_argument(
        "--measure-memory",
        action="store_true",
        help="activa tracemalloc para informar el pico de memoria (añade sobrecarga)",
    )
    args = parser.parse_args()

    if args.start is not None and args.end is not None and args.start > args.end:
        parser.error("--from debe ser anterior o igual a --to")
    if (args.start is not None or args.end is not None) and "%z" not in args.timestamp_format:
        parser.error("--timestamp-format debe incluir %z cuando se filtra por período")
    try:
        pattern = re.compile(args.format_regex)
    except re.error as error:
        parser.error(f"regex inválida: {error}")
    required_groups = {"timestamp", "route", "status"}
    if not required_groups.issubset(pattern.groupindex):
        parser.error("la regex debe definir los grupos nombrados timestamp, route y status")

    # CLI de prueba, desactivado: descomentar junto con `make_sample` para
    # generar datos, o con `load_requests` para comparar lectura con lista.
    # if args[:1] == ["--sample"]:
    #     return make_sample(float(args[1]) if len(args) > 1 else 5)
    # path, use_list = Path(args[0]), "--list" in args
    # requests = load_requests(path) if use_list else read_requests(path)
    # report(requests)
    path = args.logfile
    if not path.is_file():
        parser.error(f"{path} no es un archivo existente")

    print(f"Reading {path} ({path.stat().st_size / 1e9:.2f} GB) with a generator...")
    if args.measure_memory:
        tracemalloc.start()
    started_at = perf_counter()
    report(
        read_requests(path, pattern, args.timestamp_format),
        start=args.start,
        end=args.end,
        route=args.route,
    )
    elapsed = perf_counter() - started_at
    print(f"  Elapsed time:  {elapsed:>11,.3f} s")
    if args.measure_memory:
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        print(f"  Peak memory:   {peak / 1e6:>11,.2f} MB")


def parse_iso_datetime(value):
    """Parsea fecha ISO-8601 con zona horaria para filtros no ambiguos."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"fecha ISO-8601 inválida: {value}") from error
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("la fecha debe incluir zona horaria, por ejemplo +00:00 o Z")
    return parsed


if __name__ == "__main__":
    main()