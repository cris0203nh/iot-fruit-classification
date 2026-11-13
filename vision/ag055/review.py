"""Local human review queue and later E0/E1/E2 grouped experiment.

No source labels or historical decisions are edited. Reviews are append-only events.
An annotation is a human declaration, not proof of accreditation or independence.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import secrets
import threading
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageOps

from .experimental import (LIMITATIONS, VERSION, describe, dump, private, safe, sha,
                           train_task)


REVIEW_LOCK = threading.Lock()


class ReviewStorageError(OSError):
    """Unreadable audit evidence: fail closed without discarding or rewriting it."""


def _publish_json(path, value):
    """Publish a complete, flushed JSON with exclusive creation, never a partial event.

    The temp and final file share a filesystem. An exclusive hard link publishes the
    complete file atomically; an existing destination is never replaced. Requires
    a local filesystem supporting hard links (NTFS in the supported Windows setup).
    This does not provide cross-process review-chain transactions.
    """
    descriptor, name=tempfile.mkstemp(prefix='.ag055-',suffix='.tmp',dir=path.parent)
    temporary=Path(name)
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def load_samples(run):
    manifest = json.loads((run/'manifest.json').read_text(encoding='utf-8')) if (run/'manifest.json').exists() else []
    return manifest + [json.loads(p.read_text(encoding='utf-8')) for p in sorted((run/'registered_samples').glob('*.json'))]


def review_history(run, sample_id, image_sha256=None):
    try:
        events=[json.loads(p.read_text(encoding='utf-8')) for p in (run/'reviews').glob('*.json')]
        return sorted([e for e in events if e['id']==sample_id or (image_sha256
            and e.get('annotationPurpose')=='human_label_declaration_import' and e['imageSha256']==image_sha256)],
            key=lambda e:(e.get('reviewedAt') or e.get('importedAt') or '',e.get('eventId','')))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise ReviewStorageError('Review history unavailable; preserve evidence and restore storage') from exc


def save_review(run, payload):
    manifest = load_samples(run)
    sample = next((r for r in manifest if r['id'] == payload.get('id')), None)
    if sample is None:
        raise ValueError('Unknown image')
    return save_review_sample(run,sample,payload)


def save_review_sample(run, sample, payload, context=None):
    if payload.get('grade') not in ('E0', 'E1', 'E2', 'no_evaluable'):
        raise ValueError('Select E0/E1/E2 or no_evaluable explicitly')
    for key in ('reviewer', 'rubricVersion', 'evidence'):
        if not isinstance(payload.get(key), str) or len(payload[key].strip()) < 3 or len(payload[key]) > 2000:
            raise ValueError('Reviewer, rubric version and visual evidence are required')
    if len(payload['evidence'].strip()) < 20 or (payload['grade'] in ('E1','E2') and not re.search(r'\bR\d{2}\b',payload['evidence'])):
        raise ValueError('Describe visible evidence and location; E1/E2 also require the applicable Rxx criterion')
    raw = safe(Path(sample['root']), sample['relative']).read_bytes()
    if sha(raw) != sample['sha256']:
        raise ValueError('Original image changed')
    describe(raw, payload.get('roi', []))  # Bounds validation, no automatic human status
    if not payload.get('roiConfirmed') is True:
        raise ValueError('ROI must be explicitly confirmed by the reviewer')
    prefixes = ('mango-ext-','kent-ext-') if sample['product'] == 'mango' else ('tomato-ext-',)
    if not payload['rubricVersion'].startswith(prefixes):
        raise ValueError('Use the documented product rubric version: ' + '/'.join(prefixes))
    event = {k: payload[k] for k in ('grade','reviewer','rubricVersion','evidence','roi')}
    event.update(id=sample['id'], imageSha256=sample['sha256'],
                 reviewedAt=datetime.now(timezone.utc).isoformat(),
                 roiHumanVerified=True, accreditationVerified=False)
    event.update(context or {})
    event['eventId']=secrets.token_hex(16)
    (run/'reviews').mkdir(exist_ok=True)
    with REVIEW_LOCK:
        history=review_history(run,sample['id'],sample['sha256'])
        latest=history[-1].get('eventId') if history else None
        if 'expectedLastEventId' in payload and payload['expectedLastEventId']!=latest:
            raise ValueError('Review history changed; refresh before correcting')
        event['supersedesEventId']=latest
        (run/'registered_samples').mkdir(exist_ok=True)
        pointer=run/'registered_samples'/f'{sha(sample["id"].encode())}.json'
        if context and not pointer.exists():
            _publish_json(pointer,sample)
        # One new file per event, including corrections; originals remain immutable.
        _publish_json(run/'reviews'/f'{event["eventId"]}.json', event)
    return event


def train_reviewed(run, output, seed=55):
    """Exploratory three-class training only, with known component groups retained."""
    output = private(output); output.mkdir()
    manifest = load_samples(run)
    events = sorted((json.loads(p.read_text(encoding='utf-8')) for p in (run/'reviews').glob('*.json')),
                    key=lambda x:x.get('reviewedAt') or x.get('importedAt') or '')
    latest = {e['id']:e for e in events}
    report = {'version':VERSION, 'humanReviewEvents':len(events), 'seed':seed,
              'accreditationVerified':False, 'limitations':LIMITATIONS, 'products':{}}
    for product in ('mango','tomate'):
        rr, features = [], {}
        for sample in manifest:
            if sample['id'] not in latest or sample['product'] != product or sample['excluded']:
                continue
            event = latest[sample['id']]
            if event['grade']=='no_evaluable' or event.get('annotationPurpose')=='automated_test_not_human_ground_truth':
                continue
            raw = safe(Path(sample['root']),sample['relative']).read_bytes()
            if sha(raw) != event['imageSha256'] or sha(raw) != sample['sha256']:
                raise ValueError('Reviewed evidence changed')
            f, _, _, _ = describe(raw,event['roi'])
            features[sample['id']] = f
            rr.append({**sample, 'label':event['grade']})
        try:
            rubrics = {latest[r['id']]['rubricVersion'] for r in rr}
            if len(rubrics) != 1:
                raise ValueError('One consistent reviewed rubric version per product is required')
            if any(len({r['group'] for r in rr if r['label']==c}) < 5 for c in ('E0','E1','E2')):
                raise ValueError('At least five known components per E0/E1/E2 are required')
            model, metrics = train_task(rr,['E0','E1','E2'],features,seed)
            dump(output/f'reviewed_exploratory_{product}.json', {
                'version':'ag055-human-reviewed-unaccredited-v1', 'product':product,
                'model':model, 'labels':['E0','E1','E2'], 'evaluation':metrics,
                'rubricVersion':next(iter(rubrics)), 'featureAcquisition':'human_roi',
                'deploymentAuthorized':False, 'accreditationVerified':False,
                'reviewsSha256':sha(json.dumps(events,sort_keys=True).encode()), 'seed':seed})
            report['products'][product] = {'status':'exploratory_only', **metrics}
        except ValueError as e:
            report['products'][product] = {'status':'blocked', 'reason':str(e)}
    dump(output/'report.json',report)
    dump(output/'reviewed_manifest.json',[{**r, 'review':latest.get(r['id'])} for r in manifest if r['id'] in latest])
    return report


PAGE = '''<!doctype html><html lang="es"><meta charset="utf-8"><title>AG-055 revisión humana</title>
<style>body{font:16px system-ui;max-width:1100px;margin:auto;padding:20px}img,canvas{max-width:46%;max-height:460px;object-fit:contain}input,select,button,textarea{padding:8px;margin:5px}textarea{display:block;width:90%}</style>
<h1>AG-055 · Revisión humana de fotografías</h1>
<p>E0: sin defecto externo relevante visible. E1: defecto visible que requiere valoración.
E2: indicio grave que requiere revisión prioritaria. Aplicar la rúbrica existente del producto;
estas definiciones no sustituyen su aprobación. No se acredita identidad, Kent ni independencia.</p>
<label>Filtrar producto <select id="product"><option value="">Todos</option><option>tomate</option><option>mango</option></select></label>
<label>Fotografía <select id="photo"></select></label><p id="info"></p>
<img id="image" alt="Fotografía original orientada"><canvas id="crop" aria-label="ROI propuesta"></canvas>
<div>ROI x,y,ancho,alto <input id="roi" size="30"><button id="preview">Ver ROI</button>
<label><input type="checkbox" id="confirmed">He revisado y confirmado esta ROI</label></div>
<label>Grado humano <select id="grade"><option value="">Seleccionar…</option><option>E0</option><option>E1</option><option>E2</option><option value="no_evaluable">No evaluable</option></select></label>
<label>Revisor <input id="reviewer" required></label><label>Versión de rúbrica <input id="rubric" placeholder="tomato-ext-… / kent-ext-…" required></label>
<textarea id="evidence" placeholder="Criterio de rúbrica, defecto observado y ubicación de evidencia visible" required></textarea>
<button id="save">Guardar revisión y avanzar</button><p id="message" role="status"></p>
<script>
const token='TOKEN', el=id=>document.getElementById(id);let all=[],items=[];
async function request(path,options={}){const r=await fetch(path,{...options,headers:{'X-Review-Token':token,'Content-Type':'application/json'}});const v=await r.json();if(!r.ok)throw Error(v.error);return v}
function preview(){const [x,y,w,h]=JSON.parse(el('roi').value);el('crop').width=w;el('crop').height=h;el('crop').getContext('2d').drawImage(el('image'),x,y,w,h,0,0,w,h)}
function show(){const r=items[+el('photo').value];if(!r)return;el('info').textContent=`${r.id} · ${r.product} · original: ${r.label} · ${r.roiMethod} · ${r.excluded||'candidato'} · grupo ${r.group}`;
el('roi').value=JSON.stringify(r.roi);el('confirmed').checked=false;el('grade').value='';el('evidence').value='';el('image').onload=preview;el('image').src='/image?id='+encodeURIComponent(r.id)+'&token='+token}
function filter(){items=all.filter(r=>!el('product').value||r.product===el('product').value);el('photo').replaceChildren(...items.map((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=r.id+(r.reviewed?' · revisada':'');return o}));show()}
el('preview').onclick=()=>{try{preview()}catch(e){el('message').textContent=e.message}};el('photo').onchange=show;el('product').onchange=filter;
el('save').onclick=async()=>{try{const r=items[+el('photo').value];await request('/review',{method:'POST',body:JSON.stringify({id:r.id,grade:el('grade').value,reviewer:el('reviewer').value,rubricVersion:el('rubric').value,evidence:el('evidence').value,roi:JSON.parse(el('roi').value),roiConfirmed:el('confirmed').checked})});r.reviewed=true;el('message').textContent='Revisión humana guardada como evento nuevo.';el('photo').selectedIndex=Math.min(items.length-1,el('photo').selectedIndex+1);show()}catch(e){el('message').textContent=e.message}};
request('/queue').then(v=>{all=v;filter()}).catch(e=>el('message').textContent=e.message);
</script></html>'''


def serve(run, port):
    token = secrets.token_hex(24)
    manifest = load_samples(run)
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, raw, kind='application/json'):
            self.send_response(status); self.send_header('Content-Type', kind)
            self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers(); self.wfile.write(raw)

        def authorized(self):
            return self.headers.get('X-Review-Token') == token

        def do_GET(self):
            url = urlparse(self.path)
            # Reject DNS rebinding; UI only served from this loopback address.
            if self.headers.get('Host') != f'127.0.0.1:{port}':
                return self.respond(403,b'{}')
            if url.path == '/':
                return self.respond(200,PAGE.replace('TOKEN',token).encode(),'text/html; charset=utf-8')
            if url.path == '/queue' and self.authorized():
                reviewed = {json.loads(p.read_text(encoding='utf-8'))['id'] for p in (run/'reviews').glob('*.json')}
                return self.respond(200,json.dumps([{**r,'reviewed':r['id'] in reviewed} for r in manifest]).encode())
            query = parse_qs(url.query)
            if url.path == '/image' and query.get('token') == [token]:
                r = next((r for r in manifest if [r['id']] == query.get('id')),None)
                if r:
                    raw = safe(Path(r['root']),r['relative']).read_bytes()
                    if sha(raw) != r['sha256']:
                        return self.respond(409,b'{"error":"Original changed"}')
                    with Image.open(io.BytesIO(raw)) as im:
                        out=io.BytesIO(); ImageOps.exif_transpose(im).convert('RGB').save(out,format='JPEG')
                    return self.respond(200,out.getvalue(),'image/jpeg')
            self.respond(403,b'{}')

        def do_POST(self):
            if self.path != '/review' or not self.authorized() or self.headers.get('Host') != f'127.0.0.1:{port}':
                return self.respond(403,b'{}')
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<16000:
                    raise ValueError('Invalid review size')
                event = save_review(run,json.loads(self.rfile.read(size)))
                self.respond(201,json.dumps(event).encode())
            except (ValueError,TypeError,KeyError,OSError) as e:
                self.respond(422,json.dumps({'error':str(e)}).encode())
    print(f'Human review: http://127.0.0.1:{port} (Ctrl+C to stop)',flush=True)
    HTTPServer(('127.0.0.1',port),Handler).serve_forever()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command',choices=['serve','train-reviewed'])
    ap.add_argument('--run',type=Path,required=True)
    ap.add_argument('--port',type=int,default=8055)
    ap.add_argument('--output',type=Path)
    a=ap.parse_args(); run=private(a.run)
    if a.command=='serve':
        serve(run,a.port)
    elif a.output:
        print(json.dumps(train_reviewed(run,a.output)))
    else:
        ap.error('--output required for train-reviewed')


if __name__=='__main__':
    main()
