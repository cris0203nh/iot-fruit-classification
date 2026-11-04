import unittest

from dataset.particionar_datos import dividir_grupos


class PruebasParticionado(unittest.TestCase):

    def crear_grupos(self, cantidad):
        return [
            {
                "id": f"grupo-{i}",
                "registros": [
                    {"pieza_id": i, "device_id": f"dispositivo-{i}",
                     "boot_id": f"sesion-{i}"}
                ],
            }
            for i in range(cantidad)
        ]

    def test_genera_tres_particiones(self):
        resultado = dividir_grupos(self.crear_grupos(20))

        self.assertEqual(len(resultado), 20)
        self.assertEqual(
            set(resultado.values()),
            {"entrenamiento", "validacion", "prueba"},
        )

    def test_ningun_grupo_se_repite(self):
        grupos = self.crear_grupos(20)
        resultado = dividir_grupos(grupos)

        self.assertEqual(
            len(resultado),
            len(set(resultado.keys())),
        )

    def test_rechaza_menos_de_tres_grupos(self):
        with self.assertRaises(ValueError):
            dividir_grupos(self.crear_grupos(2))

    def test_resultado_reproducible(self):
        grupos = self.crear_grupos(20)

        primero = dividir_grupos(grupos)
        segundo = dividir_grupos(grupos)

        self.assertEqual(primero, segundo)

    def test_misma_pieza_con_varias_sesiones_permanece_unida(self):
        from dataset.particionar_datos import UnionFind

        uf = UnionFind()

        uf.union("pieza:1", "sesion:equipo1:arranque1")
        uf.union("pieza:1", "sesion:equipo1:arranque2")

        self.assertEqual(
            uf.find("sesion:equipo1:arranque1"),
            uf.find("sesion:equipo1:arranque2"),
        )

    def test_misma_sesion_con_varias_piezas_permanece_unida(self):
        from dataset.particionar_datos import UnionFind

        uf = UnionFind()

        uf.union("pieza:1", "sesion:equipo1:arranque1")
        uf.union("pieza:2", "sesion:equipo1:arranque1")

        self.assertEqual(
            uf.find("pieza:1"),
            uf.find("pieza:2"),
        )

    def test_no_existen_cruces_entre_particiones(self):
        grupos = self.crear_grupos(20)
        resultado = dividir_grupos(grupos)

        piezas_por_particion = {}

        for grupo in grupos:
            destino = resultado[grupo["id"]]
            piezas_por_particion.setdefault(destino, set())
            piezas_por_particion[destino].add(
                grupo["registros"][0]["pieza_id"]
            )

        nombres = list(piezas_por_particion)

        for i, nombre in enumerate(nombres):
            for otro in nombres[i + 1:]:
                self.assertFalse(
                    piezas_por_particion[nombre]
                    & piezas_por_particion[otro]
                )

if __name__ == "__main__":
    unittest.main()

