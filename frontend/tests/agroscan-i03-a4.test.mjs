import assert from 'node:assert/strict'
import test from 'node:test'
import { A4_BOARD_VERSION, A4_MARKER_SIDE_MM, boardToA4, measureA4, readStoredA4 } from '../src/features/geometry/a4MeasurementFlow.ts'

const evidence = [{id:'I-000009',view:'vista-1'},{id:'I-000010',view:'vista-2'}]
const measurement={majorAxisCm:6.2,minorAxisCm:5.9,widthCm:6.3,heightCm:6,projectedAreaCm2:27,projectedPerimeterCm:19}
function board(id='I-000009',extra={}) {return {id:2,evaluationId:'E-000016',imageId:id,geometryId:4,imageSha256:'a'.repeat(64),
  modelVersion:'yoloe',rulesVersion:'ag054-board-plane-v2-a4',boardVersion:A4_BOARD_VERSION,
  status:'reference_plane_estimate',reason:'projection_only_not_3d',markerIds:[0,1,2],markerCornersPx:{},
  rmsReprojectionMm:0.5,measurements:measurement,unit:'cm_reference_plane',
  physicalDimensionsValidated:false,fruitHeightCorrected:false,cameraIntrinsicsCalibrated:false,
  classificationE0E1E2Produced:false,createdAt:'2026-11-16T00:00:00Z',...extra}}
const geometry=(id='I-000009',status='measured')=>({id:4,evaluationId:'E-000016',imageId:id,
  imageSha256:'a'.repeat(64),modelVersion:'yoloe',rulesVersion:'geom',status,reason:status==='measured'?'ok':'uncertain',
  product:'tomate',confidence:.8,candidateCount:1,frameWidth:900,frameHeight:600,box:null,polygon:[],
  measurements:status==='measured'?{widthPx:1}:null,unit:'px',calibrated:false,classificationE0E1E2Produced:false,createdAt:''})
function gateway({boards={},geometries=[],onCreate=(id)=>board(id),onAnalyze=(id)=>geometry(id)}={}) {
  const calls={creates:[],analyses:[],reads:[]}
  return {calls,
    listBoardEstimates:async(_eid,id)=>{calls.reads.push(id);return boards[id]??[]},
    listFruitGeometries:async()=>geometries,
    analyzeFruitGeometry:async(_eid,id)=>{calls.analyses.push(id);return onAnalyze(id)},
    createBoardEstimate:async(_eid,id,input)=>{calls.creates.push({id,input});return onCreate(id)},
  }
}
test('Patrón A4 usa la versión exacta y 30 mm de diseño',()=>{
  assert.equal(A4_BOARD_VERSION,'ag054-board-a4-v1');assert.equal(A4_MARKER_SIDE_MM,30)
})
test('Lectura GET no ejecuta análisis ni crea proyecciones',async()=>{
  const g=gateway();const rows=await readStoredA4('E-000016',evidence,g)
  assert.deepEqual(rows.map(x=>x.status),['pending','pending']);assert.equal(g.calls.creates.length,0)
})
test('Recupera proyecciones A4 persistidas por fotografía',async()=>{
  const g=gateway({boards:{'I-000009':[board()]}})
  const rows=await readStoredA4('E-000016',evidence,g)
  assert.deepEqual(rows.map(x=>x.status),['projected','pending']);assert.equal(rows[0].measurement.majorAxisCm,6.2)
})
test('Rechaza resultados de otra evaluación o de otro formato A3',()=>{
  assert.equal(boardToA4(evidence[0],'E-000016',[board('I-000009',{boardVersion:'ag054-board-a3-v1'})]),null)
  assert.equal(boardToA4(evidence[0],'E-000016',[board('I-000009',{evaluationId:'E-999999'})]),null)
  assert.equal(boardToA4(evidence[1],'E-000016',[board()]),null)
})
test('No declara una proyección sin marcadores suficientes ni dato positivo',()=>{
  assert.equal(boardToA4(evidence[0],'E-000016',[board('I-000009',{markerIds:[0,1]})]).status,'needs_review')
  assert.equal(boardToA4(evidence[0],'E-000016',[board('I-000009',{measurements:{...measurement,majorAxisCm:0}})]).status,'needs_review')
})
test('Sin declaración física no envía POST al backend',async()=>{
  const g=gateway({geometries:[geometry(evidence[0].id),geometry(evidence[1].id)]})
  await assert.rejects(measureA4('E-000016',evidence,false,g),/verificar físicamente/)
  assert.equal(g.calls.creates.length,0)
})
test('No inventa medidas cuando hay una sola foto o vistas duplicadas',async()=>{
  const g=gateway()
  await assert.rejects(measureA4('E-000016',evidence.slice(0,1),true,g),/dos vistas/)
  await assert.rejects(measureA4('E-000016',[evidence[0],{...evidence[1],view:'vista-1'}],true,g),/dos vistas/)
  assert.equal(g.calls.creates.length,0)
})
test('Ejecuta A4 en ambas vistas y envía los cuatro controles verdaderos',async()=>{
  const g=gateway({geometries:[geometry(evidence[0].id),geometry(evidence[1].id)],onCreate:board})
  const rows=await measureA4('E-000016',evidence,true,g)
  assert.deepEqual(rows.map(x=>x.status),['projected','projected'])
  assert.equal(g.calls.creates.length,2)
  assert.deepEqual(g.calls.creates[0].input,{boardVersion:A4_BOARD_VERSION,markerAtPlatformLevel:true,
    independentSupport:true,printedDimensionsVerified:true,fixedCamera:true})
})
test('Nunca repite POST cuando el registro A4 ya existe',async()=>{
  const g=gateway({boards:{'I-000009':[board()]},geometries:[geometry('I-000010')]})
  const rows=await measureA4('E-000016',evidence,true,g)
  assert.equal(g.calls.creates.length,1);assert.equal(rows[0].status,'projected')
})
test('Geometría fallida bloquea solo esa vista',async()=>{
  const g=gateway({geometries:[geometry('I-000009','needs_review'),geometry('I-000010')]})
  const rows=await measureA4('E-000016',evidence,true,g)
  assert.deepEqual(rows.map(x=>x.status),['needs_review','projected'])
  assert.deepEqual(g.calls.creates.map(x=>x.id),['I-000010'])
})
test('Resultado de tablero sin ArUco se muestra como revisión, no centímetros',async()=>{
  const g=gateway({geometries:[geometry('I-000009'),geometry('I-000010')],onCreate:id=>board(id,{status:'needs_review',reason:'board_markers_insufficient',markerIds:[],measurements:null})})
  const rows=await measureA4('E-000016',evidence,true,g)
  assert.deepEqual(rows.map(x=>x.status),['needs_review','needs_review']);assert(rows.every(x=>x.measurement===null))
})
test('Un fallo de una vista no descarta el análisis de otra',async()=>{
  const g=gateway({geometries:[geometry('I-000009'),geometry('I-000010')],onCreate:id=>{
    if(id==='I-000009')throw Error('API 503');return board(id)
  }})
  const rows=await measureA4('E-000016',evidence,true,g)
  assert.deepEqual(rows.map(x=>x.status),['error','projected']);assert.equal(rows[0].reason,'API 503')
})
test('No interpreta una fotografía ajena como geometría válida',async()=>{
  const g=gateway({onAnalyze:()=>geometry('I-999999')})
  const rows=await measureA4('E-000016',evidence,true,g)
  assert.equal(rows[0].status,'error');assert.equal(g.calls.creates.length,0)
})
test('Reutiliza el estado de rechazo persistido sin repetir inferencia',async()=>{
  const g=gateway({boards:{'I-000009':[board('I-000009',{status:'needs_review',reason:'board_marker_cropped',markerIds:[],measurements:null})]}})
  const rows=await measureA4('E-000016',evidence,true,g)
  assert.equal(rows[0].status,'needs_review');assert.equal(g.calls.creates.length,1)
})
test('No suma ni promedia medidas de vistas diferentes',async()=>{
  const g=gateway({boards:{'I-000009':[board()], 'I-000010':[board('I-000010',{measurements:{...measurement,majorAxisCm:9}})]}})
  const rows=await readStoredA4('E-000016',evidence,g)
  assert.deepEqual(rows.map(x=>x.measurement.majorAxisCm),[6.2,9]);assert.equal(rows.length,2)
})
