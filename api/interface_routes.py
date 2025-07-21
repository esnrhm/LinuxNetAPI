from fastapi import APIRouter, HTTPException
from typing import List
import subprocess
import json
from pathlib import Path
import yaml
import sys
import os

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.network_models import NetworkInterface, NetworkConfig
from core.network_manager import NetworkManager

# ایجاد instance از NetworkManager
network_manager = NetworkManager()

# ایجاد router
router = APIRouter()

@router.get("/network/interfaces", response_model=List[NetworkInterface], tags=["Network Interfaces"])
async def get_interfaces():
    """دریافت لیست اینترفیس‌های شبکه عمومی"""
    return network_manager.get_interfaces()

@router.get("/network/interfaces/all", tags=["Network Interfaces"])
async def get_all_interfaces():
    """دریافت لیست تمام اینترفیس‌های شبکه (شامل اینترفیس‌های سیستمی)"""
    try:
        # دریافت اینترفیس‌ها بدون فیلتر
        result = subprocess.run(['ip', '-j', 'addr', 'show'], 
                              capture_output=True, text=True, check=True)
        ip_data = json.loads(result.stdout)
        
        public_interfaces = []
        system_interfaces = []
        
        for iface_data in ip_data:
            interface_name = iface_data['ifname']
            
            interface_info = {
                "name": interface_name,
                "is_active": 'UP' in iface_data.get('flags', []),
                "ip_address": None,
                "type": "public" if network_manager._is_public_network_interface(interface_name) else "system"
            }
            
            # استخراج IP address
            for addr_info in iface_data.get('addr_info', []):
                if addr_info.get('family') == 'inet':
                    interface_info["ip_address"] = addr_info.get('local')
                    break
            
            if interface_info["type"] == "public":
                public_interfaces.append(interface_info)
            else:
                system_interfaces.append(interface_info)
        
        return {
            "summary": {
                "total_interfaces": len(ip_data),
                "public_interfaces": len(public_interfaces),
                "system_interfaces": len(system_interfaces)
            },
            "public_interfaces": public_interfaces,
            "system_interfaces": system_interfaces,
            "note": "فقط اینترفیس‌های عمومی قابل پیکربندی هستند"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در دریافت اینترفیس‌ها: {str(e)}")

@router.get("/network/interfaces/{interface_name}", response_model=NetworkInterface, tags=["Network Interfaces"])
async def get_interface(interface_name: str):
    """دریافت اطلاعات یک اینترفیس خاص"""
    # بررسی اینکه اینترفیس یک کارت شبکه عمومی است
    if not network_manager._is_public_network_interface(interface_name):
        raise HTTPException(
            status_code=400, 
            detail=f"اینترفیس {interface_name} یک کارت شبکه عمومی نیست"
        )
    
    interfaces = network_manager.get_interfaces()
    for interface in interfaces:
        if interface.name == interface_name:
            return interface
    raise HTTPException(status_code=404, detail=f"اینترفیس {interface_name} یافت نشد")

@router.post("/network/interfaces/{interface_name}/configure", tags=["Interface Configuration"])
async def configure_interface(interface_name: str, config: NetworkConfig):
    """پیکربندی یک اینترفیس شبکه"""
    # بررسی اینکه اینترفیس یک کارت شبکه عمومی است
    if not network_manager._is_public_network_interface(interface_name):
        raise HTTPException(
            status_code=400, 
            detail=f"اینترفیس {interface_name} یک کارت شبکه عمومی نیست و قابل پیکربندی نمی‌باشد"
        )
    
    # بررسی وجود اینترفیس
    interfaces = network_manager.get_interfaces()
    interface_exists = any(iface.name == interface_name for iface in interfaces)
    
    if not interface_exists:
        raise HTTPException(status_code=404, detail=f"اینترفیس {interface_name} یافت نشد")
    
    success = network_manager.configure_interface(interface_name, config)
    
    if success:
        return {
            "message": f"اینترفیس {interface_name} با موفقیت پیکربندی شد",
            "interface": interface_name,
            "config": config.dict()
        }
    else:
        raise HTTPException(status_code=500, detail="خطا در پیکربندی اینترفیس")

@router.post("/network/interfaces/{interface_name}/restart", tags=["Interface Configuration"])
async def restart_interface(interface_name: str):
    """راه‌اندازی مجدد یک اینترفیس"""
    # بررسی اینکه اینترفیس یک کارت شبکه عمومی است
    if not network_manager._is_public_network_interface(interface_name):
        raise HTTPException(
            status_code=400, 
            detail=f"اینترفیس {interface_name} یک کارت شبکه عمومی نیست و قابل مدیریت نمی‌باشد"
        )
    
    try:
        # تشخیص نوع تنظیمات شبکه و استفاده از روش مناسب
        if network_manager.config_type == "netplan":
            # برای netplan از ip command و netplan apply استفاده کن
            try:
                # پایین آوردن اینترفیس
                subprocess.run(["ip", "link", "set", "dev", interface_name, "down"], check=True)
                
                # اعمال مجدد تنظیمات netplan (فقط در host system)
                if not network_manager.is_container:
                    subprocess.run(["netplan", "apply"], check=True)
                else:
                    # در container فقط generate کن
                    try:
                        subprocess.run(["netplan", "generate"], check=False)
                    except:
                        pass
                
                # بالا آوردن اینترفیس
                subprocess.run(["ip", "link", "set", "dev", interface_name, "up"], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # fallback: فقط ip command
                subprocess.run(["ip", "link", "set", "dev", interface_name, "down"], check=False)
                subprocess.run(["ip", "link", "set", "dev", interface_name, "up"], check=True)
        
        elif network_manager.config_type == "interfaces":
            # برای interfaces سنتی از ifup/ifdown استفاده کن
            try:
                subprocess.run(["ifdown", interface_name], check=False)
                subprocess.run(["ifup", interface_name], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # fallback: ip command
                subprocess.run(["ip", "link", "set", "dev", interface_name, "down"], check=False)
                subprocess.run(["ip", "link", "set", "dev", interface_name, "up"], check=True)
        
        elif network_manager.config_type == "networkmanager":
            # برای NetworkManager
            try:
                subprocess.run(["nmcli", "connection", "down", interface_name], check=False)
                subprocess.run(["nmcli", "connection", "up", interface_name], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # fallback: ip command
                subprocess.run(["ip", "link", "set", "dev", interface_name, "down"], check=False)
                subprocess.run(["ip", "link", "set", "dev", interface_name, "up"], check=True)
        
        else:
            # برای سایر موارد فقط ip command
            subprocess.run(["ip", "link", "set", "dev", interface_name, "down"], check=False)
            subprocess.run(["ip", "link", "set", "dev", interface_name, "up"], check=True)
        
        return {
            "message": f"اینترفیس {interface_name} با موفقیت راه‌اندازی مجدد شد",
            "method": network_manager.config_type
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"خطا در راه‌اندازی مجدد اینترفیس: {str(e)}"
        )

@router.post("/network/interfaces/{interface_name}/enable", tags=["Interface Configuration"])
async def enable_interface(interface_name: str):
    """فعال کردن یک اینترفیس"""
    # بررسی اینکه اینترفیس یک کارت شبکه عمومی است
    if not network_manager._is_public_network_interface(interface_name):
        raise HTTPException(
            status_code=400, 
            detail=f"اینترفیس {interface_name} یک کارت شبکه عمومی نیست و قابل مدیریت نمی‌باشد"
        )
    
    try:
        subprocess.run(["ip", "link", "set", "dev", interface_name, "up"], check=True)
        
        # اگر netplan است، تنظیمات را نیز اعمال کن
        if network_manager.config_type == "netplan":
            try:
                subprocess.run(["netplan", "apply"], check=False)
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        
        return {
            "message": f"اینترفیس {interface_name} فعال شد",
            "method": "ip command" + (" + netplan apply" if network_manager.config_type == "netplan" else "")
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"خطا در فعال کردن اینترفیس: {str(e)}"
        )

@router.post("/network/interfaces/{interface_name}/disable", tags=["Interface Configuration"])
async def disable_interface(interface_name: str):
    """غیرفعال کردن یک اینترفیس"""
    # بررسی اینکه اینترفیس یک کارت شبکه عمومی است
    if not network_manager._is_public_network_interface(interface_name):
        raise HTTPException(
            status_code=400, 
            detail=f"اینترفیس {interface_name} یک کارت شبکه عمومی نیست و قابل مدیریت نمی‌باشد"
        )
    
    try:
        subprocess.run(["ip", "link", "set", "dev", interface_name, "down"], check=True)
        return {
            "message": f"اینترفیس {interface_name} غیرفعال شد",
            "method": "ip command"
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500,
            detail=f"خطا در غیرفعال کردن اینترفیس: {str(e)}"
        )
