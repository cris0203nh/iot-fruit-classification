"""AG-036: formulario local offline con exportación íntegra CSV + soportes en ZIP.

Cada decisión depende del revisor humano. Nunca se preselecciona grado alguno.
El paquete ZIP de devolución se descomprime en devoluciones/A o /B.
"""
from __future__ import annotations

import json


def render_form(pieces: list[dict], slot: str, previews: dict[str, str] | None = None) -> bytes:
    if slot not in ('A', 'B'):
        raise ValueError('Revisor no válido')
    light = []
    previews = previews or {}
    for p in pieces:
        piece = {key:p[key] for key in ('producto','lote_id','pieza_id','rubrica_version')}
        piece['imagenes'] = [{**image, 'preview_relativa': previews.get(image['imagen_relativa'], '')}
                            for image in p['imagenes']]
        light.append(piece)
    # Evitar inyección de etiquetas HTML desde nombres de archivo externos.
    data = json.dumps(light,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    html = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgroScan · Revisión independiente __SLOT__</title>
<style>
:root{font-family:system-ui,Segoe UI,sans-serif;color:#17212e;background:#f4f6f9}body{margin:0}main{max-width:1100px;padding:24px;margin:0 auto}
header{background:#15344a;color:white;padding:16px 24px}h1{margin:0;font-size:1.4rem}h2{font-size:1.1rem}
.meta{background:white;padding:18px;border:1px solid #dbe1e8;border-radius:10px;margin:16px 0}
.cards{display:grid;gap:18px}.card{background:#fff;border:1px solid #d4dce4;border-radius:12px;padding:18px}
.card figure{margin:0;max-width:340px}.card img{max-height:230px;max-width:100%;object-fit:contain;background:#f4f4f4;border-radius:8px}
.photos{display:flex;flex-wrap:wrap;gap:12px}.photos figcaption{font-size:.72rem;overflow-wrap:anywhere;max-width:300px}
label{display:block;margin:.5rem 0;font-weight:600}select,input,textarea{border:1px solid #aab5c1;border-radius:6px;padding:10px;font:inherit;box-sizing:border-box}
select,input{width:min(100%,500px)}textarea{width:100%;min-height:75px}button{background:#176a85;color:white;border:0;border-radius:7px;padding:11px 17px;font:inherit;cursor:pointer;margin:6px 8px 6px 0}
button.secondary{background:#535e6c}.hint{font-size:.85rem;color:#555}.alert{padding:12px;background:#fff1df;border:1px solid #e0b56f;border-radius:8px}
.actions{position:sticky;bottom:0;background:#f4f6f9;border-top:1px solid #ccc;padding:12px 0}
label.inline{display:inline-flex;align-items:center;font-weight:400}.small{font-size:.85rem}
</style></head><body>
<header><h1>AgroScan · Evaluación humana independiente __SLOT__</h1></header>
<main><div class="meta">
<p><strong>Revisión de condición visual externa, no detección YOLOE ni primera/segunda comercial.</strong>
E0: sin defecto externo relevante; E1: defecto visible que requiere valoración; E2: indicio grave de deterioro que requiere prioridad de revisión. Usa la rúbrica documental del producto; no deduzcas inocuidad o condición interna.</p>
<p class="alert">Este formulario es offline. No comparte resultados con el revisor contrario ni con servidores. La selección de carpetas es exploratoria: la variedad, la independencia física y los permisos de las fuentes aún requieren verificación externa.</p>
<label for="reviewer">Identificador del revisor (ej.: REV_A1, distinto de B)</label><input id="reviewer" maxlength="90" placeholder="REV_A1" autocomplete="off">
<p class="hint">Para cada pieza, mira todas las vistas y selecciona una única decisión. Justifica según lo observable. Para E1/E2 indica criterios de rúbrica Rxx y en qué vista aparece. La exportación incluirá un CSV y soportes de texto redactados a partir de tus respuestas.</p>
<p><strong>Progreso:</strong> <span id="progress">0</span> de __COUNT__ piezas completadas.</p>
</div><div id="cards" class="cards"></div>
<div class="actions"><button id="export">Exportar devolución __SLOT__ (.zip)</button><button class="secondary" id="save">Guardar progreso (.json)</button><button class="secondary" id="load">Recuperar progreso (.json)</button><input id="file" type="file" accept="application/json,.json" hidden><span id="message" aria-live="polite"></span></div>
</main><script>
'use strict';
const SLOT = '__SLOT__';
const PIECES = __DATA__;
const FIELDS = ['producto','lote_id','pieza_id','revisor_id','fecha_revision_iso','rubrica_version','estado_revision','etiqueta_e0_e1_e2','justificacion','criterios_rxx','ubicacion_evidencia','soporte_relativo'];
const state = PIECES.map(() => ({grade:'',why:'',criteria:'',location:'',date:''}));
const cards = document.getElementById('cards');
const message = document.getElementById('message');
const reviewer = document.getElementById('reviewer');
function mark(){const n=state.filter(s=>s.grade).length;document.getElementById('progress').textContent=String(n);}
function nowIso(){ const d = new Date(),o=-d.getTimezoneOffset(),sg=o>=0?'+':'-',v=Math.abs(o); return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')+'T'+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')+':'+String(d.getSeconds()).padStart(2,'0')+sg+String(Math.floor(v/60)).padStart(2,'0')+':'+String(v%60).padStart(2,'0'); }
function elt(tag,attrs={},txt=''){const e=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='class')e.className=v;else e.setAttribute(k,v);}if(txt)e.textContent=txt;return e;}
function field(parent,txt,tag,opts,index,prop){
 const lab=elt('label',{},txt),input=elt(tag,tag==='select'?{}:{placeholder:opts||''});
 if(tag==='select'){for(const [value,label] of opts){const opt=elt('option',{value},label);input.appendChild(opt);}}
 input.value=state[index][prop];input.addEventListener('change',()=>{state[index][prop]=input.value;state[index].date=nowIso();mark();});
 if(tag==='textarea'){input.addEventListener('input',()=>{state[index][prop]=input.value;state[index].date=nowIso();});}
 lab.appendChild(input);parent.appendChild(lab);return input;
}
const widgets=[];
PIECES.forEach((p,i)=>{
 const c=elt('section',{class:'card'});c.appendChild(elt('h2',{},(i+1)+'. '+p.producto.toUpperCase()+' — '+p.pieza_id));
 c.appendChild(elt('p',{class:'hint'},'Rúbrica: '+p.rubrica_version+' | Lote técnico: '+p.lote_id));
 const photos=elt('div',{class:'photos'});
 for(const img of p.imagenes){const f=elt('figure'),im=elt('img',{loading:'lazy',alt:'Vista de '+p.pieza_id});im.src=img.preview_relativa||('imagenes/'+img.imagen_relativa.split('/').map(encodeURIComponent).join('/'));f.appendChild(im);f.appendChild(elt('figcaption',{},img.imagen_relativa.split('/').at(-1)));photos.appendChild(f);}
 c.appendChild(photos);
 const grade=field(c,'Decisión','select',[['','Pendiente'],['E0','E0 — sin defecto visible relevante'],['E1','E1 — defecto visible'],['E2','E2 — deterioro severo visible'],['no_evaluable','No evaluable']],i,'grade');
 const why=field(c,'Justificación observada','textarea','Describe lo que ves realmente en las fotografías',i,'why');
 const criteria=field(c,'Criterios Rxx para E1/E2 (ej.: R01,R03)','input','R01,R03',i,'criteria');
 const location=field(c,'Ubicación visible del defecto para E1/E2','input','Vista A, parte superior izquierda',i,'location');
 widgets.push({grade,why,criteria,location});cards.appendChild(c);
});mark();
function esc(v){const s=String(v??'');return /[",\r\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;}
function csv(rows){return '\ufeff'+[FIELDS.join(','),...rows.map(r=>FIELDS.map(k=>esc(r[k])).join(','))].join('\r\n')+'\r\n';}
const encode=new TextEncoder();
function crc32(d){let c=0xffffffff;for(const b of d){c^=b;for(let k=0;k<8;k++)c=(c>>>1)^((c&1)?0xedb88320:0);}return (c^0xffffffff)>>>0;}
function zipFiles(files){const loc=[],cen=[];let offset=0;function put16(a,n){a.push(n&255,(n>>>8)&255)}function put32(a,n){put16(a,n&65535);put16(a,(n>>>16)&65535)}
 for(const [name,content] of files){const n=encode.encode(name),d=encode.encode(content),c=crc32(d);const local=[];put32(local,0x04034b50);put16(local,20);put16(local,0x0800);put16(local,0);put16(local,0);put16(local,0);put32(local,c);put32(local,d.length);put32(local,d.length);put16(local,n.length);put16(local,0);loc.push(new Uint8Array(local),n,d);
 const entry=[];put32(entry,0x02014b50);put16(entry,20);put16(entry,20);put16(entry,0x0800);put16(entry,0);put16(entry,0);put16(entry,0);put32(entry,c);put32(entry,d.length);put32(entry,d.length);put16(entry,n.length);put16(entry,0);put16(entry,0);put16(entry,0);put16(entry,0);put32(entry,0);put32(entry,offset);cen.push(new Uint8Array(entry),n);offset+=local.length+n.length+d.length;
 }
 const centralSize=cen.reduce((s,a)=>s+a.length,0),end=[];put32(end,0x06054b50);put16(end,0);put16(end,0);put16(end,files.length);put16(end,files.length);put32(end,centralSize);put32(end,offset);put16(end,0);
 return new Blob([...loc,...cen,new Uint8Array(end)],{type:'application/zip'});
}
function download(blob,name){const a=document.createElement('a'),u=URL.createObjectURL(blob);a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),2000);}
function validId(v){return /^[A-Za-z0-9][A-Za-z0-9_-]{0,89}$/.test(v);}
function checkCriteria(s,p){if(!s.criteria)return false;const cs=s.criteria.split(',').map(x=>x.trim());const max=p.producto==='mango'?8:10;return cs.every(c=>/^R\d{2}$/.test(c)&&Number(c.slice(1))>=1&&Number(c.slice(1))<=max)&&new Set(cs).size===cs.length;}
function extract(){const id=reviewer.value.trim();if(!validId(id))throw Error('Ingresa un identificador válido del revisor.');const lines=[],files=[];for(let i=0;i<PIECES.length;i++){
 const p=PIECES[i],s=state[i],base={producto:p.producto,lote_id:p.lote_id,pieza_id:p.pieza_id,rubrica_version:p.rubrica_version};
 if(!s.grade){lines.push({...base,revisor_id:'',fecha_revision_iso:'',estado_revision:'',etiqueta_e0_e1_e2:'',justificacion:'',criterios_rxx:'',ubicacion_evidencia:'',soporte_relativo:''});continue;}
 if(!s.why.trim())throw Error('Falta justificación en '+p.pieza_id);
 if(['E1','E2'].includes(s.grade)&&(!checkCriteria(s,p)||!s.location.trim()))throw Error('E1/E2 requiere Rxx válido y ubicación visible: '+p.pieza_id);
 if(s.grade==='no_evaluable'&&(s.criteria.trim()||s.location.trim()))throw Error('No evaluable: elimina Rxx y ubicación en '+p.pieza_id);
 if(s.grade==='E0'&&(s.criteria.trim()||s.location.trim()))throw Error('E0: elimina Rxx y ubicación en '+p.pieza_id);
 const soporte='evidencia_'+i.toString().padStart(3,'0')+'.txt';const estado=s.grade==='no_evaluable'?'no_evaluable':'etiquetada';
 lines.push({...base,revisor_id:id,fecha_revision_iso:s.date||nowIso(),estado_revision:estado,etiqueta_e0_e1_e2:estado==='etiquetada'?s.grade:'',justificacion:s.why.trim(),criterios_rxx:estado==='etiquetada'?s.criteria.trim():'',ubicacion_evidencia:estado==='etiquetada'?s.location.trim():'',soporte_relativo:soporte});
 files.push(['soportes/'+soporte,'REVISIÓN HUMANA AG-036\nRevisor: '+id+'\nPieza: '+p.producto+'/'+p.lote_id+'/'+p.pieza_id+'\nFecha declarada: '+(s.date||nowIso())+'\nEstado: '+estado+'\nEtiqueta visual: '+s.grade+'\nRúbrica: '+p.rubrica_version+'\nCriterios observados: '+s.criteria+'\nUbicación: '+s.location+'\nJustificación del revisor:\n'+s.why+'\n']);
 }
 return [['revision_'+SLOT+'.csv',csv(lines)],...files];
}
document.getElementById('export').addEventListener('click',()=>{try{const files=extract();download(zipFiles(files),'AG036_Devolucion_'+SLOT+'.zip');message.textContent='ZIP preparado. Conserva tus soportes y entrega al coordinador.';}catch(err){message.textContent=err.message;alert(err.message);}});
document.getElementById('save').addEventListener('click',()=>download(new Blob([JSON.stringify({slot:SLOT,id:reviewer.value,records:state})],{type:'application/json'}),'AG036_Progreso_'+SLOT+'.json'));
document.getElementById('load').addEventListener('click',()=>document.getElementById('file').click());
document.getElementById('file').addEventListener('change',async ev=>{const file=ev.target.files?.[0];if(!file)return;try{const o=JSON.parse(await file.text());if(o.slot!==SLOT||!Array.isArray(o.records)||o.records.length!==PIECES.length)throw Error('Archivo de progreso incompatible');reviewer.value=String(o.id||'');for(let i=0;i<state.length;i++){for(const prop of ['grade','why','criteria','location','date'])state[i][prop]=String(o.records[i][prop]||'');const w=widgets[i];for(const prop of ['grade','why','criteria','location'])w[prop].value=state[i][prop];}mark();message.textContent='Progreso restaurado.';}catch(err){alert(err.message);}ev.target.value='';});
</script></body></html>'''
    # El HTML es una plantilla raw; traducir los escapes dobles a escapes JS normales.
    html = html.replace('\\\\', '\\')
    return (html.replace('__SLOT__',slot).replace('__DATA__',data).replace('__COUNT__',str(len(light)))).encode('utf-8')
