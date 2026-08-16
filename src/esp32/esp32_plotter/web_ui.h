#pragma once
#include <pgmspace.h>

// Single-page drawing UI. __BED_W__ / __BED_H__ substituted at request time.
const char WEB_UI[] PROGMEM = R"HTML(<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>DVD Plotter</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:#0b0e13;color:#e6edf3;font:15px system-ui,sans-serif;
display:flex;flex-direction:column;align-items:center;height:100vh;overflow:hidden}
h1{font-size:15px;font-weight:600;margin:10px 0 2px;letter-spacing:.02em}
#st{font-size:13px;color:#8b98a5;margin-bottom:8px;height:18px}
canvas{background:#12151a;border-radius:10px;touch-action:none;
box-shadow:0 0 0 1px #263040,0 8px 24px #0006}
#bar{display:flex;gap:8px;margin:12px 0;flex-wrap:wrap;justify-content:center}
button{background:#1c2330;color:#e6edf3;border:1px solid #2d3748;padding:11px 18px;
border-radius:8px;font-size:14px;font-weight:500}
button:active{background:#28313f}
button:disabled{opacity:.4}
#go{background:#1f6feb;border-color:#1f6feb}
#halt{background:#8b2c2c;border-color:#8b2c2c}
</style></head><body>
<h1>DVD Plotter</h1><div id="st">ready</div>
<canvas id="c"></canvas>
<div id="bar">
<button onclick="undo()">Undo</button>
<button onclick="wipe()">Clear</button>
<button id="go" onclick="plot()">Plot</button>
<button id="halt" onclick="halt()">Stop</button>
</div>
<script>
const BED_W=__BED_W__,BED_H=__BED_H__,c=document.getElementById('c'),x=c.getContext('2d'),st=document.getElementById('st');
let strokes=[],cur=null,busy=false;

function fit(){
 const maxW=innerWidth-24,maxH=innerHeight-190;
 const s=Math.min(maxW/BED_W,maxH/BED_H);
 c.width=Math.floor(BED_W*s);c.height=Math.floor(BED_H*s);draw();
}
function draw(){
 x.fillStyle='#12151a';x.fillRect(0,0,c.width,c.height);
 x.strokeStyle='#7fd1ff';x.lineWidth=2.5;x.lineCap='round';x.lineJoin='round';
 for(const s of strokes){if(s.length<2)continue;
  x.beginPath();x.moveTo(s[0][0],s[0][1]);
  for(let i=1;i<s.length;i++)x.lineTo(s[i][0],s[i][1]);x.stroke()}
}
function at(e){const r=c.getBoundingClientRect();return[e.clientX-r.left,e.clientY-r.top]}
c.onpointerdown=e=>{if(busy)return;c.setPointerCapture(e.pointerId);cur=[at(e)];strokes.push(cur)};
c.onpointermove=e=>{if(!cur)return;const p=at(e),l=cur[cur.length-1];
 if(Math.hypot(p[0]-l[0],p[1]-l[1])>1.5){cur.push(p);draw()}};
c.onpointerup=c.onpointercancel=()=>{cur=null};
function undo(){if(busy)return;strokes.pop();draw()}
function wipe(){if(busy)return;strokes=[];draw()}

function rdp(p,eps){
 if(p.length<3)return p;
 const[ax,ay]=p[0],[bx,by]=p[p.length-1],dx=bx-ax,dy=by-ay,L=Math.hypot(dx,dy)||1;
 let dm=0,k=0;
 for(let i=1;i<p.length-1;i++){
  const d=Math.abs((p[i][0]-ax)*dy-(p[i][1]-ay)*dx)/L;
  if(d>dm){dm=d;k=i}}
 return dm>eps?rdp(p.slice(0,k+1),eps).slice(0,-1).concat(rdp(p.slice(k),eps))
              :[p[0],p[p.length-1]];
}
function gcode(){
 const sx=BED_W/c.width,sy=BED_H/c.height,out=['G21','G90','M300 S50'];
 const m=p=>[(p[0]*sx).toFixed(2),((c.height-p[1])*sy).toFixed(2)];
 for(let s of strokes){
  s=rdp(s,1.5);if(s.length<2)continue;
  let[a,b]=m(s[0]);out.push('G0 X'+a+' Y'+b,'M300 S30');
  for(let i=1;i<s.length;i++){[a,b]=m(s[i]);out.push('G1 X'+a+' Y'+b+' F300')}
  out.push('M300 S50')}
 out.push('G0 X0 Y0','M18');return out.join('\n')+'\n';
}
async function plot(){
 if(busy)return;
 if(!strokes.length){st.textContent='draw something first';return}
 st.textContent='sending';
 try{const r=await fetch('/plot',{method:'POST',body:gcode()});
  st.textContent=await r.text()}catch(e){st.textContent='send failed'}
}
async function halt(){try{await fetch('/stop',{method:'POST'})}catch(e){}}
setInterval(async()=>{
 try{const j=await(await fetch('/status')).json();
  busy=j.active;
  st.textContent=j.active?'plotting '+j.pct+'%':'ready';
  document.getElementById('go').disabled=j.active;
 }catch(e){st.textContent='no connection'}
},1000);
addEventListener('resize',fit);fit();
</script></body></html>)HTML";
