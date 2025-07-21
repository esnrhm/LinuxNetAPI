#!/bin/bash

# اسکریپت init برای container

echo "🐳 راه‌اندازی Linux Network Configuration API در Container"

# بررسی و ایجاد دایرکتوری‌های مورد نیاز
mkdir -p /etc/netplan
mkdir -p /etc/network
mkdir -p /etc/systemd/network

# بررسی وجود فایل‌های مورد نیاز
if [ ! -f /etc/hostname ]; then
    echo "container-host" > /etc/hostname
fi

if [ ! -f /etc/hosts ]; then
    cat > /etc/hosts << EOF
127.0.0.1   localhost
127.0.1.1   container-host
::1         localhost ip6-localhost ip6-loopback
EOF
fi

if [ ! -f /etc/resolv.conf ]; then
    cat > /etc/resolv.conf << EOF
nameserver 8.8.8.8
nameserver 8.8.4.4
EOF
fi

# تنظیم مجوزها
chmod 644 /etc/hostname
chmod 644 /etc/hosts
chmod 644 /etc/resolv.conf

# ایجاد دایرکتوری netplan با مجوزهای صحیح
if [ -d /etc/netplan ]; then
    chmod 755 /etc/netplan
    # تنظیم مجوزهای فایل‌های netplan موجود
    find /etc/netplan -name "*.yaml" -exec chmod 600 {} \;
fi

# ایجاد فایل fake systemctl برای جلوگیری از خطا
if [ ! -f /usr/bin/systemctl.bak ]; then
    if [ -f /usr/bin/systemctl ]; then
        cp /usr/bin/systemctl /usr/bin/systemctl.bak
    fi
    cat > /usr/bin/systemctl << 'EOF'
#!/bin/bash
echo "systemctl $@ (skipped in container)"
exit 0
EOF
    chmod +x /usr/bin/systemctl
fi

# نمایش اطلاعات محیط
echo "📋 اطلاعات محیط:"
echo "   - Hostname: $(cat /etc/hostname 2>/dev/null || echo 'unknown')"
echo "   - Container: ${DOCKER_CONTAINER:-false}"
echo "   - Available tools:"
echo "     * hostnamectl: $(which hostnamectl >/dev/null 2>&1 && echo 'yes' || echo 'no')"
echo "     * netplan: $(which netplan >/dev/null 2>&1 && echo 'yes' || echo 'no')"
echo "     * ifup/ifdown: $(which ifup >/dev/null 2>&1 && echo 'yes' || echo 'no')"

echo "🚀 راه‌اندازی API..."
exec python main.py
