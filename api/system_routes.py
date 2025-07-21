from fastapi import APIRouter, HTTPException
from typing import List
import subprocess
import json
import os
import re
from pathlib import Path
import yaml
import sys

# Add the parent directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.network_models import NetworkInterface, HostnameConfig, NetworkConfig
from core.network_manager import NetworkManager

# ایجاد instance از NetworkManager
network_manager = NetworkManager()

# ایجاد router
router = APIRouter()

@router.get("/", tags=["System Info"])
async def root():
    return {"message": "Linux Network Configuration API", "version": "1.0.0"}

@router.get("/network/config-type", tags=["System Info"])
async def get_config_type():
    """دریافت نوع تنظیمات شبکه سیستم"""
    return {
        "config_type": network_manager.config_type,
        "description": {
            "netplan": "Ubuntu/Netplan configuration",
            "interfaces": "Debian/Ubuntu traditional interfaces",
            "networkmanager": "NetworkManager configuration",
            "systemd-networkd": "Systemd-networkd configuration",
            "unknown": "Unknown configuration type"
        }.get(network_manager.config_type, "Unknown")
    }

@router.get("/container/status", tags=["System Info"])
async def get_container_status():
    """بررسی وضعیت محیط اجرا (container یا host)"""
    return {
        "is_container": network_manager.is_container,
        "environment": "Docker Container" if network_manager.is_container else "Host System",
        "available_tools": {
            "hostnamectl": os.path.exists("/usr/bin/hostnamectl") or os.path.exists("/bin/hostnamectl"),
            "netplan": os.path.exists("/usr/sbin/netplan") or os.path.exists("/sbin/netplan"),
            "ifupdown": os.path.exists("/sbin/ifup"),
            "systemctl": os.path.exists("/usr/bin/systemctl") or os.path.exists("/bin/systemctl")
        },
        "config_type": network_manager.config_type
    }
