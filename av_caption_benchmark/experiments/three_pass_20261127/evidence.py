import json
from pathlib import Path
import av
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parent
for sf in sorted(ROOT.glob('cases/*/selection.json')):
    case=sf.parent
    with av.open(str(case/'clip.mp4')) as f:
        frames=list(f.decode(video=0))
        pts=[float(x.pts*x.time_base) for x in frames]
    n=12
    canvas=Image.new('RGB',(900,3*145),'white')
    d=ImageDraw.Draw(canvas)
    for j in range(n):
        t=pts[-1]*j/(n-1)
        i=min(range(len(pts)),key=lambda k:abs(t-pts[k]))
        im=frames[i].to_image();im.thumbnail((225,122))
        x=(j%4)*225;y=(j//4)*145
        canvas.paste(im,(x,y));d.text((x,y+123),f'{pts[i]:.3f} s',fill='black')
    canvas.save(case/'frames.jpg',quality=86)
