"""Blind visual fact checks using the original frames, plus a static-image control."""
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageChops, ImageStat
import av
import json
from .bench import ask, english, media, TEMPLATES
from .long_video import reference
from .io_utils import write_json

def inspect_facts(root,src,duration,rows,scopes,jobs,cast):
    buckets=[[] for _ in scopes]
    for row in rows:
        t=(row["start"]+row["end"])/2
        for i,scope in enumerate(scopes):
            if scope["core"][0]<=t<scope["core"][1]:
                buckets[i].append(row)
                break
    def one(task):
        n,items=task
        if not items:
            return
        phases=[{**p,"kind":"phase","actor":e["actor"],"brief":p["label"],"detail":p["label"]+" within "+e["label"]}
                for e in items for p in e.get("phases",[])]
        claims=[*items,*phases]
        folder=root/f"facts{n:05}"
        lo=max(0,min(e["start"] for e in items)-.35)
        hi=min(duration,max(e["end"] for e in items)+.35)
        vis,_=media(folder/"media",src,None,lo,hi)
        times=sorted(set(round(e["start"]+(e["end"]-e["start"])*frac,4) for e in items for frac in (.12,.50,.88)))
        if len(times)>36:
            times=[times[round(i*(len(times)-1)/35)] for i in range(36)]
        extra=[]
        with av.open(str(src)) as c:
            base=(c.start_time or 0)/1e6
            c.seek(max(0,int((base+lo)*1e6)))
            idx=0
            for frame in c.decode(video=0):
                if idx==len(times):break
                t=float(frame.time)-base
                if t<times[idx]-.001:continue
                pic=frame.to_image()
                pic.thumbnail((960,720))
                dst=folder/f"evidence_{idx:04}.jpg"
                pic.save(dst,quality=89)
                extra.append(reference("image",dst,time=max(0,t-lo),index=idx,shot_id="evidence"))
                while idx<len(times) and t>=times[idx]-.001:idx+=1
        # When no pixel change can be measured, keep any claimed movement out of scoring.
        traces={e["id"]:[] for e in items}
        with av.open(vis[0]["path"]) as c:
            for fr in c.decode(video=0):
                t=float(fr.time)+lo
                active=[e for e in items if e["start"]<=t<e["end"]]
                if active:
                    im=fr.to_image().convert("L").resize((160,100))
                    for e in active:traces[e["id"]].append(im)
        def is_static(trace):
            if len(trace)<3:return False
            base=trace[0]
            return all(ImageStat.Stat(ImageChops.difference(base,other)).mean[0]<.35 for other in trace[1:])
        candidates=[{**{k:e[k] for k in ("id","kind","actor","label","brief","detail")},"start":round(e["start"]-lo,4),"end":round(e["end"]-lo,4)} for e in claims]
        def check(obj):
            rr=obj.get("checks",[])
            ids=[r.get("id") for r in rr]
            if not ids or len(set(ids))!=len(ids) or not set(ids).issubset({e["id"] for e in claims}):
                raise ValueError("Return checks keyed to the supplied IDs, with no duplicate or unknown IDs.")
            for r in rr:
                if r.get("verdict") not in ("supported","weaken","unclear","contradicted") or not english(r.get("evidence")):
                    raise ValueError("Use an allowed verdict and English evidence.")
                if r["verdict"]=="weaken" and not all(english(r.get(k)) for k in ("label","brief","detail")):
                    raise ValueError("A weakened event needs complete replacement label, brief and detail.")
        msg=(TEMPLATES/"fact_check.en").read_text("utf8")+f"\nExcerpt duration {hi-lo:.3f} s.\n"+json.dumps(candidates,ensure_ascii=False)
        out=ask(folder,"fact_check",msg,[vis[0],*extra],check)
        results={r["id"]:r for r in out["checks"]}
        missing=[x for x in candidates if x["id"] not in results]
        if missing:
            follow=(TEMPLATES/"fact_check.en").read_text("utf8")+f"\nExcerpt duration {hi-lo:.3f} s. Only check these IDs:\n"+json.dumps(missing)
            remainder=ask(folder,"remaining",follow,[vis[0],*extra],check)
            for r in remainder["checks"]:
                if r["id"] not in results: results[r["id"]]=r
        for claim in claims:
            results.setdefault(claim["id"],dict(id=claim["id"],verdict="unclear",evidence="No matching fact verdict was returned."))
        disputed=[e for e in items if results[e["id"]]["verdict"] in ("contradicted","unclear") and not is_static(traces[e["id"]])]
        if disputed:
            minimal=[{"id":e["id"],"actor":e["actor"],"kind":e["kind"],"core":"visibly speaks" if e["kind"]=="visible_speech" else e["label"],
                      "start":round(e["start"]-lo,4),"end":round(e["end"]-lo,4)} for e in disputed]
            def check_core(obj):
                rr=obj.get("checks",[])
                if sorted(x["id"] for x in rr)!=sorted(e["id"] for e in disputed):
                    raise ValueError("Return each core-action ID once.")
                for x in rr:
                    if x.get("core") not in ("supported","unclear","contradicted") or not english(x.get("evidence")):
                        raise ValueError("Use one core verdict and English evidence per ID.")
                    if x["core"]=="supported" and not all(english(x.get(k)) for k in ("label","brief","detail")):
                        raise ValueError("Rewrite all three English description fields for supported actions.")
            msg=(TEMPLATES/"core_check.en").read_text("utf8")+f"\nExcerpt length {hi-lo:.3f} seconds.\n"+json.dumps(minimal)
            independent=ask(folder,"core_check",msg,[vis[0],*extra],check_core)
            for x in independent["checks"]:
                if x["core"]=="supported":
                    e=next(e for e in disputed if e["id"]==x["id"])
                    results[x["id"]]={**x,"verdict":"weaken","initial_verdict":results[x["id"]]["verdict"]}
                    if e["kind"]=="visible_speech":
                        e["evidence"]=x["evidence"]
                        if x.get("posture") in ("standing","seated","moving","lying","unclear"):
                            e["posture"]=x["posture"]
        for e in items:
            r=results[e["id"]]
            e["fact_verdict"]=r["verdict"]
            e["fact_evidence"]=r["evidence"]
            e["fact_clock_origin"]=lo
            if e["kind"]!="state" and is_static(traces[e["id"]]):
                e["review_flags"].append("No measurable movement in this interval")
            if r["verdict"]=="weaken":
                for key in ("label","brief","detail"):
                    e[key]=r[key]
                # Phases from a more specific discarded claim need their own review.
                e["withheld_phases"]=e["phases"]
                e["phases"]=[]
            elif r["verdict"]!="supported":
                e["review_flags"].append("Muted detail check: "+r["verdict"])
            for p in e["phases"]:
                check=results[p["id"]]
                p["fact_evidence"]=check["evidence"]
                p["review_flags"]=[] if check["verdict"]=="supported" else ["Phase not confirmed in muted review"]
        anonymous=[c for c in candidates if c["id"] in {e["id"] for e in items if e["actor_id"]=="unknown" and e["fact_verdict"] in ("supported","weaken")}]
        if anonymous:
            def valid_cast(obj):
                rr=obj.get("checks",[])
                if sorted(x["id"] for x in rr)!=sorted(x["id"] for x in anonymous):
                    raise ValueError("Return one check per actor query.")
                if any(x.get("actor_id") not in {p["id"] for p in cast}|{"local","none"} or not english(x.get("evidence")) for x in rr):
                    raise ValueError("Choose a roster ID, local or none and provide English evidence.")
            msg=(TEMPLATES/"actor_check.en").read_text("utf8")+"\nRoster: "+json.dumps(cast)+"\nEvents: "+json.dumps(anonymous)
            out=ask(folder,"actor_check",msg,[vis[0],*extra],valid_cast)
            for r in out["checks"]:
                if r["actor_id"]!="none" and english(r.get("appearance")):
                    e=next(e for e in items if e["id"]==r["id"])
                    e["actor_id"]=r["actor_id"] if r["actor_id"]!="local" else "local_"+e["id"]
                    e["actor"]=r["appearance"]
                    e["actor_evidence"]=r["evidence"]
                    e["review_flags"]=[f for f in e["review_flags"] if f!="Actor identity unresolved"]
        speakers=[e for e in items if e["kind"]=="visible_speech" and e["fact_verdict"] in ("supported","weaken")]
        if speakers:
            anchors={"standing":"weight_bearing","seated":"seat_contact","moving":"locomotion","lying":"horizontal_support","unclear":"none"}
            def check_posture(obj):
                rr=obj.get("checks",[])
                if sorted(x["id"] for x in rr)!=sorted(e["id"] for e in speakers):
                    raise ValueError("Return one posture check per ID.")
                for x in rr:
                    if x.get("posture") not in anchors or x.get("anchor")!=anchors[x["posture"]] or not all(english(x.get(k)) for k in ("brief","detail","evidence")):
                        raise ValueError("Use the appropriate support anchor; unclear requires none. Provide English brief, detail and evidence.")
            minimal=[{"id":e["id"],"actor":e["actor"],"start":round(e["start"]-lo,4),"end":round(e["end"]-lo,4)} for e in speakers]
            msg=(TEMPLATES/"posture.en").read_text("utf8")+"\n"+json.dumps(minimal)
            postures=ask(folder,"posture",msg,[vis[0],*extra],check_posture)["checks"]
            for x in postures:
                e=next(e for e in speakers if e["id"]==x["id"])
                e.update(posture=x["posture"],posture_evidence=x["evidence"],brief=x["brief"],detail=x["detail"])
        write_json(folder/"decisions.json",{"checks":list(results.values())})
    with ThreadPoolExecutor(jobs) as ex:
        list(ex.map(one,enumerate(buckets)))
