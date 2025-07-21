from fastapi import FastAPI
import uvicorn
import sys
import os

# Add the current directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import routers
from api.system_routes import router as system_router
from api.hostname_routes import router as hostname_router
from api.interface_routes import router as interface_router
from api.network_routes import router as network_router

app = FastAPI(
    title="Linux Network Configuration API", 
    version="1.0.0",
    description="API برای مدیریت تنظیمات شبکه در سیستم‌های لینوکس",
    tags_metadata=[
        {
            "name": "System Info",
            "description": "اطلاعات سیستم و نوع تنظیمات شبکه",
        },
        {
            "name": "Hostname Management",
            "description": "مدیریت hostname سیستم",
        },
        {
            "name": "Network Interfaces",
            "description": "مدیریت اینترفیس‌های شبکه",
        },
        {
            "name": "Interface Configuration",
            "description": "پیکربندی IP، Gateway و DNS",
        },
        {
            "name": "Network Status",
            "description": "وضعیت و مانیتورینگ شبکه",
        },
    ]
)

# Include routers
app.include_router(system_router)
app.include_router(hostname_router)
app.include_router(interface_router)
app.include_router(network_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
