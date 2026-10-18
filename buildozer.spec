[app]
title = 多账户管理
package.name = accountmanager
package.domain = org.example.am

source.dir = .
source.include_exts = py,png,jpg,otf,ttf,ttc

version = 1.0.0

requirements = python3,kivy==2.3.0,requests,cryptography

android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.arch = arm64-v8a

# 应用图标（可选）
# icon.filename = icon.png

fullscreen = 0
orientation = portrait

[buildozer]
log_level = 2
warn_on_root = 1
