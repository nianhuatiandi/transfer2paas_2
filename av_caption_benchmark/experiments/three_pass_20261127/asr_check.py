"""Independent English word-time spot check for the two previously noted compound utterances."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import wave

HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--local-dir',type=Path,default=Path(tempfile.gettempdir())/'av_threepass_asr_20261127')
args=p.parse_args()
sys.path.insert(0,str(args.local_dir/'deps'))
from vosk import Model,KaldiRecognizer,SetLogLevel
SetLogLevel(-1)
model=Model(str(args.local_dir/'vosk-model-small-en-us-0.15'))
for cid in ['timer','apple','guitar']:
    folder=HERE/'cases'/cid
    with wave.open(str(folder/'media/audio.wav')) as w:
        rec=KaldiRecognizer(model,w.getframerate());rec.SetWords(True);words=[]
        while buf:=w.readframes(4000):
            if rec.AcceptWaveform(buf):words.extend(json.loads(rec.Result()).get('result',[]))
        words.extend(json.loads(rec.FinalResult()).get('result',[]))
    (folder/'independent_asr.json').write_text(json.dumps({'model':'vosk-model-small-en-us-0.15','words':words},indent=2),encoding='utf8')
    print(cid,[(t['word'],t['start'],t['end']) for t in words],flush=True)
