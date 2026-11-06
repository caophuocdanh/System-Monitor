#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tự động cập nhật version trong mã nguồn (client.py, server.py, dashboard.py)
theo định dạng: yy.mmdd.hhMM (hh là định dạng 24 giờ).
Ví dụ: 10:50PM 11/25/2026 => 26.1125.2250

Đồng thời loại bỏ trường version trong config.ini và config.ini.txt
để đảm bảo version được quản lý cố định (hardcoded) trong code.
"""

import os
import sys
import re
import base64
import configparser
from datetime import datetime

XOR_KEY = "SM-Key-2026"


def xor_crypt(data: str, key: str = XOR_KEY) -> str:
    key_len = len(key)
    return "".join(chr(ord(c) ^ ord(key[i % key_len])) for i, c in enumerate(data))


def load_config_data(config_path: str):
    """Đọc config.ini hỗ trợ cả file thường và file mã hóa ENC:"""
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        return config, False

    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    content_stripped = content.strip()
    is_encrypted = content_stripped.startswith("ENC:")

    try:
        if is_encrypted:
            b64_data = content_stripped[4:]
            encrypted_xor = base64.b64decode(b64_data).decode("utf-8")
            decrypted_content = xor_crypt(encrypted_xor)
            config.read_string(decrypted_content)
        else:
            config.read_string(content)
    except Exception as e:
        print(f"[VERSION] Error parsing config file {config_path}: {e}")
        raise

    return config, is_encrypted


def save_config_data(config_path: str, config: configparser.ConfigParser, is_encrypted: bool):
    """Lưu config.ini bảo toàn trạng thái mã hóa ban đầu"""
    import io
    string_io = io.StringIO()
    config.write(string_io)
    plaintext = string_io.getvalue()

    if is_encrypted:
        encrypted_xor = xor_crypt(plaintext)
        b64_data = base64.b64encode(encrypted_xor.encode("utf-8")).decode("utf-8")
        final_content = f"ENC:{b64_data}"
    else:
        final_content = plaintext

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(final_content)


def generate_version_string() -> str:
    """Tạo chuỗi version theo cấu trúc yy.mmdd.hhMM (hh là định dạng 24 giờ)"""
    now = datetime.now()
    return now.strftime("%y.%m%d.%H%M")


def clean_version_from_config(config_path: str):
    """Xóa bỏ các trường version và client_version khỏi file config.ini"""
    if not os.path.exists(config_path):
        return
    try:
        config, is_encrypted = load_config_data(config_path)
        changed = False
        for section in ["server", "client"]:
            if config.has_section(section):
                if config.remove_option(section, "version"):
                    changed = True
                if config.remove_option(section, "client_version"):
                    changed = True
        if changed:
            save_config_data(config_path, config, is_encrypted)
            print(f"[VERSION] Cleaned version keys from: {config_path}")
    except Exception as e:
        print(f"[VERSION] Warning: Failed to clean version from {config_path}: {e}")


def clean_version_from_text_config(config_path: str):
    """Xóa bỏ các dòng version khỏi file text config (vd: config.ini.txt)"""
    if not os.path.exists(config_path):
        return
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = [
            line for line in lines
            if not re.match(r'^\s*(version|client_version)\s*=', line, re.IGNORECASE)
        ]
        if len(new_lines) != len(lines):
            with open(config_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            print(f"[VERSION] Cleaned version lines from text config: {config_path}")
    except Exception as e:
        print(f"[VERSION] Warning: Failed to clean text config {config_path}: {e}")


def update_version_in_file(file_path: str, new_version: str) -> bool:
    """Cập nhật biến __version__ = '...' trong file mã nguồn Python"""
    if not os.path.exists(file_path):
        print(f"[VERSION] File not found: {file_path}")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = r'(__version__\s*=\s*["\'])([^"\']+)(["\'])'
    if not re.search(pattern, content):
        print(f"[VERSION] Error: '__version__' pattern not found in {file_path}")
        return False

    new_content, count = re.subn(pattern, r'\g<1>' + new_version + r'\g<3>', content)
    if count > 0:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"[VERSION] Updated {os.path.basename(file_path)} -> '{new_version}' ({count} occurrence)")
        return True
    return False


def update_all_versions(new_version: str = None):
    req_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(req_dir)

    if not new_version:
        new_version = generate_version_string()

    print(f"[VERSION] Target release version (yy.mmdd.hhMM): {new_version}")

    # 1. Cập nhật version trong các file mã nguồn: client.py, server.py, dashboard.py
    code_files = [
        os.path.join(root_dir, "client.py"),
        os.path.join(root_dir, "server.py"),
        os.path.join(root_dir, "dashboard.py"),
    ]

    success = True
    for file_path in code_files:
        if not update_version_in_file(file_path, new_version):
            success = False

    # 2. Xóa version trong config.ini và config.ini.txt
    for cfg in [
        os.path.join(root_dir, "config.ini"),
        os.path.join(root_dir, "source", "server", "config.ini"),
        os.path.join(root_dir, "source", "client", "config.ini"),
    ]:
        clean_version_from_config(cfg)

    clean_version_from_text_config(os.path.join(root_dir, "config.ini.txt"))

    if not success:
        sys.exit(1)

    print(f"[VERSION] Version update completed successfully for client, server, and dashboard.")
    return new_version


if __name__ == "__main__":
    ver = sys.argv[1] if len(sys.argv) > 1 else None
    update_all_versions(new_version=ver)
