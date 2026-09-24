# SPDX-License-Identifier: GPL-2.0-or-later
"""Markdown Reader 环境自举（Windows，仅标准库）。

流程（run.bat → 本脚本）：
1) 已有 .venv 且 flet 可导入 → 直接启动 main.py；
2) 环境不完整 → 在命令行询问是否自动创建 .venv 并下载安装依赖；
3) 同意后：搜索本机 Python 3.10+ → 建 venv → 修 pip（必要时经 SSRF 校验后
   从 PyPA 官方地址下载 get-pip.py）→ 安装 flet → 校验 → 启动。

用法：python bootstrap.py [--yes] [传给 main.py 的附加参数]
  --yes   跳过询问，直接自动安装（供自动化场景）
"""

import contextlib
import glob
import ipaddress
import json
import os
import re
import shutil
import socket
import string
import subprocess
import sys
import traceback
from pathlib import Path
from urllib.parse import urlparse

MIN_VERSION = (3, 10)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
RUNTIME_DEP = "flet[desktop]>=1.0"   # 桌面运行期显式声明，避免首次启动时联网自装
APP_ENTRY = "main.py"

# 下载主机白名单：get-pip.py 只允许来自 PyPA 官方域
ALLOWED_DOWNLOAD_HOSTS = {"bootstrap.pypa.io", "pypi.org", "files.pythonhosted.org"}

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
LOG: list[str] = []


def report_path() -> Path:
    """报告落点按当前 ROOT 派生：导入期绑定会让测试写到仓库根，覆盖真实报告。"""
    return Path(ROOT) / "environment_report.txt"


def write(message=""):
    text = str(message)
    print(text, flush=True)
    LOG.append(text)
    with contextlib.suppress(OSError):
        report_path().write_text("\n".join(LOG) + "\n", encoding="utf-8")


def run_step(command, timeout=600):
    """以参数列表运行子命令（不经 shell），输出记录到日志。"""
    command = [str(item) for item in command]
    write("$ " + subprocess.list2cmdline(command))
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.stdout:
        write(result.stdout.rstrip())
    return result


def validate_public_https(url: str) -> str:
    """SSRF 防护：仅允许 https 且默认端口、主机在白名单内、解析结果**全部**是公网地址。"""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"仅允许 https 下载地址：{url}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"下载地址端口非法：{url}") from exc
    if port not in (None, 443):
        raise ValueError(f"仅允许默认 https 端口（443）：{url}")
    host = (parsed.hostname or "").lower()
    if not host or host == "localhost" or host.endswith(".local"):
        raise ValueError(f"拒绝受限主机：{host}")
    if host not in ALLOWED_DOWNLOAD_HOSTS:
        raise ValueError(f"主机不在下载白名单内：{host}")
    try:
        addr_infos = socket.getaddrinfo(host, port or 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise ValueError(f"主机解析失败：{host}（{exc}）") from exc
    for info in addr_infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError as exc:
            raise ValueError(f"下载主机解析到非法地址：{host} -> {info[4][0]}") from exc
        if (
            not ip.is_global          # 正向判定：只放行公网（覆盖 CGNAT 等黑名单漏项）
            or ip.is_loopback
            or ip.is_private
            or ip.is_reserved
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or getattr(ip, "is_site_local", False)   # IPv6 site-local（fec0::/10）不在 is_global 覆盖内
        ):
            raise ValueError(f"下载主机解析到受限网络地址：{host} -> {ip}")
    return url


def ask_continue(question: str, assume_yes: bool = False) -> bool:
    """命令行确认：y/yes/是/s 同意；n/no/否 拒绝；回车视为拒绝。"""
    if assume_yes:
        write(f"{question} —— 已通过 --yes 自动确认。")
        return True
    for _ in range(3):
        try:
            answer = input(f"{question} [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if answer in ("y", "yes", "是", "s"):
            return True
        if answer in ("n", "no", "否", ""):
            return False
        write("请输入 y 或 n。")
    return False


# ---------------- Python 解释器搜索 ----------------

def add_path(result, seen, value):
    if not value:
        return
    with contextlib.suppress(OSError, ValueError):
        path = Path(str(value).strip().strip('"')).expanduser()
        if not path.is_file():
            return
        key = os.path.normcase(str(path.resolve()))
        if key not in seen:
            seen.add(key)
            result.append(path)


def registry_pythons():
    """只读枚举系统标准 Python 注册表项（HKCU/HKLM PythonCore）。本项目零注册表写入。"""
    if os.name != "nt":
        return []
    with contextlib.suppress(ImportError):
        import winreg

        found = []
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for base in (r"Software\Python\PythonCore", r"Software\WOW6432Node\Python\PythonCore"):
                with contextlib.suppress(OSError), winreg.OpenKey(root, base) as key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        version_key = winreg.EnumKey(key, index)
                        with contextlib.suppress(OSError):
                            with winreg.OpenKey(root, base + "\\" + version_key + "\\InstallPath") as install:
                                folder, _ = winreg.QueryValueEx(install, None)
                                found.append(str(Path(folder) / "python.exe"))
        return found
    return []


def launcher_pythons():
    py = shutil.which("py")
    if not py:
        return []
    found = []
    for option in ("-0p", "--list-paths"):
        with contextlib.suppress(Exception):
            result = subprocess.run(
                [py, option],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            found.extend(re.findall(r"[A-Za-z]:\\[^\r\n]*?python(?:w)?\.exe", result.stdout, re.IGNORECASE))
    return found


def common_pythons():
    env = os.environ
    patterns = [
        os.path.join(env.get("LOCALAPPDATA", ""), "Programs", "Python", "Python*", "python.exe"),
        os.path.join(env.get("ProgramFiles", r"C:\Program Files"), "Python*", "python.exe"),
        os.path.join(env.get("USERPROFILE", ""), "miniconda3", "python.exe"),
        os.path.join(env.get("USERPROFILE", ""), "anaconda3", "python.exe"),
    ]
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = letter + ":\\"
            if os.path.exists(drive):
                patterns.extend(
                    [drive + r"Python*\python.exe", drive + r"Miniconda*\python.exe"]
                )
    found: list[str] = []
    for pattern in patterns:
        if pattern:
            found.extend(glob.glob(pattern))
    return found


def find_python_files():
    result, seen = [], set()
    add_path(result, seen, sys.executable)
    for variable in ("PYTHON", "VIRTUAL_ENV", "CONDA_PREFIX"):
        value = os.environ.get(variable)
        if variable in ("VIRTUAL_ENV", "CONDA_PREFIX") and value:
            value = str(Path(value) / "python.exe")
        add_path(result, seen, value)
    for command in ("python", "python3"):
        add_path(result, seen, shutil.which(command))
    for path in launcher_pythons() + registry_pythons() + common_pythons():
        add_path(result, seen, path)
    return result


PROBE = r"""
import importlib.util, json, platform, struct, sys

def has(name):
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False

print(json.dumps({
    "exe": sys.executable,
    "version": list(sys.version_info[:3]),
    "version_text": sys.version.split()[0],
    "impl": platform.python_implementation(),
    "bits": struct.calcsize("P") * 8,
    "venv": has("venv"),
    "pip": has("pip"),
    "ensurepip": has("ensurepip")
}))
"""


def probe(path):
    try:
        result = subprocess.run(
            [str(path), "-I", "-c", PROBE],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        for line in reversed(result.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line), ""
        return None, result.stdout.strip()
    except Exception as error:  # noqa: BLE001  # 探针失败仅记录，不中断搜索
        return None, str(error)


def compatible(info):
    if info["impl"] != "CPython":
        return False, "不是 CPython"
    if tuple(info["version"]) < MIN_VERSION:
        return False, f"版本低于 {MIN_VERSION[0]}.{MIN_VERSION[1]}"
    if not info["venv"]:
        return False, "缺少 venv"
    return True, ""


def search_usable_pythons():
    candidates = []
    files = find_python_files()
    write(f"共发现 {len(files)} 个 Python 路径。")
    for path in files:
        info, error = probe(path)
        if not info:
            write(f"[不可用] {path} -> {error}")
            continue
        ok, reason = compatible(info)
        status = "候选" if ok else "跳过"
        write(
            f"[{status}] {info['exe']} | {info['version_text']} | {info['bits']}位"
            f" | pip={info['pip']} | ensurepip={info['ensurepip']}"
            + (f" | {reason}" if reason else "")
        )
        if ok:
            candidates.append((Path(info["exe"]), info))
    # 宽轮子兼容性优先：3.13/3.12/3.11/3.10，其次更新版本
    order = {13: 100, 12: 95, 11: 90, 10: 85, 14: 80, 15: 60}
    candidates.sort(
        key=lambda item: (order.get(item[1]["version"][1], 50), item[1]["bits"], item[1]["version"][2]),
        reverse=True,
    )
    return candidates


# ---------------- venv 与依赖 ----------------

def venv_python():
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _version_at_least(version_text: str, minimum: tuple[int, ...]) -> bool:
    """版本号比较：'0.25.2' vs (1, 0)；不足位数按 0 补齐。"""
    numbers = [int(p) for p in re.findall(r"\d+", version_text)]
    while len(numbers) < len(minimum):
        numbers.append(0)
    return tuple(numbers[: len(minimum)]) >= minimum


def imports_ok(python) -> tuple[bool, str]:
    """检查 flet 是否真的可导入且版本 >= 1.0（只查元数据会把残缺安装误判为可用）。"""
    try:
        result = subprocess.run(
            [str(python), "-I", "-c",
             "import importlib.metadata as m, flet; print('OK', m.version('flet'))"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except Exception as error:  # noqa: BLE001
        return False, str(error)
    out = result.stdout.strip()
    if result.returncode != 0 or "OK" not in out:
        return False, out
    version = out.split("OK", 1)[1].strip()
    if not _version_at_least(version, (1, 0)):
        return False, f"flet {version} 低于要求的 1.0（应用基于 Flet 1.0 API）"
    return True, f"flet {version}"


DEPENDENCY_PROBE = r"""
import importlib
import importlib.metadata as metadata
import json
import sys

report = {"python": sys.version.split()[0]}
try:
    import flet
    version = getattr(flet, "__version__", None) or metadata.version("flet")
    report["flet"] = str(version)
except Exception:
    report["flet"] = None
print(json.dumps(report))
"""


def check_dependencies(python) -> tuple[bool, dict]:
    """在给定解释器中检查 flet，返回 (就绪, 报告字典)。"""
    result = subprocess.run(
        [str(python), "-I", "-c", DEPENDENCY_PROBE],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                report = json.loads(line)
            except json.JSONDecodeError:
                continue
            return bool(report.get("flet")), report
    return False, {}


def report_environment(dep_report: dict) -> None:
    """把环境与依赖检查结果逐项写入日志。"""
    write("环境与依赖检查结果：")
    write("  Python 解释器 : {}".format(dep_report.get("python", "?")))
    version = dep_report.get("flet")
    write("  flet          : {}".format(version if version else "缺失"))


def find_curl() -> str:
    """定位系统 curl.exe：优先 System32 绝对路径，拒绝 PATH 上的相对结果（当前目录劫持）。"""
    candidates = [Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"]
    found = shutil.which("curl")
    if found:
        candidates.append(Path(found))
    for item in candidates:
        if item.is_absolute() and item.is_file():
            return str(item)
    return ""


def download_get_pip(target: Path) -> None:
    """从 PyPA 官方固定地址下载 get-pip.py：先 SSRF 校验，再交 curl（仅 https，且复核落点主机）。"""
    validate_public_https(GET_PIP_URL)
    curl = find_curl()
    if not curl:
        raise RuntimeError("系统缺少 curl.exe（Windows 10 1803+ 自带），无法下载 get-pip.py")
    result = run_step(
        [curl, "-fsSL", "--retry", "3",
         "--proto", "=https", "--proto-redir", "=https",   # 禁止重定向降级到明文 http
         "-w", "%{url_effective}", "-o", str(target), GET_PIP_URL],
        300,
    )
    if result.returncode != 0:
        raise RuntimeError("get-pip.py 下载失败")
    landing = (getattr(result, "stdout", "") or "").strip().splitlines()
    if landing and landing[-1].strip().startswith(("http://", "https://")):
        validate_public_https(landing[-1].strip())        # 重定向后的落点必须仍在白名单内


def install_pip(python) -> None:
    if run_step([python, "-m", "pip", "--version"], 60).returncode == 0:
        return
    write("pip 缺失，先尝试 ensurepip……")
    run_step([python, "-m", "ensurepip", "--upgrade", "--default-pip"], 300)
    if run_step([python, "-m", "pip", "--version"], 60).returncode == 0:
        return
    write("ensurepip 失败，从 PyPA 官方地址下载 get-pip.py……")
    target = ROOT / "get-pip.py"
    try:
        download_get_pip(target)
        if target.stat().st_size < 10000:
            raise RuntimeError("get-pip.py 下载内容异常")
        if run_step([python, target], 600).returncode != 0:
            raise RuntimeError("get-pip.py 执行失败")
    finally:
        with contextlib.suppress(OSError):
            target.unlink()
    if run_step([python, "-m", "pip", "--version"], 60).returncode != 0:
        raise RuntimeError("pip 自动修复失败")


def prepare_with(base_python) -> Path:
    """用指定基础解释器创建 .venv 并安装运行依赖，返回 venv 解释器。

    旧环境先改名保底（``.venv.bak``），新环境建成且校验通过后才删除；
    中途失败则把旧环境放回原位，避免"旧的没了、新的也没建成"。
    """
    backup = VENV.with_name(VENV.name + ".bak")
    had_old = VENV.exists()
    if had_old:
        if backup.exists():
            shutil.rmtree(str(backup), ignore_errors=True)
        shutil.move(str(VENV), str(backup))
    try:
        if run_step([base_python, "-m", "venv", str(VENV)], 300).returncode != 0:
            raise RuntimeError("创建 .venv 失败")
        runtime = venv_python()
        install_pip(runtime)
        run_step([runtime, "-m", "pip", "install", "-U", "pip"], 900)
        if run_step([runtime, "-m", "pip", "install", "-U", RUNTIME_DEP], 1800).returncode != 0:
            raise RuntimeError("安装 flet 失败")
        ok, details = imports_ok(runtime)
        if not ok:
            raise RuntimeError(f"依赖校验失败：{details}")
    except Exception:
        with contextlib.suppress(OSError):       # 回滚：删掉半成品，把旧环境放回去
            if VENV.exists():
                shutil.rmtree(str(VENV), ignore_errors=True)
            if had_old and backup.exists():
                shutil.move(str(backup), str(VENV))
        raise
    if had_old and backup.exists():
        shutil.rmtree(str(backup), ignore_errors=True)
    return runtime


def launch(runtime, extra_args=None) -> int:
    """启动主程序（python main.py），输出回显到控制台。"""
    argv = [str(runtime), APP_ENTRY]
    if extra_args:
        argv.extend(extra_args)
    result = subprocess.run(
        argv,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        print(result.stdout, flush=True)
    return result.returncode


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    assume_yes = "--yes" in argv
    extra_args = [a for a in argv if a != "--yes"]

    write("Markdown Reader 环境检查与依赖检查")
    write(f"项目目录：{ROOT}")

    if not (ROOT / APP_ENTRY).is_file():
        raise FileNotFoundError(f"未找到 {APP_ENTRY}，请保证 bootstrap.py 与 main.py 在同一目录。")

    runtime = venv_python()
    if runtime.is_file():
        ok, details = imports_ok(runtime)
        if ok:
            deps_ok, dep_report = check_dependencies(runtime)
            if deps_ok:
                report_environment(dep_report)
                write("环境与依赖检查通过，直接启动。")
                return launch(runtime, extra_args)
            write("依赖检查发现缺失：")
            report_environment(dep_report)
        else:
            write(f"已有 .venv 依赖不完整：{details}")

    write(f"未检测到可用环境（需要 Python {MIN_VERSION[0]}.{MIN_VERSION[1]}+ 与 flet）。")
    if VENV.exists():
        write("注意：现有 .venv 会先改名为 .venv.bak 保底，新环境校验通过后才删除。")
    question = "是否自动创建 .venv 并下载安装依赖（需联网，约 40MB+）？"
    if not ask_continue(question, assume_yes=assume_yes):
        write(
            "已取消。可手动执行：\n"
            "  python -m venv .venv\n"
            "  .venv\\Scripts\\python -m pip install flet\n"
            "  .venv\\Scripts\\python main.py"
        )
        return 1

    failures = []
    for base_python, _info in search_usable_pythons():
        try:
            write(f"\n尝试使用：{base_python}")
            runtime = prepare_with(base_python)
            write("环境准备完成，正在启动程序。")
            return launch(runtime, extra_args)
        except Exception as error:  # noqa: BLE001  # 单个候选失败后继续尝试下一个
            failures.append(f"{base_python} -> {error}")
            write(f"[失败] {failures[-1]}")

    if not failures:
        raise RuntimeError("没有找到同时具备 Python 3.10+ 与 venv 的完整 CPython。")
    raise RuntimeError("所有 Python 候选均失败：\n" + "\n".join(failures))


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as error:  # 顶层兜底：写入报告后以非零码退出
        write(f"\n启动失败：{error}")
        write(traceback.format_exc())
        write(f"请查看：{report_path()}")
        raise SystemExit(1) from error
