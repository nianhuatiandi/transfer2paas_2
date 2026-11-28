"""Export timestamped frames from the exact source clips for the case notes."""
import bisect
from pathlib import Path

import av
from PIL import Image, ImageDraw

HERE=Path(__file__).resolve().parent
TIMES={
    'timer':[2.45,2.8,3.25,3.6,4.0,4.16,5.0,7.8,9.6,10.9,11.22,11.64],
    'golf':[7.5,7.85,9.5,9.85,10.02,10.16,10.27,10.46,11.2,12.45,13.0,17.2],
    'apple':[0.1,1.4,2.5,3.9,4.55,6.1,7.4,8.3,10.3,12.8,14.4,16.5],
}


def main():
    for cid,targets in TIMES.items():
        folder=HERE/'cases'/cid
        with av.open(str(folder/'clip.mp4')) as container:
            frames=list(container.decode(video=0))
            times=[float(f.pts*f.time_base) for f in frames]
        out=Image.new('RGB',(1080,3*177),'white')
        draw=ImageDraw.Draw(out)
        for i,t in enumerate(targets):
            j=bisect.bisect_left(times,t)
            ind=min(range(max(0,j-1),min(len(times),j+1)),key=lambda k:abs(times[k]-t))
            im=frames[ind].to_image()
            im.thumbnail((270,152))
            x,y=(i%4)*270,(i//4)*177
            out.paste(im,(x,y))
            draw.text((x+5,y+154),f'{times[ind]:.3f} s',fill='black')
        out.save(folder/'evidence.jpg',quality=88)


if __name__=='__main__':
    main()
