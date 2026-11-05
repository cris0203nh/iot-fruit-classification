# DevSecOps — Incremento 01 (pipeline y línea base)

**Rama de trabajo:** `security/devsecops-hardening`
**Punto de partida:** `5544bfceffedea167e40c686381e7e32ba771d41` (`origin/main` al preparar el incremento).
**Alcance:** configuración de GitHub Actions, pruebas existentes y análisis inicial. **No cambia** endpoints, lógica de negocio, frontend, firmware ni bases de datos.

## Qué se ejecuta

El workflow `.github/workflows/devsecops.yml` se activa al hacer `push` a la rama de seguridad, al abrir un PR hacia `main` o al iniciarlo manualmente cuando esté disponible.

| Job | Cobertura | ¿Bloquea? |
|---|---|---|
| `python-tests` | Backend, tests IoT/puente, núcleo C++ y validación de reportes | **Sí**, si falla una prueba |
| `frontend-tests` | Instalación limpia `npm ci`, ESLint, tests y build Vite | **Sí**, si falla una comprobación |
| `bandit` | SAST sobre `backend/app`, `backend/dataset`, `firmware/tools` | **Solo errores de ejecución**, por ahora hallazgos en observación |
| `python-sca` | `pip-audit` sobre versiones fijadas de backend y firmware | **Solo errores de ejecución**, por ahora hallazgos en observación |
| `node-sca` | `npm audit` sobre `frontend/package-lock.json` | **Solo errores de ejecución**, por ahora hallazgos en observación |
| `secrets` | Gitleaks: historial completo (observación) y cambios de la rama respecto a `origin/main` | **Sí** si aparecen secretos en commits nuevos, también errores de ejecución |

**Importante:** este incremento busca cuantificar los problemas existentes *antes de corregirlos*. No incluye una excepción permanente ni `|| true`: se distinguen códigos de hallazgos (1) de errores técnicos de los escáneres. Los hallazgos previos se documentan y se revisan antes de convertirlos en criterios de bloqueo. La ejecución aún depende de runners hospedados, conectividad a registries y de que no existan restricciones de Actions en el repositorio.

## Seguridad de la automatización

- `GITHUB_TOKEN` solo tiene permiso de lectura (`contents: read`); `checkout` no conserva credenciales después de la descarga.
- Acciones oficiales referenciadas por SHA completos, anotando la versión conocida.
- La imagen oficial Gitleaks está fijada por digest; el escáner completo recorre el historial Git y el segundo escaneo revisa `origin/main..HEAD`.
- La carpeta `reports/` contiene su propio `.gitignore`, para impedir que se versionen reportes locales. Los informes sin sanitizar se escriben allí solo de forma transitoria y **no se publican**. `normalize_scan.py` extrae exclusivamente campos explícitos y borra los originales. En especial, no exporta `Secret`, `Match`, correos, fragmentos de código ni descripciones de hallazgos.
- Artefactos con retención de 14 días, sin código ni datos de clientes. Se recomienda limitar el acceso a las ejecuciones del repositorio.
- **No** se sube `backend/.env`, bases SQLite, imágenes privadas, `.venv` ni `node_modules`.

## Cómo aplicar el parche en Windows PowerShell

Desde el directorio del worktree independiente:

```powershell
cd "C:\Users\Luigi\Documents\Proyectos Personales\iot-fruit-classification-devsecops"

git status --short
# El archivo .patch se debe colocar fuera del repositorio; reemplazar la ruta.
git apply --check "C:\RUTA\AgroScan_DEVSECOPS_Incremento01.patch"
git apply "C:\RUTA\AgroScan_DEVSECOPS_Incremento01.patch"

git status --short
python -m unittest discover -s scripts/devsecops -p 'test_*.py' -v
```

Antes de registrar:

```powershell
git diff --check
git status --short
# Revisar archivos nuevos y el contenido de los scripts
git add .github/workflows/devsecops.yml reports/.gitignore scripts/devsecops/normalize_scan.py scripts/devsecops/test_normalize_scan.py docs/devsecops/INCREMENTO-01.md
git diff --cached --name-only
git diff --cached --check
git commit -m "ci(devsecops): incorporar baseline SAST SCA secretos y QA"
git push -u origin security/devsecops-hardening
```

> Los cambios locales de `vision/` del otro worktree **no** están incluidos. Las pruebas de visión artificial no se incluyen en CI hasta que el equipo las registre en un commit y se integren en la rama base.

## Cómo comprobar el resultado en GitHub

1. **Actions → AgroScan DevSecOps - baseline y controles → ejecución de la rama.** Verificar los seis jobs.
2. **Artifacts:** descargar `devsecops-bandit`, `devsecops-python-sca`, `devsecops-npm-sca` y `devsecops-gitleaks`, si se generaron correctamente.
3. Guardar para la comparativa: fecha, SHA, conteo por herramienta, identificadores de vulnerabilidad, tests aprobados y fallos operativos. Un hallazgo de dependencia no equivale siempre a vulnerabilidad explotable; confirmar relevancia y severidad por separado.
4. **No fusionar a `main`.** Si se presenta un PR, dejarlo como borrador para revisión y comparación.

## Límites

- `pip-audit --no-deps` analiza versiones enumeradas en los archivos de requisitos; **no** resuelve nuevas dependencias transitivas no fijadas allí.
- `npm audit` depende de la base de datos de advisories del registro y ofrece gravedad por paquete; no asumir que su número de paquetes es equivalente al número de CVEs.
- Bandit genera alertas que requieren revisión, no una certificación de seguridad.
- Gitleaks busca patrones; la ausencia de coincidencias no demuestra ausencia de secretos. El escaneo del historial puede encontrar exposiciones antiguas que requieren rotación, aunque el archivo ya no esté en HEAD.
- El código de `vision/` con archivos no rastreados en el proyecto original no existe en la línea base Git `5544bfc` del worktree aislado.
- Esta fase **no es DAST** ni corrige autenticación IoT, fuerza bruta en login, validación de imágenes, TLS o paginación. Estas actividades pertenecen al siguiente incremento tras revisar la línea base.
