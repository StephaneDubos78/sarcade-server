"""Smart TV and big screens (« Affichage sur Smart TV et grand écran »).

- ``/tv``: full-screen read-only page for the TV (served on tv.sarcade.org,
  without Cloudflare Access): asks a pairing code, then shows the event.
- ``/tv/approve?code=…``: page opened by the QR code on a phone signed in
  (Access); the PCO chooses the event and approves.
- API: pairing, approval (PCO), state read by the TV, list and revocation
  of the screens of an event (PCO)."""
import secrets
import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sarcade import tv
from sarcade.db.models import EventRow, LogbookRow, MessageRow, PositionRow
from sarcade.updates.service import get_value, set_value

from .deps import get_db
from .roles import require_pco
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
def approve(body: ApproveIn, db: Session = Depends(get_db), pco: str | None = Depends(require_pco)):
    event = db.get(EventRow, body.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    p = tv.store.approve(body.code, body.event_id)
    if p is None:
        raise HTTPException(status_code=404, detail="unknown_code")
    db.add(LogbookRow(event_id=body.event_id, kind="display", object_id=None, actor_id=(pco or "PCO")[:64],
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
                      .order_by(LogbookRow.seq.desc()).limit(12)).all()
    logbook = [{"time": r.time, "actor_id": r.actor_id, "summary": r.summary} for r in reversed(logs)]
    return tv.snapshot({"id": event.id, "name": event.name}, positions, messages, logbook)


@router.get("/api/v0.1/events/{event_id}/displays")
def list_displays(event_id: str, db: Session = Depends(get_db), _pco: str | None = Depends(require_pco)):
    now = time.time()
    return [{"id": d["id"], "code": d.get("code"), "created": d["created"], "expires": d["expires"],
             "active": not d.get("revoked") and d["expires"] > now}
            for d in _displays(db) if d.get("event_id") == event_id]


@router.delete("/api/v0.1/events/{event_id}/displays/{display_id}", status_code=204)
def revoke_display(event_id: str, display_id: str, db: Session = Depends(get_db), pco: str | None = Depends(require_pco)):
    displays = _displays(db)
    for d in displays:
        if d["id"] == display_id and d.get("event_id") == event_id:
            d["revoked"] = True
            set_value(db, KEY, displays)
            db.add(LogbookRow(event_id=event_id, kind="display", object_id=None, actor_id=(pco or "PCO")[:64],
                              summary=f"Écran d'affichage révoqué (code {d.get('code')})", time=datetime.now(UTC)))
            db.commit()
            return
    raise HTTPException(status_code=404, detail="display_not_found")


@router.get("/tv/approve")
def approve_page(code: str = "", db: Session = Depends(get_db)):
    events = db.scalars(select(EventRow).where(EventRow.ended_at.is_(None)).order_by(EventRow.created_at.desc())).all()
    options = "".join(f'<option value="{e.id}">{_esc(e.name)}</option>' for e in events)
    return HTMLResponse(_APPROVE.replace("__CODE__", _esc(code)[:12]).replace("__OPTIONS__", options), headers=NO_STORE)


@router.get("/tv")
def tv_page():
    return HTMLResponse(_TV.replace("__NONCE__", secrets.token_hex(4)), headers=NO_STORE)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_APPROVE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>SARCADE · écran</title>
<style>body{font-family:system-ui,sans-serif;max-width:420px;margin:40px auto;padding:0 16px;color:#1b2430}
h1{font-size:22px}label{display:block;margin:14px 0 4px;font-weight:600}input,select,button{font-size:17px;width:100%;padding:10px;box-sizing:border-box;border-radius:10px;border:1px solid #b9c6d2}
button{background:#0b4f8a;color:#fff;border:0;margin-top:18px}#r{margin-top:16px}</style></head><body>
<h1>Afficher SARCADE sur un écran</h1>
<p>Choisissez l'événement à afficher sur la TV, puis validez.</p>
<label for="c">Code affiché sur la TV</label><input id="c" value="__CODE__" autocapitalize="characters">
<label for="e">Événement</label><select id="e">__OPTIONS__</select>
<button id="b">Afficher sur la TV</button><p id="r"></p>
<script>document.getElementById('b').onclick=async()=>{const r=await fetch('/api/v0.1/tv/approve',{method:'POST',
headers:{'content-type':'application/json'},body:JSON.stringify({code:document.getElementById('c').value,event_id:document.getElementById('e').value})});
document.getElementById('r').textContent=r.ok?'C\\u2019est fait : la TV affiche l\\u2019événement.':(r.status==403?'Réservé au PCO.':'Code inconnu ou expiré.');};</script>
</body></html>"""

_TV = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>SARCADE · affichage</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>html,body{margin:0;height:100%;background:#070b10;color:#e6eef5;font-family:system-ui,sans-serif}
#pair{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:18px}
#code{font-size:96px;letter-spacing:12px;font-weight:700;color:#3dd6f5}#qr{background:#fff;padding:12px;border-radius:12px}
#app{display:none;height:100%;grid-template-columns:1fr 34%;grid-template-rows:56px 1fr}
header{grid-column:1/3;display:flex;align-items:center;padding:0 20px;font-size:24px;font-weight:600;border-bottom:1px solid #1e2c38}
#map{height:100%}aside{overflow:hidden;padding:12px 16px;border-left:1px solid #1e2c38;font-size:20px}
h2{font-size:16px;color:#b9c6d2;text-transform:uppercase;letter-spacing:1px;margin:14px 0 6px}
.m{padding:6px 0;border-bottom:1px solid #16212b}.u{color:#ffb020}.i{color:#ff4d5e;font-weight:700}
#alert{display:none;position:fixed;left:0;right:0;top:0;padding:18px;background:#ff4d5e;color:#fff;font-size:30px;font-weight:700;text-align:center;z-index:2000}
</style></head><body>
<div id="pair"><div>Pour afficher SARCADE, saisissez ce code dans l'application (Paramètres › Événement › Écrans) ou scannez le QR code</div>
<div id="code">······</div><div id="qr"></div><div id="hint"></div></div>
<div id="app"><header id="title">SARCADE</header><div id="map"></div><aside><h2>Messages</h2><div id="msgs"></div><h2>Main courante</h2><div id="log"></div></aside></div>
<div id="alert"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const $=id=>document.getElementById(id);let token=localStorage.getItem('sarcade_tv_token');let map,markers={};
const appHost=location.hostname.replace(/^tv\\./,'app.');
function hm(t){const d=new Date(t);return d.toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});}
async function pair(){const r=await fetch('/api/v0.1/tv/pair',{method:'POST'});if(!r.ok){$('hint').textContent='Réessai dans une minute…';setTimeout(pair,60000);return;}
const p=await r.json();$('code').textContent=p.code;$('qr').innerHTML='';new QRCode($('qr'),{text:'https://'+appHost+'/tv/approve?code='+p.code,width:220,height:220});
const until=Date.now()+p.expires_in*1000;const poll=async()=>{if(Date.now()>until){pair();return;}
const s=await fetch('/api/v0.1/tv/pair/'+p.pair_id);if(s.ok){const j=await s.json();if(j.status==='approved'){token=j.token;localStorage.setItem('sarcade_tv_token',token);start();return;}}
setTimeout(poll,3000);};poll();}
async function refresh(){const r=await fetch('/api/v0.1/tv/state',{headers:{authorization:'Display '+token}});
if(r.status===401){localStorage.removeItem('sarcade_tv_token');location.reload();return;}if(!r.ok)return;const s=await r.json();
$('title').textContent='SARCADE · '+s.event.name;const pts=[];
for(const p of s.positions){const ll=[p.lat,p.lon];pts.push(ll);const k=p.device_id;
if(!markers[k])markers[k]=L.circleMarker(ll,{radius:8,color:'#3dd6f5',fillOpacity:.9}).bindTooltip(k,{permanent:true,direction:'right'}).addTo(map);else markers[k].setLatLng(ll);}
if(pts.length&&!map._fitted){map.fitBounds(pts,{padding:[40,40],maxZoom:15});map._fitted=true;}
$('msgs').innerHTML=s.messages.slice(-8).reverse().map(m=>'<div class="m '+(m.priority==='immediate'?'i':m.priority==='urgent'?'u':'')+'">'+hm(m.created_at)+' · <b>'+m.sender_id+'</b> : '+m.body.replace(/</g,'&lt;')+'</div>').join('');
$('log').innerHTML=s.logbook.slice(-8).reverse().map(l=>'<div class="m">'+hm(l.time)+' · '+l.summary.replace(/</g,'&lt;')+'</div>').join('');
const recent=s.messages.filter(m=>m.priority==='immediate'&&Date.now()-new Date(m.created_at)<10*60000).pop();
$('alert').style.display=recent?'block':'none';if(recent)$('alert').textContent=recent.sender_id+' : '+recent.body;}
function start(){$('pair').style.display='none';$('app').style.display='grid';map=L.map('map',{zoomControl:false}).setView([46.6,2.4],6);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(map);refresh();setInterval(refresh,10000);}
if(token)start();else pair();
</script></body></html>"""
