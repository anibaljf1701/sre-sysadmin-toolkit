"""
Un servidor web escribe una línea en su registro de acceso por cada página
que sirve. En un sitio con mucho tráfico, ese archivo puede crecer hasta
ocupar varios gigabytes. Si guardas todas las líneas en una lista, Python
mantiene el archivo entero en memoria. En cambio, un generador entrega una
    línea a la vez, por lo que la memoria no crece con el tamaño del archivo.
    Los contadores sí ocupan memoria según la cantidad de rutas distintas.


EJECUCIÓN
    python3 {script_name} access.log          lo analiza línea por línea

No requiere paquetes externos: usa únicamente la biblioteca estándar de Python.
La generación de muestras y la lectura con listas quedan comentadas en el
código como material de prueba y comparación.
"""

import sys
import tracemalloc
from collections import Counter
from pathlib import Path

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


def parse(line):
    """Extrae página y estado, o devuelve None si la línea no es válida."""
    parts = line.split('"')             # la solicitud y el navegador están entre comillas
    if len(parts) < 3:
        return None

    request = parts[1].split()
    status_fields = parts[2].split()
    if len(request) != 3 or not request[0] or not request[1] or not request[2].startswith("HTTP/"):
        return None
    if not status_fields or not status_fields[0].isdigit() or len(status_fields[0]) != 3:
        return None

    status_code = int(status_fields[0])
    if not 100 <= status_code <= 599:
        return None

    page = request[1]
    status = status_fields[0]
    return page, status


def read_requests(path):
    """Generador de solicitudes; entrega None para líneas malformadas."""
    with open(path) as f:
        for line in f:                  # lee el archivo una línea a la vez
            yield parse(line)


# Código de comparación, desactivado: conserva todas las solicitudes en una
# lista para medir la diferencia de memoria frente a `read_requests`.
# def load_requests(path):
#     requests = []
#     with open(path) as f:
#         for line in f:
#             requests.append(parse(line))
#     return requests


def report(requests):
    """Resume solicitudes válidas e informa cuántas líneas se descartaron."""
    total, not_found, malformed = 0, 0, 0
    pages, errors = Counter(), Counter()
    for request in requests:
        if request is None:
            malformed += 1
            continue
        page, status = request
        total += 1
        pages[page] += 1
        if status.startswith("5"):
            errors[page] += 1
        elif status == "404":
            not_found += 1
    print(f"  Requests:      {total:>11,}")
    print(f"  Malformed lines:{malformed:>10,}   (skipped)")
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
    args = sys.argv[1:]
    script_name = Path(sys.argv[0]).name  # Obtiene dinámicamente el nombre del script
    # CLI de prueba, desactivado: descomentar junto con `make_sample` para
    # generar datos, o con `load_requests` para comparar lectura con lista.
    # if args[:1] == ["--sample"]:
    #     return make_sample(float(args[1]) if len(args) > 1 else 5)
    # path, use_list = Path(args[0]), "--list" in args
    # requests = load_requests(path) if use_list else read_requests(path)
    # report(requests)
    if not args:
        raise SystemExit(
            f"Usage: python3 {script_name} access.log"
        )
    path = Path(args[0])
    if not path.exists():
        raise SystemExit(f"{path} not found")

    print(f"Reading {path} ({path.stat().st_size / 1e9:.2f} GB) with a generator...")
    tracemalloc.start()                 # mide la memoria a partir de aquí (esto ralentiza Python)
    report(read_requests(path))
    peak = tracemalloc.get_traced_memory()[1]
    print(f"  Peak memory:   {peak / 1e6:>11,.2f} MB")


if __name__ == "__main__":
    main()