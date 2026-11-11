"""AG-038: evidencia reproducible de bitácora con API real y SQLite temporal.

NO usa la base operativa, ESP32, fotografías de frutas ni resultados reales.
El script NO certifica una validación física ni un dictamen agronómico.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.decision_models import ReviewDecisionEvidence
from app.main import app
from app.models import Evaluation, Image, Lot, Review, Role, User
from app.routers import review_decisions
from app.security import create_access_token, hash_password


CSV_FIELDS = ["evaluation_id", "original_value", "review_id", "action", "previous_value", "new_value",
              "actor_id", "performed_at", "reason", "image_id", "image_sha256", "request_id"]


def _require(response, expected: int, case: str) -> dict:
    if response.status_code != expected:
        raise AssertionError(f"{case}: HTTP {response.status_code}, esperado {expected}: {response.text[:400]}")
    return response.json()


def _write_exclusive(path: Path, text: str):
    with path.open('x', encoding='utf-8', newline='') as out:
        out.write(text)


def audit(output: Path) -> dict:
    """Produce evidencia de API real bajo autenticación simulada y datos aislados."""
    output = output.resolve()
    # Fail before doing any work if a previous report could be overwritten.
    if output.exists():
        raise ValueError('La carpeta de salida ya existe; elija una nueva para no sobrescribir evidencias.')
    # A production repository should not accidentally ingest synthetic evidence.
    repo = Path(__file__).resolve().parents[2]
    if output == repo or output.is_relative_to(repo):
        raise ValueError('La evidencia debe guardarse fuera del repositorio Git.')
    with tempfile.TemporaryDirectory(prefix='ag038-auditoria-') as temporary:
        root = Path(temporary)
        source = root / 'prueba_rgb.jpg'
        # Test-only synthetic JPEG: no photographs of a real fruit.
        try:
            import cv2
            import numpy as np
            pixels = np.full((48, 48, 3), (25, 140, 210), dtype=np.uint8)
            valid, encoded = cv2.imencode('.jpg', pixels)
            if not valid:
                raise ValueError('No se pudo crear evidencia JPEG sintética')
            original_bytes = encoded.tobytes()
        except ImportError as exc:
            raise RuntimeError('Faltan OpenCV o NumPy para generar la fotografía de prueba') from exc
        source.write_bytes(original_bytes)
        original_sha = hashlib.sha256(original_bytes).hexdigest()
        dbfile = root / 'ag038_simulada.sqlite'
        engine = create_engine(f'sqlite:///{dbfile.as_posix()}', connect_args={'check_same_thread':False, 'timeout':5})
        Base.metadata.create_all(engine)
        maker = sessionmaker(bind=engine, expire_on_commit=False)
        try:
            with maker() as db:
                users = {}
                for role in ('revisor', 'operador'):
                    user = User(username='ag038_sim_' + role, full_name='Cuenta de prueba ' + role,
                                password_hash=hash_password('NoEsContrasenaRealSoloTest123'),
                                is_active=True, roles=[Role(name=role)])
                    db.add(user)
                    db.flush()
                    users[role] = user.id
                lot = Lot(code='AG038-AUDITORIA-SIM', product='mango', status='open')
                db.add(lot)
                db.flush()
                fixtures = [
                    ('A', 'E1', 'completed'),
                    ('B', None, 'pending_review'),
                ]
                ids = {}
                for name, initial, status in fixtures:
                    ev = Evaluation(lot_id=lot.id, piece_id='SIM-' + name, product='mango',
                                    status=status, visual_category=initial)
                    db.add(ev)
                    db.flush()
                    img = Image(evaluation_id=ev.id, view='vista-1', relative_path='prueba_rgb.jpg',
                                content_type='image/jpeg', size_bytes=len(original_bytes))
                    db.add(img)
                    db.flush()
                    ids[name] = (ev.id, img.id)
                db.commit()

            def db_override():
                with maker() as session:
                    yield session

            events = []
            checks = []
            with ExitStack() as stack:
                # Local-only dependency override; restored on every exit.
                had_override = get_db in app.dependency_overrides
                original_override = app.dependency_overrides.get(get_db)
                app.dependency_overrides[get_db] = db_override
                def restore():
                    if had_override:
                        app.dependency_overrides[get_db] = original_override
                    else:
                        app.dependency_overrides.pop(get_db, None)
                stack.callback(restore)
                stack.enter_context(patch.object(review_decisions, 'DATA_DIR', root))
                client = stack.enter_context(TestClient(app))

                def auth(role):
                    return {'Authorization': 'Bearer ' + create_access_token(users[role])}

                def url(name):
                    return f'/api/evaluations/E-{ids[name][0]:06d}/review-decisions'

                def get_state(name):
                    return _require(client.get(url(name),headers=auth('revisor')),200,'GET bitácora '+name)

                def decide(name, action, value, expected, reason, *, rid=None, role='revisor', image_pk=None):
                    return client.post(url(name), headers=auth(role), json={
                        'action':action, 'newValue':value,
                        'imageId':f'I-{image_pk if image_pk is not None else ids[name][1]:06d}',
                        'reason':reason, 'expectedReviewId':expected,
                        'requestId':rid or str(uuid4()),
                    })

                def persist(name, action, value, expected, reason):
                    item = _require(decide(name,action,value,expected,reason),201,f'{name}: {action}')
                    assert item['imageSha256'] == original_sha, 'SHA256 distinto del archivo original'
                    assert item['actorId'] == 'ag038_sim_revisor', 'Autor no vinculado al JWT'
                    assert item['previousValue'] == expected_value[name], 'Valor anterior equivocado'
                    expected_value[name] = item['newValue']
                    events.append({**item, 'fixture': name})
                    checks.append(f'{name}: {action} {item["previousValue"]} -> {item["newValue"]}: HTTP 201')
                    return item

                expected_value = {'A':'E1', 'B':None}
                # A: initial E1 is a synthetic legacy seed, then explicit confirmation/correction.
                a1 = persist('A','confirm','E1',None,
                             'Se confirma grado E1 después de revisar la imagen simulada')
                a2 = persist('A','correct','E2',a1['id'],
                             'Se corrige de E1 a E2 en el escenario de auditoría simulada')
                a3 = persist('A','confirm','E2',a2['id'],
                             'Se confirma el grado E2 en una segunda decisión de prueba')
                # B: no fake automatic quality result: create human first label.
                b1 = persist('B','initial_label','E0',None,
                             'Primera etiqueta humana E0 sobre evidencia de prueba sintética')
                b2 = persist('B','no_evaluable','no_evaluable',b1['id'],
                             'Se retira el dictamen por falta de evidencia visual suficiente')
                b3 = persist('B','correct','E1',b2['id'],
                             'Nueva inspección de prueba admite registro E1 con justificación')
                state_a, state_b = get_state('A'), get_state('B')
                assert state_a['currentValue']=='E2' and state_a['originalValue']=='E1'
                assert state_b['currentValue']=='E1' and state_b['originalValue'] is None
                assert [x['action'] for x in state_a['decisions']] == ['confirm','correct','confirm']
                assert [x['action'] for x in state_b['decisions']] == ['initial_label','no_evaluable','correct']
                checks.append('GET bitácoras: 6 eventos, secuencia original/vigente correcta')

                # Failure modes: unprivileged, stale revision, missing rationale, wrong image.
                negatives = [
                    ('usuario operador', decide('A','correct','E0',a3['id'],
                        'Intento no autorizado desde perfil operador',role='operador'),403),
                    ('version antigua', decide('A','correct','E1',a1['id'],
                        'Conflicto intencional con versión antigua'),409),
                    ('sin motivo', decide('A','correct','E1',a3['id'],'breve'),422),
                    ('imagen de otra evaluacion',decide('A','correct','E1',a3['id'],
                        'Imagen de otra evaluación en este escenario',image_pk=ids['B'][1]),404),
                ]
                for label, response, status in negatives:
                    _require(response,status,label)
                    checks.append(f'Bloqueo {label}: HTTP {status}')

                # Idempotent exact replay: no new event is created.
                repeated_id = str(uuid4())
                repeat_payload = dict(action='confirm',newValue='E2',imageId=f'I-{ids["A"][1]:06d}',
                                      expectedReviewId=a3['id'],reason='Confirmación idempotente del último resultado de prueba',
                                      requestId=repeated_id)
                replay_first = _require(client.post(url('A'),headers=auth('revisor'),json=repeat_payload),201,
                                        'primera solicitud idempotente')
                replay_second = _require(client.post(url('A'),headers=auth('revisor'),json=repeat_payload),201,
                                         'segunda solicitud idempotente')
                assert replay_first['id'] == replay_second['id'], 'Reintento produjo un evento nuevo'
                events.append({**replay_first,'fixture':'A'})
                checks.append('Reintento idéntico: mismo ID de evento, sin duplicación')
                # The saved original category remains immutable; the actual current value is in the events.
                with maker() as db:
                    original_a = db.get(Evaluation, ids['A'][0])
                    original_b = db.get(Evaluation, ids['B'][0])
                    assert original_a.visual_category == 'E1' and original_b.visual_category is None
                    assert db.query(ReviewDecisionEvidence).count() == 7
                    assert db.query(Review).count() == 7
                    stored = list(db.scalars(select(ReviewDecisionEvidence)).all())
                    assert all(x.image_sha256 == original_sha for x in stored)
                assert hashlib.sha256(source.read_bytes()).hexdigest() == original_sha
                checks.append('Archivo de imagen original y SHA256 preservados')

            # Reopen from a fresh database connection to prove durable storage.
            reopened = create_engine(f'sqlite:///{dbfile.as_posix()}')
            try:
                with Session(reopened) as db:
                    reviews = db.scalars(select(Review).order_by(Review.id)).all()
                    meta = db.scalars(select(ReviewDecisionEvidence)).all()
                    assert len(reviews)==7 and len(meta)==7
                    for row in reviews:
                        assert row.actor_id == 'ag038_sim_revisor'
                        assert len(row.reason.strip())>=10
                        assert row.performed_at is not None
                    assert db.get(Evaluation,ids['A'][0]).visual_category=='E1'
                    assert db.get(Evaluation,ids['B'][0]).visual_category is None
                    checks.append('Persistencia confirmada desde segunda conexión SQLite')
            finally:
                reopened.dispose()
            assert len(events)==7
            # Only generated, observed data from this execution are exported.
            rows=[]
            for item in events:
                rows.append({
                    'evaluation_id':item['evaluationId'],
                    'original_value':'E1' if item['fixture']=='A' else '',
                    'review_id':item['id'], 'action':item['action'],
                    'previous_value':item['previousValue'] or '', 'new_value':item['newValue'] or '',
                    'actor_id':item['actorId'], 'performed_at':item['performedAt'],
                    'reason':item['reason'], 'image_id':item['imageId'],
                    'image_sha256':item['imageSha256'], 'request_id':item['requestId']
                })
            result = {
                'story':'AGROP-46', 'type':'auditoria_integracion_simulada',
                'source':'FastAPI TestClient + SQLite temporal + autenticación de roles de prueba',
                'hardware_esp32_utilizado':False,
                'fotografias_reales_utilizadas':False,
                'base_de_datos_productiva_utilizada':False,
                'fecha_ejecucion_utc':datetime.now(timezone.utc).isoformat(),
                'resultado':'aprobado', 'cantidad_evaluaciones_simuladas':2,
                'cantidad_decisiones_almacenadas':7,
                'cantidad_validaciones':len(checks),
                'sha256_fotografia_sintetica':original_sha,
                'pruebas':checks,
                'nota':'Las etiquetas son ejemplos de funcionamiento del software, NO dictámenes de fruta real.'
            }
            output.mkdir(parents=True, exist_ok=False)
            _write_exclusive(output/'resumen_auditoria.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            with (output/'bitacora_decisiones.csv').open('x',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=CSV_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            markdown=['# AG-038 — Evidencia de auditoría simulada', '',
                      '**Tipo de prueba:** API real FastAPI y SQLite temporal. Sin ESP32 ni fruta real.',
                      '',f'**Resultado:** {result["resultado"]}. **Eventos:** 7. **Comprobaciones:** {len(checks)}.',
                      '', '## Acciones verificadas', '']
            markdown.extend(f'- {c}' for c in checks)
            markdown.extend(['','## Alcance','',
                             'La prueba acredita creación de decisiones humanas simuladas, respuesta HTTP, persistencia, '
                             'autorización, concurrencia optimista, idempotencia y preservación de la evidencia sintética.',
                             'No acredita precisión agronómica, clasificación automática E0/E1/E2, ni hardware físico.',
                             'Se deben tomar capturas del panel real para acreditar la interfaz React.', ''])
            _write_exclusive(output/'informe_auditoria.md','\n'.join(markdown))
            return result
        finally:
            engine.dispose()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--salida',type=Path,required=True,help='Carpeta nueva fuera de Git')
    args=parser.parse_args(argv)
    try:
        result=audit(args.salida)
        print(json.dumps({'estado':result['resultado'],'eventos':result['cantidad_decisiones_almacenadas'],
                          'validaciones':result['cantidad_validaciones'],'salida':str(args.salida)},ensure_ascii=False))
    except (OSError,ValueError,AssertionError) as exc:
        parser.exit(2,'AG038 auditoría: '+str(exc)+'\n')

if __name__=='__main__':
    main()
