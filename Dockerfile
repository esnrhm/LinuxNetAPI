FROM python:3.11-slim

# نصب ابزارهای شبکه و سیستم مورد نیاز
RUN apt-get update && apt-get install -y \
    iproute2 \
    net-tools \
    iputils-ping \
    netplan.io \
    ifupdown \
    curl \
    wget \
    nano \
    dbus \
    && rm -rf /var/lib/apt/lists/*

# تنظیم متغیرهای محیطی برای جلوگیری از خطاهای systemd
ENV SYSTEMD_IGNORE_CHROOT=1

# تنظیم working directory
WORKDIR /app

# کپی فایل‌های پروژه
COPY . .

# تنظیم مجوزها
RUN chmod +x init-container.sh

# نصب Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# تنظیم متغیر محیطی
ENV PYTHONPATH=/app

# expose port
EXPOSE 8000

# دستور اجرا
CMD ["./init-container.sh"]
