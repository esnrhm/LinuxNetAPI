from pydantic import BaseModel
from typing import List, Optional

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
