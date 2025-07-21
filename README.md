# Linux Network Configuration API

API برای مدیریت تنظیمات شبکه در سیستم‌های لینوکس با FastAPI

## ساختار پروژه

```
config_script/
├── main_new.py              # فایل اصلی FastAPI (تمیز شده)
├── main.py                  # فایل قدیمی (backup)
├── models/                  # مدل‌های Pydantic
│   ├── __init__.py
│   └── network_models.py
├── core/                    # منطق اصلی برنامه
│   ├── __init__.py
│   └── network_manager.py   # کلاس NetworkManager
├── api/                     # Route ها
│   ├── __init__.py
│   ├── system_routes.py     # اطلاعات سیستم
│   ├── hostname_routes.py   # مدیریت hostname
│   ├── interface_routes.py  # مدیریت اینترفیس‌ها
│   └── network_routes.py    # عملیات شبکه و netplan
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── init-container.sh
└── test_api.py
```

## ویژگی‌ها

- **فیلترینگ اینترفیس‌ها**: فقط کارت‌های شبکه عمومی (eth, ens, enp, وغیره) قابل مشاهده و کانفیگ هستند
- **پشتیبانی از Container**: تشخیص خودکار محیط container و اعمال تنظیمات مناسب
- **پشتیبانی از چندین نوع کانفیگ**: netplan، interfaces، NetworkManager
- **اعمال مستقیم IP**: استفاده از دستورات ip برای اعمال فوری تغییرات
- **مدیریت hostname**: تغییر و مدیریت hostname سیستم
- **پاکسازی خودکار**: حذف فایل‌های netplan اضافی

## اجرا

### روش 1: مستقیم
```bash
python main_new.py
```

### روش 2: با Docker
```bash
docker-compose up --build
```

## API Endpoints

### اطلاعات سیستم
- `GET /` - صفحه اصلی
- `GET /network/config-type` - نوع کانفیگ شبکه
- `GET /container/status` - وضعیت container
- `GET /system/info` - اطلاعات کامل سیستم

### مدیریت Hostname
- `GET /hostname` - دریافت hostname فعلی
- `POST /hostname` - تنظیم hostname جدید

### مدیریت اینترفیس‌ها
- `GET /network/interfaces` - لیست اینترفیس‌های عمومی
- `GET /network/interfaces/all` - تمام اینترفیس‌ها (عمومی + سیستمی)
- `GET /network/interfaces/{name}` - جزئیات یک اینترفیس
- `POST /network/interfaces/{name}/configure` - کانفیگ اینترفیس
- `POST /network/interfaces/{name}/restart` - ری‌استارت اینترفیس
- `POST /network/interfaces/{name}/enable` - فعال کردن اینترفیس
- `POST /network/interfaces/{name}/disable` - غیرفعال کردن اینترفیس

### عملیات شبکه
- `GET /network/status` - وضعیت کلی شبکه
- `GET /network/dns` - DNS servers
- `GET /network/routes` - جدول routing
- `GET /network/netplan/files` - فایل‌های netplan
- `POST /network/apply-config` - اعمال کانفیگ شبکه
- `POST /network/netplan/validate` - اعتبارسنجی netplan
- `DELETE /network/netplan/cleanup/{name}` - پاکسازی فایل‌های netplan

## نمونه استفاده

### کانفیگ IP استاتیک
```bash
curl -X POST "http://localhost:8000/network/interfaces/eth0/configure" \
  -H "Content-Type: application/json" \
  -d '{
    "ip_address": "192.168.1.100",
    "netmask": "255.255.255.0",
    "gateway": "192.168.1.1",
    "dns_servers": ["8.8.8.8", "1.1.1.1"],
    "is_dhcp": false
  }'
```

### فعال کردن DHCP
```bash
curl -X POST "http://localhost:8000/network/interfaces/eth0/configure" \
  -H "Content-Type: application/json" \
  -d '{
    "ip_address": "",
    "netmask": "",
    "is_dhcp": true
  }'
```

### تغییر hostname
```bash
curl -X POST "http://localhost:8000/hostname" \
  -H "Content-Type: application/json" \
  -d '{"hostname": "my-server"}'
```

## محدودیت‌ها

- فقط اینترفیس‌های شبکه عمومی قابل کانفیگ هستند
- در محیط container ممکن است برخی عملیات محدود باشند
- نیاز به دسترسی root برای تغییر تنظیمات شبکه

## مسائل حل شده

- ✅ فیلترینگ اینترفیس‌ها
- ✅ پشتیبانی از container
- ✅ اعمال مستقیم IP
- ✅ پاکسازی خودکار netplan
