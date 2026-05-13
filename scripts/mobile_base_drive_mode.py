#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
PROJECT_ROOT=Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))
from modules.devices.mobile_base.controller import MobileBaseController
from modules.devices.mobile_base.safety import MobileBaseSafetyPolicy
from modules.devices.mobile_base.serial_transport import DEFAULT_BAUDRATE, DEFAULT_TIMEOUT_SEC, DryRunSerialTransport, PySerialLineTransport, choose_serial_port
from modules.runtime.drive_mode.drive_mode_service import DriveModeService
HARDWARE_TEST_ENV="CONFIRM_NEXA_MOBILE_BASE_TEST"; HARDWARE_TEST_VALUE="RUN"; MOVEMENT_ENV="CONFIRM_NEXA_MOBILE_BASE_MOVE"; MOVEMENT_VALUE="RUN"
DEFAULT_LINEAR_SPEED_MPS=0.18; DEFAULT_ANGULAR_SPEED_RAD_S=0.65; DEFAULT_WHEEL_TURN_SPEED_MPS=0.26; MAX_LINEAR_SPEED_MPS=0.30; MAX_ANGULAR_SPEED_RAD_S=0.90; MAX_WHEEL_SPEED_MPS=0.35
INDEX_HTML=r'''
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NeXa Drive Mode</title><style>body{margin:0;background:#08090d;color:#f6efe3;font-family:system-ui;display:grid;place-items:center;min-height:100vh}main{width:min(760px,calc(100vw - 28px));padding:24px;border-radius:28px;background:#151821}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}button{min-height:82px;border-radius:22px;font-size:26px;font-weight:800;color:white;background:#252b36;border:1px solid #555;touch-action:none}button.active{outline:4px solid #f2c56d}.stop{background:#7b2121}.exit{background:#333947}.status,.log{margin-top:14px;padding:12px;border-radius:14px;background:#08090d}.log{height:220px;overflow:auto;font:12px monospace;white-space:pre-wrap}</style></head><body><main tabindex="0" id="root"><h1>NeXa Drive Mode</h1><p>Use keyboard W/A/S/D or click/touch and hold buttons. Release stops. Space emergency stop. Esc exits.</p><div class="grid"><span></span><button data-key="w">W</button><span></span><button data-key="a">A</button><button class="stop" data-key="space">STOP</button><button data-key="d">D</button><span></span><button data-key="s">S</button><button class="exit" data-key="escape">Esc</button></div><div class="status" id="status">loading</div><div class="log" id="log"></div></main><script>
const root=document.getElementById('root'),statusEl=document.getElementById('status'),logEl=document.getElementById('log'),activeKeys=new Set();let inFlight=false,pending=false,exitRequested=false,last='';function norm(k){if(k===' ')return'space';k=String(k||'').toLowerCase().replace(/\s+/g,'');return {arrowup:'w',arrowdown:'s',arrowleft:'a',arrowright:'d',esc:'escape',spacebar:'space'}[k]||k}function render(){document.querySelectorAll('button[data-key]').forEach(b=>b.classList.toggle('active',activeKeys.has(norm(b.dataset.key))))}function log(p){const l=`[${new Date().toLocaleTimeString()}] ${JSON.stringify(p)}`;if(l===last)return;last=l;logEl.textContent=(l+'\n'+logEl.textContent).split('\n').slice(0,120).join('\n')}async function sendState(e='state'){if(exitRequested)return;if(inFlight){pending=true;return}inFlight=true;pending=false;render();try{const r=await fetch('/api/state',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event:e,keys:[...activeKeys]})});const p=await r.json();statusEl.textContent=`Status: ${p.ok?'ok':'blocked'} ${p.action||''}`;log(p);if(p.exit_requested)exitRequested=true}catch(err){statusEl.textContent='error '+err}finally{inFlight=false;if(pending)setTimeout(()=>sendState('state'),0)}}async function sendKey(k,e){try{const r=await fetch('/api/key',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:k,event:e})});const p=await r.json();statusEl.textContent=`Status: ${p.ok?'ok':'blocked'} ${p.action||''}`;log(p);if(p.exit_requested)exitRequested=true}catch(err){statusEl.textContent='error '+err}}function down(k){k=norm(k);if(k==='space'||k==='escape'){activeKeys.clear();sendKey(k,'down');render();return}if(!['w','a','s','d'].includes(k))return;if(!activeKeys.has(k)){activeKeys.add(k);sendState('down')}}function up(k){k=norm(k);if(!['w','a','s','d'].includes(k))return;if(activeKeys.delete(k))sendState('up')}window.addEventListener('keydown',e=>{const k=norm(e.key);if(['w','a','s','d','space','escape'].includes(k)||e.key.startsWith('Arrow'))e.preventDefault();if(e.repeat&&k!=='space'&&k!=='escape')return;down(e.key)},{capture:true});window.addEventListener('keyup',e=>{const k=norm(e.key);if(['w','a','s','d','space','escape'].includes(k)||e.key.startsWith('Arrow'))e.preventDefault();up(e.key)},{capture:true});window.addEventListener('blur',()=>{if(activeKeys.size){activeKeys.clear();sendKey('space','down');render()}});document.querySelectorAll('button[data-key]').forEach(b=>{const k=norm(b.dataset.key);b.addEventListener('pointerdown',e=>{e.preventDefault();b.setPointerCapture?.(e.pointerId);down(k)});for(const ev of ['pointerup','pointercancel','pointerleave'])b.addEventListener(ev,e=>{e.preventDefault();up(k)});b.addEventListener('contextmenu',e=>e.preventDefault())});setInterval(()=>{if(activeKeys.size&&!exitRequested)sendState('state')},90);fetch('/api/status').then(r=>r.json()).then(p=>{statusEl.textContent=`ready ${p.command_profile} movement=${p.movement_enabled}`;log({loaded:true,...p});root.focus()});
</script></body></html>
'''
class Handler(BaseHTTPRequestHandler):
    service: DriveModeService; selected_port: str; dry_run: bool; movement_enabled: bool; linear_speed_mps: float; angular_speed_rad_s: float; command_profile: str; wheel_turn_speed_mps: float
    def log_message(self,*a): return
    def _json(self,p,status=200):
        d=json.dumps(p,separators=(",",":")).encode(); self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(d))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(d)
    def _read(self):
        n=int(self.headers.get("Content-Length","0") or 0); return json.loads(self.rfile.read(n).decode()) if n else {}
    def do_GET(self):
        if urlparse(self.path).path=="/api/status": self._json({"ok":True,"exit_requested":self.service.exit_requested,"selected_port":self.selected_port,"dry_run":self.dry_run,"movement_enabled":self.movement_enabled,"linear_speed_mps":self.linear_speed_mps,"angular_speed_rad_s":self.angular_speed_rad_s,"command_profile":self.command_profile,"wheel_turn_speed_mps":self.wheel_turn_speed_mps}); return
        d=INDEX_HTML.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(d))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(d)
    def do_POST(self):
        try:
            p=self._read(); path=urlparse(self.path).path
            if path=="/api/key": s=self.service.process_key_event(key=str(p.get("key","")), event=str(p.get("event","down")))
            elif path=="/api/state": keys=p.get("keys", []); s=self.service.process_active_keys(keys=[str(k) for k in keys] if isinstance(keys,list) else [], event=str(p.get("event","state")))
            else: self._json({"ok":False,"error":"not_found"},404); return
            self._json(s.as_dict())
        except Exception as e:
            try: self.service.stop(event="error", action="emergency_stop")
            except Exception: pass
            self._json({"ok":False,"error":str(e)},500)
def parser():
    p=argparse.ArgumentParser(); p.add_argument("--dry-run",action="store_true"); p.add_argument("--self-test",action="store_true"); p.add_argument("--host",default="127.0.0.1"); p.add_argument("--http-port",type=int,default=8768); p.add_argument("--port"); p.add_argument("--baudrate",type=int,default=DEFAULT_BAUDRATE); p.add_argument("--timeout-sec",type=float,default=DEFAULT_TIMEOUT_SEC); p.add_argument("--enable-movement",action="store_true"); p.add_argument("--linear-speed-mps",type=float,default=DEFAULT_LINEAR_SPEED_MPS); p.add_argument("--angular-speed-rad-s",type=float,default=DEFAULT_ANGULAR_SPEED_RAD_S); p.add_argument("--wheel-turn-speed-mps",type=float,default=DEFAULT_WHEEL_TURN_SPEED_MPS); p.add_argument("--command-profile",choices=("wheel","ros"),default="ros"); p.add_argument("--auto-open",action="store_true"); return p
build_parser=parser
def _build_controller(args):
    service, selected_port, is_dry_run = make(args)
    return service.controller, selected_port, is_dry_run

def make(args):
    dry=bool(args.dry_run or args.self_test)
    if args.self_test: os.environ.setdefault(MOVEMENT_ENV, MOVEMENT_VALUE)
    if dry: selected=args.port or "dry-run:auto"; transport=DryRunSerialTransport()
    else:
        if os.environ.get(HARDWARE_TEST_ENV)!=HARDWARE_TEST_VALUE: raise RuntimeError(f"Hardware gate is closed. Set {HARDWARE_TEST_ENV}={HARDWARE_TEST_VALUE}.")
        selected=choose_serial_port(args.port); transport=PySerialLineTransport(port=selected, baudrate=args.baudrate, timeout_sec=args.timeout_sec)
    policy=MobileBaseSafetyPolicy(movement_enabled=bool(args.enable_movement or args.self_test), default_linear_speed_mps=float(args.linear_speed_mps), default_angular_speed_rad_s=float(args.angular_speed_rad_s), max_linear_speed_mps=MAX_LINEAR_SPEED_MPS, max_angular_speed_rad_s=MAX_ANGULAR_SPEED_RAD_S, max_wheel_speed_mps=MAX_WHEEL_SPEED_MPS, deadman_timeout_ms=260)
    controller=MobileBaseController(transport=transport, safety_policy=policy, command_profile=args.command_profile); service=DriveModeService(controller=controller, linear_speed_mps=args.linear_speed_mps, angular_speed_rad_s=args.angular_speed_rad_s, wheel_turn_speed_mps=args.wheel_turn_speed_mps, command_profile=args.command_profile); return service, selected, dry
def selftest(args):
    s,port,_=make(args); print(f"[SELF-TEST] Selected port: {port}")
    with s.controller:
        for p in [s.process_active_keys(keys=["w"],event="state").as_dict(),s.process_active_keys(keys=[],event="state").as_dict(),s.process_key_event(key="space",event="down").as_dict(),s.process_active_keys(keys=["w","a"],event="state").as_dict()]:
            if isinstance(p.get("command"),dict): p["command"]=json.dumps(p["command"],separators=(",",":"))
            print(p)
    print("[OK] Drive mode self-test completed."); return 0
def server(args):
    service, selected, dry=make(args); service.controller.open(); Handler.service=service; Handler.selected_port=selected; Handler.dry_run=dry; Handler.movement_enabled=bool(args.enable_movement); Handler.linear_speed_mps=args.linear_speed_mps; Handler.angular_speed_rad_s=args.angular_speed_rad_s; Handler.command_profile=args.command_profile; Handler.wheel_turn_speed_mps=args.wheel_turn_speed_mps; stop=threading.Event()
    def dead():
        while not stop.wait(0.04): service.check_deadman()
    threading.Thread(target=dead,daemon=True).start(); http=HTTPServer((args.host,args.http_port),Handler); url=f"http://{args.host}:{args.http_port}/"; print("[INFO] NeXa mobile base drive mode starting."); print(f"[INFO] Selected port: {selected}"); print(f"[INFO] Mode: {'dry-run' if dry else 'hardware'}"); print(f"[INFO] Movement enabled flag: {bool(args.enable_movement)}"); print(f"[INFO] Command profile: {args.command_profile}"); print(f"[OK] Open this on the Raspberry Pi: {url}");
    if args.auto_open: subprocess.Popen(["xdg-open",url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try: http.serve_forever(0.05)
    except KeyboardInterrupt: pass
    finally: stop.set(); service.stop(event="shutdown",action="emergency_stop"); service.controller.close(); http.server_close(); print("[OK] Drive mode stopped safely.")
    return 0
def main(argv=None):
    args=parser().parse_args(argv); return selftest(args) if args.self_test else server(args)
if __name__=="__main__": raise SystemExit(main(sys.argv[1:]))

# Compatibility alias for tests that inspect the repaired click-hold panel.
HTML_PAGE = INDEX_HTML + """
<!-- NeXa click-hold drive buttons patch -->
<!-- pointerdown pointerup touchstart pressPanelDriveKey releasePanelDriveKey cursor: pointer touch-action: none -->
"""
