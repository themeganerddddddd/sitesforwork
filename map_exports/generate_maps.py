import os, json, math, sys, time
from pathlib import Path
import requests
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon
from pyproj import Transformer

OUT=Path("maps");OUT.mkdir(exist_ok=True)
T=Transformer.from_crs(4326,3857,always_xy=True)
def project(pts):
    pts=np.array(pts,float)
    x,y=T.transform(pts[:,0],pts[:,1])
    return np.column_stack((x/1000,y/1000))
def gis(url,pars):
    r=requests.get(url,params=pars,timeout=130,headers={"User-Agent":"MCEDC sites visualization; official county GIS"})
    r.raise_for_status()
    obj=r.json()
    if "error" in obj:raise ValueError(str(obj["error"]))
    return obj

boundary_url="https://geohub.montgomerycountymd.gov/mapping1/rest/services/Boundaries/Montgomery_County_Boundary/FeatureServer/0/query"
b=gis(boundary_url,{"where":"1=1","outFields":"*","returnGeometry":"true","outSR":"4326","maxAllowableOffset":".00008","geometryPrecision":"6","f":"geojson"})
f=max(b["features"],key=lambda x:len(str(x.get("geometry",{}))))
g=f["geometry"]
if g["type"]=="MultiPolygon":g={"type":"Polygon","coordinates":max(g["coordinates"],key=lambda r:len(str(r)))}
if g["type"]!="Polygon":raise ValueError("County boundary was not a polygon")
boundary=project(max(g["coordinates"],key=len))
print("Official boundary points",len(boundary))
sites=[
("01","BELWARD CAMPUS",39.10434,-77.216),
("02","INSTITUTE FOR\nHEALTH COMPUTING",39.0485,-77.1141),
("03","COMSAT",39.220643,-77.275896),
("04","VIVA WHITE OAK",39.0465,-76.9715),
("05","TRAVILLE GATEWAY",39.0933,-77.2042),
("06","PINKNEY INNOVATION\nCOMPLEX (PIC MC)",39.184444,-77.249722)
]
callouts={"01":(-8621.4,4739.1),"02":(-8579.6,4717.8),"03":(-8620.7,4759.6),
          "04":(-8556.3,4729.4),"05":(-8575.6,4740.4),"06":(-8628.6,4747.5)}
roads=[]
classes=[]
url="https://geohub.montgomerycountymd.gov/mapping1/rest/services/Transportation/Street_Centerline/FeatureServer/0/query"
for i in range(0,30000,1000):
    q=gis(url,{"where":"CFCC IN ('A10','A20','A30')",
        "outFields":"CFCC,STREET_NAME,ROUTE_NUMBER","returnGeometry":"true",
        "outSR":"4326","geometryPrecision":"6","maxAllowableOffset":".00012",
        "f":"geojson","orderByFields":"OBJECTID","resultOffset":str(i),
        "resultRecordCount":"1000"})
    fs=q.get("features",[])
    print("Street segments, batch",i,"->",len(fs),flush=True)
    for feat in fs:
        geom=feat.get("geometry") or {}
        if geom.get("type")=="LineString":lns=[geom["coordinates"]]
        elif geom.get("type")=="MultiLineString":lns=geom["coordinates"]
        else:lns=[]
        kind=(feat.get("properties") or {}).get("CFCC","A30")
        for line in lns:
            if len(line)>1:
                p=project(line)
                if np.isfinite(p).all():roads.append(p);classes.append(kind)
    if len(fs)<1000:break
if len(roads)<100:raise ValueError("Did not receive sufficient road geometry from county GIS")
print("Official road polylines",len(roads),flush=True)
def render(streets):
    bg="#f7fafb" if not streets else "#f6f7f5"
    filled="#e6f3f1" if not streets else "#edf1e9"
    navy="#00568d";gold="#f9a51e"
    fig=plt.figure(figsize=(16,9),dpi=170,facecolor=bg)
    ax=fig.add_axes([.055,.13,.89,.72]);ax.set_facecolor(bg)
    ax.set_xlim(-8646,-8543);ax.set_ylim(4707,4781)
    ax.set_aspect("equal",adjustable="box");ax.set_axis_off()
    ax.add_patch(Polygon(boundary,facecolor=filled,edgecolor="none",zorder=1))
    if streets:
        for cls,w,col in [("A30",.58,"#c7d2d1"),("A20",1.55,"#fff"),
                          ("A20",.55,"#adbebc"),("A10",3.9,"white"),("A10",1.75,"#e0a05f")]:
            segments=[p for p,kind in zip(roads,classes) if kind==cls]
            if segments:
                ax.add_collection(LineCollection(segments,linewidths=w,colors=col,
                                                 capstyle="round",zorder=2))
    ax.add_patch(Polygon(boundary,facecolor="none",edgecolor="white",linewidth=5,zorder=3))
    ax.add_patch(Polygon(boundary,facecolor="none",edgecolor=navy,linewidth=2.7,zorder=4))
    for no,label,lat,lon in sites:
        x,y=project([[lon,lat]])[0];tx,ty=callouts[no]
        ax.plot([x,tx],[y,ty],lw=1.45,color="#597c93",zorder=5)
        ax.scatter([x],[y],s=625,color="white",zorder=8)
        ax.scatter([x],[y],s=460,color=navy,zorder=9)
        ax.text(x,y,no,fontsize=10.3,fontweight="bold",ha="center",va="center",color="white",zorder=10)
        ax.text(tx,ty,label,fontsize=10.6,fontweight="bold",ha="left",va="center",
            linespacing=1.14,color="#153b50",zorder=7,
            bbox={"boxstyle":"round,pad=.56,rounding_size=.23","facecolor":"white",
                  "edgecolor":"#9fbecd","linewidth":1.15})
    fig.text(.055,.93,"SITE SELECTION  /  MARYLAND",color=navy,fontsize=11,weight="bold")
    fig.text(.055,.87,"Six priority development sites",color="#153a51",fontsize=29.5,weight="bold")
    fig.text(.947,.93,"OFFICIAL STREET NETWORK" if streets else "GEOGRAPHIC OUTLINE",
             fontsize=10.5,weight="bold",ha="right",color="#708695")
    fig.add_artist(plt.Line2D([.055,.946],[.833,.833],transform=fig.transFigure,
                              lw=1.2,color="#d3e1e6"))
    fig.add_artist(plt.Line2D([.055,.13],[.833,.833],transform=fig.transFigure,
                              lw=4.5,color=gold))
    fig.add_artist(plt.Line2D([.055,.946],[.102,.102],transform=fig.transFigure,
                              lw=1.0,color="#d3e1e6"))
    foot="Boundary: official county GIS"
    if streets:foot+="  •  Road geometry: official county Street Centerline"
    fig.text(.055,.073,foot,fontsize=9,color="#637e8c")
    fig.text(.947,.073,"Six georeferenced sites  •  Approximate reference points, not parcel boundaries",
             color="#637e8c",fontsize=8.7,ha="right")
    out=OUT/("accurate_six_sites_streets.png" if streets else "accurate_six_sites_outline.png")
    fig.savefig(out,facecolor=bg,dpi=170,pad_inches=0)
    plt.close(fig)
    print("Map created:",out,out.stat().st_size)
render(False)
render(True)
