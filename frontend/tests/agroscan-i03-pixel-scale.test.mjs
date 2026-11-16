import assert from 'node:assert/strict'
import test from 'node:test'
import { recoverApproxA4 } from '../src/features/geometry/approxA4Flow.ts'
// Tests de contrato estáticos; los casos de lógica dinámica se cubren en I03.
const rows = [{ id:1, evaluationId:'E-000019',imageId:'I-000015',
 boardVersion:'ag054-board-a4-v1',rulesVersion:'ag054-board-plane-v4-a4-marker-pixels',
 status:'pixel_scale_estimate', reason:'approximate_marker_pixel_scale_no_3d',
 markerIds:[0,1,2,3], measurements:{majorAxisCm:6,minorAxisCm:4,widthCm:6,heightCm:4},
 physicalDimensionsValidated:false,fruitHeightCorrected:false,cameraIntrinsicsCalibrated:false,
 classificationE0E1E2Produced:false,unit:'cm_reference_plane' }]
const evidence=[{id:'I-000015',view:'vista-1'}]
test('Solo usa registros pixel v4 de la evaluación exacta',()=>{
 assert.equal(recoverApproxA4('E-000019',evidence,[rows])[0].status,'estimated')
 assert.equal(recoverApproxA4('E-000020',evidence,[rows])[0].status,'pending')
})
test('No convierte un rechazo en una medida',()=>{
 const bad={...rows[0],status:'needs_review',measurements:null}
 assert.equal(recoverApproxA4('E-000019',evidence,[[bad]])[0].status,'needs_review')
})
test('No confunde el A4 homografia con la aproximación',()=>{
 const old={...rows[0],rulesVersion:'ag054-board-plane-v3-a4-global-fit',status:'reference_plane_estimate'}
 assert.equal(recoverApproxA4('E-000019',evidence,[[old]])[0].status,'pending')
})
