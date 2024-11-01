from fastapi import APIRouter
from services.data_service import DataService

router = APIRouter()
data_service = DataService()

@router.get("/data")
async def get_data():
    data = data_service.read_data()
    return {"data": data}

@router.post("/data")
async def post_data(data: dict):
    data_service.write_data(data)
    return {"status": "success"} 