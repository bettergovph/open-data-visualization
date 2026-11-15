#!/usr/bin/env python3
"""Build municipality-sized DPWH road, bridge and FY2027 FMR map payloads."""
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCGIS = Path('/Users/joebertj/nep/data_sources/arcgis_dpwh/archive/selected')
OUT = ROOT / 'static/data/connectivity-municipality-maps'
LANDING = ROOT / 'static/data/connectivity-landing.json'
BOUNDARIES = ROOT / 'static/data/ph-municipality-boundaries.geojson'
ROAD = ARCGIS / 'road_condition/layers/Road_Condition_with_No_Assessment_FeatureServer_0-ba559ab9/features.jsonl'
BRIDGE = ARCGIS / 'bridge_inventory/layers/Detailed_Bridge_Inventory_Final_FeatureServer_1-72c1d1a7/features.jsonl'
DPWH_BOUNDS = ARCGIS / 'city_municipal_boundaries/layers/City_Municipal_Boundaries_FeatureServer_0-0340fd6a/features.jsonl'
FMR = ROOT / 'static/nep-preview/connectivity-fmr-road.json'


def norm(value):
    value = unicodedata.normalize('NFKD', str(value or ''))
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def psgc(value):
    return str(value or '').split('.')[0].zfill(9)


def dpwh_code_from_map_key(value):
    key=psgc(value)
    # The public map boundary export reverses the region and leading zero in 9-digit PSGCs.
    return key[1]+key[0]+key[2:] if len(key)==9 and key[1]=='0' else key


def utm51(lon, lat):
    a, e, k0 = 6378137.0, .00669437999014, .9996
    lat, lon, lon0 = math.radians(lat), math.radians(lon), math.radians(123)
    ep = e / (1 - e); n = a / math.sqrt(1 - e * math.sin(lat)**2)
    t = math.tan(lat)**2; c = ep * math.cos(lat)**2; aa = math.cos(lat) * (lon-lon0)
    m = a*((1-e/4-3*e**2/64-5*e**3/256)*lat-(3*e/8+3*e**2/32+45*e**3/1024)*math.sin(2*lat)+(15*e**2/256+45*e**3/1024)*math.sin(4*lat)-(35*e**3/3072)*math.sin(6*lat))
    x = k0*n*(aa+(1-t+c)*aa**3/6+(5-18*t+t*t+72*c-58*ep)*aa**5/120)+500000
    y = k0*(m+n*math.tan(lat)*(aa**2/2+(61-58*t+t*t+600*c-330*ep)*aa**6/720+(5-t+9*c+4*c*c)*aa**4/24))
    return [x, y]


def point_in_ring(point, ring):
    x, y = point; inside = False
    for i in range(len(ring)-1):
        x1,y1=ring[i][:2]; x2,y2=ring[i+1][:2]
        if (y1>y)!=(y2>y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: inside = not inside
    return inside


def inside(point, rings):
    value = False
    for ring in rings:
        if point_in_ring(point, ring): value = not value
    return value


def simplify(points, tolerance=75):
    if len(points) <= 2: return points
    a,b=points[0],points[-1]; dx,dy=b[0]-a[0],b[1]-a[1]; den=dx*dx+dy*dy
    best,idx=-1,0
    for i,p in enumerate(points[1:-1],1):
        t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
        d=math.hypot(p[0]-(a[0]+t*dx),p[1]-(a[1]+t*dy))
        if d>best: best,idx=d,i
    if best<=tolerance: return [a,b]
    return simplify(points[:idx+1],tolerance)[:-1]+simplify(points[idx:],tolerance)


def clip_path(path, rings, bbox):
    runs=[]; current=[]; was_inside=False
    if path:
        p=path[0]
        was_inside=(bbox[0]<=p[0]<=bbox[2] and bbox[1]<=p[1]<=bbox[3] and inside(p,rings))
        if was_inside: current=[p]
    for a,b in zip(path,path[1:]):
        steps=max(1,math.ceil(math.hypot(b[0]-a[0],b[1]-a[1])/200))
        for i in range(1,steps+1):
            t=i/steps; p=[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]
            hit=(bbox[0]<=p[0]<=bbox[2] and bbox[1]<=p[1]<=bbox[3] and inside(p,rings))
            if hit:
                if not was_inside and current:
                    if len(current)>1: runs.append(simplify(current))
                    current=[]
                current.append(p)
            elif was_inside and len(current)>1:
                runs.append(simplify(current)); current=[]
            was_inside=hit
    if len(current)>1: runs.append(simplify(current))
    return runs


def polygon_paths(geometry, convert=False):
    coords=geometry['coordinates']
    polys=[coords] if geometry['type']=='Polygon' else coords
    return [[utm51(*point[:2]) if convert else [point[0],point[1]] for point in ring] for poly in polys for ring in poly]


def make_places():
    landing={f['key']:f for f in json.loads(LANDING.read_text())['features']}
    source=json.loads(BOUNDARIES.read_text())['features']
    places={}
    for f in source:
        p=f['properties']; key=psgc(p.get('adm3_psgc'))
        info=landing.get(key)
        if not info: continue
        rings=polygon_paths(f['geometry'],True)
        xs=[x for r in rings for x,y in r]; ys=[y for r in rings for x,y in r]
        places[key]={'key':key,'name':info['name'],'province':'','rings':rings,'bbox':[min(xs),min(ys),max(xs),max(ys)],'roads':[],'bridges':[],'fmr':[]}
    # Use DPWH's higher-detail municipality boundaries when they have a PSGC code.
    dpwh=[]
    for line in DPWH_BOUNDS.open():
        f=json.loads(line); a=f.get('attributes') or {}; key=psgc(a.get('MUN_CODE'))
        if not (f.get('geometry') or {}).get('rings'): continue
        rings=f['geometry']['rings']; xs=[p[0] for r in rings for p in r]; ys=[p[1] for r in rings for p in r]
        if max(xs)-min(xs)>0 and max(ys)-min(ys)>0:
            dpwh.append((key,rings,[min(xs),min(ys),max(xs),max(ys)],a.get('PROVINCE') or '',a.get('MUNICIPAL') or ''))
    by_name=defaultdict(list); by_code={dpwh_code_from_map_key(key):place for key,place in places.items()}
    for place in places.values(): by_name[norm(place['name'])].append(place)
    for code,rings,bbox,province,name in dpwh:
        direct=by_code.get(code)
        candidates=[direct] if direct else by_name.get(norm(name),[])
        if not candidates: continue
        def overlap(place):
            b=place['bbox']; dx=max(0,min(b[2],bbox[2])-max(b[0],bbox[0])); dy=max(0,min(b[3],bbox[3])-max(b[1],bbox[1]))
            return dx*dy/max(1,(bbox[2]-bbox[0])*(bbox[3]-bbox[1]))
        place=direct or max(candidates,key=overlap)
        if not direct and overlap(place)<=0: continue
        place['rings']=[simplify(ring) for ring in rings]; place['bbox']=bbox; place['province']=province
        if name: place['name']=name
    # Province-indexed candidates keep line clipping practical on the national snapshot.
    by_province=defaultdict(list)
    for p in places.values():
        if p['province']: by_province[norm(p['province'])].append(p)
    return places,by_province


def main():
    places,by_province=make_places()
    road_count=0
    for line in ROAD.open():
        f=json.loads(line); a=f.get('attributes') or {}; g=f.get('geometry') or {}
        province=norm(a.get('PROVINCE')); candidates=by_province.get(province,[])
        if not candidates: continue
        paths=[]
        for path in g.get('paths') or []:
            pts=[[p[0],p[1]] for p in path if len(p)>=2]
            if len(pts)>1: paths.append(pts)
        if not paths: continue
        line_x=[p[0] for path in paths for p in path]; line_y=[p[1] for path in paths for p in path]
        road_bbox=[min(line_x),min(line_y),max(line_x),max(line_y)]
        for place in candidates:
            b=place['bbox']
            if road_bbox[2]<b[0] or road_bbox[0]>b[2] or road_bbox[3]<b[1] or road_bbox[1]>b[3]: continue
            clipped=[part for path in paths for part in clip_path(path,place['rings'],b)]
            if not clipped: continue
            place['roads'].append({'name':a.get('ROAD_NAME') or 'Unnamed DPWH road','roadId':a.get('ROAD_ID'),'sectionId':a.get('SECTION_ID'),'class':a.get('ROAD_SEC_CLASS'),'condition':a.get('CONDITION') or 'No Assessment','lengthM':a.get('SEG_LENGTH'),'paths':clipped})
            road_count+=1
    bridge_count=0
    for line in BRIDGE.open():
        f=json.loads(line); a=f.get('attributes') or {}; g=f.get('geometry') or {}
        if g.get('x') is None or g.get('y') is None: continue
        point=[g['x'],g['y']]
        candidates=by_province.get(norm(a.get('PROVINCE')),[])
        place=next((candidate for candidate in candidates if candidate['bbox'][0]<=point[0]<=candidate['bbox'][2] and candidate['bbox'][1]<=point[1]<=candidate['bbox'][3] and inside(point,candidate['rings'])),None)
        if place:
            place['bridges'].append({'name':a.get('BR_NAME') or 'Unnamed DPWH bridge','bridgeId':a.get('BRIDGE_ID'),'roadName':a.get('ROAD_NAME'),'condition':a.get('CONDITION') or 'Not assessed','lengthM':a.get('BR_LENGTH'),'point':point})
            bridge_count+=1
    fmr_data=json.loads(FMR.read_text())
    fmr_count=0
    for row in fmr_data.get('projects',[]):
        points=[p for p in [row.get('start'),row.get('end')] if p]
        if not points: points=[part[0] for part in row.get('routeParts',[]) if part]
        for place in places.values():
            b=place['bbox']; matched=[]
            for point in points:
                xy=utm51(float(point[0]),float(point[1]))
                if b[0]<=xy[0]<=b[2] and b[1]<=xy[1]<=b[3] and inside(xy,place['rings']): matched.append(xy)
            if not matched: continue
            routes=[]
            for part in row.get('routeParts',[]):
                coords=[utm51(float(p[0]),float(p[1])) for p in part]
                if len(coords)>1: routes.extend(clip_path(coords,place['rings'],b))
            place['fmr'].append({'id':row.get('id'),'title':row.get('title'),'amountPesos':row.get('amountPesos') or 0,'sourcePage':row.get('sourcePage'),'coordinateQualityFlag':row.get('coordinateQualityFlag',False),'routes':routes,'endpoints':matched})
            fmr_count+=1
    OUT.mkdir(parents=True,exist_ok=True)
    written=0; total_bytes=0
    for key,p in places.items():
        p['metadata']={'roadSource':'DPWH RBIA Road Condition layer · database as of Jan 2026','bridgeSource':'DPWH RBIA Detailed Bridge Inventory · database as of Jul 2026','fmrSource':'DPWH FY2027 House Bill FMR rows · printed source coordinates','boundarySource':'DPWH city/municipal boundary matched by PSGC code; PSA/NAMRIA boundary used where no coded match is available'}
        path=OUT/f'{key}.json'; path.write_text(json.dumps(p,separators=(',',':'),ensure_ascii=False))
        written+=bool(p['roads'] or p['bridges'] or p['fmr']); total_bytes+=path.stat().st_size
    print(json.dumps({'municipalities':len(places),'withMappedFeatures':written,'roadFeaturesClipped':road_count,'bridgePoints':bridge_count,'fmrMunicipalityAssignments':fmr_count,'payloadBytes':total_bytes},indent=2))


if __name__=='__main__': main()
