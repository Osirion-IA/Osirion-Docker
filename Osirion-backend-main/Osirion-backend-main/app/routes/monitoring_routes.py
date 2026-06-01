from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Dict, Any

from app.services.sys_monitoring_service import get_system_info
from app.middleware.auth_middleware import require_admin

router = APIRouter()

class SystemInfoResponse(BaseModel):
    general: Dict[str, Any]
    boot_time: str
    cpu: Dict[str, Any]
    ram: Dict[str, Any]
    swap: Dict[str, Any]
    disks: list[Dict[str, Any]]
    network: Dict[str, Any]
    network_interfaces: Dict[str, Dict[str, Any]]

    class Config:
        schema_extra = {
            "example": {
                "general": {"system": "Linux", "hostname": "my-server"},
                # ... etc
            }
        }

@router.get("/", response_model=SystemInfoResponse)
async def get_system_info_endpoint(_current_user=Depends(require_admin)) -> SystemInfoResponse:
    return get_system_info()