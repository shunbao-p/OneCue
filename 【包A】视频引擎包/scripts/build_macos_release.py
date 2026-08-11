#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the auditable, unsigned Package A macOS arm64 distribution.

The script is intentionally standard-library-only. It downloads only assets in
``macos-runtime-lock.json``, verifies SHA-256 before extraction, builds the GPL
FFmpeg stack without ``--enable-nonfree``, archives exact source inputs, and
labels the result unsigned/unnotarized unless a later credentialed release step
is performed.
"""

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent
LOCK_FILE = SCRIPT_DIR / "macos-runtime-lock.json"


class BuildError(RuntimeError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_lock(path=LOCK_FILE):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("target") != "aarch64-apple-darwin":
        raise BuildError("运行时锁 schema/target 不受支持")
    configuration = " ".join(data.get("ffmpeg_configure", []))
    for forbidden in data.get("forbidden_configure", []):
        if forbidden in configuration:
            raise BuildError("FFmpeg 锁包含禁止配置：%s" % forbidden)
    for required in ("--enable-gpl", "--enable-libx264", "--enable-libass", "--enable-zlib"):
        if required not in configuration:
            raise BuildError("FFmpeg 锁缺少配置：%s" % required)
    return data


def _download(item, cache, offline=False):
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / item["asset"]
    if destination.is_file() and sha256(destination) == item["sha256"]:
        return destination
    if destination.exists():
        destination.unlink()
    if offline:
        raise BuildError("离线缓存缺失或哈希错误：%s" % destination)
    partial = destination.with_name(destination.name + ".part-%d" % os.getpid())
    try:
        request = urllib.request.Request(item["url"], headers={"User-Agent": "PackageA-Phase4-Builder/1"})
        with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        actual = sha256(partial)
        if actual != item["sha256"]:
            raise BuildError("下载哈希不匹配：%s expected=%s actual=%s" % (item["asset"], item["sha256"], actual))
        os.replace(str(partial), str(destination))
    finally:
        if partial.exists():
            partial.unlink()
    return destination


def _safe_extract(archive, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(str(archive), "r:*") as bundle:
        members = bundle.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            try:
                target.relative_to(destination)
            except ValueError:
                raise BuildError("归档路径越界：%s" % member.name)
            if member.issym() or member.islnk():
                link_target = (target.parent / member.linkname).resolve()
                try:
                    link_target.relative_to(destination)
                except ValueError:
                    raise BuildError("归档链接越界：%s -> %s" % (member.name, member.linkname))
        bundle.extractall(str(destination), members=members)


def _single_source_root(destination):
    entries = [item for item in Path(destination).iterdir() if item.name != "__MACOSX"]
    if len(entries) != 1 or not entries[0].is_dir():
        raise BuildError("源码归档必须包含唯一顶层目录：%s" % destination)
    return entries[0]


def _run(argv, cwd, env, log, check=True):
    argv = [str(item) for item in argv]
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as output:
        output.write("\n$ %s\n" % json.dumps(argv, ensure_ascii=False))
        output.flush()
        result = subprocess.run(argv, cwd=str(cwd), env=env, stdout=output, stderr=subprocess.STDOUT, check=False)
        output.write("[returncode=%d]\n" % result.returncode)
    if check and result.returncode:
        raise BuildError("命令失败（%s），详见 %s" % (argv[0], log))
    return result


def _configure_make(source, arguments, env, jobs, log):
    _run([source / "configure"] + list(arguments), source, env, log)
    _run(["make", "-j%d" % jobs], source, env, log)
    _run(["make", "install"], source, env, log)


def _prepare_sources(lock, cache, work, offline):
    source_archives = {}
    for item in lock["ffmpeg_sources"]:
        archive = _download(item, cache, offline)
        target = work / "sources" / item["name"]
        if target.exists():
            shutil.rmtree(target)
        _safe_extract(archive, target)
        source_archives[item["name"]] = (archive, _single_source_root(target), item)
    return source_archives


def _prepare_python(lock, cache, work, offline):
    archive = _download(lock["python"], cache, offline)
    destination = work / "python-asset"
    if destination.exists():
        shutil.rmtree(destination)
    _safe_extract(archive, destination)
    runtime = destination / "python"
    executable = runtime / "bin" / "python3"
    if not executable.is_file():
        raise BuildError("Python 资产缺少 bin/python3")
    return archive, runtime, executable


def _prepare_build_tools(lock, cache, work, python, offline, log):
    wheels = [_download(item, cache, offline) for item in lock["build_python_packages"]]
    venv = work / "build-venv"
    if venv.exists():
        shutil.rmtree(venv)
    env = os.environ.copy()
    _run([python, "-m", "venv", venv], work, env, log)
    pip = venv / "bin" / "python"
    _run([pip, "-m", "pip", "install", "--no-index"] + wheels, work, env, log)
    return venv


def build_ffmpeg(lock, sources, prefix, venv, work, jobs, log):
    prefix.mkdir(parents=True, exist_ok=True)
    minimum = lock["minimum_macos"]
    common_flags = "-O2 -arch arm64 -mmacosx-version-min=%s" % minimum
    env = os.environ.copy()
    env.update({
        "PATH": "%s:%s:%s" % (venv / "bin", prefix / "bin", env.get("PATH", "")),
        "MACOSX_DEPLOYMENT_TARGET": minimum,
        "CFLAGS": common_flags,
        "CXXFLAGS": common_flags,
        "CPPFLAGS": "-I%s" % (prefix / "include"),
        "LDFLAGS": "-L%s -arch arm64 -mmacosx-version-min=%s" % (prefix / "lib", minimum),
        "PKG_CONFIG_PATH": "%s:%s" % (prefix / "lib" / "pkgconfig", prefix / "share" / "pkgconfig"),
        "PKG_CONFIG_LIBDIR": "%s:%s" % (prefix / "lib" / "pkgconfig", prefix / "share" / "pkgconfig"),
    })

    _configure_make(sources["pkgconf"][1], [
        "--prefix=%s" % prefix, "--disable-shared", "--enable-static",
    ], env, jobs, log)
    pkgconf = prefix / "bin" / "pkgconf"
    if not pkgconf.is_file():
        raise BuildError("pkgconf 构建未生成可执行文件")
    pkg_config = prefix / "bin" / "pkg-config"
    if not pkg_config.exists():
        pkg_config.symlink_to(pkgconf.name)
    env["PKG_CONFIG"] = str(pkg_config)

    _configure_make(sources["freetype"][1], [
        "--prefix=%s" % prefix, "--disable-shared", "--enable-static",
        "--without-bzip2", "--without-png", "--without-harfbuzz",
    ], env, jobs, log)
    _configure_make(sources["fribidi"][1], [
        "--prefix=%s" % prefix, "--disable-shared", "--enable-static", "--disable-docs",
    ], env, jobs, log)

    harfbuzz_source = sources["harfbuzz"][1]
    harfbuzz_build = work / "build-harfbuzz"
    if harfbuzz_build.exists():
        shutil.rmtree(harfbuzz_build)
    _run([
        venv / "bin" / "meson", "setup", harfbuzz_build, harfbuzz_source,
        "--prefix", prefix, "--buildtype=release", "--default-library=static", "--wrap-mode=nodownload",
        "-Dtests=disabled", "-Ddocs=disabled", "-Dutilities=disabled",
        "-Dintrospection=disabled", "-Dglib=disabled", "-Dgobject=disabled",
        "-Dcairo=disabled", "-Dicu=disabled", "-Dfreetype=enabled",
    ], work, env, log)
    _run([venv / "bin" / "meson", "compile", "-C", harfbuzz_build, "-j", str(jobs)], work, env, log)
    _run([venv / "bin" / "meson", "install", "-C", harfbuzz_build], work, env, log)

    _configure_make(sources["libass"][1], [
        "--prefix=%s" % prefix, "--disable-shared", "--enable-static", "--disable-fontconfig",
    ], env, jobs, log)
    _configure_make(sources["x264"][1], [
        "--prefix=%s" % prefix, "--host=aarch64-apple-darwin", "--enable-static",
        "--disable-cli", "--disable-opencl",
    ], env, jobs, log)

    ffmpeg = sources["ffmpeg"][1]
    configure = [
        ffmpeg / "configure", "--prefix=%s" % prefix,
        "--extra-cflags=%s" % env["CPPFLAGS"],
        "--extra-ldflags=%s" % env["LDFLAGS"],
    ] + list(lock["ffmpeg_configure"])
    _run(configure, ffmpeg, env, log)
    _run(["make", "-j%d" % jobs], ffmpeg, env, log)
    _run(["make", "install"], ffmpeg, env, log)
    for tool in (prefix / "bin" / "ffmpeg", prefix / "bin" / "ffprobe"):
        if not tool.is_file():
            raise BuildError("FFmpeg 构建缺少 %s" % tool.name)
    return env


def _copy_file(source, destination, mode=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source), str(destination))
    if mode is not None:
        destination.chmod(mode)


def _copy_release_application(destination, python_runtime, prefix):
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for name in (
        "①开始使用.command",
        "②连接语音引擎.command",
        "macOS使用与构建说明.md",
        "使用手册.txt",
        "先看我.txt",
    ):
        mode = 0o755 if name.endswith(".command") else 0o644
        _copy_file(PACKAGE_ROOT / name, destination / name, mode)
    if (PACKAGE_ROOT / "示范素材").is_dir():
        shutil.copytree(PACKAGE_ROOT / "示范素材", destination / "示范素材")
    for name in ("我的素材", "成片"):
        (destination / name).mkdir()

    program = destination / "程序文件"
    for name in (
        "paths.py",
        "platform_support.py",
        "diag.py",
        "mac_launcher.py",
        "connect_dots.py",
        "dots_control.py",
    ):
        _copy_file(PACKAGE_ROOT / "程序文件" / name, program / name, 0o644)
    (program / "config.ini").write_text(
        "[server]\nport = 8787\n\n[dots]\nroot =\nport = 7860\n",
        encoding="utf-8",
    )
    shutil.copytree(PACKAGE_ROOT / "程序文件" / "引擎", program / "引擎", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    website = program / "网站"
    website.mkdir(parents=True)
    for name in ("kt_web.py", "dots_synth.py", "index.html"):
        _copy_file(PACKAGE_ROOT / "程序文件" / "网站" / name, website / name, 0o644)
    shutil.copytree(PACKAGE_ROOT / "程序文件" / "fonts", program / "fonts")
    shutil.copytree(python_runtime, program / "runtime", symlinks=True)
    (program / "bin").mkdir(parents=True)
    for name in ("ffmpeg", "ffprobe"):
        _copy_file(prefix / "bin" / name, program / "bin" / name, 0o755)
    for name in ("临时文件", "日志"):
        (program / name).mkdir()
    return destination


def _copy_license(source, candidates, destination):
    for candidate in candidates:
        path = source / candidate
        if path.is_file():
            _copy_file(path, destination, 0o644)
            return
    raise BuildError("未找到许可证：%s (%s)" % (source, candidates))


def _write_notices(package, lock, sources):
    info = package / "程序文件" / "发布信息"
    licenses = info / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    _copy_license(sources["ffmpeg"][1], ["COPYING.GPLv2"], licenses / "FFmpeg-GPL-2.0.txt")
    _copy_license(sources["x264"][1], ["COPYING"], licenses / "x264-GPL-2.0.txt")
    _copy_license(sources["libass"][1], ["COPYING"], licenses / "libass-ISC.txt")
    _copy_license(sources["freetype"][1], ["LICENSE.TXT", "docs/FTL.TXT"], licenses / "FreeType.txt")
    _copy_license(sources["fribidi"][1], ["COPYING"], licenses / "FriBidi-LGPL-2.1.txt")
    _copy_license(sources["harfbuzz"][1], ["COPYING"], licenses / "HarfBuzz.txt")
    _copy_license(sources["pkgconf"][1], ["COPYING"], licenses / "pkgconf-ISC.txt")
    python_license = package / "程序文件" / "runtime" / "lib" / "python3.13" / "LICENSE.txt"
    if python_license.is_file():
        _copy_file(python_license, licenses / "Python-3.13.txt", 0o644)
    notices = [
        "# 第三方组件与分发说明",
        "",
        "此本地验收构建包含独立 FFmpeg/ffprobe 可执行文件。因启用 GPL 的 libx264，",
        "该 FFmpeg 构建按 GPL-2.0-or-later 处理；未启用 `--enable-nonfree` 或 libfdk-aac。",
        "精确源码归档、SHA-256、版本和构建参数位于同构建 ID 的 sources.zip 与 manifest.json。",
        "这不是法律意见；正式分发前应由发布方完成许可证与专利合规复核。",
        "",
        "Python 运行时来自 astral-sh/python-build-standalone；运行时内保留 CPython 与 vendored 组件许可证。",
        "包内 jieba 0.42.1 使用 MIT 许可证（Copyright 2013 Sun Junyi）。",
        "",
        "## 锁定组件",
        "",
    ]
    for item in [lock["python"]] + lock["ffmpeg_sources"]:
        notices.append("- %s %s — %s — `%s`" % (
            item.get("name") or item.get("project"), item.get("version"), item.get("license"), item.get("sha256")
        ))
    (info / "THIRD_PARTY_NOTICES.md").write_text("\n".join(notices) + "\n", encoding="utf-8")


def _tool_output(argv):
    result = subprocess.run([str(item) for item in argv], capture_output=True, text=True, check=False)
    if result.returncode:
        raise BuildError("产物验证失败：%s\n%s" % (argv, result.stderr[-2000:]))
    return result.stdout


def _file_manifest(root, excluded=()):
    excluded = {Path(item).resolve() for item in excluded}
    rows = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        if path.resolve() in excluded:
            continue
        rows.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size, "sha256": sha256(path)})
    return rows


def _verify_product(package, lock):
    python = package / "程序文件" / "runtime" / "bin" / "python3"
    ffmpeg = package / "程序文件" / "bin" / "ffmpeg"
    ffprobe = package / "程序文件" / "bin" / "ffprobe"
    python_text = _tool_output([python, "-B", "-c", "import platform,sys;print(platform.python_version());print(platform.machine());print(sys.executable)"])
    ffmpeg_text = _tool_output([ffmpeg, "-hide_banner", "-version"])
    filters = _tool_output([ffmpeg, "-hide_banner", "-filters"])
    encoders = _tool_output([ffmpeg, "-hide_banner", "-encoders"])
    ffprobe_text = _tool_output([ffprobe, "-hide_banner", "-version"])
    if "arm64" not in python_text:
        raise BuildError("发布 Python 不是 arm64")
    for required, text in (
        ("subtitles", filters), ("libx264", encoders), (" aac ", " " + encoders + " "),
        (" png ", " " + encoders + " "),
    ):
        if required not in text:
            raise BuildError("发布 FFmpeg 缺少能力：%s" % required.strip())
    if "--enable-nonfree" in ffmpeg_text or "--enable-gpl" not in ffmpeg_text:
        raise BuildError("发布 FFmpeg 许可配置不符合锁")
    return {
        "python": python_text.splitlines(),
        "ffmpeg": ffmpeg_text.splitlines()[0],
        "ffprobe": ffprobe_text.splitlines()[0],
        "ffmpeg_sha256": sha256(ffmpeg),
        "ffprobe_sha256": sha256(ffprobe),
        "runtime_python_sha256": sha256(python.resolve()),
        "command_mode": oct((package / "①开始使用.command").stat().st_mode & 0o777),
    }


def _zip_tree(root, output, epoch):
    output.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.fromtimestamp(epoch, tz=timezone.utc)
    zip_time = (max(1980, timestamp.year), timestamp.month, timestamp.day, timestamp.hour, timestamp.minute, timestamp.second)
    temporary = output.with_name(output.name + ".part")
    with zipfile.ZipFile(str(temporary), "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root.parent).as_posix()
            if path.is_dir():
                continue
            info = zipfile.ZipInfo(relative, zip_time)
            mode = path.stat().st_mode & 0o777
            info.external_attr = ((stat.S_IFREG | mode) << 16)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    os.replace(str(temporary), str(output))


def _source_zip(cache, lock, output, epoch):
    staging = output.parent / (output.stem + "-staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for item in lock["ffmpeg_sources"]:
        _copy_file(cache / item["asset"], staging / item["asset"], 0o644)
    _copy_file(LOCK_FILE, staging / LOCK_FILE.name, 0o644)
    _copy_file(Path(__file__), staging / Path(__file__).name, 0o644)
    _zip_tree(staging, output, epoch)
    shutil.rmtree(staging)


def build(args):
    lock = load_lock(args.lock)
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise BuildError("构建必须在 Apple Silicon macOS 上执行；检测到 %s/%s" % (platform.system(), platform.machine()))
    work = Path(args.work_dir).expanduser().resolve()
    cache = Path(args.cache_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    log = work / "build.log"
    log.write_text("Package A Phase 4 build\n", encoding="utf-8")

    python_archive, python_runtime, python = _prepare_python(lock, cache, work, args.offline)
    venv = _prepare_build_tools(lock, cache, work, python, args.offline, log)
    sources = _prepare_sources(lock, cache, work, args.offline)
    prefix = work / "prefix"
    if prefix.exists():
        shutil.rmtree(prefix)
    build_ffmpeg(lock, sources, prefix, venv, work, args.jobs, log)

    build_id = "package-a-macos-arm64-python%s-ffmpeg%s" % (lock["python"]["version"], sources["ffmpeg"][2]["version"])
    package = _copy_release_application(work / "release" / "【包A】视频引擎包", python_runtime, prefix)
    _write_notices(package, lock, sources)
    verification = _verify_product(package, lock)
    manifest = {
        "schema_version": 1,
        "build_id": build_id,
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target": lock["target"],
        "minimum_macos": lock["minimum_macos"],
        "signature": "unsigned-unnotarized-local-validation",
        "notarization": "not-submitted-no-credentials",
        "python_asset": {"name": python_archive.name, "sha256": sha256(python_archive)},
        "verification": verification,
        "source_lock_sha256": sha256(args.lock),
        "files": [],
    }
    manifest_path = package / "程序文件" / "发布信息" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["files"] = _file_manifest(package, excluded=(manifest_path,))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    product_zip = output_dir / (build_id + "-unsigned-unnotarized.zip")
    sources_zip = output_dir / (build_id + "-sources.zip")
    _zip_tree(package, product_zip, int(lock["source_date_epoch"]))
    _source_zip(cache, lock, sources_zip, int(lock["source_date_epoch"]))
    report = {
        "result": "pass",
        "build_id": build_id,
        "product": str(product_zip),
        "product_sha256": sha256(product_zip),
        "sources": str(sources_zip),
        "sources_sha256": sha256(sources_zip),
        "manifest": str(manifest_path),
        "build_log": str(log),
        "signature": manifest["signature"],
        "notarization": manifest["notarization"],
        "verification": verification,
    }
    report_path = output_dir / (build_id + "-build-report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def _parser():
    parser = argparse.ArgumentParser(description="构建包 A macOS arm64 本地验收发布包")
    parser.add_argument("--lock", type=Path, default=LOCK_FILE)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=max(1, os.cpu_count() or 1))
    parser.add_argument("--offline", action="store_true")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        build(args)
        return 0
    except Exception as exc:
        print("构建失败：%s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
