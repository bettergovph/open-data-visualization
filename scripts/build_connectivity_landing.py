#!/usr/bin/env python3
"""Build a compact map and project index for the Connectivity landing page."""
import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "static/nep-preview"
OUT = ROOT / "static/data/connectivity-landing.json"


def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def simplify(points, tolerance=0.0012):
    """Ramer-Douglas-Peucker simplification, preserving closed polygon rings."""
    if len(points) <= 5:
        return points
    closed = points[0] == points[-1]
    src = points[:-1] if closed else points
    if len(src) <= 4:
        return points
    # Split at the point farthest from the first vertex so the closed ring is
    # simplified as two open chains without losing its overall shape.
    first = src[0]
    farthest = max(range(1, len(src)), key=lambda i: (src[i][0]-first[0])**2 + (src[i][1]-first[1])**2)
    chain_a, chain_b = src[:farthest+1], src[farthest:] + [src[0]]

    def rdp(chain):
        if len(chain) <= 2:
            return chain
        (x1,y1),(x2,y2)=chain[0],chain[-1]
        dx,dy=x2-x1,y2-y1
        den=math.hypot(dx,dy) or 1
        best,idx=-1,-1
        for i,(x,y) in enumerate(chain[1:-1],1):
            dist=abs(dy*x-dx*y+x2*y1-y2*x1)/den
            if dist>best: best,idx=dist,i
        if best<=tolerance: return [chain[0],chain[-1]]
        return rdp(chain[:idx+1])[:-1]+rdp(chain[idx:])

    result=rdp(chain_a)[:-1]+rdp(chain_b)[:-1]
    if len(result)<4: result=src
    return result+[result[0]] if closed else result


def inside(point, rings):
    x,y=point; inside_any=False
    for ring in rings:
        hit=False
        for i in range(len(ring)-1):
            x1,y1=ring[i]; x2,y2=ring[i+1]
            if (y1>y)!=(y2>y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1: hit=not hit
        if hit: inside_any=not inside_any
    return inside_any


features=[]
boundaries=json.loads((ROOT/'static/data/ph-municipality-boundaries.geojson').read_text())
for feature in boundaries['features']:
    p=feature['properties']; geometry=feature['geometry']; polygons=geometry['coordinates'] if geometry['type']=='MultiPolygon' else [geometry['coordinates']]
    rings=[simplify(r) for polygon in polygons for r in polygon if len(r)>=4]
    if not rings: continue
    xs=[pt[0] for ring in rings for pt in ring]; ys=[pt[1] for ring in rings for pt in ring]
    features.append({"key":str(p['adm3_psgc']),"province":p.get('adm2_en') or '',"name":p.get('adm3_en') or '',"city":p.get('geo_level')!='Mun',"rings":rings,"bbox":[min(xs),min(ys),max(xs),max(ys)],"items":{"road":[],"bridge":[],"fmr":[]}})

# Match FY2027 DPWH road and bridge titles to unambiguous named municipalities.
integrated=json.loads((PREVIEW/'integrated-project-data.json').read_text())
localities=[]
for f in features:
    name=norm(f['name'])
    if len(name)>=4: localities.append((name,f))

for row in integrated['projects']:
    if row.get('year')!=2027 or row.get('stage')!='HGAB 3rd' or row.get('category') not in ('Road','Bridge'):
        continue
    title=norm(row.get('name'))
    matches=[f for name,f in localities if re.search(r'(?<![a-z0-9])'+re.escape(name)+r'(?![a-z0-9])',title)]
    if not matches: continue
    # If title names a province, use that to disambiguate repeated locality names.
    province_matches=[f for f in matches if norm(f['province']) and re.search(r'(?<![a-z0-9])'+re.escape(norm(f['province']))+r'(?![a-z0-9])',title)]
    if len(province_matches)==1: matches=province_matches
    if len(matches)!=1: continue
    f=matches[0]; kind='bridge' if row['category']=='Bridge' else 'road'
    f['items'][kind].append({"title":row['name'],"amount":row.get('amountPesos') or 0,"source":row.get('source','')})

# FY2027 FMR route endpoints are matched to the DPWH municipality polygons.
fmr=json.loads((PREVIEW/'connectivity-fmr-road.json').read_text())
for row in fmr.get('projects',[]):
    points=[]
    for key in ('start','end'):
        if row.get(key+'Longitude') is not None and row.get(key+'Latitude') is not None:
            points.append([row[key+'Longitude'],row[key+'Latitude']])
    if not points:
        for part in row.get('routeParts',[]):
            if part: points.extend([part[0],part[-1]])
    hits=[]
    for f in features:
        if any(f['bbox'][0]<=p[0]<=f['bbox'][2] and f['bbox'][1]<=p[1]<=f['bbox'][3] and inside(p,f['rings']) for p in points): hits.append(f)
    if len(hits)==1:
        hits[0]['items']['fmr'].append({"title":row.get('title',''),"amount":row.get('amountPesos') or 0,"sourcePage":row.get('sourcePage'),"id":row.get('id')})

for f in features:
    f['counts']={key:len(val) for key,val in f['items'].items()}
    f['totals']={key:round(sum(float(x.get('amount') or 0) for x in val)) for key,val in f['items'].items()}

result={"boundarySource":"Philippine PSGC Administrative Boundaries · 3Q 2026 low-resolution GeoJSON. Boundary source: NAMRIA and PSA via OCHA COD-AB (CC BY-IGO).","roadBridgeSource":"DPWH integrated-project-data · FY2027 HGAB 3rd · exact municipality title matches only; ambiguous names omitted","fmrSource":"DPWH FY2027 HGAB 3rd FMR rows · printed endpoints within municipality polygon","features":features}
OUT.write_text(json.dumps(result,separators=(',',':'),ensure_ascii=False))
print(f"wrote {OUT.relative_to(ROOT)} · {len(features):,} boundaries · {OUT.stat().st_size:,} bytes")
for kind in ('road','bridge','fmr'):
    print(f"{kind}: {sum(x['counts'][kind] for x in features):,} matched project rows · ₱{sum(x['totals'][kind] for x in features):,}")
