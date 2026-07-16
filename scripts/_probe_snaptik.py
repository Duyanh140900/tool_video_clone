import re
from pathlib import Path

html = Path("work/_snaptik_home.html").read_text(encoding="utf-8")
for m in re.finditer(r"<form[\s\S]{0,1200}?</form>", html, re.I):
    print("FORM:", m.group(0)[:1000])
    print("---")
for m in re.findall(r'src="([^"]+\.js[^"]*)"', html):
    print("js", m)
for m in re.findall(r"['\"](/[a-zA-Z0-9_./-]+\.php)['\"]", html):
    print("php", m)
for m in re.findall(r"fetch\(`([^`]+)`\)", html):
    print("fetch", m)
for m in re.findall(r"action=[\"']([^\"']+)[\"']", html, re.I):
    print("action", m)
