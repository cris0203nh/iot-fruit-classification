from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import DATA_DIR, get_db
from ..dependencies import require_admin
from ..services.organization_export import organization_export
from ..services.device_auth import require_iot_schema

router = APIRouter(prefix='/api/organization', tags=['exportación empresarial'])


@router.get('/export', dependencies=[Depends(require_admin), Depends(require_iot_schema)])
def export_organization(db: Session = Depends(get_db)):
    result = organization_export(db, DATA_DIR)

    def stream():
        try:
            while chunk := result.read(65536):
                yield chunk
        finally:
            result.close()

    return StreamingResponse(stream(), media_type='application/zip', headers={
        'Cache-Control': 'no-store',
        'Content-Disposition': f'attachment; filename="agroscan-organization-{db.info["organization_id"]}.zip"'})
