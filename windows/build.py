#!/usr/bin/env python3

import argparse
import os
import re
import shutil
import subprocess
import sys
import json

# Handle commandline arguments
parser = argparse.ArgumentParser()
parser.add_argument('--release', action='store_true')
parser.add_argument('--rustup', default=(os.environ['HOMEPATH'] + "/.cargo/bin/rustup.exe"))
parser.add_argument('--wix', default="C:/Program Files (x86)/WiX Toolset v3.11")
args = parser.parse_args()

# Rust toolchain version to use
RUST_TOOLCHAIN = 'stable-i686-pc-windows-gnu'
CARGO = [args.rustup, "run", RUST_TOOLCHAIN, "cargo"]
# Executables to install
TARGET_DIR = "../target/" + ('release' if args.release else 'debug')
EXES = {
    f"{TARGET_DIR}/system76-keyboard-configurator.exe",
}
ICON = "../data/icons/scalable/apps/com.system76.keyboardconfigurator.svg"

DLL_RE = r"(?<==> )(.*\\mingw32)\\bin\\(\S+.dll)"


# Use ntldd to find the mingw dlls required by a .exe
def find_depends(exe):
    if not os.path.exists(exe):
        sys.exit(f"'{exe}' does not exist")
    output = subprocess.check_output(['ntldd.exe', '-R', exe], universal_newlines=True)
    dlls = set()
    mingw_dir = None
    for l in output.splitlines():
        m = re.search(DLL_RE, l, re.IGNORECASE)
        if m:
            dlls.add((m.group(0), m.group(2)))
            mingw_dir = m.group(1)
    return mingw_dir, dlls


# Build application with rustup
cmd = CARGO + ['build']
if args.release:
    cmd.append('--release')
subprocess.check_call(cmd)

# Generate set of all required dlls
dlls = set()
mingw_dir = None
for i in EXES:
    mingw_dir_new, dlls_new = find_depends(i)
    dlls = dlls.union(dlls_new)
    mingw_dir = mingw_dir or mingw_dir_new

# The svg module is loaded at runtime, so it's dependencies are also needed
dlls = dlls.union(find_depends(f"{mingw_dir}/lib/gdk-pixbuf-2.0/2.10.0/loaders/libpixbufloader-svg.dll")[1])

# Generate libraries.wxi
with open('libraries.wxi', 'w') as f:
    f.write("<!-- Generated by build.py -->\n")
    f.write('<Include>\n')

    for _, i in dlls:
        id_ = i.replace('.dll', '').replace('-', '_').replace('+', '')
        f.write(f"    <Component Id='{id_}' Feature='Complete' Guid='*'>\n")
        f.write(f"        <File Name='{i}' Source='out/{i}' />\n")
        f.write(f"    </Component>\n")

    f.write('</Include>\n')

# Copy executables and libraries
if os.path.exists('out'):
    shutil.rmtree('out')
os.mkdir('out')
for i in EXES:
    filename = i.split('/')[-1]
    print(f"Strip {i} -> out/{filename}")
    subprocess.check_call([f"strip.exe", '-o', f"out/{filename}", i])
for src, filename in dlls:
    dest = "out/" + filename
    print(f"Copy {src} -> {dest}")
    shutil.copy(src, 'out')

# Copy additional data
os.mkdir("out/lib")
os.makedirs("out/share/glib-2.0/schemas")
os.makedirs("out/share/icons/hicolor")
for i in ('share/glib-2.0/schemas/org.gtk.Settings.FileChooser.gschema.xml', 'share/icons/hicolor/index.theme', 'lib/p11-kit', 'lib/gdk-pixbuf-2.0'):
    src = mingw_dir + '\\' + i.replace('/', '\\')
    dest = "out/" + i
    print(f"Copy {src} -> {dest}")
    if os.path.isdir(src):
        shutil.copytree(src, dest)
    else:
        shutil.copy(src, dest)
subprocess.check_call(["glib-compile-schemas", "out/share/glib-2.0/schemas"])

# Extract crate version from cargo
meta_str = subprocess.check_output(CARGO + ["metadata", "--format-version", "1", "--no-deps"])
meta = json.loads(meta_str)
package = next(i for i in meta['packages'] if i['name'] == 'system76-keyboard-configurator')
crate_version = package['version']

# Generate Icon
subprocess.check_call(["rsvg-convert", "--width", "256", "--height", "256", "-o", "keyboard-configurator.png", ICON])
subprocess.check_call(["convert", "keyboard-configurator.png", "out/keyboard-configurator.ico"])

# Build .msi
subprocess.check_call([f"{args.wix}/bin/candle.exe", ".\keyboard-configurator.wxs", f"-dcrate_version={crate_version}"])
subprocess.check_call([f"{args.wix}/bin/light.exe", "-ext", "WixUIExtension", ".\keyboard-configurator.wixobj"])
