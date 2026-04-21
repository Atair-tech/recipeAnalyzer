from fastapi import APIRouter, HTTPException, Query

from app.services.database_browser_service import get_table_rows, list_database_tables


router = APIRouter()


@router.get("/database/tables")
def database_tables():
    return list_database_tables()


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
