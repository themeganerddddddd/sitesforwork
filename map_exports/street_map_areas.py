"""Export literal street-basemap screenshots with the official county boundary,
the six existing development site coordinate pins, and their city/area names.
Data: Montgomery County GIS (boundary); CARTO (street map tiles)."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import io, math, time, json
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont

OUT=Path("maps");OUT.mkdir(exist_ok=True)
W,H=2720,1530
Z=12
S=256*(2**Z)
NAVY="#00568d";GOLD="#f9a51e";TEXT="#173d53"
SESSION_HEADERS={"User-Agent":"MCEDC-SixSites-Map/1.0 (site selection map rendering; cartographic attribution)"}
def px(lon,lat):
    lat=max(-85.05112878,min(85.05112878,lat))
    sl=math.sin(math.radians(lat))
    return ((lon+180.0)/360.0*S,(.5-math.log((1+sl)/(1-sl))/(4*math.pi))*S)
def gjson(endpoint,params):
    for attempt in range(3):
        try:
            resp=requests.get(endpoint,params=params,timeout=45,headers=SESSION_HEADERS)
            resp.raise_for_status()
            o=resp.json()
            if o.get("error"):raise RuntimeError(o["error"])
            return o
        except Exception as e:
            if attempt==2:raise
            time.sleep(1.2*(attempt+1))
    raise RuntimeError("unreachable")
endpoint="https://geohub.montgomerycountymd.gov/mapping1/rest/services/Boundaries/Montgomery_County_Boundary/FeatureServer/0/query"
geo=gjson(endpoint,{"where":"1=1","outFields":"*","returnGeometry":"true","outSR":"4326","maxAllowableOffset":"0.00007","geometryPrecision":"6","f":"geojson"})
features=[f for f in geo.get("features",[]) if f.get("geometry")]
if not features:raise RuntimeError("Official county boundary could not be obtained")
rings=[]
for f in features:
    geom=f["geometry"]
    if geom["type"]=="Polygon": polys=[geom["coordinates"]]
    elif geom["type"]=="MultiPolygon":polys=geom["coordinates"]
    else:continue
    for poly in polys:
        if poly and len(poly[0])>=4:
            rings.append([px(*p[:2]) for p in poly[0]])
if not rings:raise RuntimeError("Official boundary did not contain usable coordinates")
xs=[p[0] for ring in rings for p in ring]
ys=[p[1] for ring in rings for p in ring]
minx,maxx,miny,maxy=min(xs),max(xs),min(ys),max(ys)
print("Boundary dimensions in source pixels:", round(maxx-minx),round(maxy-miny),flush=True)
# A padded real map crop in EPSG:3857 with no redrawn streets.
# Leave room for labels near both sides of the county and for an unobstructed lower margin.
scale=min((W-400)/(maxx-minx),(H-315)/(maxy-miny),1.06)
centerx,centery=(minx+maxx)/2,(miny+maxy)/2
source_left=centerx-W/(2*scale)
source_top=centery-H/(2*scale)
source_w,source_h=W/scale,H/scale
print("Output scale:",scale,"viewport:",[round(source_left),round(source_top),round(source_w),round(source_h)],flush=True)
def to_image(x,y):
    return (int(round((x-source_left)*scale)),int(round((y-source_top)*scale)))
county_rings=[[to_image(x,y) for x,y in ring] for ring in rings]
first_tile_x=int(math.floor(source_left/256))
last_tile_x=int(math.floor((source_left+source_w)/256))
first_tile_y=int(math.floor(source_top/256))
last_tile_y=int(math.floor((source_top+source_h)/256))
tiles=[(x,y) for y in range(first_tile_y,last_tile_y+1) for x in range(first_tile_x,last_tile_x+1)]
print("Tile range",len(tiles),"tiles",flush=True)
def get_tile(task):
    provider,x,y=task
    if provider=="voyager":
        # CARTO's full-featured literal street background including town and road labels.
        url=f"https://a.basemaps.cartocdn.com/rastertiles/voyager/{Z}/{x}/{y}.png"
    elif provider=="positron":
        url=f"https://a.basemaps.cartocdn.com/light_all/{Z}/{x}/{y}.png"
    else:
        url=f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{Z}/{y}/{x}"
    for attempt in range(3):
        try:
            r=requests.get(url,headers=SESSION_HEADERS,timeout=22)
            r.raise_for_status()
            image=Image.open(io.BytesIO(r.content)).convert("RGB")
            if image.size!=(256,256):raise ValueError("Unexpected tile dimensions")
            return x,y,image
        except Exception as err:
            if attempt==2:return x,y,None
            time.sleep(.45*(attempt+1))
def compose_tiles(provider):
    jobs=[(provider,x,y) for x,y in tiles]
    canvas=Image.new("RGB",((last_tile_x-first_tile_x+1)*256,(last_tile_y-first_tile_y+1)*256),"#f1f3f4")
    failures=0
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures=[executor.submit(get_tile,t) for t in jobs]
        for future in as_completed(futures):
            x,y,tile=future.result()
            if tile is None:failures+=1;continue
            canvas.paste(tile,((x-first_tile_x)*256,(y-first_tile_y)*256))
    print(provider,"failures",failures,"of",len(jobs),flush=True)
    if failures>max(1,int(len(jobs)*.07)):raise RuntimeError("Too many unavailable real street tiles. Refusing to draw fictional streets.")
    ox=source_left-first_tile_x*256
    oy=source_top-first_tile_y*256
    left,top=int(round(ox)),int(round(oy))
    source=canvas.crop((left,top,left+int(math.ceil(source_w)),top+int(math.ceil(source_h))))
    return source.resize((W,H),Image.Resampling.LANCZOS)
def font(sz,bold=False):
    path="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path,sz)
F_TITLE=font(43,True);F_OVER=font(18,True);F_NAME=font(24,True);F_AREA=font(20,False);F_PIN=font(19,True);F_NOTE=font(17,False)
# Site coordinates and mailing/local community areas from the six-site source project.
sites=[
  {"id":"01","name":"BELWARD CAMPUS","area":"Rockville / Shady Grove","lat":39.10434,"lon":-77.216,"shift":(-340,-145)},
  {"id":"02","name":"INSTITUTE FOR HEALTH COMPUTING","area":"North Bethesda","lat":39.0485,"lon":-77.1141,"shift":(65,95)},
  {"id":"03","name":"COMSAT","area":"Clarksburg","lat":39.220643,"lon":-77.275896,"shift":(-280,-130)},
  {"id":"04","name":"VIVA WHITE OAK","area":"White Oak / Silver Spring","lat":39.0465,"lon":-76.9715,"shift":(70,-65)},
  {"id":"05","name":"TRAVILLE GATEWAY","area":"Rockville / Traville","lat":39.0933,"lon":-77.2042,"shift":(-365,60)},
  {"id":"06","name":"PINKNEY INNOVATION COMPLEX","area":"Germantown (PIC MC)","lat":39.184444,"lon":-77.249722,"shift":(70,25)}
]
def rounded_card(img,d,xy,site):
    x,y=xy
    name=site["name"];area=site["area"]
    nameW=d.textbbox((0,0),name,font=F_NAME)[2]
    areaW=d.textbbox((0,0),area,font=F_AREA)[2]
    bw=max(nameW,areaW)+52
    bh=91
    # Put callout fully on the map and above the footnote.
    x=max(30,min(W-bw-30,x));y=max(160,min(H-bh-65,y))
    d.rounded_rectangle([x+3,y+5,x+bw+3,y+bh+5],radius=14,fill=(11,44,62,30))
    d.rounded_rectangle([x,y,x+bw,y+bh],radius=14,fill=(255,255,255,248),outline=(142,175,190,255),width=2)
    d.rectangle([x,y+13,x+6,y+bh-13],fill=GOLD)
    d.text((x+24,y+12),name,font=F_NAME,fill=TEXT)
    d.text((x+24,y+51),area,font=F_AREA,fill=(68,92,104))
    return (x,y,bw,bh)
def draw_export(provider,name):
    basemap=compose_tiles(provider).convert("RGBA")
    overlay=Image.new("RGBA",(W,H),(0,0,0,0));draw=ImageDraw.Draw(overlay)
    for points in county_rings:
        if len(points)<4:continue
        draw.line(points+[points[0]],fill=(255,255,255,245),width=10,joint="curve")
        draw.line(points+[points[0]],fill=(0,86,141,252),width=5,joint="curve")
    # White header band with a simple accurate geographic description, not an invented map.
    draw.rounded_rectangle([65,38,940,145],radius=19,fill=(255,255,255,240))
    draw.rectangle([65,38,75,145],fill=GOLD)
    draw.text((95,47),"SIX DEVELOPMENT SITES",font=F_TITLE,fill=NAVY)
    draw.text((98,106),"County outline  ·  Site and community labels",font=F_OVER,fill=(91,110,119))
    for site in sites:
        cx,cy=to_image(*px(site["lon"],site["lat"]))
        bx=cx+site["shift"][0];by=cy+site["shift"][1]
        # dynamic target card placement
        tw=draw.textbbox((0,0),site["name"],font=F_NAME)[2]
        aw=draw.textbbox((0,0),site["area"],font=F_AREA)[2]
        cardw=max(tw,aw)+52;cardh=91
        bx=max(30,min(W-cardw-30,bx))
        by=max(160,min(H-cardh-65,by))
        tx=max(bx,min(cx,bx+cardw));ty=max(by,min(cy,by+cardh))
        draw.line((cx,cy,tx,ty),fill=(255,255,255,255),width=6)
        draw.line((cx,cy,tx,ty),fill=(49,93,118,235),width=2)
        rounded_card(basemap,draw,(bx,by),site)
    # Draw markers AFTER callouts so the actual site position is never obscured.
    for site in sites:
        cx,cy=to_image(*px(site["lon"],site["lat"]))
        rad=27
        draw.ellipse((cx-rad-2,cy-rad-2,cx+rad+2,cy+rad+2),fill="white")
        draw.ellipse((cx-rad+3,cy-rad+3,cx+rad-3,cy+rad-3),fill=NAVY)
        bb=draw.textbbox((0,0),site["id"],font=F_PIN)
        draw.text((cx-(bb[2]-bb[0])/2,cy-(bb[3]-bb[1])/2-bb[1]),site["id"],font=F_PIN,fill="white")
    draw.rounded_rectangle([62,H-79,1440,H-30],radius=13,fill=(255,255,255,232))
    draw.text((82,H-69),"Source: county GIS boundary · CARTO/OSM street tiles · approximate site coordinates",font=F_NOTE,fill=(60,82,92))
    final=Image.alpha_composite(basemap,overlay).convert("RGB")
    path=OUT/name;final.save(path,optimize=True)
    print("SAVED",path,path.stat().st_size,flush=True)
draw_export("voyager","six_sites_literal_streets_areas.png")
draw_export("positron","six_sites_literal_light_streets_areas.png")
