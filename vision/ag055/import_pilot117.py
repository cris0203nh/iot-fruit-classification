"""Audit supplied archives, register declared labels and export inference-only JSON.

Never executes archive scripts, never fits an estimator. Use sklearn 1.8.0 only for
restricted one-time conversion/parity; production inference uses NumPy/OpenCV JSON.
"""
import argparse
import io
import json
import re
import zipfile
import zlib
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
from PIL import Image

from .experimental import Union, dump, private, rows, safe, sha
from .pilot117 import FEATURE_VERSION,VERSION,decision,features,validate
from .review import _publish_json


def extract(archive,output):
    output.mkdir()
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist())!=len(set(z.namelist())) or sum(i.file_size for i in z.infolist())>150_000_000:
            raise ValueError('Duplicate entries/oversized archive')
        for i in z.infolist():
            p=(output/i.filename).resolve()
            if (not p.is_relative_to(output.resolve()) or '\\' in i.filename or ':' in i.filename
                or '..' in Path(i.filename).parts or (i.external_attr>>16)&0o170000==0o120000):
                raise ValueError('Unsafe archive path')
            if i.is_dir():p.mkdir(parents=True,exist_ok=True)
            else:
                p.parent.mkdir(parents=True,exist_ok=True)
                with p.open('xb') as stream:stream.write(z.read(i))


def restricted_model(path):
    import sklearn
    from joblib.numpy_pickle import NumpyUnpickler,NumpyArrayWrapper
    if sklearn.__version__!='1.8.0':
        raise ValueError('Conversion requires the original sklearn 1.8.0')
    class NumericArray(NumpyArrayWrapper):
        def read(self,unpickler,ensure_native_byte_order):
            if self.dtype.hasobject or int(np.prod(self.shape))>2_000_000:
                raise ValueError('Object/oversized arrays forbidden')
            return super().read(unpickler,ensure_native_byte_order)
    allowed={('sklearn.pipeline','Pipeline'),('sklearn.preprocessing._data','StandardScaler'),
        ('sklearn.svm._classes','SVC'),('numpy','ndarray'),('numpy','dtype'),
        ('numpy._core.multiarray','_reconstruct'),('numpy._core.multiarray','scalar'),
        ('numpy.core.multiarray','_reconstruct'),('numpy.core.multiarray','scalar')}
    seen=[]
    class Restricted(NumpyUnpickler):
        def find_class(self,module,name):
            seen.append((module,name))
            if (module,name)==('joblib.numpy_pickle','NumpyArrayWrapper'):return NumericArray
            if (module,name) not in allowed:raise ValueError('Unapproved pickle global: '+module+'.'+name)
            return super().find_class(module,name)
    raw=path.read_bytes(); dec=zlib.decompressobj(); data=dec.decompress(raw,8*1024*1024)
    if not dec.eof or dec.unconsumed_tail or dec.unused_data:raise ValueError('Invalid/oversized model compression')
    stream=io.BytesIO(data)
    model=Restricted(str(path),stream,ensure_native_byte_order=True,mmap_mode=None).load()
    if stream.tell()!=len(data):raise ValueError('Trailing model payload')
    if type(model).__name__!='Pipeline' or [type(s).__name__ for _,s in model.steps]!=['StandardScaler','SVC']:
        raise ValueError('Unexpected estimator pipeline')
    scaler,svc=[s for _,s in model.steps]
    if list(svc.classes_)!=['E0','E1','E2'] or svc.kernel!='rbf' or svc.probability or svc.break_ties:
        raise ValueError('Unsupported SVC configuration')
    return model,scaler,svc,seen


def prepare(dataset_zip,package_zip,previous,output):
    output=private(output)
    output.mkdir(exist_ok=True)
    # The parent workspace may already contain a baseline. All produced paths are new.
    extract(dataset_zip,output/'data'); extract(package_zip,output/'package')
    package=output/'package/AG055_Piloto_117'
    for line in (package/'SHA256S.txt').read_text(encoding='utf-8').splitlines():
        expected,relative=line.split(None,1)
        if sha(safe(package,relative.strip()).read_bytes())!=expected:raise ValueError('Package checksum mismatch')
    inventory=rows(package/'inventario_trazabilidad_117.csv')
    diagnostics={r['ruta']:r for r in rows(package/'resultados/predicciones_diagnostico.csv')}
    old=json.loads((previous/'manifest.json').read_text(encoding='utf-8'))
    by_sha=defaultdict(list)
    for r in old:by_sha[r['sha256']].append(r)
    if len(inventory)!=117 or len(diagnostics)!=117:raise ValueError('Expected 117 declared labels/training rows')
    u=Union(r['ruta_zip'] for r in inventory); similar=rows(package/'pares_similares_para_revision.csv')
    for edge in similar:u.join(edge['foto_A'],edge['foto_B'])
    seen_groups={}; records=[]; received=datetime.now(timezone.utc).isoformat()
    for r in inventory:
        relative=r['ruta_zip']; parts=relative.split('/')
        if len(parts)!=4 or parts[1] not in ('Mango_Kent','Tomate') or parts[2].upper() not in ('E0','E1','E2'):
            raise ValueError('Unexpected human label folder')
        raw=safe(output/'data',relative).read_bytes(); digest=sha(raw)
        if digest!=r['sha256'] or diagnostics[relative]['sha256']!=digest or diagnostics[relative]['etiqueta_declarada']!=parts[2].upper():
            raise ValueError('Image/training/label mismatch')
        if r['etiqueta_humana_declarada']!=parts[2].upper() or not by_sha[digest]:raise ValueError('Original provenance mismatch')
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            if image.size!=(int(r['ancho']),int(r['alto'])) or len(raw)!=int(r['bytes']):raise ValueError('Metadata mismatch')
        original=by_sha[digest][0]
        keys=[('old',original['group'])]
        date=re.search(r'20\d{6}',Path(relative).stem)
        if parts[1]=='Tomate':keys.append(('date',date[0] if date else 'unknown'))
        for key in keys:
            if key in seen_groups:u.join(relative,seen_groups[key])
            else:seen_groups[key]=relative
        _,roi=features(raw)
        records.append({'id':'pilot117_'+digest[:20],'root':str((output/'data').resolve()),'relative':relative,
            'product':'mango' if parts[1]=='Mango_Kent' else 'tomate','source':'pilot117',
            'label':parts[2].upper(),'humanGrade':parts[2].upper(),'sha256':digest,'pixelSha256':original['pixelSha256'],
            'roi':roi,'roiMethod':'whole_image_training_descriptor','roiHumanVerified':False,
            'reviewer':None,'reviewedAt':None,'rubricVersion':None,'sourceLabel':r['clase_original_fuente'],
            'license':r['licencia_publicada_fuente'],'kentAccredited':False,'varietyDeclaredFolder':parts[1],
            'excluded':'human_metadata_physical_identity_pending','split':'training',
            'sourceImageId':original['id'],'previousGroup':original['group']})
    if len({r['sha256'] for r in records})!=117:raise ValueError('Exact duplicate in supplied human-labelled set')
    for r in records:r['group']=u.find(r['relative'])
    dump(output/'manifest.json',records)
    (output/'reviews').mkdir(); (output/'models').mkdir()
    dataset_sha=sha(dataset_zip.read_bytes()); package_sha=sha(package_zip.read_bytes())
    for r in records:
        event={'id':r['id'],'eventId':sha((dataset_sha+r['sha256']+r['label']).encode()),'grade':r['label'],
            'reviewer':None,'reviewedAt':None,'rubricVersion':None,'evidence':None,'criteriaRxx':None,
            'importedAt':received,'annotationPurpose':'human_label_declaration_import','imageSha256':r['sha256'],
            'roi':r['roi'],'roiHumanVerified':False,'accreditationVerified':False,'humanReviewAuthenticityVerified':False,
            'actorSource':'explicit_user_declaration','sourceDatasetZipSha256':dataset_sha,
            'sourcePackageZipSha256':package_sha,'sourceLabelPath':r['relative'],'supersedesEventId':None}
        _publish_json(output/'reviews'/f'{event["eventId"]}.json',event)
    models={}
    for product,folder in [('mango','Mango_Kent'),('tomate','Tomate')]:
        path=package/'resultados'/f'{folder}_piloto.joblib'
        reference,scaler,svc,globals_seen=restricted_model(path)
        rr=[r for r in records if r['product']==product]
        artifact={'version':VERSION,'featureVersion':FEATURE_VERSION,'labels':['E0','E1','E2'],
            'labelSpace':'pilot_declared_e0e1e2','product':product,'deploymentAuthorized':False,'humanReviewRequired':True,
            'independentTestMetrics':None,'kentAccredited':False,'trainingImageHashes':[r['sha256'] for r in rr],
            'dataVersion':dataset_sha,'sourceJoblibSha256':sha(path.read_bytes()),'sourcePackageZipSha256':package_sha,
            'sourceFeatureScriptSha256':sha((package/'train_pilot.py').read_bytes()),
            'model':{'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),'gamma':float(svc._gamma),
                'supportVectors':svc.support_vectors_.tolist(),'dualCoef':svc.dual_coef_.tolist(),
                'intercept':svc.intercept_.tolist(),'supportCounts':svc.n_support_.tolist()},
            'limitations':['All 117 supplied images were used for training','No independent E0/E1/E2 test',
                'Whole-image descriptor includes background','Reviewer/date/rubric not supplied','Kent not accredited']}
        validate(artifact,product); max_error=0.; parity=[]
        for r in rr:
            x,_=features(safe(Path(r['root']),r['relative']).read_bytes())
            label,ovr,_=decision(artifact,x)
            expected=str(reference.predict([x])[0]); expected_scores=reference.decision_function([x])[0]
            max_error=max(max_error,float(np.max(np.abs(ovr-expected_scores))))
            if label!=expected or expected!=diagnostics[r['relative']]['prediccion_mismo_entrenamiento']:
                raise ValueError('Adapter prediction parity failed')
            parity.append({'id':r['id'],'label':label,'diagnosticOnly':True,'sampleUse':'training'})
        if max_error>1e-5:raise ValueError('Adapter decision-score parity failed')
        dump(output/'models'/f'ag055_pilot117_{product}.json',artifact)
        models[product]={'sourceJoblibSha256':artifact['sourceJoblibSha256'],'predictionParityImages':len(parity),
            'maximumDecisionDifference':max_error,'allowedPickleGlobals':globals_seen,
            'independentTestMetrics':None,'trainingDiagnosticNotPerformance':parity}
    training_hashes={r['sha256'] for r in records}; old_groups={r['previousGroup'] for r in records}
    unseen=[r for r in old if r['sha256'] not in training_hashes]
    report={'images':117,'datasetZipSha256':dataset_sha,'packageZipSha256':package_sha,
        'declaredCounts':dict(Counter(r['product']+'/'+r['label'] for r in records)),
        'declaredHumanReviewsImported':117,'reviewerAndReviewDatesSupplied':False,'knownExactDuplicates':0,
        'similarPairs':len(similar),'crossLabelSimilarPairs':sum(e['grado_A']!=e['grado_B'] for e in similar),
        'allSuppliedImagesUsedInTraining':True,'knownRelatedSplitLeakage':False,'physicalIndependenceVerified':False,
        'independentTestMetrics':None,'kentAccredited':False,'models':models,
        'evaluationPlan':{'independentReviewedEligibleImages':0,'unusedOldPoolImages':len(unseen),
            'unusedOldPoolInKnownTrainingGroups':sum(r['group'] in old_groups for r in unseen),
            'status':'blocked_no_independent_reviewed_holdout',
            'requirements':['Exclude training bytes and related fruit/session/source groups',
                'Obtain independent human E0/E1/E2 labels, reviewer/date/rubric and evidence',
                'Confirm physical independence and provenance before calculating held-out metrics']}}
    dump(output/'audit.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-zip',type=Path,required=True);parser.add_argument('--package-zip',type=Path,required=True)
    parser.add_argument('--previous-run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();result=prepare(a.dataset_zip,a.package_zip,a.previous_run,a.output)
    print(json.dumps({'imported':result['declaredHumanReviewsImported'],'models':list(result['models']),'independentTestMetrics':None}))
