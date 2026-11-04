import argparse
import json
import random
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
DB = BASE / "data" / "agroscan.db"
OUTPUT = Path(__file__).resolve().parent / "salidas"

SEMILLA = 39
PORCENTAJES = {
    "entrenamiento": 0.70,
    "validacion": 0.15,
    "prueba": 0.15,
}


class UnionFind:
    def __init__(self):
        self.parent = {}
        self.rank = {}

    def add(self, item):
        if item not in self.parent:
            self.parent[item] = item
            self.rank[item] = 0

    def find(self, item):
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, a, b):
        self.add(a)
        self.add(b)
        ra, rb = self.find(a), self.find(b)

        if ra == rb:
            return

        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra

        self.parent[rb] = ra

        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def dividir_grupos(grupos):
    if len(grupos) < 3:
        raise ValueError(
            "Se necesitan al menos tres grupos independientes "
            "para generar entrenamiento, validacion y prueba."
        )

    nombres = list(PORCENTAJES)
    cantidades = {
        nombre: 1 for nombre in nombres
    }

    restantes = len(grupos) - 3

    while restantes:
        nombre = max(
            nombres,
            key=lambda n: (
                PORCENTAJES[n] * len(grupos) - cantidades[n],
                -nombres.index(n),
            ),
        )
        cantidades[nombre] += 1
        restantes -= 1

    ordenados = sorted(grupos, key=lambda g: (-len(g), g["id"]))
    random.Random(SEMILLA).shuffle(ordenados)
    ordenados.sort(key=lambda g: (-len(g), g["id"]))

    asignacion = {}
    cargas = {nombre: 0 for nombre in nombres}

    for grupo in ordenados:
        candidatos = [
            n for n in nombres
            if cantidades[n] > 0
        ]

        destino = max(
            candidatos,
            key=lambda n: (
                (cantidades[n] - cargas[n] - len(grupo["registros"])),
                PORCENTAJES[n] - cargas[n] / len(grupos),
            ),
        )

        asignacion[grupo["id"]] = destino
        cargas[destino] += 1
        cantidades[destino] -= 1

    return asignacion


def cargar_registros():
    if not DB.exists():
        raise FileNotFoundError(
            f"No se encontro la base principal: {DB}"
        )

    conexion = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
    )
    conexion.row_factory = sqlite3.Row

    consulta = """
        SELECT
            e.id AS evaluacion_id,
            e.piece_ref_id AS pieza_id,
            p.code AS codigo_pieza,
            l.product AS producto,
            e.device_id,
            e.boot_id,
            i.id AS imagen_id,
            i.relative_path,
            i.content_type,
            i.created_at AS imagen_fecha
        FROM evaluations e
        JOIN pieces p ON p.id = e.piece_ref_id
        JOIN lots l ON l.id = e.lot_id
        JOIN images i ON i.evaluation_id = e.id
        ORDER BY e.id, i.id
    """

    try:
        registros = [
            dict(row)
            for row in conexion.execute(consulta).fetchall()
        ]
    finally:
        conexion.close()

    return registros


def ejecutar():
    registros = cargar_registros()

    reporte = {
        "tarea": "AGROP-39",
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "base_utilizada": str(DB),
        "semilla": SEMILLA,
        "porcentajes_objetivo": PORCENTAJES,
        "total_fotografias_consultadas": len(registros),
        "fotografias_incluidas": 0,
        "fotografias_excluidas": 0,
        "motivos_exclusion": {},
        "grupos_independientes": 0,
        "particiones_generadas": False,
        "integridad": {},
    }

    piezas_invalidas = set()
    motivos = defaultdict(int)

    for registro in registros:
        if not registro["device_id"] or not registro["boot_id"]:
            piezas_invalidas.add(registro["pieza_id"])
            motivos["pieza_sin_sesion_verificable"] += 1

        if not registro["relative_path"]:
            piezas_invalidas.add(registro["pieza_id"])
            motivos["imagen_sin_ruta"] += 1

    elegibles = []

    for registro in registros:
        if registro["pieza_id"] in piezas_invalidas:
            continue

        ruta = (BASE / "data" / registro["relative_path"]).resolve()

        if not ruta.is_relative_to(BASE.resolve()):
            motivos["ruta_fuera_del_proyecto"] += 1
            continue

        if not ruta.is_file():
            motivos["archivo_no_encontrado"] += 1
            continue

        registro["ruta_archivo"] = str(ruta.relative_to(BASE.resolve()))
        elegibles.append(registro)

    reporte["fotografias_excluidas"] = (
        len(registros) - len(elegibles)
    )
    reporte["fotografias_incluidas"] = len(elegibles)
    reporte["motivos_exclusion"] = dict(motivos)

    OUTPUT.mkdir(parents=True, exist_ok=True)

    if not elegibles:
        reporte["mensaje"] = (
            "No existen fotografias con pieza, sesion y archivo verificables."
        )
        guardar_reporte(reporte)
        raise SystemExit(reporte["mensaje"])

    uf = UnionFind()

    for registro in elegibles:
        pieza = f"pieza:{registro['pieza_id']}"
        sesion = (
            f"sesion:{registro['device_id']}:"
            f"{registro['boot_id']}"
        )
        uf.union(pieza, sesion)

    componentes = defaultdict(list)

    for registro in elegibles:
        clave = uf.find(f"pieza:{registro['pieza_id']}")
        componentes[clave].append(registro)

    grupos = []

    for indice, (clave, items) in enumerate(
        sorted(componentes.items(), key=lambda x: str(x[0])),
        start=1,
    ):
        grupos.append({
            "id": f"grupo-{indice}",
            "registros": items,
        })

    reporte["grupos_independientes"] = len(grupos)

    try:
        asignacion = dividir_grupos(grupos)
    except ValueError as error:
        reporte["mensaje"] = str(error)
        reporte["estado"] = "bloqueado_por_datos_insuficientes"
        reporte["integridad"] = {
            "sin_cruces_de_piezas": None,
            "sin_cruces_de_sesiones": None,
            "validacion_ejecutada": False,
            "motivo": str(error),
            "fotografias_por_particion": {
                nombre: 0 for nombre in PORCENTAJES
            },
            "piezas_por_particion": {
                nombre: 0 for nombre in PORCENTAJES
            },
        }
        guardar_reporte(reporte)
        raise SystemExit(str(error))

    particiones = {
        nombre: [] for nombre in PORCENTAJES
    }

    for grupo in grupos:
        destino = asignacion[grupo["id"]]

        for registro in grupo["registros"]:
            particiones[destino].append({
                "imagen_id": registro["imagen_id"],
                "evaluacion_id": registro["evaluacion_id"],
                "pieza_id": registro["pieza_id"],
                "codigo_pieza": registro["codigo_pieza"],
                "producto": registro["producto"],
                "device_id": registro["device_id"],
                "boot_id": registro["boot_id"],
                "ruta_archivo": registro["ruta_archivo"],
            })

    def valores(particion, campo):
        return {
            item[campo] for item in particion
        }

    nombres = list(particiones)

    cruces_piezas = {}
    cruces_sesiones = {}

    for i, nombre in enumerate(nombres):
        for otro in nombres[i + 1:]:
            cruces_piezas[f"{nombre}-{otro}"] = sorted(
                valores(particiones[nombre], "pieza_id")
                & valores(particiones[otro], "pieza_id")
            )

            cruces_sesiones[f"{nombre}-{otro}"] = sorted(
                {
                    (x["device_id"], x["boot_id"])
                    for x in particiones[nombre]
                }
                & {
                    (x["device_id"], x["boot_id"])
                    for x in particiones[otro]
                }
            )

    sin_cruces = (
        all(not x for x in cruces_piezas.values())
        and all(not x for x in cruces_sesiones.values())
    )

    reporte["integridad"] = {
        "sin_cruces_de_piezas": all(
            not x for x in cruces_piezas.values()
        ),
        "sin_cruces_de_sesiones": all(
            not x for x in cruces_sesiones.values()
        ),
        "cruces_de_piezas": cruces_piezas,
        "cruces_de_sesiones": {
            k: [list(s) for s in v]
            for k, v in cruces_sesiones.items()
        },
        "fotografias_por_particion": {
            k: len(v) for k, v in particiones.items()
        },
        "piezas_por_particion": {
            k: len(valores(v, "pieza_id"))
            for k, v in particiones.items()
        },
    }

    reporte["particiones_generadas"] = sin_cruces

    if not sin_cruces:
        guardar_reporte(reporte)
        raise SystemExit("Error: se detectaron cruces entre particiones.")

    salida = {
        "tarea": "AGROP-39",
        "semilla": SEMILLA,
        "particiones": particiones,
    }

    (OUTPUT / "particiones.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    guardar_reporte(reporte)

    print("\n===== RESULTADO AGROP-39 =====")
    print(json.dumps(reporte, ensure_ascii=False, indent=2))


def guardar_reporte(reporte):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ruta = OUTPUT / "reporte_integridad.json"
    ruta.write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    ejecutar()


