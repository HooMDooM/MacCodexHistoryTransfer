import json,os
from pathlib import Path

LANGUAGE=os.environ.get('CODEX_TRANSFER_LANGUAGE','ru')
TRANSLATIONS=json.loads(Path(__file__).with_name('translations.json').read_text())

def translate(text):
    if LANGUAGE=='ru':return text
    for source in sorted(TRANSLATIONS,key=len,reverse=True): text=text.replace(source,TRANSLATIONS[source])
    return text
