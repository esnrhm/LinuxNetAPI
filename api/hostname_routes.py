from fastapi import APIRouter, HTTPException
from typing import List
import subprocess
import re
import sys
import os

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.network_models import HostnameConfig
from core.network_manager import NetworkManager

# ایجاد instance از NetworkManager
network_manager = NetworkManager()

# ایجاد router
router = APIRouter()

@router.get("/hostname", tags=["Hostname Management"])
async def get_hostname():
    """دریافت hostname فعلی سیستم"""
    hostname = network_manager.get_hostname()
    return {
        "hostname": hostname,
        "message": f"Hostname فعلی: {hostname}"
    }

@router.post("/hostname", tags=["Hostname Management"])
async def set_hostname(config: HostnameConfig):
    """تنظیم hostname جدید برای سیستم"""
    # اعتبارسنجی hostname
    if not config.hostname or len(config.hostname.strip()) == 0:
        raise HTTPException(status_code=400, detail="Hostname نمی‌تواند خالی باشد")
    
    # بررسی قوانین hostname
    hostname = config.hostname.strip().lower()
    if not re.match(r'^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?$', hostname):
        raise HTTPException(
            status_code=400, 
            detail="Hostname باید شامل حروف، اعداد و خط تیره باشد و بیشتر از 63 کاراکتر نباشد"
        )
    
    current_hostname = network_manager.get_hostname()
    
    if current_hostname == hostname:
        return {
            "message": f"Hostname قبلاً روی {hostname} تنظیم شده است",
            "hostname": hostname,
            "changed": False
        }
    
    success = network_manager.set_hostname(hostname)
    
    if success:
        return {
            "message": f"Hostname با موفقیت به {hostname} تغییر یافت",
            "old_hostname": current_hostname,
            "new_hostname": hostname,
            "changed": True,
            "note": "برای اعمال کامل تغییرات، سیستم را restart کنید"
        }
    else:
        raise HTTPException(status_code=500, detail="خطا در تنظیم hostname")

@router.get("/system/info", tags=["System Info"])
async def get_system_info():
    """دریافت اطلاعات کامل سیستم شامل hostname و تنظیمات شبکه"""
    try:
        hostname = network_manager.get_hostname()
        interfaces = network_manager.get_interfaces()
        active_interfaces = [iface for iface in interfaces if iface.is_active]
        dns_servers = network_manager._get_dns_servers()
        
        return {
            "hostname": hostname,
            "network_config_type": network_manager.config_type,
            "total_interfaces": len(interfaces),
            "active_interfaces": len(active_interfaces),
            "dns_servers": dns_servers,
            "system_summary": {
                "hostname": hostname,
                "network_method": network_manager.config_type,
                "active_connections": len(active_interfaces),
                "primary_dns": dns_servers[0] if dns_servers else "None"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در دریافت اطلاعات سیستم: {str(e)}")
