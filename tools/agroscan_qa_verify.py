"""Commercial API walkthrough on a disposable QA copy; no browser/SMTP/hardware claim."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import patch
import uuid

from agroscan_qa import ROOT, QA_ROOT, HEAD, configuration, check_database


def fingerprint(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.execute('BEGIN')
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {name: hashlib.sha256(repr(db.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()).encode()).hexdigest() for name in tables}


def copy_photos(source, destination, database):
    hashes = {}
    with closing(sqlite3.connect(database)) as db:
        paths = [r[0] for r in db.execute('SELECT relative_path FROM images')]
    for relative in paths:
        path = (source / relative).resolve()
        target = (destination / relative).resolve()
        assert path.is_relative_to(source.resolve()) and target.is_relative_to(destination.resolve()), 'Unsafe QA photo reference'
        assert path.is_file(), 'Missing QA photo'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == hashes[relative]
    return hashes


def walkthrough(client, accounts):
    def request(method, path, expected=200, headers=None, **kwargs):
        response = client.request(method, path, headers=headers, **kwargs)
        assert response.status_code == expected, f'{method} {path}: {response.status_code}, expected {expected}'
        return response.json() if response.content else None
    def login(account):
        result = request('POST', '/api/auth/login', data=account)
        return {'Authorization': 'Bearer ' + result['access_token']}
    def decision(application, action='approve', key=None):
        body = {'action': action, 'reason': 'COM07 synthetic verification', 'idempotencyKey': key or str(uuid.uuid4())}
        if action == 'approve': body.update(identityConfirmed=True, approvedPlanId=plan['id'])
        return request('POST', f'/api/platform/commercial/applications/{application}/decision', headers=owner, json=body)
    def invitation(application, action, key=None, expected=201):
        return request('POST', f'/api/platform/commercial/applications/{application}/administrator-invitation', expected,
            headers=owner, json={'action': action, 'idempotencyKey': key or str(uuid.uuid4())})
    def company(headers): return request('GET', '/api/commercial/subscription', headers=headers)
    def order(action, selected=None, headers=None):
        return request('POST', '/api/commercial/orders', 201, headers=headers or admin_a,
            json={'planId': (selected or plan)['id'], 'action': action, 'idempotencyKey': str(uuid.uuid4())})
    def confirm(item, scenario='approve', headers=None, expected=200):
        return request('POST', f'/api/commercial/orders/{item["id"]}/confirm', expected, headers=headers or admin_a, json={'scenario': scenario})

    owner = login(accounts['propietario'])
    baseline = request('GET', '/api/platform/commercial/overview', headers=owner)
    metrics_before = request('GET', '/api/platform/metrics', headers=owner)
    plans = request('GET', '/api/commercial/plans')['plans']
    assert plans and all(p['isActive'] for p in plans)
    plan = plans[0]
    nonce = uuid.uuid4().hex[:12]
    bodies = []
    for suffix in ('A', 'Rejected', 'B'):
        body = {'companyName': f'COM07 {nonce} {suffix}', 'contactName': 'Synthetic Contact',
            'contactEmail': f'com07-{suffix.lower()}@example.test', 'requestedPlanId': plan['id'],
            'requestedPeriod': plan['period'], 'idempotencyKey': str(uuid.uuid4())}
        receipt = request('POST', '/api/commercial/applications', 201, json=body)
        assert receipt['status'] == 'pending' and receipt['ownerNotification'] == 'disabled'
        assert set(receipt) == {'id', 'status', 'message', 'ownerNotification'}
        assert receipt['message'] == 'Solicitud recibida, pendiente de revisi\u00f3n'
        bodies.append((body, receipt))
    body_a, receipt_a = bodies[0]
    assert request('POST', '/api/commercial/applications', 200, json=body_a) == receipt_a
    key = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        approved = list(pool.map(lambda _: decision(receipt_a['id'], key=key), range(2)))
    assert approved[0] == approved[1]
    company_a = approved[0]['organizationId']
    assert approved[0]['provisioningState'] == 'awaiting_admin'
    rejected = decision(bodies[1][1]['id'], 'reject')
    assert rejected['organizationId'] is None and rejected['status'] == 'rejected'
    company_b = decision(bodies[2][1]['id'])['organizationId']
    assert company_a != company_b
    assert request('GET', '/api/platform/metrics', headers=owner)['organizations'] == metrics_before['organizations'] + 2

    key = str(uuid.uuid4())
    first = invitation(receipt_a['id'], 'issue', key)
    repeated = invitation(receipt_a['id'], 'issue', key, 200)
    assert 'token' not in repeated and first['invitation']['id'] == repeated['invitation']['id']
    invitation(receipt_a['id'], 'revoke', expected=200)
    request('POST', '/api/auth/invitations/preview', 410, json={'token': first['token']})
    replacement = invitation(receipt_a['id'], 'reissue')
    admins = []
    for suffix, app, token, org in [('a', receipt_a['id'], replacement['token'], company_a),
                                 ('b', bodies[2][1]['id'], invitation(bodies[2][1]['id'], 'issue')['token'], company_b)]:
        preview = request('POST', '/api/auth/invitations/preview', json={'token': token})
        assert preview['role'] == 'administrador'
        credentials = {'username': f'com07_{nonce}_{suffix}', 'password': secrets.token_urlsafe(32)}
        accepted = request('POST', '/api/auth/invitations/register', 201,
            json={**credentials, 'fullName': 'COM07 Synthetic Administrator', 'token': token})
        assert not accepted['is_superadmin'] and accepted['organization_id'] == org
        headers = login(credentials)
        assert request('GET', '/api/auth/me', headers=headers)['roles'] == ['administrador']
        request('POST', '/api/auth/invitations/register', 410, json={**credentials, 'fullName': 'Replay', 'token': token})
        assert company(headers)['onboarding']['stage'] == 'awaiting_demo_order'
        admins.append(headers)
    admin_a, admin_b = admins
    for scenario, expected in [('reject', 'demo_rejected'), ('cancel', 'cancelled')]:
        item = order('subscribe')
        assert confirm(item, scenario)['status'] == expected
        assert company(admin_a)['subscription'] is None
        assert company(admin_a)['onboarding']['stage'] == 'awaiting_demo_order'
    first_order = order('subscribe')
    assert first_order['amountCents'] == plan['amountCents'] and first_order['plan'] == plan
    with ThreadPoolExecutor(max_workers=3) as pool:
        result = list(pool.map(lambda _: confirm(first_order), range(3)))
    assert all(r['status'] == 'demo_approved' for r in result)
    state = company(admin_a)
    assert state['onboarding']['stage'] == 'completed'
    assert state['onboarding']['orderId'] == first_order['id']
    assert state['onboarding']['subscriptionId'] == state['subscription']['id']
    assert len(state['transactions']) == 3
    assert company(admin_b)['subscription'] is None
    confirm(first_order, headers=admin_b, expected=404)
    for headers, other in [(admin_a, company_b), (admin_b, company_a)]:
        request('GET', '/api/commercial/subscription', 403, headers={**headers, 'X-Organization-ID': str(other)})
    request('POST', '/api/commercial/orders', 422, headers=admin_a, json={
        'planId': plan['id'], 'action': 'renew', 'idempotencyKey': str(uuid.uuid4()), 'amountCents': 1})

    renewal = order('renew'); confirm(renewal)
    renewed = company(admin_a)['subscription']['endsAt']; assert renewed > state['subscription']['endsAt']; confirm(renewal)
    assert company(admin_a)['subscription']['endsAt'] == renewed
    other = next((p for p in plans if p['id'] != plan['id']), plan)
    changing = order('change', other); confirm(changing, 'reject')
    assert company(admin_a)['subscription']['plan']['id'] == plan['id']
    changed = order('change', other)
    assert company(admin_a)['subscription']['plan']['id'] == plan['id']
    confirm(changed)
    current = company(admin_a)['subscription']
    assert current['plan']['id'] == other['id']
    expiry = datetime.fromisoformat(current['endsAt'].removesuffix('Z'))
    for days, grace in [(1, True), (7, False), (8, False)]:
        with patch('app.routers.commercial.now', return_value=expiry + timedelta(days=days)):
            timed = company(admin_a)['subscription']
            assert timed['status'] == 'expired' and timed['inGracePeriod'] is grace
            assert isinstance(request('GET', '/api/lots', headers=admin_a), list)
    with patch('app.routers.commercial.now', return_value=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=25)):
        expired_order = order('change', other)
    assert next(o for o in company(admin_a)['orders'] if o['id'] == expired_order['id'])['isExpired']
    confirm(expired_order, expected=409)
    cancelled = request('POST', '/api/commercial/subscription/cancel', headers=admin_a)
    assert cancelled['status'] == 'cancelled' and not cancelled['inGracePeriod']
    tx_count = len(company(admin_a)['transactions'])
    request('POST', '/api/commercial/subscription/cancel', headers=admin_a)
    assert len(company(admin_a)['transactions']) == tx_count
    assert company(admin_a)['onboarding']['stage'] == 'completed'
    assert isinstance(request('GET', '/api/lots', headers=admin_a), list)
    for role in ('operador', 'revisor'):
        headers = login(accounts[role])
        assert isinstance(request('GET', '/api/lots', headers=headers), list)
        request('GET', '/api/commercial/subscription', 403, headers=headers)
        request('POST', '/api/commercial/orders', 403, headers=headers,
            json={'planId': plan['id'], 'action': 'renew', 'idempotencyKey': str(uuid.uuid4())})
        request('POST', '/api/commercial/subscription/cancel', 403, headers=headers)
        if role == 'revisor':
            request('POST', '/api/lots', 403, headers=headers, json={})
    totals = request('GET', '/api/platform/commercial/overview', headers=owner)
    added_orders = [o for o in totals['orders'] if o['organizationId'] in (company_a, company_b)]
    assert len(totals['orders']) == len(baseline['orders']) + 7
    assert len(totals['transactions']) == len(baseline['transactions']) + 7
    assert totals['simulatedTotalCents'] - baseline['simulatedTotalCents'] == sum(o['amountCents'] for o in added_orders if o['status'] == 'demo_approved')
    trace = next(o for o in totals['onboardings'] if o['applicationId'] == receipt_a['id'])
    assert trace['stage'] == 'completed' and trace['orderId'] == first_order['id']
    listing = request('GET', '/api/platform/commercial/applications', headers=owner)['items']
    assert next(a for a in listing if a['id'] == receipt_a['id'])['provisioningState'] == 'completed'
    assert request('POST', '/api/commercial/applications', 200, json=body_a) == receipt_a
    return {'publicRequest': True, 'approvalRejection': True, 'approvalConcurrentRetry': True,
        'initialInvitation': True, 'revocationReissue': True, 'localAcceptanceAndLogin': True,
        'firstDemoRejectedCancelledWithoutActivation': True, 'firstDemoApproved': True,
        'confirmationConcurrency': True, 'renewalIdempotency': True, 'changePlan': True,
        'changeToDifferentPlan': other['id'] != plan['id'], 'expiryAndSevenDayGrace': True,
        'immediateCancellationIdempotency': True, 'crossCompanyAB': True, 'operationalRolesDeniedCommerce': True,
        'ownerConsistency': True, 'ordersAddedOnCopy': 7, 'transactionsAddedOnCopy': 7,
        'browserExecuted': False, 'smtpRealExecuted': False, 'googleRealExecuted': False}


def main():
    configuration()
    accounts = json.load(sys.stdin)
    source = QA_ROOT / 'data/agroscan.db'
    # Solo el verificador puede leer la revisión anterior para migrar una COPIA.
    # El arranque normal sigue exigiendo HEAD y nunca migra automáticamente.
    check_database(source, allow_previous=True)
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        source_schema = db.execute('SELECT version_num FROM alembic_version').fetchone()[0]
    before = fingerprint(source)
    with tempfile.TemporaryDirectory(prefix='commerce-check-', dir=QA_ROOT) as directory:
        target_dir = Path(directory).resolve()
        assert target_dir.is_relative_to(QA_ROOT.resolve())
        target = target_dir / 'agroscan.db'
        with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            assert dst.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
            assert dst.execute('PRAGMA foreign_key_check').fetchall() == []
        photo_hashes = copy_photos(source.parent, target_dir, target)
        os.environ.update(AGROSCAN_DATA_DIR=str(target_dir), AGROSCAN_DATABASE_URL='sqlite:///' + target.as_posix(), AGROSCAN_SMTP_ENABLED='false')
        migration = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', HEAD], cwd=ROOT / 'backend',
                                   capture_output=True, text=True)
        assert migration.returncode == 0, 'Disposable copy migration failed'
        check_database(target)
        sys.path.insert(0, str(ROOT / 'backend'))
        from app.main import app
        from app.database import engine
        from fastapi.testclient import TestClient
        try:
            with TestClient(app) as client:
                report = walkthrough(client, accounts)
            with closing(sqlite3.connect(target)) as db:
                assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
                assert db.execute('PRAGMA foreign_key_check').fetchall() == []
            for relative, expected in photo_hashes.items():
                assert hashlib.sha256((target_dir / relative).read_bytes()).hexdigest() == expected
        finally:
            engine.dispose()
    assert fingerprint(source) == before, 'QA source records changed during verification'
    check_database(source, allow_previous=True)
    report.update(qaDatabaseUnchanged=True, sqliteIntegrity='ok', foreignKeyViolations=0, qaPhotoFilesVerified=len(photo_hashes),
                  sourceSchema=source_schema, testedSchema=HEAD, sourceUpgradePending=source_schema != HEAD)
    (QA_ROOT / 'commerce-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
