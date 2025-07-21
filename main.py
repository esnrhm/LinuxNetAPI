from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import subprocess
import json
import os
import re
import yaml
from pathlib import Path

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

class NetworkInterface(BaseModel):
    name: str
    ip_address: Optional[str] = None
    netmask: Optional[str] = None
    gateway: Optional[str] = None
    dns_servers: Optional[List[str]] = None
    is_dhcp: bool = False
    is_active: bool = False

class NetworkConfig(BaseModel):
    ip_address: str
    netmask: str
    gateway: Optional[str] = None
    dns_servers: Optional[List[str]] = None
    is_dhcp: bool = False

class HostnameConfig(BaseModel):
    hostname: str

class NetworkManager:
    def __init__(self):
        self.config_type = self.detect_network_config_type()
        self.is_container = self._detect_container_environment()
    
    def _detect_container_environment(self) -> bool:
        """تشخیص اینکه آیا در محیط container هستیم یا نه"""
        # بررسی فایل /.dockerenv
        if os.path.exists('/.dockerenv'):
            return True
        
        # بررسی متغیر محیطی
        if os.environ.get('container') or os.environ.get('DOCKER_CONTAINER'):
            return True
        
        # بررسی cgroup
        try:
            with open('/proc/1/cgroup', 'r') as f:
                content = f.read()
                if 'docker' in content or 'containerd' in content:
                    return True
        except:
            pass
        
        return False
    
    def _is_public_network_interface(self, interface_name: str) -> bool:
        """بررسی اینکه آیا اینترفیس یک کارت شبکه عمومی است"""
        # پترن‌های مجاز برای نام اینترفیس‌های شبکه عمومی
        public_patterns = [
            r'^eth\d+$',        # eth0, eth1, ...
            r'^ens\d+$',        # ens33, ens160, ...
            r'^enp\d+s\d+$',    # enp0s3, enp2s0, ...
            r'^eno\d+$',        # eno1, eno2, ...
            r'^enx[0-9a-f]{12}$',  # enx001122334455 (MAC-based)
            r'^em\d+$',         # em1, em2, ... (old naming)
            r'^p\d+p\d+$',      # p1p1, p2p1, ... (physical port)
            r'^wlan\d+$',       # wlan0, wlan1, ... (wireless)
            r'^wlp\d+s\d+$',    # wlp2s0, wlp3s0, ... (wireless PCI)
            r'^wlo\d+$',        # wlo1, wlo2, ... (wireless on-board)
            r'^wwp\d+s\d+$',    # wwp0s20f0u6 (wireless WAN)
        ]
        
        # بررسی با هر یک از پترن‌ها
        for pattern in public_patterns:
            if re.match(pattern, interface_name):
                return True
        
        return False
    
    def detect_network_config_type(self) -> str:
        """تشخیص نوع تنظیمات شبکه در سیستم"""
        # بررسی netplan
        if os.path.exists("/etc/netplan") and os.listdir("/etc/netplan"):
            return "netplan"
        
        # بررسی NetworkManager
        if os.path.exists("/etc/NetworkManager/system-connections"):
            return "networkmanager"
        
        # بررسی interfaces سنتی
        if os.path.exists("/etc/network/interfaces"):
            return "interfaces"
        
        # بررسی systemd-networkd
        if os.path.exists("/etc/systemd/network"):
            return "systemd-networkd"
        
        return "unknown"
    
    def get_interfaces(self) -> List[NetworkInterface]:
        """دریافت لیست اینترفیس‌های شبکه"""
        interfaces = []
        
        try:
            # دریافت اینترفیس‌ها با ip command
            result = subprocess.run(['ip', '-j', 'addr', 'show'], 
                                  capture_output=True, text=True, check=True)
            ip_data = json.loads(result.stdout)
            
            for iface_data in ip_data:
                interface_name = iface_data['ifname']
                
                # فیلتر کردن اینترفیس‌ها - فقط کارت‌های شبکه عمومی
                if not self._is_public_network_interface(interface_name):
                    continue
                
                interface = NetworkInterface(
                    name=iface_data['ifname'],
                    is_active='UP' in iface_data.get('flags', [])
                )
                
                # استخراج IP address
                for addr_info in iface_data.get('addr_info', []):
                    if addr_info.get('family') == 'inet':
                        interface.ip_address = addr_info.get('local')
                        # محاسبه netmask از prefix length
                        prefix_len = addr_info.get('prefixlen', 24)
                        interface.netmask = self._prefix_to_netmask(prefix_len)
                        break
                
                # دریافت gateway
                interface.gateway = self._get_gateway_for_interface(interface.name)
                
                # دریافت DNS servers
                interface.dns_servers = self._get_dns_servers()
                
                # بررسی DHCP
                interface.is_dhcp = self._is_dhcp_enabled(interface.name)
                
                interfaces.append(interface)
        
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"خطا در دریافت اینترفیس‌ها: {str(e)}")
        
        return interfaces
    
    def _prefix_to_netmask(self, prefix_len: int) -> str:
        """تبدیل prefix length به netmask"""
        mask = (0xffffffff >> (32 - prefix_len)) << (32 - prefix_len)
        return f"{(mask >> 24) & 255}.{(mask >> 16) & 255}.{(mask >> 8) & 255}.{mask & 255}"
    
    def _get_gateway_for_interface(self, interface_name: str) -> Optional[str]:
        """دریافت gateway برای یک اینترفیس"""
        try:
            result = subprocess.run(['ip', 'route', 'show', 'dev', interface_name], 
                                  capture_output=True, text=True, check=True)
            for line in result.stdout.splitlines():
                if 'default' in line:
                    parts = line.split()
                    if 'via' in parts:
                        via_index = parts.index('via')
                        if via_index + 1 < len(parts):
                            return parts[via_index + 1]
        except subprocess.CalledProcessError:
            pass
        return None
    
    def _get_dns_servers(self) -> List[str]:
        """دریافت DNS servers"""
        dns_servers = []
        try:
            if os.path.exists("/etc/resolv.conf"):
                with open("/etc/resolv.conf", "r") as f:
                    for line in f:
                        if line.strip().startswith("nameserver"):
                            dns_server = line.strip().split()[1]
                            dns_servers.append(dns_server)
        except Exception:
            pass
        return dns_servers
    
    def _is_dhcp_enabled(self, interface_name: str) -> bool:
        """بررسی فعال بودن DHCP برای یک اینترفیس"""
        if self.config_type == "netplan":
            return self._check_dhcp_netplan(interface_name)
        elif self.config_type == "interfaces":
            return self._check_dhcp_interfaces(interface_name)
        return False
    
    def _check_dhcp_netplan(self, interface_name: str) -> bool:
        """بررسی DHCP در netplan"""
        try:
            netplan_dir = Path("/etc/netplan")
            for config_file in netplan_dir.glob("*.yaml"):
                with open(config_file, "r") as f:
                    config = yaml.safe_load(f)
                    if config and "network" in config:
                        ethernets = config["network"].get("ethernets", {})
                        if interface_name in ethernets:
                            return ethernets[interface_name].get("dhcp4", False)
        except Exception:
            pass
        return False
    
    def _check_dhcp_interfaces(self, interface_name: str) -> bool:
        """بررسی DHCP در /etc/network/interfaces"""
        try:
            with open("/etc/network/interfaces", "r") as f:
                content = f.read()
                pattern = rf"iface\s+{interface_name}\s+inet\s+dhcp"
                return bool(re.search(pattern, content))
        except Exception:
            pass
        return False
    
    def configure_interface(self, interface_name: str, config: NetworkConfig) -> bool:
        """پیکربندی یک اینترفیس شبکه"""
        if self.config_type == "netplan":
            return self._configure_netplan(interface_name, config)
        elif self.config_type == "interfaces":
            return self._configure_interfaces(interface_name, config)
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"نوع پیکربندی {self.config_type} پشتیبانی نمی‌شود"
            )
    
    def _configure_netplan(self, interface_name: str, config: NetworkConfig) -> bool:
        """پیکربندی اینترفیس با netplan"""
        try:
            # ابتدا فایل‌های قبلی این اینترفیس را پاک کن
            self._cleanup_netplan_files(interface_name)
            
            netplan_config = {
                "network": {
                    "version": 2,
                    "ethernets": {
                        interface_name: {}
                    }
                }
            }
            
            if config.is_dhcp:
                netplan_config["network"]["ethernets"][interface_name]["dhcp4"] = True
            else:
                # محاسبه CIDR از IP و netmask
                cidr = self._calculate_cidr(config.ip_address, config.netmask)
                netplan_config["network"]["ethernets"][interface_name]["addresses"] = [cidr]
                
                # استفاده از routes جدید به جای gateway4 deprecated
                if config.gateway:
                    netplan_config["network"]["ethernets"][interface_name]["routes"] = [
                        {
                            "to": "default",
                            "via": config.gateway
                        }
                    ]
                
                if config.dns_servers:
                    netplan_config["network"]["ethernets"][interface_name]["nameservers"] = {
                        "addresses": config.dns_servers
                    }
            
            # نوشتن فایل پیکربندی جدید
            config_file = f"/etc/netplan/01-{interface_name}.yaml"
            with open(config_file, "w") as f:
                yaml.dump(netplan_config, f, default_flow_style=False)
            
            # تنظیم مجوزهای صحیح برای فایل netplan
            try:
                os.chmod(config_file, 0o600)  # فقط root بتواند بخواند/بنویسد
            except Exception:
                pass
            
            # اعتبارسنجی فایل تولید شده
            if not self._validate_netplan_config(config_file):
                print(f"Warning: Generated netplan config might have issues: {config_file}")
            
            # اعمال تنظیمات
            try:
                # در container، systemd ممکن است کار نکند، پس فقط generate کنیم
                if self.is_container:
                    # در container فقط فایل‌ها را تولید کن، سیستم را restart نکن
                    subprocess.run(["netplan", "generate"], check=True)
                    print(f"Generated netplan configuration for {interface_name}")
                    # سپس IP را مستقیماً با ip command اعمال کن
                    self._apply_ip_directly(interface_name, config)
                else:
                    # در host system معمولی از apply استفاده کن
                    subprocess.run(["netplan", "apply"], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                # اگر netplan وجود نداشت یا کار نکرد، IP را مستقیماً اعمال کن
                print(f"Warning: Could not apply netplan configuration for {interface_name}: {e}")
                print(f"Applying IP configuration directly...")
                self._apply_ip_directly(interface_name, config)
            return True
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"خطا در پیکربندی netplan: {str(e)}")
    
    def _cleanup_netplan_files(self, interface_name: str):
        """پاک کردن فایل‌های netplan قبلی مربوط به یک اینترفیس"""
        try:
            netplan_dir = Path("/etc/netplan")
            if not netplan_dir.exists():
                return
            
            # جستجو برای فایل‌هایی که این اینترفیس را تعریف می‌کنند
            for config_file in netplan_dir.glob("*.yaml"):
                try:
                    with open(config_file, "r") as f:
                        config = yaml.safe_load(f)
                        
                    if config and "network" in config:
                        ethernets = config["network"].get("ethernets", {})
                        
                        # اگر این فایل شامل اینترفیس مورد نظر است
                        if interface_name in ethernets:
                            # اگر فایل فقط این اینترفیس را دارد، کل فایل را پاک کن
                            if len(ethernets) == 1:
                                config_file.unlink()
                                print(f"Removed netplan file: {config_file}")
                            else:
                                # اگر فایل چندین اینترفیس دارد، فقط این اینترفیس را حذف کن
                                del ethernets[interface_name]
                                
                                # اگر بعد از حذف، هیچ اینترفیسی نماند، فایل را پاک کن
                                if not ethernets:
                                    config_file.unlink()
                                    print(f"Removed empty netplan file: {config_file}")
                                else:
                                    # فایل به‌روزرسانی شده را ذخیره کن
                                    with open(config_file, "w") as f:
                                        yaml.dump(config, f, default_flow_style=False)
                                    print(f"Updated netplan file: {config_file}")
                
                except Exception as e:
                    # اگر خطایی در خواندن/پردازش فایل رخ داد، ادامه بده
                    print(f"Warning: Could not process netplan file {config_file}: {e}")
                    continue
        
        except Exception as e:
            print(f"Warning: Could not cleanup netplan files: {e}")
            # در صورت خطا در cleanup، ادامه بده
    
    def _validate_netplan_config(self, config_file: str) -> bool:
        """اعتبارسنجی فایل netplan"""
        try:
            # بررسی syntax با netplan
            result = subprocess.run(
                ["netplan", "info", config_file], 
                capture_output=True, 
                text=True, 
                check=False
            )
            return result.returncode == 0
        except Exception:
            # اگر netplan info در دسترس نیست، فقط YAML را بررسی کن
            try:
                with open(config_file, 'r') as f:
                    yaml.safe_load(f)
                return True
            except Exception:
                return False
    
    def _apply_ip_directly(self, interface_name: str, config: NetworkConfig):
        """اعمال مستقیم IP configuration با ip command"""
        try:
            print(f"Applying IP configuration directly to {interface_name}")
            
            # ابتدا اینترفیس را فعال کن
            subprocess.run(["ip", "link", "set", "dev", interface_name, "up"], check=False)
            
            if config.is_dhcp:
                # برای DHCP، سعی کن dhclient استفاده کنی
                try:
                    # ابتدا IP استاتیک قبلی را پاک کن
                    subprocess.run(["ip", "addr", "flush", "dev", interface_name], check=False)
                    # شروع DHCP
                    subprocess.run(["dhclient", interface_name], check=True)
                    print(f"DHCP started for {interface_name}")
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # اگر dhclient نبود، حداقل اینترفیس را فعال کن
                    print(f"Warning: Could not start DHCP for {interface_name}")
            else:
                # برای IP استاتیک
                cidr = self._calculate_cidr(config.ip_address, config.netmask)
                
                # پاک کردن IP قبلی
                subprocess.run(["ip", "addr", "flush", "dev", interface_name], check=False)
                
                # اضافه کردن IP جدید
                subprocess.run(["ip", "addr", "add", cidr, "dev", interface_name], check=True)
                print(f"Added IP {cidr} to {interface_name}")
                
                # اضافه کردن gateway
                if config.gateway:
                    try:
                        # حذف route قبلی
                        subprocess.run(["ip", "route", "del", "default", "dev", interface_name], check=False)
                        # اضافه کردن route جدید
                        subprocess.run(["ip", "route", "add", "default", "via", config.gateway, "dev", interface_name], check=True)
                        print(f"Added gateway {config.gateway} for {interface_name}")
                    except subprocess.CalledProcessError as e:
                        print(f"Warning: Could not set gateway: {e}")
                
                # به‌روزرسانی DNS
                if config.dns_servers:
                    try:
                        self._update_dns_servers(config.dns_servers)
                        print(f"Updated DNS servers: {', '.join(config.dns_servers)}")
                    except Exception as e:
                        print(f"Warning: Could not update DNS: {e}")
        
        except subprocess.CalledProcessError as e:
            print(f"Error applying IP directly: {e}")
            raise
    
    def _update_dns_servers(self, dns_servers: List[str]):
        """به‌روزرسانی DNS servers در /etc/resolv.conf"""
        try:
            # خواندن فایل فعلی
            resolv_conf = "/etc/resolv.conf"
            content = []
            
            if os.path.exists(resolv_conf):
                with open(resolv_conf, 'r') as f:
                    for line in f:
                        # نگه‌داشتن خطوط غیر nameserver
                        if not line.strip().startswith('nameserver'):
                            content.append(line.rstrip())
            
            # اضافه کردن DNS servers جدید
            for dns in dns_servers:
                content.append(f"nameserver {dns}")
            
            # نوشتن فایل جدید
            with open(resolv_conf, 'w') as f:
                f.write('\n'.join(content) + '\n')
        
        except Exception as e:
            print(f"Warning: Could not update resolv.conf: {e}")
    
    def _calculate_cidr(self, ip_address: str, netmask: str) -> str:
        """تبدیل IP address و netmask به فرمت CIDR"""
        try:
            import socket
            import struct
            
            # تبدیل netmask به باینری و شمارش بیت‌های 1
            netmask_int = struct.unpack("!I", socket.inet_aton(netmask))[0]
            prefix_length = bin(netmask_int).count('1')
            
            return f"{ip_address}/{prefix_length}"
        except:
            # در صورت خطا، فرض می‌کنیم /24
            return f"{ip_address}/24"
    
    def _configure_interfaces(self, interface_name: str, config: NetworkConfig) -> bool:
        """پیکربندی اینترفیس با /etc/network/interfaces"""
        try:
            # خواندن فایل کنونی
            interfaces_file = "/etc/network/interfaces"
            if os.path.exists(interfaces_file):
                with open(interfaces_file, "r") as f:
                    content = f.read()
            else:
                content = ""
            
            # حذف پیکربندی قبلی این اینترفیس
            pattern = rf"auto\s+{interface_name}.*?(?=auto\s+\w+|iface\s+\w+|\Z)"
            content = re.sub(pattern, "", content, flags=re.DOTALL)
            
            # اضافه کردن پیکربندی جدید
            new_config = f"\nauto {interface_name}\n"
            
            if config.is_dhcp:
                new_config += f"iface {interface_name} inet dhcp\n"
            else:
                new_config += f"iface {interface_name} inet static\n"
                new_config += f"    address {config.ip_address}\n"
                new_config += f"    netmask {config.netmask}\n"
                
                if config.gateway:
                    new_config += f"    gateway {config.gateway}\n"
                
                if config.dns_servers:
                    new_config += f"    dns-nameservers {' '.join(config.dns_servers)}\n"
            
            content += new_config
            
            # نوشتن فایل
            with open(interfaces_file, "w") as f:
                f.write(content)
            
            # راه‌اندازی مجدد اینترفیس برای interfaces
            try:
                subprocess.run(["ifdown", interface_name], check=False)
                subprocess.run(["ifup", interface_name], check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                # اگر ifup/ifdown کار نکرد، از ip command استفاده کن
                try:
                    subprocess.run(["ip", "link", "set", "dev", interface_name, "down"], check=False)
                    subprocess.run(["ip", "link", "set", "dev", interface_name, "up"], check=True)
                except subprocess.CalledProcessError:
                    print(f"Warning: Could not restart interface {interface_name}")
            
            # اعمال مستقیم IP configuration
            try:
                self._apply_ip_directly(interface_name, config)
            except Exception as e:
                print(f"Warning: Could not apply IP directly: {e}")
            
            return True
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"خطا در پیکربندی interfaces: {str(e)}")
    
    def _calculate_cidr(self, ip_address: str, netmask: str) -> str:
        """محاسبه CIDR notation از IP و netmask"""
        # تبدیل netmask به prefix length
        octets = netmask.split('.')
        binary_str = ''.join([format(int(octet), '08b') for octet in octets])
        prefix_len = binary_str.count('1')
        return f"{ip_address}/{prefix_len}"
    
    def get_hostname(self) -> str:
        """دریافت hostname فعلی سیستم"""
        try:
            # ابتدا hostnamectl را امتحان کن
            result = subprocess.run(['hostnamectl', 'hostname'], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                # اگر hostnamectl وجود نداشت، از hostname استفاده کن
                result = subprocess.run(['hostname'], capture_output=True, text=True, check=True)
                return result.stdout.strip()
            except subprocess.CalledProcessError:
                try:
                    # اگر هیچکدام کار نکرد، از فایل /etc/hostname بخوان
                    if os.path.exists('/etc/hostname'):
                        with open('/etc/hostname', 'r') as f:
                            return f.read().strip()
                    else:
                        return "unknown"
                except Exception:
                    return "unknown"
    
    def set_hostname(self, new_hostname: str) -> bool:
        """تنظیم hostname جدید برای سیستم"""
        try:
            # ابتدا hostnamectl را امتحان کن
            try:
                subprocess.run(['hostnamectl', 'set-hostname', new_hostname], check=True)
                hostname_set_success = True
            except (subprocess.CalledProcessError, FileNotFoundError):
                # اگر hostnamectl وجود نداشت، فقط فایل‌ها را به‌روزرسانی کن
                hostname_set_success = False
            
            # به‌روزرسانی فایل /etc/hostname
            try:
                with open('/etc/hostname', 'w') as f:
                    f.write(new_hostname + '\n')
            except Exception as e:
                if not hostname_set_success:
                    raise HTTPException(status_code=500, detail=f"خطا در نوشتن فایل hostname: {str(e)}")
            
            # به‌روزرسانی فایل /etc/hosts
            try:
                self._update_hosts_file(new_hostname)
            except Exception:
                # در محیط container ممکن است /etc/hosts محدود باشد
                pass
            
            return True
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"خطا در تنظیم hostname: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"خطا در به‌روزرسانی فایل‌های hostname: {str(e)}")
    
    def _update_hosts_file(self, new_hostname: str):
        """به‌روزرسانی فایل /etc/hosts با hostname جدید"""
        try:
            hosts_file = "/etc/hosts"
            if os.path.exists(hosts_file):
                with open(hosts_file, 'r') as f:
                    content = f.read()
                
                # حذف ورودی‌های قبلی hostname
                lines = content.splitlines()
                new_lines = []
                hostname_updated = False
                
                for line in lines:
                    if line.strip().startswith('127.0.1.1'):
                        # به‌روزرسانی خط 127.0.1.1
                        new_lines.append(f"127.0.1.1\t{new_hostname}")
                        hostname_updated = True
                    elif not (line.strip().startswith('127.0.0.1') and 'localhost' in line):
                        # نگه‌داشتن سایر خطوط به جز localhost
                        if not any(old_name in line for old_name in ['127.0.1.1']):
                            new_lines.append(line)
                
                # اگر خط 127.0.1.1 وجود نداشت، اضافه کن
                if not hostname_updated:
                    new_lines.append(f"127.0.1.1\t{new_hostname}")
                
                # اطمینان از وجود localhost
                localhost_exists = any('127.0.0.1' in line and 'localhost' in line for line in new_lines)
                if not localhost_exists:
                    new_lines.insert(0, "127.0.0.1\tlocalhost")
                
                with open(hosts_file, 'w') as f:
                    f.write('\n'.join(new_lines) + '\n')
            else:
                # ایجاد فایل hosts جدید
                with open(hosts_file, 'w') as f:
                    f.write(f"127.0.0.1\tlocalhost\n")
                    f.write(f"127.0.1.1\t{new_hostname}\n")
        
        except Exception as e:
            # در صورت خطا در به‌روزرسانی hosts، ادامه دهیم
            pass

# ایجاد instance از NetworkManager
network_manager = NetworkManager()

@app.get("/", tags=["System Info"])
async def root():
    return {"message": "Linux Network Configuration API", "version": "1.0.0"}

@app.get("/network/config-type", tags=["System Info"])
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

@app.get("/container/status", tags=["System Info"])
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

@app.get("/hostname", tags=["Hostname Management"])
async def get_hostname():
    """دریافت hostname فعلی سیستم"""
    hostname = network_manager.get_hostname()
    return {
        "hostname": hostname,
        "message": f"Hostname فعلی: {hostname}"
    }

@app.post("/hostname", tags=["Hostname Management"])
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

@app.get("/system/info", tags=["System Info"])
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

@app.get("/network/netplan/files", tags=["System Info"])
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

@app.delete("/network/netplan/cleanup/{interface_name}", tags=["Interface Configuration"])
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

@app.post("/network/apply-config", tags=["Interface Configuration"])
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

@app.post("/network/netplan/validate", tags=["System Info"])
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

@app.get("/network/interfaces", response_model=List[NetworkInterface], tags=["Network Interfaces"])
async def get_interfaces():
    """دریافت لیست اینترفیس‌های شبکه عمومی"""
    return network_manager.get_interfaces()

@app.get("/network/interfaces/all", tags=["Network Interfaces"])
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

@app.get("/network/interfaces/{interface_name}", response_model=NetworkInterface, tags=["Network Interfaces"])
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

@app.post("/network/interfaces/{interface_name}/configure", tags=["Interface Configuration"])
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

@app.post("/network/interfaces/{interface_name}/restart", tags=["Interface Configuration"])
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

@app.get("/network/status", tags=["Network Status"])
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

@app.get("/network/dns", tags=["Network Status"])
async def get_dns_servers():
    """دریافت لیست DNS servers فعلی"""
    dns_servers = network_manager._get_dns_servers()
    return {
        "dns_servers": dns_servers,
        "count": len(dns_servers)
    }

@app.get("/network/routes", tags=["Network Status"]) 
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

@app.post("/network/interfaces/{interface_name}/enable", tags=["Interface Configuration"])
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

@app.post("/network/interfaces/{interface_name}/disable", tags=["Interface Configuration"])
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
