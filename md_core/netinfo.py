# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-2.0-or-later
"""局域网地址探测：纯本地枚举本机网卡 IPv4，不发起任何网络请求。"""

from __future__ import annotations

import contextlib
import ipaddress
import socket


def get_lan_ips() -> list[str]:
    """返回本机局域网 IPv4 列表（私有网段、去重、排除环回）。

    仅通过解析本机主机名获得地址，不向外发送数据包；
    失败时返回空列表（调用方隐藏入口即可）。
    """
    ips: list[str] = []
    seen: set[str] = set()
    with contextlib.suppress(OSError):
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            _append_if_lan(ip, ips, seen)
    return ips


def _append_if_lan(ip: str, ips: list[str], seen: set[str]) -> None:
    with contextlib.suppress(ValueError):
        addr = ipaddress.ip_address(ip)
        if addr.version == 4 and addr.is_private and not addr.is_loopback:
            text = str(addr)
            if text not in seen:
                seen.add(text)
                ips.append(text)
