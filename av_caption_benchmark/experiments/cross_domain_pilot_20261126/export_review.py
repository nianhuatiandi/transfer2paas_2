"""Export candidate labels, visible-span intersections and local review pages."""
import hashlib
import json
import math
import re
from collections import Counter
from html import escape
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_text('utf8'))
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),'utf8')
def show(value):
    if value is None:return '未给出'
    return value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
def rpair(value,duration):
    if isinstance(value,str):
        m=re.fullmatch(r'\s*[\[(]\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*[\])]\s*',value)
        if m:value=list(map(float,m.groups()))
    if not (isinstance(value,(list,tuple)) and len(value)==2 and all(type(x) in (int,float) and math.isfinite(x) for x in value)):return None
    a,b=value
    if 0<=a<=b<=duration+0.001:return [round(a,6),round(min(b,duration),6)]
    return None

def visual_details(evidence, duration):
    items = evidence if isinstance(evidence, list) else [evidence]
    for item in items:
        if not item:
            continue
        if not isinstance(item, dict):
            yield None, show(item)
            continue
        note = next((item[k] for k in ('note', 'visual', 'desc', 'cue') if item.get(k)), None)
        if note is None:
            yield None, show(item)
            continue
        when = item.get('time_point', item.get('time', item.get('time_window_sec')))
        span = rpair(when, duration)
        if span:
            yield span[0], f'{span[0]:g}–{span[1]:g} 秒　{note}'
        elif type(when) in (int, float) and 0 <= when <= duration:
            yield when, f'{when:g} 秒　{note}'
        else:
            yield None, str(note)

def playback_button(time):
    if time is None:
        return ''
    return f'<button data-start="{time}">▶ {time:.2f} s</button> '

def attach_action_details(folder, visual_stage, facts, clip_hash):
    directory = folder / 'stages/visual_action_details'
    metadata = directory / 'metadata.json'
    if not metadata.exists() or visual_stage != 'visual_v2':
        return False
    meta = read(metadata)
    if meta.get('status') != 'complete':
        return False
    provenance = read(directory / 'request.json')['provenance']
    visual_file = folder / 'stages' / visual_stage / 'result.json'
    result = directory / 'result.json'
    if (provenance['clip_sha256'] != clip_hash or
            provenance['visual_result_sha256'] != hashlib.sha256(visual_file.read_bytes()).hexdigest() or
            meta['result_sha256'] != hashlib.sha256(result.read_bytes()).hexdigest()):
        raise ValueError(f'Action detail checkpoint does not match the source in {folder.name}')
    by_id = {row['id']: row for row in read(result)['action_details']}
    for fact in facts:
        if fact.get('level') == 'L2' and fact.get('kind') == 'action':
            row = by_id[fact['id']]
            fact.update(action_detail=row['action_detail'], detail_frame_indices=row['frame_indices'],
                        detail_review_note=row['review_note'])
    return True

def rbounds(r,d):
    raw=r.get('boundary_ranges')
    if not isinstance(raw,dict):return None
    a,b=rpair(raw.get('start'),d),rpair(raw.get('end'),d)
    nom=rpair(r.get('instance_range'),d)
    if a and b and nom and a[0]<=nom[0]<=a[1] and b[0]<=nom[1]<=b[1]:return a,b
    return None
def union(ranges):
    merged=[]
    for a,b in sorted(ranges):
        if merged and a<=merged[-1][1]:
            merged[-1][1]=max(b,merged[-1][1])
        else:merged.append([a,b])
    return merged
def av_edges(actions,sounds,duration,warnings):
    out=[]
    for a in actions:
        nom=rpair(a.get('instance_range'),duration)
        spans=a.get('visible_spans')
        if not isinstance(spans,list):spans=[]
        valid=[rpair(s,duration) for s in spans]
        if None in valid or not valid or not nom or any(s[0]<nom[0]-.001 or s[1]>nom[1]+.001 for s in valid if s):
            warnings.append(a['id']+' 可见子段或名义端点待确认，未参与关系计算。');continue
        spans=union(valid)
        for snd in sounds:
            if snd.get('intermittent_envelope_only'):continue
            sr=rpair(snd.get('instance_range'),duration)
            if not sr:continue
            overlaps=[]
            for x,y in spans:
                start=max(x,sr[0]);end=min(y,sr[1])
                if start<end:overlaps.append([start,end])
            peak=snd.get('peak_time')
            if sr[0]==sr[1]:peak=sr[0]
            hit=type(peak) in (int,float) and sr[0]<=peak<=sr[1] and any(x<=peak<y for x,y in spans)
            ba,bs=rbounds(a,duration),rbounds(snd,duration)
            if ba and bs and spans==[nom]:
                margin=min(ba[1][0],bs[1][0])-max(ba[0][1],bs[0][1])
                possible=min(ba[1][1],bs[1][1])>max(ba[0][0],bs[0][0])
                status='给定边界范围内均重叠' if margin>0 else '边界待审'
            else:
                possible=False;status='仅名义区间'
            if not overlaps and not hit and not possible:continue
            out.append(dict(visual_id=a['id'],audio_id=snd['id'],audio_layer=snd.get('layer'),audio_type=snd.get('type'),intersections=overlaps,
                            peak_in_visible_span=peak if hit else None,status=status,nominal=bool(overlaps or hit),derived=True))
    return out
def main():
    summary=[]
    for folder in sorted((ROOT/'cases').iterdir()):
        if not (folder/'source.json').exists():continue
        src=read(folder/'source.json');m=read(folder/'media/manifest.json');duration=m['duration']; warnings=[]
        def stage(name,empty):
            path=folder/'stages'/name/'result.json';return read(path) if path.exists() else empty
        attempted=src.get('disposition')=='extra_rejected_audio'
        vname='visual' if attempted else 'visual_v2';aname='audio' if attempted else 'audio_v2'
        visual=stage(vname,{});audio=stage(aname,{})
        first=stage('visual',{});sounds=audio.get('audio_events',[]);facts=visual.get('facts',[])
        has_action_details = attach_action_details(folder, vname, facts, m['source_sha256'])
        actions=[a for a in facts if a.get('kind')=='action' and a.get('level')=='L2' and a.get('certainty')!='unresolved' and a.get('polarity')!='negated']
        raw_audio=audio
        alignment=stage('audio_sentences',{})
        aligned_by_parent={}
        for sentence in alignment.get('sentences',[]):
            key=sentence['id'].rsplit('.',1)[0]
            aligned_by_parent.setdefault(key,[]).append(sentence)
        effective_sounds=[]
        for event in sounds:
            matches=aligned_by_parent.get(event['id'],[])
            if matches:
                for item in matches:
                    data={**event,**item,'parent_audio_id':event['id'],'claim':'逐句复听定位','evidence_time':None,'confidence':None}
                    data['boundary_ranges']=item.get('boundary_ranges')
                    if not item.get('instance_range'):warnings.append(item['id']+' 逐句复听无法定位，保留文本，不参与求交。')
                    effective_sounds.append(data)
            else:
                data=dict(event)
                if data.get('type')=='sfx' and re.search('多次|数次|两声|几声|间歇|断续|穿插',str(data.get('claim') or '')):
                    data['intermittent_envelope_only']=True
                    warnings.append(data['id']+' 将若干短音合成一段，包络内可能有空隙；保留事件，排除该包络产生的边。')
                effective_sounds.append(data)
        sounds=effective_sounds
        if audio:audio={**audio,'audio_events':sounds}
        ids={r['id'] for r in facts}
        def label(r):
            return r.get('claim') or r.get('description') or r.get('transcript') or r.get('sound_description') or '只输出了类别，缺听感描述'
        for r in facts+sounds:
            if not rpair(r.get('instance_range'),duration) and not isinstance(r.get('time_point'),(int,float)):warnings.append(r['id']+' 缺有效名义区间。')
            if r in sounds and not r.get('transcript') and not (r.get('claim') or r.get('description') or r.get('sound_description')):warnings.append(r['id']+' 缺声音听感或描述。')
            if r in facts and any(p not in ids for p in (r.get('parent_ids') or [])):warnings.append(r['id']+' 存在未解析父项。')
            if r in sounds and r.get('type')=='speech' and re.search(r'[?？。!]\s*[^\s"”]',str(r.get('transcript',''))):
                warnings.append(r['id']+' 同一声段含句末标点及后续文字，需复听句界。')
        edges=av_edges(actions,sounds,duration,warnings)
        if attempted:warnings+=['原音频请求 HTTP 400，服务端返回 data_inspection_failed；没有该条音频伪标注。']
        if not attempted and not (audio and visual):warnings+=['缺失至少一个独立阶段的结果。']
        if '抽查备注' in src:warnings.extend(src['抽查备注'])
        if not any(r.get('level')=='L3' and r.get('kind')=='motion' for r in facts):warnings+=['本次未输出 L3 部位运动，需按画面判定是否有漏项。']
        obj=dict(source=src,model='qwen3.8-omni-flash',human_verified=False,duration_seconds=duration,shot_candidates=m['shots'],
                 timestamped_frames=len(m['frames']),stages=dict(visual=vname,audio=aname),visual=visual,audio=audio,original_audio_events=raw_audio.get('audio_events',[]),sentence_alignment=alignment,temporal_edges=edges,warnings=warnings)
        if has_action_details:
            obj['stages']['action_details'] = 'visual_action_details'
        write(folder/'annotations.json',obj)
        get_first=lambda f:list(a for a in f.get('facts',[]) if a.get('kind')=='action' and a.get('level')=='L2' and a.get('certainty')!='unresolved' and a.get('polarity')!='negated')
        row=dict(id=src['id'],benchmark=src['benchmark'],domain=src['domain'],window=src['source_window_seconds'],duration=duration,
                 T=len(m['frames']),first_L2=len(get_first(first)),L2=len(actions),L3=sum(r.get('kind')=='motion' and r.get('level')=='L3' for r in facts),audio=len(sounds),
                 edges=sum(e['nominal'] for e in edges),foreground=sum(e['nominal'] and e['audio_layer']=='foreground' for e in edges),
                 bounded=sum(e['status']=='给定边界范围内均重叠' for e in edges),complete=bool(visual and audio),extra=attempted or src.get('disposition')=='extra_cut_control',supplement=src.get('disposition'))
        summary.append(row)
        parts=[];plain=[src['benchmark']+' ｜ '+src['domain'],src['original_id']+' ｜ 原片窗口 '+show(src['source_window_seconds'])+' 秒','机器伪 GT，等待人工复核；以下时间相对裁片起点。','使用原音频逐句复听的样本保留父声段与修订记录（见 annotations.json）；持续声与动作的时间交集不判定声源。']
        frame_times = {frame['index']: frame['time'] for frame in m['frames']}
        def section(title,rows,details=None):
            plain.extend(['',title])
            markup=[]
            for index,(t,line) in enumerate(rows):
                plain.append(line)
                item=playback_button(t)+escape(line)
                if details is not None:
                    fact = facts[index]
                    if 'action_detail' in fact:
                        description = fact['action_detail'] or '画面不足以确认此候选动作。'
                        plain.append('  动作详述　' + description)
                        item += '<div><strong>动作详述</strong>　' + escape(description) + '</div>'
                        if fact['detail_review_note']:
                            note = '详述待核　' + fact['detail_review_note']
                            plain.append('  ' + note)
                            item += '<div>' + escape(note) + '</div>'
                        times = [frame_times[i] for i in fact['detail_frame_indices']]
                        if times:
                            plain.append('  详述参考帧　' + '、'.join(f'{t:.3f} 秒' for t in times))
                            item += '<div>详述参考帧　' + ''.join(playback_button(t) for t in times) + '</div>'
                    lines=details[index] or [(None, '模型未给出动作细节。')]
                    plain.append('  模型描述的画面细节')
                    plain.extend('    '+note for _,note in lines)
                    notes=''.join('<li>'+playback_button(at)+escape(note)+'</li>' for at,note in lines)
                    item+='<div>模型描述的画面细节</div><ul>'+notes+'</ul>'
                markup.append('<li>'+item+'</li>')
            if not rows:plain.append('无输出')
            parts.append('<h2>'+escape(title)+'</h2><ul>'+(''.join(markup) or '<li>无输出</li>')+'</ul>')
        def timed(r,line):
            t=rpair(r.get('instance_range'),duration)
            return (t[0] if t else None,r['id']+'  '+show(r.get('instance_range'))+' 秒  '+line)
        section('视觉 · 全部分层事实',[timed(r,show(r.get('level'))+' / '+show(r.get('kind'))+' ｜ '+show(r.get('actor'))+' ｜ '+str(label(r))) for r in facts],
                [list(visual_details(r.get('evidence'),duration)) for r in facts])
        section('声音 · 原语逐字稿与可听事件',[timed(r,show(r.get('type'))+' / '+show(r.get('layer'))+' ｜ '+show(r.get('speaker_id'))+' ｜ '+str(r.get('transcript') or label(r))) for r in sounds])
        amap={r['id']:r['claim'] for r in actions}; smap={r['id']:r for r in sounds}
        section('L2 动作与声音 · 按可见子段求交',[((e['intersections'][0][0] if e['intersections'] else e['peak_in_visible_span']),
                e['visual_id']+' × '+e['audio_id']+' ｜ '+show(e['intersections'])+' ｜ '+e['status']+' ｜ '+str(amap[e['visual_id']])+' × '+str(smap[e['audio_id']].get('transcript') or label(smap[e['audio_id']]))) for e in edges])
        section('待审与覆盖',[(None,line) for line in warnings]+[(None,show(line)) for line in visual.get('residual',[]) or []]+[(None,show(line)) for line in audio.get('unresolved',[]) or []])
        (folder/'人工审阅.txt').write_text('\n'.join(plain),'utf-8-sig')
        (folder/'审阅.html').write_text('<!doctype html><meta charset=utf-8><title>'+escape(src['domain'])+'</title>'+STYLE+'<a href="../../试标总览.html">返回总览</a><h1>'+escape(src['domain'])+'</h1><p>'+escape(' ｜ '.join(plain[:3]))+'</p><video id="v" src="clip.mp4" controls preload="metadata"></video>'+''.join(parts)+"""<script>document.addEventListener('click',function(e){if(e.target.dataset.start){let v=document.getElementById('v');v.currentTime=Number(e.target.dataset.start);v.play();}});</script>""",'utf8')
    write(ROOT/'summary.json',summary)
    rows=''.join('<tr><td><a href="cases/'+quote(r['id'])+'/审阅.html">'+escape(r['domain'])+'</a></td><td>'+escape(r['benchmark'])+'</td>'+''.join('<td>'+str(v)+'</td>' for v in [r['window'],r['first_L2'],r['L2'],r['L3'],r['audio'],r['edges'],r['bounded'],'额外失败样本' if r['supplement']=='extra_rejected_audio' else '额外切镜对照' if r['extra'] else '双通道返回' if r['complete'] else '未完成'])+'</tr>' for r in summary)
    (ROOT/'试标总览.html').write_text('<!doctype html><meta charset=utf-8><title>跨领域伪 GT 试标</title>'+STYLE+'<h1>跨领域视听伪 GT 试标</h1><p>点击样本名称打开裁片、逐字稿、动作与可定位的交集。<a href="实验记录.txt">实验记录及人工抽查</a></p><p>窗口使用原片秒数，审阅页使用裁片秒数。L2 为功能动作实例，L3 为部位运动。模型提出的时间只用于定位；“范围内重叠”仅表示模型自己给出的边界支持同期。边数包含前景和背景。正式抽样包括四个 benchmark 各两条，以及两个自有运动片段；另列两条切镜对照与一次音频被接口拒绝的 UGC 尝试。</p><table><tr>'+''.join('<th>'+s+'</th>' for s in ['样本','来源','原片窗口','首轮 L2','复跑 L2','L3','声段','名义边','范围内重叠','状态'])+'</tr>'+rows+'</table>','utf8')
STYLE='<style>body{max-width:1150px;margin:30px auto;padding:0 20px;font:16px/1.6 system-ui;color:#183b42}video{width:min(100%,680px);max-height:44vh;background:#202020}td,th{padding:.4em .65em;border-bottom:1px solid #ccc;text-align:left}table{border-collapse:collapse}li{margin:.32em 0}button{cursor:pointer}h2{font-size:1.2em}a{color:#056d78}</style>'
if __name__=='__main__':main()
