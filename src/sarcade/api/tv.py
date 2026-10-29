"""Smart TV and big screens (« Affichage sur Smart TV et grand écran »).

- ``/tv`` (and ``/`` of tv.sarcade.org): full-screen read-only page for the TV (served on tv.sarcade.org,
  without Cloudflare Access): asks a pairing code, then shows the event.
- ``/tv/approve?code=…``: page opened by the QR code on a phone signed in
  (Access); any operator chooses the event and approves.
- API: pairing, approval and revocation by any operator (decision of the
  porteur, 29 Oct 2026: showing SARCADE on a TV is not a PCO right), state
  read by the TV, list of the screens of an event."""
import html
import secrets
import time
import uuid
from pathlib import Path
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sarcade import tv
from sarcade.db.models import EventRow, LogbookRow, MessageRow, PositionRow
from sarcade.updates.service import get_value, set_value

from .deps import get_db
from .roles import checked_email
from .serializers import position_dict

router = APIRouter()
KEY = "displays"
NO_STORE = {"Cache-Control": "no-store"}

# Paths served on the TV address (tv.*): nothing else answers there.
TV_HOST_PATHS = ("/tv", "/api/v0.1/tv/pair", "/api/v0.1/tv/state", "/health")


def tv_host_allows(path: str) -> bool:
    if path.startswith("/tv/approve") or path.startswith("/api/v0.1/tv/approve"):
        return False
    return any(path == p or path.startswith(p + "/") for p in TV_HOST_PATHS)


def _displays(db: Session) -> list[dict]:
    return list(get_value(db, KEY, []) or [])


def _actor(request: Request) -> str:
    """Who approved or revoked a screen, for the logbook: the email checked
    by Cloudflare Access, else « opérateur » (local network)."""
    return (checked_email(request) or "opérateur")[:64]


def _client(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


@router.post("/api/v0.1/tv/pair")
def pair(request: Request):
    if not tv.store.allowed(_client(request)):
        raise HTTPException(status_code=429, detail="too_many_requests")
    try:
        p = tv.store.new()
    except OverflowError:
        raise HTTPException(status_code=503, detail="busy")
    return {"pair_id": p.pair_id, "code": p.code, "expires_in": tv.CODE_TTL_S}


@router.get("/api/v0.1/tv/pair/{pair_id}")
def pair_status(pair_id: str, db: Session = Depends(get_db)):
    p = tv.store.status(pair_id)
    if p is None:
        raise HTTPException(status_code=404, detail="expired")
    if p.token is None:
        return {"status": "pending"}
    token, event_id = p.token, p.event_id
    tv.store.pairings.pop(pair_id, None)
    tv.store.by_code.pop(p.code, None)
    now = time.time()
    displays = [d for d in _displays(db) if d.get("expires", 0) > now - 7 * 24 * 3600]
    displays.append({"id": str(uuid.uuid4()), "hash": tv.token_hash(token), "event_id": event_id,
                     "created": now, "expires": now + tv.TOKEN_TTL_S, "revoked": False, "code": p.code})
    set_value(db, KEY, displays)
    db.commit()
    return {"status": "approved", "token": token, "event_id": event_id}


class ApproveIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)
    event_id: str = Field(min_length=1, max_length=64)


@router.post("/api/v0.1/tv/approve")
def approve(body: ApproveIn, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request)
    event = db.get(EventRow, body.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    p = tv.store.approve(body.code, body.event_id)
    if p is None:
        raise HTTPException(status_code=404, detail="unknown_code")
    db.add(LogbookRow(event_id=body.event_id, kind="display", object_id=None, actor_id=actor,
                      summary=f"Écran d'affichage appairé (code {p.code})", time=datetime.now(UTC)))
    db.commit()
    return {"approved": True}


def _display(request: Request, db: Session) -> dict:
    auth = request.headers.get("authorization", "")
    token = auth[8:] if auth.lower().startswith("display ") else ""
    d = tv.valid_display(_displays(db), token) if token else None
    if d is None:
        raise HTTPException(status_code=401, detail="display_token_required")
    return d


@router.get("/api/v0.1/tv/state")
def state(request: Request, db: Session = Depends(get_db)):
    d = _display(request, db)
    event = db.get(EventRow, d["event_id"])
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    ranked = select(PositionRow.id, func.row_number().over(
        partition_by=PositionRow.device_id, order_by=PositionRow.time.desc()).label("rn")
    ).where(PositionRow.event_id == event.id).subquery()
    rows = db.scalars(select(PositionRow).join(ranked, PositionRow.id == ranked.c.id).where(ranked.c.rn == 1)).all()
    positions = [{k: v for k, v in position_dict(r).items() if k in ("device_id", "lat", "lon", "time", "source", "callsign")}
                 for r in rows]
    msgs = db.scalars(select(MessageRow).where(MessageRow.event_id == event.id)
                      .order_by(MessageRow.created_at.desc()).limit(60)).all()
    messages = [{"sender_id": m.sender_id, "recipient_ids": m.recipient_ids or [], "priority": m.priority,
                 "body": m.body, "created_at": m.created_at} for m in reversed(msgs)]
    logs = db.scalars(select(LogbookRow).where(LogbookRow.event_id == event.id)
                      .where(LogbookRow.kind.not_in(tuple(tv.TV_HIDDEN_LOG_KINDS)))
                      .order_by(LogbookRow.seq.desc()).limit(12)).all()
    logbook = [{"time": r.time, "actor_id": r.actor_id, "kind": r.kind, "summary": r.summary} for r in reversed(logs)]
    snap = tv.snapshot({"id": event.id, "name": event.name}, positions, messages, logbook)
    snap["view"] = d.get("view")
    return snap


@router.get("/api/v0.1/events/{event_id}/displays")
def list_displays(event_id: str, db: Session = Depends(get_db)):
    now = time.time()
    return [{"id": d["id"], "code": d.get("code"), "created": d["created"], "expires": d["expires"],
             "active": not d.get("revoked") and d["expires"] > now}
            for d in _displays(db) if d.get("event_id") == event_id]


@router.delete("/api/v0.1/events/{event_id}/displays/{display_id}", status_code=204)
def revoke_display(event_id: str, display_id: str, request: Request, db: Session = Depends(get_db)):
    actor = _actor(request)
    displays = _displays(db)
    for d in displays:
        if d["id"] == display_id and d.get("event_id") == event_id:
            d["revoked"] = True
            set_value(db, KEY, displays)
            db.add(LogbookRow(event_id=event_id, kind="display", object_id=None, actor_id=actor,
                              summary=f"Écran d'affichage révoqué (code {d.get('code')})", time=datetime.now(UTC)))
            db.commit()
            return
    raise HTTPException(status_code=404, detail="display_not_found")


class ViewIn(BaseModel):
    """View of a phone copied onto a TV (« Envoyer ma vue », 29 Oct 2026);
    ``view`` null gives the TV back its automatic framing."""
    view: dict | None = None


@router.put("/api/v0.1/events/{event_id}/displays/{display_id}/view")
def send_view(event_id: str, display_id: str, body: ViewIn, request: Request, db: Session = Depends(get_db)):
    try:
        view = tv.clean_view(body.view)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    displays = _displays(db)
    for d in displays:
        if d["id"] == display_id and d.get("event_id") == event_id and not d.get("revoked"):
            d["view"] = view
            set_value(db, KEY, displays)
            text = "Vue envoyée sur l'écran" if view else "Cadrage automatique rendu à l'écran"
            db.add(LogbookRow(event_id=event_id, kind="display", object_id=None, actor_id=_actor(request),
                              summary=f"{text} (code {d.get('code')})", time=datetime.now(UTC)))
            db.commit()
            return {"view": view}
    raise HTTPException(status_code=404, detail="display_not_found")


@router.get("/tv/approve")
def approve_page(db: Session = Depends(get_db)):
    """The code comes from the QR code (?code=…): read by the page script,
    never written into the HTML by the server."""
    events = db.scalars(select(EventRow).where(EventRow.ended_at.is_(None)).order_by(EventRow.created_at.desc())).all()
    options = "".join(f'<option value="{html.escape(e.id)}">{html.escape(e.name or "")}</option>' for e in events)
    return HTMLResponse(_APPROVE.replace("__OPTIONS__", options), headers=NO_STORE)


_LOGO = Path(__file__).with_name("tv_logo.png")


@router.get("/tv/logo.png")
def tv_logo():
    return FileResponse(_LOGO, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/tv")
def tv_page():
    return HTMLResponse(_TV.replace("__NONCE__", secrets.token_hex(4)), headers=NO_STORE)


_APPROVE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>SARCADE · écran</title>
<style>body{font-family:system-ui,sans-serif;max-width:420px;margin:32px auto;padding:0 16px;color:#022a58}
.logo{display:block;width:180px;margin:0 auto 18px}
h1{font-size:22px}label{display:block;margin:14px 0 4px;font-weight:600}input,select,button{font-size:17px;width:100%;padding:10px;box-sizing:border-box;border-radius:10px;border:1px solid #b9c6d2}
button{background:#022a58;color:#fff;border:0;margin-top:18px;font-weight:600}#r{margin-top:16px}</style></head><body>
<img class="logo" src="/tv/logo.png" alt="SARCADE"><h1>Afficher SARCADE sur un écran</h1>
<p>Choisissez l'événement à afficher sur la TV, puis validez.</p>
<label for="c">Code affiché sur la TV</label><input id="c" autocapitalize="characters" maxlength="12">
<label for="e">Événement</label><select id="e">__OPTIONS__</select>
<button id="b">Afficher sur la TV</button><p id="r"></p>
<script>document.getElementById('c').value=(new URLSearchParams(location.search).get('code')||'').slice(0,12);
document.getElementById('b').onclick=async()=>{const r=await fetch('/api/v0.1/tv/approve',{method:'POST',
headers:{'content-type':'application/json'},body:JSON.stringify({code:document.getElementById('c').value,event_id:document.getElementById('e').value})});
document.getElementById('r').textContent=r.ok?'C\\u2019est fait : la TV affiche l\\u2019événement.':(r.status===401||r.status===403?'Connectez-vous à SARCADE, puis réessayez.':'Code inconnu ou expiré.');};</script>
</body></html>"""

_TV = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>SARCADE · affichage</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>html,body{margin:0;height:100%;background:#03152b;color:#eef3f9;font-family:system-ui,sans-serif}
#pair{display:grid;grid-template-columns:auto auto;justify-content:center;align-items:center;gap:8vw;height:100%;padding:0 8vw;box-sizing:border-box;
background:radial-gradient(ellipse at 20% 30%,#0a3266 0%,#03152b 60%)}
.left{display:flex;flex-direction:column;gap:3.2vh;min-width:0}
.logo{background:#fff;border-radius:22px;padding:14px 24px;width:max-content}.logo img{height:min(20vh,170px);display:block}
.lead{font-size:min(4.2vh,38px);font-weight:700}
#code{font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace;font-size:min(16vh,9vw,150px);letter-spacing:.16em;font-weight:800;
color:#ffb020;border-left:8px solid #ff4d1a;padding-left:3vw;line-height:1}
.how{font-size:min(2.6vh,24px);line-height:1.45;color:#c4d1e0;max-width:32em}.how b{color:#fff}
#qr{background:#fff;padding:22px;border-radius:24px;box-shadow:0 12px 40px rgba(0,0,0,.35)}#qr img,#qr canvas{display:block}
#hint{font-size:18px;color:#ffb020;min-height:1em}
@media (max-aspect-ratio:1/1){#pair{grid-template-columns:1fr;justify-items:center;text-align:center;padding:6vh 6vw;align-content:center}
.left{align-items:center}#code{border-left:0;padding-left:0}}
#app{display:none;height:100%;grid-template-columns:1fr minmax(300px,17%);grid-template-rows:68px 1fr}
header{grid-column:1/3;display:flex;align-items:center;gap:22px;padding:0 20px;background:#03152b;border-bottom:1px solid #1e2c38}
.hlogo{background:#fff;border-radius:10px;padding:4px 10px;display:flex}.hlogo img{height:50px;display:block}
#title{font-size:26px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.stats{display:flex;align-items:center;gap:26px;margin-left:auto;font-size:19px;color:#c4d1e0;white-space:nowrap}.stats b{color:#fff;font-size:22px}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;background:#3ddc84;margin-right:7px}#link.lost{color:#ff6b6b}#link.lost .dot{background:#ff4d5e}
#clock{font-size:34px;font-weight:700;font-variant-numeric:tabular-nums;margin-left:10px;color:#fff}#date{font-size:15px;color:#c4d1e0;text-align:right;line-height:1.1}
#map{height:100%}aside{overflow:hidden;padding:12px 14px;border-left:1px solid #1e2c38;font-size:17px}
h2{font-size:16px;color:#b9c6d2;text-transform:uppercase;letter-spacing:1px;margin:14px 0 6px}
.m{padding:6px 0;border-bottom:1px solid #16212b}.u{color:#ffb020}.i{color:#ff4d5e;font-weight:700}
#alert{display:none;position:fixed;left:0;right:0;top:0;padding:18px;background:#ff4d5e;color:#fff;font-size:30px;font-weight:700;text-align:center;z-index:2000}
</style></head><body>
<div id="pair"><div class="left"><div class="logo"><img src="/tv/logo.png" alt="SARCADE"></div>
<div class="lead">Afficher SARCADE sur cet écran</div><div id="code">······</div>
<div class="how">Dans l'application SARCADE : <b>Paramètres › Affichage › Écrans</b>, puis scannez le QR code ou saisissez ce code.</div>
<div id="hint"></div></div><div id="qr"></div></div>
<div id="app"><header><div class="hlogo"><img src="/tv/logo.png" alt="SARCADE"></div><div id="title"></div><div class="stats"><span><b id="nOps">0</b> opérateurs actifs</span><span><b id="nAprs">0</b> stations APRS</span><span id="link"><span class="dot"></span><span id="linkTxt">Connexion…</span></span></div><div><div id="clock">--:--</div><div id="date"></div></div></header><div id="map"></div><aside><h2>Messages</h2><div id="msgs"></div><h2>Main courante</h2><div id="log"></div></aside></div>
<div id="alert"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const $=id=>document.getElementById(id);let token=localStorage.getItem('sarcade_tv_token');let map,markers={};
const appHost=location.hostname.replace(/^tv\\./,'app.');
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Station name without the technical prefix: callsign for APRS, else the terminal.
function label(p){return p.callsign||String(p.device_id||'').replace(/^aprs:/,'');}
// Labels that would overlap are hidden (operators first, then APRS), recomputed on zoom.
function declutter(){if(!map)return;const kept=[];
const ms=Object.values(markers).sort((a,b)=>(a._aprs?1:0)-(b._aprs?1:0));
for(const m of ms){const pt=map.latLngToContainerPoint(m.getLatLng());
const clash=kept.some(q=>Math.abs(q.x-pt.x)<110&&Math.abs(q.y-pt.y)<22);
if(clash)m.closeTooltip();else{m.openTooltip();kept.push(pt);}}}
function hm(t){const d=new Date(t);return d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});}
async function pair(){const r=await fetch('/api/v0.1/tv/pair',{method:'POST'});if(!r.ok){$('hint').textContent='Réessai dans une minute…';setTimeout(pair,60000);return;}
const p=await r.json();$('code').textContent=p.code;$('qr').innerHTML='';new QRCode($('qr'),{text:'https://'+appHost+'/tv/approve?code='+p.code,width:340,height:340});
const until=Date.now()+p.expires_in*1000;const poll=async()=>{if(Date.now()>until){pair();return;}
const s=await fetch('/api/v0.1/tv/pair/'+p.pair_id);if(s.ok){const j=await s.json();if(j.status==='approved'){token=j.token;localStorage.setItem('sarcade_tv_token',token);start();return;}}
setTimeout(poll,3000);};poll();}
// View sent by a phone (« Envoyer ma vue »): centre, zoom and base map, kept
// until the next one; none: automatic framing on the stations.
const OSM='https://tile.openstreetmap.org/{z}/{x}/{y}.png';let base=null,viewRev;
function setBase(url,attr){const u=url||OSM;if(base&&base._url===u)return;if(base)map.removeLayer(base);
base=L.tileLayer(u,{attribution:esc(url?(attr||''):'© OpenStreetMap'),maxZoom:19}).addTo(map);}
function applyView(v){const rev=v?v.rev:null;if(rev===viewRev)return;viewRev=rev;
if(v){map._fitted=true;map.setView([v.lat,v.lon],v.zoom);setBase(v.tile_url,v.attribution);}else{map._fitted=false;setBase(null);}}
// Top bar: clock, and the state of the link with the server.
let lastOk=0;
function tick(){const d=new Date();$('clock').textContent=d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
$('date').textContent=d.toLocaleDateString('fr-FR',{weekday:'short',day:'numeric',month:'short'});}
function linkState(ok){if(ok)lastOk=Date.now();const lost=!ok&&Date.now()-lastOk>30000;$('link').className=lost?'lost':'';
$('linkTxt').textContent=lost?'Liaison perdue'+(lastOk?' depuis '+hm(lastOk):''):(lastOk?'En direct':'Connexion…');}
async function refresh(){let r;try{r=await fetch('/api/v0.1/tv/state',{headers:{authorization:'Display '+token}});}catch(e){linkState(false);return;}
if(r.status===401){localStorage.removeItem('sarcade_tv_token');location.reload();return;}if(!r.ok){linkState(false);return;}const s=await r.json();linkState(true);
$('title').textContent=s.event.name;const pts=[];const now=Date.now();
$('nOps').textContent=s.positions.filter(p=>p.source!=='aprs'&&now-new Date(p.time)<10*60000).length;
$('nAprs').textContent=s.positions.filter(p=>p.source==='aprs').length;
for(const p of s.positions){const ll=[p.lat,p.lon];pts.push(ll);const k=p.device_id;const aprs=p.source==='aprs';
if(!markers[k]){markers[k]=L.circleMarker(ll,{radius:aprs?6:8,color:aprs?'#ffb020':'#3dd6f5',fillOpacity:.9}).bindTooltip(esc(label(p)),{permanent:true,direction:'right'}).addTo(map);markers[k]._aprs=aprs;}else markers[k].setLatLng(ll);}
declutter();
applyView(s.view);
if(pts.length&&!map._fitted){map.fitBounds(pts,{padding:[40,40],maxZoom:15});map._fitted=true;}
$('msgs').innerHTML=s.messages.slice(-8).reverse().map(m=>'<div class="m '+(m.priority==='immediate'?'i':m.priority==='urgent'?'u':'')+'">'+hm(m.created_at)+' · <b>'+esc(m.sender_id)+'</b> : '+esc(m.body)+'</div>').join('');
$('log').innerHTML=s.logbook.slice(-8).reverse().map(l=>'<div class="m">'+hm(l.time)+' · '+esc(l.summary)+'</div>').join('');
const recent=s.messages.filter(m=>m.priority==='immediate'&&Date.now()-new Date(m.created_at)<10*60000).pop();
$('alert').style.display=recent?'block':'none';if(recent)$('alert').textContent=recent.sender_id+' : '+recent.body;}
function start(){$('pair').style.display='none';$('app').style.display='grid';map=L.map('map',{zoomControl:false}).setView([46.6,2.4],6);
setBase(null);map.on('zoomend moveend',declutter);tick();setInterval(tick,1000);refresh();setInterval(refresh,10000);}
if(token)start();else pair();
</script></body></html>"""
