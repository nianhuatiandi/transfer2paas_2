"""Estimate background-image displacement from original sampled frames, per shot."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def gray(path):
    img=cv2.imdecode(np.fromfile(str(path),dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
    if img is None: raise ValueError("Unreadable frame: "+str(path))
    return cv2.resize(img,(480,round(img.shape[0]*480/img.shape[1])))


def pair(first,second,dt):
    feature=cv2.goodFeaturesToTrack(first,400,.012,8)
    if feature is None or len(feature)<16: return None
    dst,ok,_=cv2.calcOpticalFlowPyrLK(first,second,feature,None)
    if dst is None: return None
    p=feature[ok.ravel()==1].reshape(-1,2);q=dst[ok.ravel()==1].reshape(-1,2)
    if len(p)<16: return None
    a,mask=cv2.estimateAffinePartial2D(p,q,method=cv2.RANSAC,ransacReprojThreshold=2)
    if a is None: return None
    inliers=p[mask.ravel().astype(bool)]
    h,w=first.shape
    coverage=len(set((min(3,int(x*4/w)),min(3,int(y*4/h))) for x,y in inliers))
    if len(inliers)<16 or len(inliers)<.5*len(p) or coverage<6: return None
    center=np.array([w*.5,h*.5])
    shift=a[:,:2]@center+a[:,2]-center
    return {"dx_pct_width_per_s":round(float(shift[0]/w/dt*100),1),
            "dy_pct_height_per_s":round(float(shift[1]/h/dt*100),1),
            "scale_per_pair":round(float(np.hypot(a[0,0],a[1,0])),3),"grid_support":coverage}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--media-run",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--case-id",help="Process just one existing case without changing its inputs.")
    args=p.parse_args()
    for path in (args.media_run/"cases").glob("*/media/manifest.json"):
        if args.case_id and path.parents[1].name!=args.case_id: continue
        m=json.loads(path.read_text("utf8"))
        rows=[];prev=None
        for f in m["frames"]:
            im=gray(path.parent/f["file"])
            if prev and prev["shot_id"]==f["shot_id"]:
                obs=pair(last,im,f["time"]-prev["time"])
                if obs: rows.append({"shot_id":f["shot_id"],"frames":[prev["index"],f["index"]],**obs})
            prev,last=f,im
        dest=args.output/"cases"/path.parents[1].name/"camera_measurements.json"
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps({"source_sha256":m["source_sha256"],"pairs":rows},indent=2),"utf8")


if __name__=="__main__":
    main()
