// Standalone Browser Preview & Simulator for Hush (hussh.tech)
// Operates without a backend server or Socket.IO connection.
const $=s=>document.querySelector(s), statusEl=$('#status'), button=$('#start'), gain=$('#gain'), nameInput=$('#micName');
const segments=Array.from({length:13},()=>{const e=document.createElement('div');e.className='seg';$('#meter').append(e);return e});
let stream,ctx,sampleTimer,wake,active=false,displayLevel=0,lastPaint=0,dbHistory=[],currentLevel=0;
let simulatedSources=[
  {id:'s1', name:'West Hallway (Simulated)', level:18},
  {id:'s2', name:'Lobby Desk (Simulated)', level:28}
];

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
 }
}

const roomHistory=new HistoryChart('Room history');
$('#roomHistory').append(roomHistory.el);
setInterval(()=>roomHistory.commit(true), 250);

function text(el,value){if(el.textContent!==String(value))el.textContent=value}
function updateGain(){ $('#gainLabel').textContent=(+gain.value>=0?'+':'')+gain.value+' dB'}
gain.oninput=updateGain;updateGain();

async function keepAwake(){try{wake=await navigator.wakeLock.request('screen')}catch{}}

function stop(){
  active=false;clearInterval(sampleTimer);
  stream?.getTracks().forEach(t=>t.stop());stream=null;ctx?.close();ctx=null;wake?.release();
  button.textContent='Start microphone';$('#calibrate').disabled=true;dbHistory=[];currentLevel=0;
  text($('#myLevel'),'Microphone is off');
}

button.onclick=async()=>{
  if(active){stop();return}
  button.disabled=true;$('#micError').hidden=true;
  try {
    if(!navigator.mediaDevices?.getUserMedia)throw Error('Microphone access requires HTTPS.');
    stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
    ctx=new AudioContext();await ctx.resume();
    const analyser=ctx.createAnalyser();analyser.fftSize=2048;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const samples=new Float32Array(analyser.fftSize);
    active=true;dbHistory=[];button.textContent='Stop microphone';$('#calibrate').disabled=false;
    await keepAwake();
    sampleTimer=setInterval(()=>{
      analyser.getFloatTimeDomainData(samples);
      let sum=0;for(const s of samples)sum+=s*s;
      const db=20*Math.log10(Math.max(1e-6,Math.sqrt(sum/samples.length)));
      dbHistory.push(db);if(dbHistory.length>12)dbHistory.shift();
      currentLevel=Math.max(0,Math.min(100,(db+60+Number(gain.value))/60*100));
    },100);
  } catch(e) {
    stop();$('#micError').textContent=e.message;$('#micError').hidden=false;
  } finally {
    button.disabled=false;
  }
};

$('#calibrate').onclick=()=>{
  if(dbHistory.length<5){$('#calibrationStatus').textContent='Listening... try again in a moment.';return}
  const baseline=dbHistory.reduce((a,b)=>a+b,0)/dbHistory.length;
  gain.value=Math.max(-35,Math.min(40,Math.round(-42-baseline)));updateGain();
  $('#calibrationStatus').textContent='Baseline calibrated. Sensitivity adjusted.';
};

function paint(){
  const now=Date.now();
  if(now-lastPaint<100)return;
  lastPaint=now;

  // Add slight ambient variation to simulated sources
  simulatedSources[0].level=Math.max(12, Math.min(32, Math.round(18 + Math.sin(now/1500)*6)));
  simulatedSources[1].level=Math.max(18, Math.min(42, Math.round(26 + Math.cos(now/2000)*8)));

  const all=[...simulatedSources];
  if(active){
    all.push({id:'local', name:nameInput.value || 'Your Microphone', level:Math.round(currentLevel), isMe:true});
  }

  const loudest=all.reduce((max,s)=>s.level>max.level?s:max, all[0]);
  displayLevel+=(loudest.level-displayLevel)*0.65;
  const reading=Math.round(displayLevel);

  roomHistory.observe(reading);

  segments.forEach((e,i)=>{
    const next='seg'+(i<Math.round(reading*13/100)?' on'+(i>9?' hot':''):'');
    if(e.className!==next)e.className=next;
  });

  text($('#reading'), reading);
  const isAlert=reading>=80;
  $('#loud').hidden=!isAlert;
  $('#meter').hidden=isAlert;

  text($('#arrayCount'), `${all.length} microphone sources (1 local, ${simulatedSources.length} simulated)`);
  text($('#location'), `Loudest source: ${loudest.name}`);
  if(active) text($('#myLevel'), `Your microphone: ${Math.round(currentLevel)}/100`);

  // Render sources list
  const container=$('#sources');
  container.innerHTML='';
  all.forEach(s=>{
    const row=document.createElement('div');
    row.className='source'+(s===loudest?' leading':'');
    const label=document.createElement('span');
    label.textContent=s.name+(s.isMe?' (You)':'');
    const val=document.createElement('b');
    val.textContent=s.level;
    const track=document.createElement('div');track.className='track';
    const fill=document.createElement('div');fill.className='fill';
    fill.style.width=s.level+'%';
    track.append(fill);
    row.append(label,val,track);
    container.append(row);
  });
}
setInterval(paint, 50);

