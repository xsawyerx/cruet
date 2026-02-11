"""Build configuration for cruet C extension."""
import os
import platform
import subprocess
import sys
from setuptools import setup, Extension

# Compiler flags
extra_compile_args = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Wno-unused-parameter"]
extra_link_args = []
include_dirs = ["src/_cruet"]
define_macros = []
libraries = []
library_dirs = []

if platform.system() == "Darwin":
    extra_compile_args.append("-Wno-missing-field-initializers")
elif platform.system() == "Linux":
    define_macros.append(("_GNU_SOURCE", "1"))


def detect_libevent():
    """Try to detect libevent2. Returns True if found."""
    # Try pkg-config first
    try:
        cflags = subprocess.check_output(
            ["pkg-config", "--cflags", "libevent"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        libs = subprocess.check_output(
            ["pkg-config", "--libs", "libevent"],
            stderr=subprocess.DEVNULL
        ).decode().strip()

        for flag in cflags.split():
            if flag.startswith("-I"):
                include_dirs.append(flag[2:])
        for flag in libs.split():
            if flag.startswith("-L"):
                library_dirs.append(flag[2:])
            elif flag.startswith("-l"):
                libraries.append(flag[2:])
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fall back to common paths
    search_includes = [
        "/opt/homebrew/include",
        "/usr/local/include",
        "/usr/include",
    ]
    search_libs = [
        "/opt/homebrew/lib",
        "/usr/local/lib",
        "/usr/lib",
    ]

    found_include = None
    for d in search_includes:
        if os.path.isfile(os.path.join(d, "event2", "event.h")):
            found_include = d
            break

    found_lib = None
    for d in search_libs:
        for ext in ("dylib", "so", "a"):
            if os.path.isfile(os.path.join(d, f"libevent.{ext}")):
                found_lib = d
                break
        if found_lib:
            break

    if found_include and found_lib:
        include_dirs.append(found_include)
        library_dirs.append(found_lib)
        libraries.append("event")
        return True

    return False


has_libevent = detect_libevent()

if has_libevent:
    define_macros.append(("CRUET_HAS_LIBEVENT", "1"))
    print("** libevent2 found — building with async server support", file=sys.stderr)
else:
    print("** libevent2 not found — async server will not be available", file=sys.stderr)


# Collect all .c source files
def collect_sources():
    sources = []
    src_root = os.path.join("src", "_cruet")
    for dirpath, dirnames, filenames in os.walk(src_root):
        for fn in filenames:
            if fn.endswith(".c"):
                # Skip io_loop.c if libevent is not available
                if fn == "io_loop.c" and not has_libevent:
                    continue
                sources.append(os.path.join(dirpath, fn))
    return sources


_cruet_ext = Extension(
    name="cruet._cruet",
    sources=collect_sources(),
    include_dirs=include_dirs,
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
    define_macros=define_macros,
    libraries=libraries,
    library_dirs=library_dirs,
)

setup(
    ext_modules=[_cruet_ext],
)
