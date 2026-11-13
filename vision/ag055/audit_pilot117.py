"""Independent, explicit similarity heuristic for the imported pilot; never relabels/fits."""
import argparse
import csv
import io
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image,ImageOps

from .experimental import Union,dump,private,safe,sha


def audit(root,output):
    records=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    bits={};by_path={r['relative']:r for r in records}
    for r in records:
        raw=safe(Path(r['root']),r['relative']).read_bytes()
        if sha(raw)!=r['sha256']:raise ValueError('Changed imported original')
        with Image.open(io.BytesIO(raw)) as im:
            gray=np.array(ImageOps.exif_transpose(im).convert('L').resize((32,32)),dtype=np.float32)
        dct=cv2.dct(gray)[:8,:8].ravel()[1:]
        bits[r['relative']]=dct>np.median(dct)
    pairs=[];names=sorted(bits);u=Union(names)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            distance=int(np.count_nonzero(bits[a]!=bits[b]))
            if distance<=8:
                u.join(a,b);pairs.append({'a':a,'b':b,'hamming63':distance,
                    'crossLabel':by_path[a]['label']!=by_path[b]['label']})
    with (root/'package/AG055_Piloto_117/pares_similares_para_revision.csv').open(encoding='utf-8-sig') as f:
        supplied=list(csv.DictReader(f))
    for edge in supplied:u.join(edge['foto_A'],edge['foto_B'])
    # Retain the previously prepared original/date/similarity group constraints too.
    seen={}
    for r in records:
        if r['group'] in seen:u.join(r['relative'],seen[r['group']])
        else:seen[r['group']]=r['relative']
    result={'imagesVerified':len(records),'exactByteDuplicates':len(records)-len({r['sha256'] for r in records}),
        'knownPixelDuplicates':len(records)-len({r['pixelSha256'] for r in records}),
        'method':'EXIF oriented PIL L resize32(default bicubic), cv2 DCT8x8 excluding DC; median, Hamming<=8',
        'newHeuristicPairs':pairs,'newHeuristicCrossLabelPairs':sum(p['crossLabel'] for p in pairs),
        'suppliedCandidatePairs':len(supplied),
        'suppliedDistancesDifferFromThisMethod':sum(int(np.count_nonzero(bits[e['foto_A']]!=bits[e['foto_B']]))!=int(e['distancia_phash_63bits']) for e in supplied),
        'similarityDoesNotEstablishFruitIdentity':True,'independentTestMetrics':None,
        'groupsForFutureHoldoutExclusion':{r['id']:u.find(r['relative']) for r in records},
        'all117AlreadyTrained':True,'holdoutEligibleAnnotatedImages':0,
        'note':'Supplied pHash preprocessing is not specified; differing distances are method-dependent, not proof of wrong human labels'}
    dump(private(output),result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    r=audit(args.run,args.output);print(json.dumps({'pairs':len(r['newHeuristicPairs']),'crossLabel':r['newHeuristicCrossLabelPairs'],'eligibleIndependent':0}))
