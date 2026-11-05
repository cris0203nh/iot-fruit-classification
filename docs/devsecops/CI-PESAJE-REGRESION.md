# Incremento 05 — Corrección de regresión del workflow de pesaje

El commit `7b8e2eb` aprobó el workflow DevSecOps (run `41967242501`) pero falló el workflow heredado «Pesaje ESP32 y pruebas de software» (run `41967242502`). El log del job `software` registra:

`RuntimeError: La clave JWT no está configurada correctamente.`

Las pruebas de integración importan `app.security`, que exige un secreto JWT de longitud válida incluso durante la ejecución de tests. En la rama de seguridad esta exigencia es deliberada y **no** debe relajarse.

La corrección modifica exclusivamente `.github/workflows/pesaje.yml` y no el código de autenticación: genera una clave efímera con `secrets.token_hex(32)` para ese job, no la registra en Git ni la imprime, y define `PYTHONPATH=backend`. Además, actualiza las acciones `checkout`/`setup-python` a variantes Node.js 24 fijadas por SHA. La acción externa `arduino/setup-arduino-cli@v2` se fija por SHA pero sigue declarando Node.js 20; el aviso de deprecación puede persistir en el job de compilación.

**Criterio de aceptación:** en el push de este incremento deben aprobarse tanto «AgroScan DevSecOps - baseline y controles» como «Pesaje ESP32 y pruebas de software». El primer workflow ejecutará las pruebas ampliadas (incluida la integridad de evidencias), el segundo la suite de IoT (25 casos) y la compilación ESP32.

No fusionar a `main` desde esta rama sin revisión del equipo y sin revisar los riesgos residuales del informe final.
