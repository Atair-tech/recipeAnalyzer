from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.services.database_browser_service import get_table_rows, list_database_tables
from app.services.database_transfer_service import get_database_export_info, import_database_file


router = APIRouter()


@router.get("/database/tables")
def database_tables():
    return list_database_tables()


@router.get("/database/export")
def export_database():
    try:
        export_info = get_database_export_info()
        return FileResponse(
            export_info["path"],
            media_type="application/x-sqlite3",
            filename=export_info["file_name"],
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to export database: {error}") from error


@router.post("/database/import")
def import_database(file: UploadFile = File(...)):
    try:
        return import_database_file(file)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to import database: {error}") from error


@router.get("/database/tables/{table_name}")
def database_table_rows(
    table_name: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    try:
        return get_table_rows(table_name=table_name, limit=limit, offset=offset)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Failed to load table rows: {error}") from error
