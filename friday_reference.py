#!/usr/bin/env python3
"""
F.R.I.D.A.Y. - Termux AI assistant powered by Google Gemini.
Voice + Telegram (works with screen off) + phone control + persistent memory.
"""
import os, sys, json, time, re, shutil, subprocess, threading, difflib, datetime
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(BASE, "config.json")
MEM_PATH = os.path.join(BASE, "memory.json")
LOCK = threading.Lock()

# ---------------------------------------------------------------- config
DEFAULT_CFG = {
    "gemini_api_key": "",
    "model": "gemini-2.5-flash",
    "user_name": "Boss",
    "wake_word": "friday",
    "shell": "auto",                 # auto | root | adb
    "adb_serial": "localhost:5555",
    "unlock": {
        "method": "pin",             # pin | pattern
        "pin": "0000",
        "pattern": [1, 2, 3, 6, 9],  # grid 1..9 (left->right, top->bottom)
        "grid_x": [0.25, 0.50, 0.75],
        "grid_y": [0.55, 0.67, 0.79],
        "passphrase": ""             # agar set hai to command mein ye word hona chahiye
    },
    "telegram_token": "",
    "telegram_chat_id": "",
    "tts_lang": "hi",
    "low_battery": 15
}

def load_cfg():
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    if os.path.exists(CFG_PATH):
        with open(CFG_PATH) as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    cfg["gemini_api_key"] = os.environ.get("GEMINI_API_KEY", cfg["gemini_api_key"])
    return cfg

CFG = load_cfg()

# ---------------------------------------------------------------- memory (brain)
def load_mem():
    if os.path.exists(MEM_PATH):
        try:
            with open(MEM_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {"facts": [], "history": []}

def save_mem(m):
    with open(MEM_PATH, "w") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- shell helpers
def run(args, timeout=20):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))

def priv(cmd):
    """Run a command with shell/root privileges (needed for input events)."""
    mode = CFG["shell"]
    if mode == "auto":
        mode = "root" if shutil.which("su") else "adb"
    if mode == "root":
        return run(["su", "-c", cmd])
    return run(["adb", "-s", CFG["adb_serial"], "shell", cmd])

def screen_size():
    out = priv("wm size").stdout
    m = re.search(r"(\d+)x(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 2400)

# ---------------------------------------------------------------- voice io
def speak(text):
    if not text:
        return
    print(f"\n[FRIDAY] {text}")
    run(["termux-tts-speak", "-l", CFG["tts_lang"], "-p", "1.1", text], timeout=60)

def listen():
    r = run(["termux-speech-to-text"], timeout=30)
    return (r.stdout or "").strip()

# ---------------------------------------------------------------- phone actions
APPS = {
    "whatsapp": "com.whatsapp", "instagram": "com.instagram.android",
    "youtube": "com.google.android.youtube", "chrome": "com.android.chrome",
    "camera": "com.android.camera", "settings": "com.android.settings",
    "maps": "com.google.android.apps.maps", "gmail": "com.google.android.gm",
    "spotify": "com.spotify.music", "telegram": "org.telegram.messenger",
    "phonepe": "com.phonepe.app", "gpay": "com.google.android.apps.nbu.paisa.user",
}

def battery():
    r = run(["termux-battery-status"])
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"percentage": -1, "status": "UNKNOWN"}

def find_contact(name):
    r = run(["termux-contact-list"], timeout=30)
    try:
        contacts = json.loads(r.stdout)
    except Exception:
        return None
    names = {c["name"].lower(): c for c in contacts if c.get("name")}
    hit = difflib.get_close_matches(name.lower(), names.keys(), n=1, cutoff=0.5)
    return names[hit[0]]["number"] if hit else None

def resolve_number(target):
    digits = re.sub(r"[^\d+]", "", target)
    if len(re.sub(r"\D", "", digits)) >= 6:
        return digits
    return find_contact(target)

def unlock_phone():
    u = CFG["unlock"]
    w, h = screen_size()
    priv("input keyevent 224")                        # wake
    time.sleep(0.6)
    priv(f"input swipe {w//2} {int(h*0.85)} {w//2} {int(h*0.30)} 300")
    time.sleep(0.7)
    if u["method"] == "pin":
        priv(f"input text {u['pin']}")
        priv("input keyevent 66")
    else:
        pts = []
        for n in u["pattern"]:
            i = n - 1
            pts.append((int(w * u["grid_x"][i % 3]), int(h * u["grid_y"][i // 3])))
        cmds = [f"input motionevent DOWN {pts[0][0]} {pts[0][1]}"]
        for x, y in pts[1:]:
            cmds.append(f"input motionevent MOVE {x} {y}")
        cmds.append(f"input motionevent UP {pts[-1][0]} {pts[-1][1]}")
        priv(" ; sleep 0.08 ; ".join(cmds))
    return "Phone unlock kar diya."

def do_action(a, original):
    t = a.get("type")
    try:
        if t == "open_youtube":
            q = a.get("query", "")
            url = ("https://www.youtube.com/results?search_query=" + requests.utils.quote(q)) if q else "https://www.youtube.com"
            r = run(["am", "start", "-a", "android.intent.action.VIEW", "-d", url, "com.google.android.youtube"])
            if r.returncode != 0:
                run(["termux-open-url", url])
        elif t == "open_url":
            run(["termux-open-url", a["url"]])
        elif t == "open_app":
            pkg = APPS.get(a.get("name", "").lower(), a.get("name", ""))
            priv(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
        elif t == "call":
            num = resolve_number(a.get("target", ""))
            if not num:
                return "Number nahi mila."
            run(["termux-telephony-call", num])
        elif t == "sms":
            num = resolve_number(a.get("target", ""))
            if not num:
                return "Contact nahi mila."
            run(["termux-sms-send", "-n", num, a.get("text", "")])
        elif t == "unlock":
            p = CFG["unlock"].get("passphrase", "")
            if p and p.lower() not in original.lower():
                return "Unlock ke liye passphrase chahiye."
            return unlock_phone()
        elif t == "lock":
            priv("input keyevent 223")
        elif t == "flashlight":
            run(["termux-torch", "on" if a.get("on", True) else "off"])
        elif t == "volume":
            run(["termux-volume", "music", str(a.get("level", 8))])
        elif t == "brightness":
            run(["termux-brightness", str(a.get("level", 128))])
        elif t == "battery":
            b = battery()
            return f"Battery {b['percentage']} percent, {b['status']}."
        elif t == "location":
            r = run(["termux-location", "-p", "network"], timeout=30)
            j = json.loads(r.stdout)
            return f"Lat {j['latitude']:.4f}, Lon {j['longitude']:.4f}."
        elif t == "notify":
            run(["termux-notification", "-t", "FRIDAY", "-c", a.get("text", "")])
        elif t == "vibrate":
            run(["termux-vibrate", "-d", "300"])
    except Exception as e:
        return f"Action fail: {t} ({e})"
    return ""

# ---------------------------------------------------------------- gemini brain
SYSTEM = """You are F.R.I.D.A.Y., the personal AI of __USER__, modelled on Tony Stark's assistant.
Personality: calm, loyal, witty, light sarcasm, extremely competent. Reply in Hinglish (Hindi in Roman script mixed with English) unless the user speaks pure English. Address the user as "__USER__".
Your "say" is spoken aloud: max 2 short sentences, no markdown, no emojis.
You control the user's Android phone. Respond ONLY with JSON:
{"say": "...", "actions": [ ... ], "remember": ["short fact to store permanently", ...]}
Action objects (use only when the user asks):
 {"type":"open_youtube","query":"..."}   {"type":"open_app","name":"whatsapp"}
 {"type":"open_url","url":"https://..."} {"type":"call","target":"name or number"}
 {"type":"sms","target":"name or number","text":"..."}
 {"type":"unlock"} {"type":"lock"} {"type":"flashlight","on":true}
 {"type":"volume","level":0-15} {"type":"brightness","level":0-255}
 {"type":"battery"} {"type":"location"} {"type":"notify","text":"..."} {"type":"vibrate"}
If no action is needed, return "actions": []. "remember" only for durable personal facts/preferences.
Never claim to have done something you have no action for.
Context now: __NOW__ | Battery: __BAT__%
Known facts about the user:
__FACTS__
"""

def ask_gemini(history, mem):
    b = battery()
    sys_prompt = (SYSTEM.replace("__USER__", CFG["user_name"])
                  .replace("__NOW__", datetime.datetime.now().strftime("%A %d %B %Y, %I:%M %p"))
                  .replace("__BAT__", str(b.get("percentage")))
                  .replace("__FACTS__", "\n".join("- " + f for f in mem["facts"]) or "(none yet)"))
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{CFG['model']}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": sys_prompt}]},
        "contents": history,
        "generationConfig": {"temperature": 0.8, "responseMimeType": "application/json"},
    }
    r = requests.post(url, headers={"x-goog-api-key": CFG["gemini_api_key"]}, json=body, timeout=40)
    r.raise_for_status()
    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    try:
        return json.loads(txt)
    except Exception:
        return {"say": txt, "actions": [], "remember": []}

def handle(text, source="voice"):
    with LOCK:
        mem = load_mem()
        hist = mem["history"][-16:] + [{"role": "user", "parts": [{"text": text}]}]
        try:
            data = ask_gemini(hist, mem)
        except Exception as e:
            return f"Brain se connection nahi ho paya: {e}"
        say = data.get("say", "")
        for a in data.get("actions", []) or []:
            extra = do_action(a, text)
            if extra:
                say = (say + " " + extra).strip()
        for fact in data.get("remember", []) or []:
            if fact and fact not in mem["facts"]:
                mem["facts"].append(fact)
        mem["history"] += [{"role": "user", "parts": [{"text": text}]},
                           {"role": "model", "parts": [{"text": json.dumps({"say": say, "actions": [], "remember": []}, ensure_ascii=False)}]}]
        mem["history"] = mem["history"][-40:]
        save_mem(mem)
        return say

# ---------------------------------------------------------------- telegram (screen-off remote)
def tg_send(text):
    t, c = CFG.get("telegram_token"), CFG.get("telegram_chat_id")
    if t and c:
        try:
            requests.post(f"https://api.telegram.org/bot{t}/sendMessage",
                          json={"chat_id": c, "text": text}, timeout=15)
        except Exception:
            pass

def tg_loop():
    token = CFG["telegram_token"]
    offset = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                             params={"timeout": 25, "offset": offset}, timeout=35).json()
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                m = u.get("message") or {}
                if str(m.get("chat", {}).get("id")) != str(CFG["telegram_chat_id"]):
                    continue          # sirf tumhari chat allowed
                if m.get("text"):
                    tg_send(handle(m["text"], "telegram"))
        except Exception:
            time.sleep(5)

# ---------------------------------------------------------------- background watchers
def battery_watch():
    warned = False
    while True:
        b = battery()
        p, st = b.get("percentage", 100), b.get("status", "")
        if 0 <= p <= CFG["low_battery"] and st != "CHARGING" and not warned:
            msg = f"{CFG['user_name']}, battery {p} percent reh gayi hai. Charger lagao."
            speak(msg); tg_send(msg); warned = True
        if p > CFG["low_battery"] + 5:
            warned = False
        time.sleep(90)

# ---------------------------------------------------------------- main
def main():
    if not CFG["gemini_api_key"]:
        sys.exit("config.json mein gemini_api_key daalo ya GEMINI_API_KEY set karo.")
    text_mode = "--text" in sys.argv
    run(["termux-wake-lock"])
    hour = datetime.datetime.now().hour
    greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    if text_mode:
        print(f"[FRIDAY] {greet} {CFG['user_name']}. Online hoon.")
    else:
        speak(f"{greet} {CFG['user_name']}. FRIDAY online hai. Kya karna hai?")
    threading.Thread(target=battery_watch, daemon=True).start()
    if CFG.get("telegram_token") and CFG.get("telegram_chat_id"):
        threading.Thread(target=tg_loop, daemon=True).start()
        tg_send("FRIDAY online. Screen off ho tab bhi yahin se command do.")

    wake = CFG["wake_word"].lower()
    active_until = 0
    while True:
        try:
            if text_mode:
                text = input("\nYou> ").strip()
                if text in ("exit", "quit"):
                    break
                print("[FRIDAY]", handle(text, "text"))
                continue
            heard = listen()
            if not heard:
                continue
            low = heard.lower()
            now = time.time()
            if wake in low:
                active_until = now + 40
                heard = re.sub(wake, "", heard, flags=re.I).strip(" ,.")
                if not heard:
                    speak("Ji, bolo.")
                    continue
            elif now > active_until:
                continue
            if any(w in low for w in ("band ho ja", "shutdown friday", "go to sleep")):
                speak("Theek hai. Sleep mode.")
                break
            speak(handle(heard, "voice"))
            active_until = time.time() + 40
        except KeyboardInterrupt:
            break
        except Exception as e:
            print("error:", e)
            time.sleep(2)

if __name__ == "__main__":
    main()
