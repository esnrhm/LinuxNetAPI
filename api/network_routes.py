from fastapi import APIRouter, HTTPException
import subprocess
from pathlib import Path
import yaml
import sys
import os

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.network_manager import NetworkManager

# ایجاد instance از NetworkManager
network_manager = NetworkManager()

# ایجاد router
router = APIRouter()

@router.get("/network/netplan/files", tags=["System Info"])
async def get_netplan_files():
    """دریافت لیست فایل‌های netplan موجود"""
    try:
        netplan_dir = Path("/etc/netplan")
        files_info = []
        
        if netplan_dir.exists():
            for config_file in netplan_dir.glob("*.yaml"):
                try:
                    with open(config_file, "r") as f:
                        config = yaml.safe_load(f)
                    
                    # استخراج اینترفیس‌های تعریف شده
                    interfaces = []
                    if config and "network" in config:
                        ethernets = config["network"].get("ethernets", {})
                        interfaces = list(ethernets.keys())
                    
                    file_info = {
                        "filename": config_file.name,
                        "path": str(config_file),
                        "interfaces": interfaces,
                        "size": config_file.stat().st_size,
                        "modified": config_file.stat().st_mtime
                    }
                    files_info.append(file_info)
                
                except Exception as e:
                    # اگر خطایی در خواندن فایل رخ داد
                    file_info = {
                        "filename": config_file.name,
                        "path": str(config_file),
                        "interfaces": [],
                        "error": str(e),
                        "size": config_file.stat().st_size,
                        "modified": config_file.stat().st_mtime
                    }
                    files_info.append(file_info)
        
        return {
            "netplan_directory": str(netplan_dir),
            "total_files": len(files_info),
            "files": files_info
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در دریافت فایل‌های netplan: {str(e)}")

@router.delete("/network/netplan/cleanup/{interface_name}", tags=["Interface Configuration"])
async def cleanup_netplan_interface(interface_name: str):
    """پاک کردن دستی فایل‌های netplan مربوط به یک اینترفیس"""
    try:
        # بررسی اینکه اینترفیس یک کارت شبکه عمومی است
        if not network_manager._is_public_network_interface(interface_name):
            raise HTTPException(
                status_code=400, 
                detail=f"اینترفیس {interface_name} یک کارت شبکه عمومی نیست و قابل مدیریت نمی‌باشد"
            )
        
        # بررسی وجود اینترفیس
        interfaces = network_manager.get_interfaces()
        interface_exists = any(iface.name == interface_name for iface in interfaces)
        
        if not interface_exists:
            raise HTTPException(status_code=404, detail=f"اینترفیس {interface_name} یافت نشد")
        
        # پاک کردن فایل‌های netplan
        network_manager._cleanup_netplan_files(interface_name)
        
        return {
            "message": f"فایل‌های netplan مربوط به اینترفیس {interface_name} پاک شدند",
            "interface": interface_name
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در پاک کردن فایل‌های netplan: {str(e)}")

@router.post("/network/apply-config", tags=["Interface Configuration"])
async def apply_network_config():
    """اعمال تنظیمات شبکه بر اساس نوع سیستم"""
    try:
        result = {
            "config_type": network_manager.config_type,
            "actions_performed": [],
            "success": True
        }
        
        if network_manager.config_type == "netplan":
            try:
                if network_manager.is_container:
                    # در container فقط generate کن
                    subprocess.run(["netplan", "generate"], check=True)
                    result["actions_performed"].append("netplan generate executed (container mode)")
                else:
                    # در host system از apply استفاده کن
                    subprocess.run(["netplan", "apply"], check=True)
                    result["actions_performed"].append("netplan apply executed")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                result["actions_performed"].append(f"netplan operation failed: {str(e)}")
                result["success"] = False
        
        elif network_manager.config_type == "interfaces":
            try:
                subprocess.run(["systemctl", "restart", "networking"], check=True)
                result["actions_performed"].append("networking service restarted")
            except (subprocess.CalledProcessError, FileNotFoundError):
                try:
                    subprocess.run(["/etc/init.d/networking", "restart"], check=True)
                    result["actions_performed"].append("networking init script executed")
                except (subprocess.CalledProcessError, FileNotFoundError) as e:
                    result["actions_performed"].append(f"networking restart failed: {str(e)}")
                    result["success"] = False
        
        elif network_manager.config_type == "networkmanager":
            try:
                subprocess.run(["systemctl", "restart", "NetworkManager"], check=True)
                result["actions_performed"].append("NetworkManager restarted")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                result["actions_performed"].append(f"NetworkManager restart failed: {str(e)}")
                result["success"] = False
        
        else:
            result["actions_performed"].append("No specific action for unknown config type")
            result["success"] = False
        
        if result["success"]:
            result["message"] = "تنظیمات شبکه با موفقیت اعمال شد"
        else:
            result["message"] = "برخی از عملیات با شکست مواجه شدند"
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در اعمال تنظیمات شبکه: {str(e)}")

@router.post("/network/netplan/validate", tags=["System Info"])
async def validate_netplan():
    """اعتبارسنجی تمام فایل‌های netplan"""
    try:
        netplan_dir = Path("/etc/netplan")
        validation_results = []
        
        if netplan_dir.exists():
            for config_file in netplan_dir.glob("*.yaml"):
                is_valid = network_manager._validate_netplan_config(str(config_file))
                
                result = {
                    "file": config_file.name,
                    "path": str(config_file),
                    "valid": is_valid,
                    "permissions": oct(config_file.stat().st_mode)[-3:]
                }
                
                # بررسی مجوزها
                file_mode = config_file.stat().st_mode & 0o777
                if file_mode != 0o600:
                    result["permission_warning"] = f"مجوزها باید 600 باشند، اما {oct(file_mode)[-3:]} هستند"
                
                validation_results.append(result)
        
        all_valid = all(r["valid"] for r in validation_results)
        
        return {
            "all_valid": all_valid,
            "total_files": len(validation_results),
            "valid_files": sum(1 for r in validation_results if r["valid"]),
            "files": validation_results
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در اعتبارسنجی netplan: {str(e)}")

@router.get("/network/status", tags=["Network Status"])
async def get_network_status():
    """دریافت وضعیت کلی شبکه"""
    try:
        # دریافت اطلاعات routing table
        route_result = subprocess.run(['ip', 'route'], capture_output=True, text=True, check=True)
        
        # دریافت اطلاعات DNS
        dns_servers = network_manager._get_dns_servers()
        
        # دریافت اینترفیس‌های فعال
        interfaces = network_manager.get_interfaces()
        active_interfaces = [iface for iface in interfaces if iface.is_active]
        
        return {
            "config_type": network_manager.config_type,
            "total_interfaces": len(interfaces),
            "active_interfaces": len(active_interfaces),
            "dns_servers": dns_servers,
            "interfaces": [
                {
                    "name": iface.name,
                    "ip": iface.ip_address,
                    "active": iface.is_active,
                    "dhcp": iface.is_dhcp
                }
                for iface in interfaces
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطا در دریافت وضعیت شبکه: {str(e)}")

@router.get("/network/dns", tags=["Network Status"])
async def get_dns_servers():
    """دریافت لیست DNS servers فعلی"""
    dns_servers = network_manager._get_dns_servers()
    return {
        "dns_servers": dns_servers,
        "count": len(dns_servers)
    }

@router.get("/network/routes", tags=["Network Status"]) 
async def get_routes():
    """دریافت جدول مسیریابی"""
    try:
        result = subprocess.run(['ip', 'route'], capture_output=True, text=True, check=True)
        routes = []
        for line in result.stdout.splitlines():
            if line.strip():
                routes.append(line.strip())
        return {
            "routes": routes,
            "count": len(routes)
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"خطا در دریافت جدول مسیریابی: {str(e)}")
