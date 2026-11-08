[app]

title = FRIDAY

package.name = ai
package.domain = com.friday

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt

version = 1.0

requirements = python3,kivy,requests

orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 35
android.minapi = 26
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

p4a.bootstrap = sdl2

[buildozer]

log_level = 2
warn_on_root = 1
