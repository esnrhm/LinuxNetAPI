#!/bin/bash

# اسکریپت راه‌اندازی Linux Network Configuration API

echo "🚀 راه‌اندازی Linux Network Configuration API"
echo "=" 

# بررسی وجود Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 یافت نشد. لطفاً ابتدا Python3 را نصب کنید."
    exit 1
fi

# بررسی وجود pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 یافت نشد. لطفاً ابتدا pip3 را نصب کنید."
    exit 1
fi

echo "📦 نصب وابستگی‌ها..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ وابستگی‌ها با موفقیت نصب شدند"
else
    echo "❌ خطا در نصب وابستگی‌ها"
    exit 1
fi

# بررسی دسترسی root
if [ "$EUID" -ne 0 ]; then
    echo "⚠️  توجه: این API برای تغییر تنظیمات شبکه نیاز به دسترسی root دارد"
    echo "   برای اجرای کامل API از sudo استفاده کنید:"
    echo "   sudo python3 main.py"
    echo ""
fi

echo "🌐 راه‌اندازی API..."
echo "📍 API در آدرس http://localhost:8000 در دسترس خواهد بود"
echo "📖 مستندات در آدرس http://localhost:8000/docs قابل مشاهده است"
echo ""

# اجرای API
python3 main.py
