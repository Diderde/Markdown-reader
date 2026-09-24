# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-2.0-or-later
"""md_core.netinfo 局域网探测的单元测试（纯本地，不发网络包）。"""

from __future__ import annotations

from md_core import netinfo


def _fake_resolver(entries):
    def resolver(hostname):
        return (hostname, [], entries)

    return resolver


class TestGetLanIps:
    def test_filters_to_private_ipv4(self, monkeypatch):
        monkeypatch.setattr(
            netinfo.socket,
            "gethostbyname_ex",
            _fake_resolver(["192.168.1.100", "8.8.8.8", "127.0.0.1", "fe80::1", "10.0.0.5"]),
        )
        assert netinfo.get_lan_ips() == ["192.168.1.100", "10.0.0.5"]

    def test_deduplicates(self, monkeypatch):
        monkeypatch.setattr(
            netinfo.socket,
            "gethostbyname_ex",
            _fake_resolver(["192.168.1.2", "192.168.1.2"]),
        )
        assert netinfo.get_lan_ips() == ["192.168.1.2"]

    def test_hostname_failure_returns_empty(self, monkeypatch):
        def boom(hostname):
            raise OSError("dns")

        monkeypatch.setattr(netinfo.socket, "gethostbyname_ex", boom)
        assert netinfo.get_lan_ips() == []

    def test_real_enumeration_returns_private_only(self):
        """真实网卡枚举：不联网，只断言结果（若有）全是私有 IPv4。"""
        import ipaddress

        for ip in netinfo.get_lan_ips():
            addr = ipaddress.ip_address(ip)
            assert addr.version == 4 and addr.is_private and not addr.is_loopback
