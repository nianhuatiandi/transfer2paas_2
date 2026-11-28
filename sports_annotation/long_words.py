"""Optional independent word-time evidence for windowed captions (Vosk local recognizer)."""
import json
import wave
from difflib import SequenceMatcher
from pathlib import Path
from .io_utils import file_hash, read_json, write_json

def recognize(wav, model_dir, save):
    signature={"audio_sha256":file_hash(wav),"model":model_dir.name,
               "acoustic_model_sha256":file_hash(model_dir/"am/final.mdl")}
    if save.exists() and read_json(save)["signature"]==signature:
        return read_json(save)["words"]
    from vosk import Model, KaldiRecognizer, SetLogLevel
    SetLogLevel(-1)
    with wave.open(str(wav),"rb") as audio:
        recognizer=KaldiRecognizer(Model(str(model_dir)),audio.getframerate())
        recognizer.SetWords(True)
        words=[]
        while block:=audio.readframes(4000):
            if recognizer.AcceptWaveform(block):
                words.extend(json.loads(recognizer.Result()).get("result",[]))
        words.extend(json.loads(recognizer.FinalResult()).get("result",[]))
    write_json(save,dict(signature=signature,words=words))
    return words

def norm(text):
    return "".join(c.lower() for c in text if c.isalnum())

def anchor(phrase, words, low, high):
    target=norm(phrase)
    if len(target)<2:
        return None
    pool=[w for w in words if w["start"]>=low and w["end"]<=high and norm(w["word"])]
    choices=[]
    for i,first in enumerate(pool):
        candidate=""
        for j in range(i,len(pool)):
            if j>i and pool[j]["start"]-pool[j-1]["end"]>1.5:
                break
            candidate+=norm(pool[j]["word"])
            if len(candidate)>len(target)*1.5+1:
                break
            if len(candidate)<len(target)*.70:
                continue
            matcher=SequenceMatcher(None,target,candidate,autojunk=False)
            blocks=matcher.get_matching_blocks()[:-1]
            if not blocks or blocks[0].a!=0 or blocks[0].b!=0 or blocks[-1].a+blocks[-1].size!=len(target) or blocks[-1].b+blocks[-1].size!=len(candidate):
                continue
            score=matcher.ratio()
            if score < (.99 if len(target)<5 else .78):
                continue
            if any(w.get("conf",1)<.55 for w in (first,pool[j])):
                continue
            choices.append((score,first["start"],pool[j]["end"],candidate))
    if not choices:
        return None
    choices.sort(reverse=True)
    score,a,b,phrase=choices[0]
    if any(s>=score-.04 and (d<=a or c>=b) for s,c,d,_ in choices[1:]):
        return None
    return dict(start=a,end=b,asr_text=phrase,similarity=round(score,3))
