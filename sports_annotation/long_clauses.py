"""Re-listen to clause candidates. Missing speech stays searchable without a fabricated interval."""
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor
import json
from difflib import SequenceMatcher
import re
from .long_video import PROMPTS, ask, reference, wav_slice
from .long_words import anchor, norm

def candidates(text):
    # These are candidate quotes only. All timestamps are obtained from audio.
    parts=[s.strip() for s in re.split(r"(?<=[，,。！？!?；;])|(?<=[.])\s+",text) if norm(s)]
    return parts or [text]

def same_excerpt(primary, extra):
    if not set(primary["sources"]).intersection(extra["sources"]) and primary["actor"]!=extra["actor"]:
        return False
    common=min(primary["end"],extra["end"])-max(primary["start"],extra["start"])
    if common<=.55*min(primary["end"]-primary["start"],extra["end"]-extra["start"]):
        return False
    a,b=norm(primary["text"]),norm(extra["text"])
    match=SequenceMatcher(None,b,a,autojunk=False)
    if match.ratio()>.82:
        return True
    blocks=match.get_matching_blocks()[:-1]
    return (len(b)>=4 and len(a)>len(b) and blocks and blocks[0].a==0 and
            blocks[-1].a+blocks[-1].size==len(b) and sum(v.size for v in blocks)>=.9*len(b) and
            blocks[-1].b+blocks[-1].size-blocks[0].b<=1.3*len(b) and
            primary["start"]-.1<=extra["start"] and extra["end"]<=primary["end"]+.1)

def align(root, full_wav, audio, windows, words, jobs, *, english=False, request=ask):
    boundaries=[w["core"][1] for w in windows]
    batches=[[] for w in windows]
    alternate=[[] for w in windows]
    for e in audio:
        if e["kind"]=="speech":
            idx=min(len(windows)-1,bisect_left(boundaries,(e["start"]+e["end"])/2))
            for j,part in enumerate(candidates(e["text"]),1):
                batches[idx].append((f'{e["id"]}.{j}',e,part))
            main=norm(e["text"])
            seen=set()
            for alt in e.get("alternate_quotes",[]):
                for j,part in enumerate(candidates(alt["text"]),1):
                    s=norm(part)
                    similar=any(SequenceMatcher(None,s,norm(p),autojunk=False).ratio()>=.82 for p in candidates(e["text"]))
                    if s and s not in main and s not in seen and not similar:
                        seen.add(s)
                        key=f'{alt["origin"]}.{j}'
                        alternate[idx].append((key,{**e,"start":alt["start"],"end":alt["end"],"sources":[alt["origin"]]},part))
    def one(batch):
        folder_name,rows=batch
        if not rows:
            return [],[]
        lo=max(0,min(e["start"] for _,e,_ in rows)-1.5)
        hi=min(boundaries[-1],max(e["end"] for _,e,_ in rows)+1.5)
        folder=root/folder_name
        folder.mkdir(exist_ok=True)
        wav=folder/"audio.wav"
        wav_slice(full_wav,wav,lo,hi)
        clues=[dict(id=k, candidate=s, speaker=e["actor"],source=[round(e["start"]-lo,3),round(e["end"]-lo,3)]) for k,e,s in rows]
        template=PROMPTS/("bench/phrases.txt" if english else "clause_evidence.txt")
        clock=f"\nExcerpt length {hi-lo:.3f} seconds.\n" if english else f"\n音频长度 {hi-lo:.3f} 秒。\n"
        msg=template.read_text("utf8")+clock+json.dumps(clues,ensure_ascii=False)
        def check(obj):
            rr=obj.get("items")
            if not isinstance(rr,list) or [r.get("id") for r in rr]!=[q[0] for q in rows]:
                raise ValueError("Keep each given id exactly once in the original order")
            for r in rr:
                cc=r.get("clauses")
                if not isinstance(cc,list) or (not cc and not r.get("note")):
                    raise ValueError("Provide clauses array and explain empty array")
                prev=0
                for c in cc:
                    if english and not re.search(r"[A-Za-z]",str(c.get("english",""))):
                        raise ValueError("Every clause requires an English rendering in english")
                    a,b=float(c["start"]),float(c["end"])
                    if not (max(0,prev-.07)<=a<b<=hi-lo+.10 and a<hi-lo and isinstance(c["text"],str) and norm(c["text"])):
                        raise ValueError(f'{r["id"]}: invalid ordered clause or timestamp (0 to {hi-lo:.3f})')
                    prev=b
        obj=request(folder,"phrases",msg,[reference("audio",wav)],check)
        kept=[]
        missing=[]
        pool=[w for w in words if lo-1<=w["start"] and w["end"]<=hi+1]
        for (k,parent,quote),r in zip(rows,obj["items"]):
            if not r["clauses"]:
                missing.append(dict(probe=k,candidate=quote,parent_sources=parent["sources"],search_span=[lo,hi],reason=r["note"]))
            for c in r["clauses"]:
                a,b=round(lo+float(c["start"]),3),round(min(hi,lo+float(c["end"])),3)
                flags=set(parent["review_flags"])-{"分句边界未解","复听未定位"}
                evidence={"method":"qwen_audio_relisten","qwen_range":[a,b],"candidate":quote,"probe":k}
                word=anchor(c["text"],pool,max(lo,a-1.3),min(hi,b+1.3)) if pool else None
                if word:
                    evidence.update(method="qwen_and_asr",word_match=word)
                    if max(abs(a-word["start"]),abs(b-word["end"]))>.65:
                        flags.add("词时标与复听边界差异超过0.65秒")
                    a,b=word["start"],word["end"]
                elif pool and len(norm(c["text"]))<=2 and b-a<=.65:
                    flags.add("短语未获独立词时标支持")
                if b-a>5.5 or len(candidates(c["text"]))>1 and b-a>3.5:
                    flags.add("仍可能含多个分句")
                kept.append({"actor":parent["actor"],"kind":"speech","layer":parent["layer"],"label":"语音",
                             **({"english":c["english"]} if english else {}),
                             "text":c["text"],"start":a,"end":b,"sources":parent["sources"],
                             "timing_evidence":evidence,"review_flags":sorted(flags)})
        return kept,missing
    kept=[e for e in audio if e["kind"]!="speech"]
    missing=[]
    tasks=[(f"clauses{i:05d}",b) for i,b in enumerate(batches)]+[(f"extra{i:05d}",b) for i,b in enumerate(alternate)]
    with ThreadPoolExecutor(jobs) as pool:
        for found,miss in pool.map(one,tasks):
            unique=[]
            for e in found:
                if "/" in e["timing_evidence"]["probe"]:
                    duplicate=next((v for v in kept if v["kind"]=="speech" and same_excerpt(v,e)),None)
                    if duplicate:
                        duplicate["sources"]=sorted(set(duplicate["sources"]+e["sources"]))
                        continue
                unique.append(e)
            kept.extend(unique)
            missing.extend(miss)
    kept.sort(key=lambda e:(e["start"],e["end"],e["sources"][0]))
    removed=set()
    for i,e in enumerate(kept):
        if i in removed or e["kind"]!="speech":
            continue
        for j in range(i+1,len(kept)):
            b=kept[j]
            if b["start"]>=e["end"]:
                break
            if j in removed or b["kind"]!="speech" or norm(e["text"])!=norm(b["text"]):
                continue
            if min(e["end"],b["end"])-b["start"] < .6*min(e["end"]-e["start"],b["end"]-b["start"]):
                continue
            lo,hi=max(0,e["start"]-.6), min(boundaries[-1],max(e["end"],b["end"])+.6)
            folder=root/f"duplicate_{i}_{j}"
            folder.mkdir(exist_ok=True)
            wav=folder/"audio.wav"
            wav_slice(full_wav,wav,lo,hi)
            msg=("只听录音。两个窗口都在这一时段记下了同一句引语。判断可听见一次发言、两个可区分的声音或两次复述、"
                 "还是无法区分。只返回 JSON，count 为 one、two 或 unclear，evidence 写实际听感。候选引语："+e["text"])
            if english:
                msg='Listen for one utterance, two voices or repetitions, or unresolved evidence. Return {"count":"one|two|unclear","evidence":"English auditory evidence"}. Candidate words: '+e["text"]
            def check_count(x):
                if x.get("count") not in ("one","two","unclear") or not x.get("evidence"):
                    raise ValueError("Return count and evidence")
            decision=request(folder,"duplicates",msg,[reference("audio",wav)],check_count)
            if decision["count"]=="one":
                if b["timing_evidence"]["method"]=="qwen_and_asr" and e["timing_evidence"]["method"]!="qwen_and_asr":
                    e["start"],e["end"],e["timing_evidence"]=b["start"],b["end"],b["timing_evidence"]
                e["sources"]=sorted(set(e["sources"]+b["sources"]))
                e["duplicate_review"]=decision
                removed.add(j)
            elif decision["count"]=="unclear":
                for row in (e,b):
                    row["review_flags"]=sorted(set(row["review_flags"])|{"同句发言次数待核"})
    kept=sorted((e for i,e in enumerate(kept) if i not in removed),key=lambda e:(e["start"],e["end"],e["sources"][0]))
    for i,e in enumerate(kept):
        e["id"]=f"A{i+1:04}"
        if e["kind"]!="speech":
            continue
        for b in kept[i+1:]:
            overlap=min(e["end"],b["end"])-b["start"]
            if b["start"]>=e["end"]:
                break
            if b["kind"]=="speech" and overlap>.15 and (norm(e["text"])==norm(b["text"]) or e["actor"]==b["actor"]):
                for row in (e,b):
                    row["review_flags"]=sorted(set(row["review_flags"])|{"可能为同一说话人重叠，需复听"})
    for miss in missing:
        match=[e["id"] for e in kept if e["kind"]=="speech" and norm(e["text"])==norm(miss["candidate"]) and
               miss["search_span"][0]<=e["start"] and e["end"]<=miss["search_span"][1]]
        if match:
            miss["also_located_as"]=match
    return kept,missing
