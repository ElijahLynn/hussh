const socket=io({transports:['websocket','polling']});
const $=s=>document.querySelector(s), statusEl=$('#status'),button=$('#start'),gain=$('#gain'),nameInput=$('#micName');
const segments=Array.from({length:13},()=>{const e=document.createElement('div');e.className='seg';$('#meter').append(e);return e});
let stream,ctx,sampleTimer,wake,active=false,pending=false,pendingAt=0,lastStateAt=0,lastPaint=0,displayLevel=0,dbHistory=[];
let state={level:0,count:0,microphones:[],loudest:null,alert:false,board_ok:false};
const rows=new Map();
let lastNumbers=0;
function text(el,value){if(el.textContent!==String(value))el.textContent=value}

// Thirty seconds of quarter-second peak buckets. Missing readings stay blank.
class HistoryChart {
 constructor(label){
  this.label=label;this.values=Array(120).fill(null);this.pending=null;
  this.el=document.createElement('div');this.el.className='history';
  const caption=document.createElement('div');caption.className='history-caption';caption.textContent=label+' · last 30 seconds';
  const ns='http://www.w3.org/2000/svg';this.svg=document.createElementNS(ns,'svg');this.svg.setAttribute('viewBox','0 0 240 52');this.svg.setAttribute('preserveAspectRatio','none');this.svg.setAttribute('role','img');
  for(const y of [13,26,39]){const line=document.createElementNS(ns,'line');line.setAttribute('x1',0);line.setAttribute('x2',240);line.setAttribute('y1',y);line.setAttribute('y2',y);line.setAttribute('stroke','var(--chart-grid)');line.setAttribute('stroke-dasharray','2 3');this.svg.append(line)}
  this.paths=['var(--quiet)','var(--moderate)','var(--loud)'].map(color=>{const path=document.createElementNS(ns,'path');path.setAttribute('fill',color);this.svg.append(path);return path});
  const axis=document.createElement('div');axis.className='history-axis';const before=document.createElement('span'),after=document.createElement('span');before.textContent='30s ago';after.textContent='now · 0–100';axis.append(before,after);
  this.el.append(caption,this.svg,axis);this.draw();
 }
 observe(value){if(Number.isFinite(value))this.pending=Math.max(this.pending??0,Math.max(0,Math.min(100,value)))}
 commit(live){this.values.shift();this.values.push(live?this.pending:null);this.pending=null;this.draw()}
 draw(){
  const paths=['','',''];
  this.values.forEach((v,i)=>{if(v===null)return;const height=Math.max(1,v*.52);const group=v>=75?2:v>=45?1:0;paths[group]+=`M${i*2},${52-height}h1.5v${height}h-1.5z`;});
  this.paths.forEach((path,i)=>{if(path.getAttribute('d')!==paths[i])path.setAttribute('d',paths[i])});
  const latest=this.values[this.values.length-1];this.svg.setAttribute('aria-label',this.label+', last 30 seconds'+(latest===null?', no recent sample':', latest '+Math.round(latest)+' out of 100'));
 }
}
const roomHistory=new HistoryChart('Room history');$('#roomHistory').append(roomHistory.el);
setInterval(()=>{const live=socket.connected&&Date.now()-lastStateAt<2500;roomHistory.commit(live);for(const row of rows.values())row.history.commit(live)},250);
function saved(key,fallback){try{return localStorage.getItem(key)??fallback}catch{return fallback}}
function save(key,value){try{localStorage.setItem(key,value)}catch{}}
nameInput.value=saved('vu-mic-name','');gain.value=saved('vu-mic-gain','0');
function updateGain(){ $('#gainLabel').textContent=(+gain.value>=0?'+':'')+gain.value+' dB';save('vu-mic-gain',gain.value)}
gain.oninput=updateGain;updateGain();
function identify(){save('vu-mic-name',nameInput.value);if(socket.connected)socket.emit('identify',{name:nameInput.value})}
nameInput.onchange=identify;
socket.on('connect',()=>{pending=false;identify();statusEl.textContent='Connected. Waiting for array readings…'});
socket.on('disconnect',()=>{pending=false;statusEl.textContent='Connection lost. Reconnecting…'});
socket.on('ack',()=>pending=false);
socket.on('array_state',data=>{state=data;lastStateAt=Date.now();roomHistory.observe(data.level);for(const mic of data.microphones){const row=rows.get(mic.id);if(row)row.history.observe(mic.level)}});
async function keepAwake(){try{wake=await navigator.wakeLock.request('screen')}catch{}}
function stop(){active=false;pending=false;clearInterval(sampleTimer);stream?.getTracks().forEach(t=>t.stop());stream=null;ctx?.close();ctx=null;wake?.release();button.textContent='Start microphone';$('#calibrate').disabled=true;dbHistory=[];if(socket.connected)socket.emit('stop_microphone',{});}
button.onclick=async()=>{
 if(active){stop();return}button.disabled=true;$('#micError').hidden=true;
 try{
  if(!navigator.mediaDevices?.getUserMedia)throw Error('Microphone requires HTTPS. Open the secure demo link.');
  stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
  ctx=new AudioContext();await ctx.resume();const analyser=ctx.createAnalyser();analyser.fftSize=2048;ctx.createMediaStreamSource(stream).connect(analyser);const samples=new Float32Array(analyser.fftSize);
  active=true;pending=false;dbHistory=[];button.textContent='Stop microphone';$('#calibrate').disabled=false;identify();await keepAwake();
  sampleTimer=setInterval(()=>{
   analyser.getFloatTimeDomainData(samples);let sum=0;for(const s of samples)sum+=s*s;
   const db=20*Math.log10(Math.max(1e-6,Math.sqrt(sum/samples.length)));dbHistory.push(db);if(dbHistory.length>12)dbHistory.shift();
   const level=Math.max(0,Math.min(100,(db+60+Number(gain.value))/60*100));
   if(socket.connected&&(!pending||Date.now()-pendingAt>1000)){
    pending=true;pendingAt=Date.now();socket.volatile.emit('level',{level,name:nameInput.value});
   }
  },100);
 }catch(e){stop();$('#micError').textContent=e.message;$('#micError').hidden=false;}finally{button.disabled=false}
};
$('#calibrate').onclick=()=>{
 if(dbHistory.length<5){$('#calibrationStatus').textContent='Let the microphone listen for a second, then try again.';return}
 const baseline=dbHistory.reduce((a,b)=>a+b,0)/dbHistory.length;
 gain.value=Math.max(-35,Math.min(40,Math.round(-42-baseline)));updateGain();
 $('#calibrationStatus').textContent='Background sensitivity adjusted. Compare phones and fine-tune with the slider if needed.';
};
function paint(){
 const now=Date.now();if(now-lastPaint<100)return;lastPaint=now;
 const live=socket.connected&&now-lastStateAt<2500;
 displayLevel+=(state.level-displayLevel)*0.65;
 const reading=live?Math.round(displayLevel):0;
 segments.forEach((e,i)=>{const next='seg'+(live&&i<Math.round(reading*13/100)?' on'+(i>9?' hot':''):'');if(e.className!==next)e.className=next});
 const updateNumbers=now-lastNumbers>=250;if(updateNumbers){lastNumbers=now;text($('#reading'),live?reading:'—');}$('#loud').hidden=!(live&&state.alert);$('#meter').hidden=live&&state.alert;
 text($('#arrayCount'),live?`${state.count} active microphone${state.count===1?'':'s'}`:'Waiting for connection');
 text($('#location'),live&&state.loudest?`Loudest location: ${state.loudest.name}`:'Start a microphone to join the array');
 const mine=state.microphones.find(m=>m.id===socket.id);
 if(updateNumbers)text($('#myLevel'),active?(mine?`Your microphone: ${mine.level}/100`:'Your microphone is joining…'):'Viewing the array · your microphone is off');
 text(statusEl,!socket.connected?'Connection lost. Reconnecting…':!live?'Waiting for live readings…':!state.board_ok?'Phones connected · Arduino is reconnecting…':`Live → Arduino · ${active?'Your microphone is contributing':'Viewer mode'}`);
 const ids=new Set();
 for(const mic of live?state.microphones:[]){
  ids.add(mic.id);let row=rows.get(mic.id);
  if(!row){const el=document.createElement('div');el.className='source';const label=document.createElement('span'),value=document.createElement('b'),track=document.createElement('div'),fill=document.createElement('div');track.className='track';fill.className='fill';track.append(fill);const history=new HistoryChart('Microphone history');history.observe(mic.level);el.append(label,value,track,history.el);$('#sources').append(el);row={el,label,value,fill,history};rows.set(mic.id,row)}
  text(row.label,mic.name+(mic.id===socket.id?' (you)':''));if(updateNumbers)text(row.value,mic.level);row.fill.style.width=mic.level+'%';row.el.classList.toggle('leading',state.loudest?.id===mic.id);
 }
 for(const [id,row] of rows){if(!ids.has(id)){row.el.remove();rows.delete(id)}}
 $('#empty').hidden=live&&state.count>0;
}
setInterval(paint,50);
document.addEventListener('visibilitychange',()=>{if(active&&document.visibilityState==='visible')keepAwake()});
