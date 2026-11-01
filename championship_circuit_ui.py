'''Straight-lane championship playback and its dependency-free controller.'''
from __future__ import annotations

import html

NOTES = {
    'sprint_2026': ('Sprint schedule: 2026 F1 venues, unless explicitly set in Excel. China · Miami · Canada · Britain · Netherlands · Singapore.', 'Sprints: circuitos da F1 2026, salvo indicação explícita no Excel. China · Miami · Canadá · Grã-Bretanha · Países Baixos · Singapura.'),
    'history_unavailable': ('Race-by-race playback is unavailable. Choose saved standings in the race selector to inspect the published results.', 'Reprodução por corrida indisponível. Seleciona a classificação guardada para consultar os resultados publicados.'),
    'calendar_unavailable': ('The season calendar is unavailable or ambiguous. Remaining points and distances cannot be calculated.', 'O calendário não está disponível ou é ambíguo. Não é possível calcular os pontos restantes e as distâncias.'),
    'scoring_unavailable': ('The scoring rules cannot be verified. Configure league scoring to calculate remaining points; no target has been assumed.', 'Não foi possível verificar a pontuação. Configura as regras da liga para calcular os pontos restantes; não foi presumido um objetivo.'),
    'no_drivers': ('No drivers are recorded for this league yet.', 'Ainda não há pilotos registados nesta liga.'),
    'archive_calendar': ('Archived season: the calendar uses the published round order and recorded Sprints. No future races have been assumed.', 'Época arquivada: o calendário usa as rondas publicadas e os Sprints registados. Não foram presumidas corridas futuras.'),
    'final_calendar_unavailable': ('The race calendar is unavailable. Final distances use the published completed-season standings.', 'O calendário não está disponível. As distâncias finais usam a classificação publicada da época concluída.'),
    'final_scoring_unavailable': ('Historical scoring rules cannot be verified. Only the published final standings are shown.', 'Não foi possível verificar a pontuação histórica. É apresentada apenas a classificação final publicada.'),
    'final_history_unavailable': ('Race-by-race playback is unavailable. Showing the published final standings.', 'Reprodução por corrida indisponível. É apresentada a classificação final publicada.'),
}


def render(model: dict | None, lang='en') -> str:
    if model is None:
        return ''
    pt = lang == 'pt'
    esc = lambda value: html.escape(str(value), quote=True)
    title = 'Evolução do campeonato' if pt else 'Championship progress'
    saved_final = model.get('completedSeason') and model.get('playback') is False
    initial_title = ('Classificação guardada' if pt else 'Saved standings') if saved_final else ('Grelha de partida' if pt else 'Starting grid')
    meta = model['meta']
    catalog = model.get('catalog') or [{'key': '', 'label': ' · '.join(str(meta.get(k, '')) for k in ('Game', 'SeasonLabel', 'League Name'))}]
    options = ''.join(f'<option value="{esc(item["key"])}" {"selected" if item["key"] == model.get("selectedKey", "") else ""}>{esc(item["label"])}</option>' for item in catalog)
    note_keys = [('final_' + n) if n in ('calendar_unavailable', 'scoring_unavailable', 'history_unavailable') and model.get('completedSeason') else n for n in model['notes']]
    notes = ''.join(f'<p class="cc-note {"cc-warning" if n != "sprint_2026" else ""}">{esc(NOTES[n][int(pt)])}</p>' for n in note_keys)
    return f'''{STYLE}
    <div class="p-section-label" id="championship"><span>04</span> {title.upper()}</div>
    <section class="cc" aria-label="{title}">
      <header class="cc-header"><div class="cc-heading">
        <h2 class="cc-race">{initial_title}</h2><p class="cc-round" aria-live="polite" aria-atomic="true"></p></div>
        <div class="cc-metrics"><div><span>{'Pontos da meta' if pt else 'Finish-line score'}</span><strong class="cc-target">—</strong></div>
        <div><span>{'Máximo ainda disponível' if pt else 'Maximum points remaining'}</span><strong class="cc-remaining">—</strong></div></div>
      </header>
      <div class="cc-controls"><div class="cc-buttons">
        <button class="cc-play cc-primary" type="button">{'Reproduzir' if pt else 'Play'}</button>
        <button class="cc-restart" type="button">{'Recomeçar' if pt else 'Restart'}</button>
        <button class="cc-prev" type="button" aria-label="{'Corrida anterior' if pt else 'Previous race'}">← <span>{'Anterior' if pt else 'Previous'}</span></button>
        <button class="cc-next" type="button" aria-label="{'Corrida seguinte' if pt else 'Next race'}"><span>{'Seguinte' if pt else 'Next'}</span> →</button>
      </div><label class="cc-season-label">{'Liga / época' if pt else 'League / season'}<select class="cc-season" aria-label="{'Selecionar liga e época' if pt else 'Select league and season'}" {'disabled' if len(catalog) < 2 else ''}>{options}</select></label>
      <label class="cc-race-select">{'Corrida' if pt else 'Race'}<select class="cc-select" aria-label="{'Selecionar corrida' if pt else 'Select race'}"></select></label>
      <label>{'Velocidade' if pt else 'Speed'}<select class="cc-speed" aria-label="{'Velocidade de reprodução' if pt else 'Playback speed'}"><option value="0.5">0.5×</option><option value="1">1×</option><option value="2" selected>2×</option></select></label></div>
      <label class="cc-timeline-label"><span>{'Época' if pt else 'Season timeline'}</span><input class="cc-timeline" type="range" min="0" max="0" value="0" aria-label="{'Linha temporal da época' if pt else 'Season timeline'}"/></label>
      <div class="cc-group-note">{'Colegas de equipa juntos · ordem alfabética fixa' if pt else 'Teammates together · fixed alphabetical order'}</div>
      <div class="cc-straight">
        <div class="cc-straight-heading"><span>{'Equipa' if pt else 'Team'}</span><span>{'Piloto' if pt else 'Driver'}</span><div class="cc-axis"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div><span>{'Pontos' if pt else 'Points'}</span></div>
        <div class="cc-lanes" role="group" aria-label="{'Progresso do campeonato por equipa' if pt else 'Championship progress by team'}"></div>
      </div>
      <div class="cc-driver-detail" aria-live="off"></div>
      <p class="cc-explanation">{'A meta representa os pontos do líder mais o máximo ainda disponível para um piloto. No fim da época, o campeão chega à meta.' if pt else 'The finish line represents the leader’s points plus the maximum points still available to one driver. At the end of the season, the champion reaches the finish line.'}</p>
      <p class="cc-note">{'As equipas refletem as atribuições mais recentes. A animação liga classificações publicadas; não representa posições durante um GP.' if pt else 'Teams reflect the latest assignments. Movement connects published standings; it does not represent positions during a GP.'}</p>
      {notes}
    </section>'''


STYLE = '''<style>
.cc{box-sizing:border-box;display:flex;flex-direction:column;height:var(--cc-height,calc(100svh - 145px));min-height:420px;max-height:1000px;margin:8px 28px 12px;padding:10px 14px;background:#11151c;border:1px solid #2c3440;border-radius:16px;color:#edf1f7;font:12px Inter,system-ui,sans-serif;overflow:hidden}.cc *{box-sizing:border-box}.cc [hidden]{display:none!important}
.cc-header{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:7px;flex-shrink:0}.cc-context{font-size:10px;color:#abb7c6;margin:0 0 2px}.cc .cc-race{font:750 19px Inter,system-ui;margin:0 0 2px;letter-spacing:-.03em}.cc-round{font-size:10px;color:#aeb9c9;min-height:14px;margin:0}.cc-metrics{display:flex;gap:20px;flex-shrink:0}.cc-metrics>div{display:flex;flex-direction:column;gap:3px}.cc-metrics span{font-size:9px;color:#b5c0cf}.cc-metrics strong{font-size:23px;font-variant-numeric:tabular-nums;letter-spacing:-.04em}.cc-target{color:#d9ed9c}
.cc-controls{display:flex;align-items:end;gap:10px;margin:0 0 5px;padding:5px 0;border-top:1px solid #2b3542;border-bottom:1px solid #2b3542;flex-shrink:0;flex-wrap:wrap}.cc-buttons{display:flex;gap:5px}.cc button:not(.cc-lane),.cc select{min-height:28px;padding:4px 9px;border:1px solid #414d60;border-radius:6px;background:#1b2430;color:#eef3fa;font:600 11px Inter,system-ui;cursor:pointer}.cc .cc-controls button.cc-primary{background:#e10600;border-color:#e10600;min-width:68px}.cc button:disabled,.cc select:disabled{opacity:.4;cursor:default}.cc button:focus-visible,.cc select:focus-visible,.cc input:focus-visible{outline:2px solid #d9ed9c;outline-offset:2px}.cc-controls label{display:flex;flex-direction:column;font-size:9px;color:#aab8cb;gap:2px}.cc-race-select{flex:1;min-width:160px}.cc-select{width:100%}.cc select{color-scheme:dark}.cc-timeline-label{display:flex;align-items:center;gap:12px;margin:0 0 4px;min-height:20px;font-size:10px;color:#abb7c9;flex-shrink:0}.cc-timeline{flex:1;width:0;min-height:20px;accent-color:#dcf3a0;cursor:pointer}.cc-group-note{font-size:9px;color:#aab8cb;margin-bottom:5px;flex-shrink:0}
.cc-heading{flex:1;min-width:0}.cc-season-label{flex:1;min-width:200px;max-width:420px}.cc .cc-season{width:100%;min-width:0}.cc-buttons{flex-shrink:0}
.cc-straight{display:flex;flex:1;flex-direction:column;min-height:0}.cc-straight-heading,.cc .cc-lane{display:grid;grid-template-columns:85px 140px minmax(0,1fr) 82px;gap:10px}.cc-straight-heading{font-size:9px;color:#aab8cb;padding:0 7px 4px;flex-shrink:0}.cc-straight-heading>span:last-child{text-align:right}.cc-axis{display:flex;justify-content:space-between;margin:0 17px}.cc-axis span{width:0;display:flex;justify-content:center;white-space:nowrap}.cc-lanes{position:relative;flex:1;min-height:0;border:1px solid #38434e;border-radius:8px;overflow:hidden;overflow-anchor:none}.cc .cc-lane{position:absolute;left:0;top:0;width:100%;height:calc((100% - 2px)/var(--cc-count));min-height:0;padding:0 7px;border:0;border-bottom:1px solid #36434b;border-radius:0;align-items:center;background:#29353b;text-align:left;color:#e5ebf4;font:11px Inter,system-ui;cursor:pointer;box-shadow:inset 3px 0 var(--driver-color)}.cc .cc-lane.cc-team-alt{background:#303d44}.cc .cc-lane.cc-team-start{border-top:1px solid #8a9ba377}.cc .cc-lane:hover,.cc .cc-lane[aria-pressed=true],.cc .cc-lane.cc-hover{background:#40514f}.cc .cc-lane:focus-visible{outline:2px solid #d9ed9c;outline-offset:-2px}.cc-team-label{font-size:9px;color:#bfcbd5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.cc-lane-name{font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cc-lane-track{position:relative;height:100%;min-height:0;margin:0 17px;background:repeating-linear-gradient(90deg,#ffffff22 0 1px,transparent 1px 25%);border-left:1px solid #bac7cd;border-right:3px solid #e5ecd8}.cc-lane-track:after{content:'';position:absolute;right:-5px;top:0;bottom:0;width:8px;background:repeating-conic-gradient(#eff3e9 0 25%,#263137 0 50%) 0 0/8px 8px}.cc-lane-trail{position:absolute;left:0;top:calc(50% - 2px);height:4px;background:var(--driver-color);opacity:.24;border-radius:3px}.cc-lane-car{position:absolute;top:50%;width:28px;height:100%;max-height:18px;transform:translate(-50%,-50%);overflow:visible;z-index:1;filter:drop-shadow(0 1px 1px #0008)}.cc-car-halo{fill:none;stroke:#fff;stroke-width:2;opacity:0}.cc-lane[aria-pressed=true] .cc-car-halo,.cc-lane.cc-hover .cc-car-halo,.cc-lane:focus-visible .cc-car-halo{opacity:1}.cc-lane.cc-finished .cc-car-halo{opacity:1;stroke:#d9ed9c}.cc-lane-score{display:flex;justify-content:end;gap:8px;align-items:center;font-variant-numeric:tabular-nums}.cc-lane-score b{font-size:10px}.cc-lane-score small{font-size:9px;color:#b6c4d2;min-width:23px;text-align:right}
.cc-driver-detail{display:flex;align-items:center;min-height:26px;flex-shrink:0;gap:6px;padding-top:5px;flex-wrap:nowrap}.cc-detail-name{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px}.cc-detail-stat{display:flex;flex-direction:column;min-width:45px;gap:1px}.cc-detail-stat span{font-size:8px;color:#9ba8bc}.cc-detail-stat b{font-size:10px;font-variant-numeric:tabular-nums}.cc-explanation{font-size:9px;color:#d0d8e3;line-height:1.3;margin:5px 0 0;flex-shrink:0}.cc-note{display:none}.cc-warning{display:block;color:#ffd49d;font-size:9px;line-height:1.25;padding:3px 5px;border-left:2px solid #f3bb75;background:#d3951910;margin:2px 0 0;flex-shrink:0}
@media(max-width:900px){.cc{margin-left:8px;margin-right:8px;padding:8px 10px}.cc-metrics strong{font-size:20px}.cc-straight-heading,.cc .cc-lane{grid-template-columns:70px 120px minmax(0,1fr) 70px;gap:7px}}
@media(max-width:520px){.cc{padding:7px 6px;min-height:450px;border-radius:12px}.cc-header{gap:6px;flex-wrap:wrap;margin-bottom:4px}.cc-context{font-size:8px}.cc .cc-race{font-size:15px}.cc-round{font-size:9px}.cc-metrics{width:100%;justify-content:space-between;gap:8px}.cc-metrics>div{flex-direction:row;align-items:center;gap:6px}.cc-metrics span{font-size:8px;max-width:80px}.cc-metrics strong{font-size:18px}.cc-controls{gap:4px;display:grid;grid-template-columns:minmax(0,1fr) 52px;padding:4px 0;margin-bottom:3px}.cc-buttons{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,1fr);gap:4px}.cc button:not(.cc-lane){min-height:27px;padding:3px;font-size:10px}.cc .cc-controls button.cc-primary{min-width:0}.cc-controls select{min-height:27px;padding:3px;font-size:10px}.cc-controls label{font-size:8px}.cc-race-select{min-width:0}.cc-timeline-label{font-size:9px;min-height:18px}.cc-group-note{font-size:8px;margin-bottom:4px}.cc-straight-heading,.cc .cc-lane{grid-template-columns:44px 82px minmax(0,1fr) 40px;gap:3px}.cc-straight-heading{padding-left:3px;padding-right:3px;font-size:8px}.cc .cc-lane{padding:0 3px;font-size:9px}.cc-team-label{font-size:8px}.cc-lane-name{font-size:9px}.cc-axis,.cc-lane-track{margin:0 10px}.cc-axis{font-size:8px}.cc-lane-car{width:22px;max-height:14px}.cc-lane-score{gap:3px}.cc-lane-score b{font-size:9px}.cc-lane-score small{font-size:7px;min-width:14px}.cc-driver-detail{gap:4px;min-height:26px}.cc-detail-name{font-size:9px}.cc-detail-stat{min-width:31px}.cc-detail-stat span{font-size:7px}.cc-detail-stat b{font-size:9px}.cc-explanation{font-size:8px;margin-top:3px}}
@media(prefers-reduced-motion:reduce){.cc *{scroll-behavior:auto!important;transition:none!important}}
@media(max-width:1000px){.cc-controls{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr) 58px}.cc-buttons{grid-column:1/-1}.cc-season-label{min-width:0;max-width:none}}
@media(max-width:520px){.cc-heading{width:100%;flex-basis:100%}.cc-controls{grid-template-columns:minmax(0,1.25fr) minmax(0,1fr) 44px}.cc-straight-heading,.cc .cc-lane{grid-template-columns:44px 82px minmax(0,1fr) 54px}.cc-lane-score{gap:2px}.cc-lane-score b{font-size:8px}}
</style>'''


JS = r'''
function championshipTeamOrder(drivers) {
  const clean=value=>String(value||'').normalize('NFKC').trim().replace(/\s+/g,' ');
  const compare=(a,b)=>a.localeCompare(b,'en',{sensitivity:'base',numeric:true})||a.localeCompare(b,'en');
  return [...drivers].sort((a,b)=>{
    const ta=clean(a.team),tb=clean(b.team);
    return Number(!ta)-Number(!tb)||compare(ta.toLocaleLowerCase('en'),tb.toLocaleLowerCase('en'))||compare(clean(a.name),clean(b.name))||compare(String(a.id),String(b.id));
  }).map(d=>d.id);
}
function championshipPlaybackFrames(model) {
  if(model.completedSeason&&model.playback===false)return [...model.frames];
  if(model.frames[0]?.name==='grid')return [...model.frames];
  // An explicit zero-point preview is not a reconstructed result or a guessed target.
  const grid={name:'grid',round:0,completed:0,target:null,remaining:null,remainingRaces:model.totalRaces,remainingSprints:0,
    standings:model.drivers.map((d,i)=>({id:d.id,position:i+1,points:0,gap:0,progress:0}))};
  return [grid,...model.frames];
}
function championshipSeries(values) {
  const delta=values.slice(1).map((v,i)=>v-values[i]);
  const slopes=values.map((_,i)=>{
    if(i===0||i===values.length-1)return 0;
    const a=delta[i-1],b=delta[i];return a*b>0?2*a*b/(a+b):0;
  });
  return cursor=>{
    if(values.length===1)return values[0];
    const x=Math.max(0,Math.min(values.length-1,cursor)),i=Math.min(values.length-2,Math.floor(x)),t=x-i,t2=t*t,t3=t2*t;
    return (2*t3-3*t2+1)*values[i]+(t3-2*t2+t)*slopes[i]+(-2*t3+3*t2)*values[i+1]+(t3-t2)*slopes[i+1];
  };
}
function advanceChampionship(cursor,elapsed,speed,last) {
  return Math.min(last,Math.max(0,cursor+Math.max(0,elapsed)*speed/2400));
}
function championshipCorrectionOpacity(values,at) {
  if(at>=values.length-1)return 1;
  const i=Math.floor(at),t=at-i;
  if(values[i+1]<values[i]&&t>.85)return Math.max(0,(1-t)/.15);
  if(i>0&&values[i]<values[i-1]&&t<.15)return t/.15;
  return 1;
}
function championshipForwardProgress(values,cursor) {
  const at=Math.max(0,Math.min(values.length-1,cursor)),i=Math.floor(at);
  return i<values.length-1&&values[i+1]<values[i]?values[i]:championshipSeries(values)(at);
}
function championshipSampler(frames,order) {
  const entries=frames.map(f=>new Map(f.standings.map(e=>[e.id,e])));
  const curves=new Map(order.map(id=>{
    const progress=entries.map(e=>Math.max(0,Math.min(1,e.get(id)?.progress||0)));
    return [id,{progress,sampleProgress:championshipSeries(progress),samplePoints:championshipSeries(entries.map(e=>e.get(id)?.points||0))}];
  }));
  return at=>new Map(order.map(id=>{
    const curve=curves.get(id),i=Math.floor(Math.max(0,Math.min(frames.length-1,at))),correcting=i<frames.length-1&&curve.progress[i+1]<curve.progress[i];
    return [id,{p:correcting?curve.progress[i]:curve.sampleProgress(at),points:curve.samplePoints(at),opacity:championshipCorrectionOpacity(curve.progress,at)}];
  }));
}
function mountChampionship(root,model,pt) {
  const section=root.querySelector('.cc');
  if(!section||!model?.frames?.length)return ()=>{};
  const q=s=>section.querySelector(s),NS='http://www.w3.org/2000/svg';
  const frames=championshipPlaybackFrames(model),order=championshipTeamOrder(model.drivers),drivers=new Map(model.drivers.map(d=>[d.id,d]));
  const lanes=new Map(),entries=frames.map(f=>new Map(f.standings.map(e=>[e.id,e])));
  const reduce=window.matchMedia('(prefers-reduced-motion: reduce)');
  const canPlay=model.playback&&frames.length>1;
  const numberFormat=new Intl.NumberFormat(pt?'pt-PT':'en-GB',{maximumFractionDigits:2});
  const fmt=n=>n==null?'—':numberFormat.format(Math.abs(n)<.000001?0:n);
  const team=d=>d.team||(pt?'Sem equipa':'Unassigned');
  const raceName=f=>f.name==='grid'?(pt?'Grelha de partida':'Starting grid'):f.name==='current'?(pt?'Classificação guardada':'Saved standings'):f.name;
  const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;};
  const svg=(tag,attrs={})=>{const e=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));return e;};
  let index=0,cursor=0,playing=false,started=false,selected=order[0],hovered=null,raf=0,focusRaf=0,lastTime=0,speed=2,disposed=false,motion=null;
  let positions=new Map();
  const sample=championshipSampler(frames,order),detailValues=new Map();
  const leaderPoints=()=>positions.size?Math.max(...[...positions.values()].map(p=>p.points)):0;
  function paintDetail(){
    const id=hovered||selected,p=positions.get(id),e=entries[index].get(id);if(!p||!e)return;
    const gap=Math.max(0,leaderPoints()-p.points);
    [['points',fmt(p.points)],['gap',gap?`\u2212${fmt(gap)}`:'—'],['progress',e.progress==null?'—':`${fmt(p.p*100)}%`]].forEach(([key,value])=>{const node=detailValues.get(key);if(node)node.textContent=value;});
  }
  function state(){q('.cc-play').textContent=playing?(pt?'Pausar':'Pause'):(pt?'Reproduzir':'Play');q('.cc-play').setAttribute('aria-pressed',String(playing));section.dataset.playing=String(playing);}
  function showDriver(){
    const id=hovered||selected,d=drivers.get(id),e=entries[index].get(id);if(!d||!e)return;
    lanes.forEach((row,key)=>{row.setAttribute('aria-pressed',String(key===selected));row.classList.toggle('cc-hover',key===hovered);});
    const detail=q('.cc-driver-detail');detail.replaceChildren();detailValues.clear();
    const name=el('strong','cc-detail-name',`${d.name} · ${team(d)}`);name.style.borderLeft=`3px solid ${d.teamColor||d.color}`;name.style.paddingLeft='7px';detail.append(name);
    [['position',pt?'Posição':'Position',frames[index].name==='grid'?'—':`P${e.position}`],['points',pt?'Pontos':'Points','0'],
     ['gap',pt?'Diferença':'Gap','—'],['progress',pt?'Progresso':'Progress','0%']].forEach(([key,label,value])=>{
      const stat=el('div','cc-detail-stat'),number=el('b',`cc-detail-${key}`,value);stat.append(el('span','',label),number);detail.append(stat);detailValues.set(key,number);
    });section.dataset.selectedDriver=id;paintDetail();
  }
  function select(id,temporary=false){if(temporary)hovered=id;else{selected=id;hovered=null;}showDriver();}
  let lastTeam=null,group=-1;
  order.forEach((id,i)=>{
    const d=drivers.get(id),teamKey=String(d.team||'').trim().toLocaleLowerCase('en'),newTeam=teamKey!==lastTeam;
    if(newTeam){group++;lastTeam=teamKey;}
    const row=el('button','cc-lane');row.type='button';row.dataset.driverId=id;row.dataset.lane=String(i+1);row.dataset.team=d.team||'';
    row.style.transform=`translateY(${i*100}%)`;row.style.setProperty('--driver-color',d.teamColor||d.color);
    row.classList.toggle('cc-team-alt',group%2===1);row.classList.toggle('cc-team-start',newTeam&&i>0);
    row.append(el('span','cc-team-label',team(d)),el('span','cc-lane-name',d.name));
    const track=el('span','cc-lane-track'),trail=el('span','cc-lane-trail');track.append(trail);
    const car=svg('svg',{class:'cc-lane-car',viewBox:'-23 -15 46 30','aria-hidden':'true'}),body=svg('g');
    body.append(svg('rect',{class:'cc-car-halo',x:-20,y:-12,width:39,height:24,rx:5}));
    [[-14,-10,8,5],[-14,5,8,5],[7,-10,7,5],[7,5,7,5]].forEach(([x,y,width,height])=>body.append(svg('rect',{x,y,width,height,rx:1,fill:'#071014',stroke:'#91a4aa','stroke-width':.6})));
    const color=d.teamColor||d.color;
    body.append(svg('path',{d:'M-15-5L-5-6 4-4 15-2 17 0 15 2 4 4-5 6-15 5Z',fill:color,stroke:'#e5f1ed','stroke-width':.7}),
      svg('rect',{x:-15,y:-9,width:3,height:18,rx:1,fill:color}),svg('rect',{x:12,y:-8,width:3,height:16,rx:1,fill:color}),svg('ellipse',{cx:-3,cy:0,rx:4,ry:3,fill:'#17242e'}));
    car.append(body);track.append(car);row.append(track);
    const score=el('span','cc-lane-score');score.append(el('b','cc-lane-points','0'),el('small','cc-lane-gap','—'));row.append(score);
    row.addEventListener('click',()=>select(id));row.addEventListener('focus',()=>select(id));
    row.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')select(id,true);});row.addEventListener('pointerleave',()=>{hovered=null;showDriver();});
    lanes.set(id,row);q('.cc-lanes').append(row);
  });
  q('.cc-lanes').style.setProperty('--cc-count',String(order.length));
  frames.forEach((f,i)=>{const option=el('option','',`${f.round?`R${f.round} · `:''}${raceName(f)}`);option.value=String(i);q('.cc-select').append(option);});
  q('.cc-timeline').max=String(frames.length-1);
  function paint(next){
    positions=next;const leader=leaderPoints();
    positions.forEach((p,id)=>{
      const row=lanes.get(id),d=drivers.get(id),e=entries[index].get(id),gap=Math.max(0,leader-p.points);
      row.querySelector('.cc-lane-car').style.left=`${p.p*100}%`;row.querySelector('.cc-lane-car').style.opacity=String(p.opacity??1);row.querySelector('.cc-lane-trail').style.width=`${p.p*100}%`;
      row.dataset.visualProgress=String(p.p);row.dataset.animatedPoints=String(p.points);
      row.querySelector('.cc-lane-points').textContent=fmt(p.points);row.querySelector('.cc-lane-gap').textContent=gap?`\u2212${fmt(gap)}`:'—';
      const description=`${d.name}, ${team(d)}, ${fmt(p.points)} ${pt?'pontos':'points'}, ${frames[index].name==='grid'?raceName(frames[index]):`P${e.position}`}, ${pt?'diferença':'gap'} ${fmt(gap)}, ${e.progress==null?'—':fmt(p.p*100)+'%'}`;
      row.setAttribute('aria-label',description);row.title=description;
    });paintDetail();
  }
  function display(next){
    index=next;const frame=frames[index],grid=frame.name==='grid';section.dataset.frame=String(index);section.dataset.grid=String(grid);
    q('.cc-race').textContent=raceName(frame);q('.cc-round').textContent=model.completedSeason&&frame.name==='current'?(pt?'Época concluída · classificação guardada':'Season complete · saved standings'):model.completedSeason&&!model.totalRaces?(pt?'Prévia da grelha · seleciona a classificação guardada':'Grid preview · choose saved standings'):`${frame.round?`${pt?'Ronda':'Round'} ${frame.round} · `:''}${frame.completed} / ${model.totalRaces} ${pt?'corridas concluídas':'races completed'}`;
    q('.cc-target').textContent=fmt(frame.target);q('.cc-remaining').textContent=fmt(frame.remaining);
    q('.cc-select').value=String(index);q('.cc-timeline').value=String(index);q('.cc-timeline').setAttribute('aria-valuetext',raceName(frame));
    q('.cc-prev').disabled=index===0;q('.cc-next').disabled=index===frames.length-1;
    order.forEach(id=>{
      const e=entries[index].get(id),row=lanes.get(id);if(!e)return;
      row.dataset.progress=String(e.progress??'');row.dataset.position=grid?'':String(e.position);
      row.classList.toggle('cc-finished',e.progress===1&&frame.remaining===0&&frame.target>0);
    });showDriver();
  }
  function transition(active){section.dataset.transition=String(active);}
  function tick(now){
    if(disposed)return;const elapsed=Math.max(0,now-lastTime);lastTime=now;
    if(motion?.running){
      motion.elapsed+=elapsed;const t=Math.min(1,motion.elapsed/600),ease=t*t*(3-2*t),next=new Map();
      motion.to.forEach((to,id)=>{const from=motion.from.get(id)||to;next.set(id,{...to,p:from.p+(to.p-from.p)*ease,points:from.points+(to.points-from.points)*ease});});paint(next);
      if(t===1){motion=null;transition(false);}
    }else if(playing){
      cursor=advanceChampionship(cursor,elapsed,speed,frames.length-1);
      const checkpoint=reduce.matches?Math.floor(cursor):Math.ceil(cursor-1e-9),changed=checkpoint!==index;
      if(changed)display(checkpoint);if(!reduce.matches||changed)paint(sample(reduce.matches?checkpoint:cursor));
      transition(!reduce.matches&&cursor<frames.length-1);
      if(cursor===frames.length-1){playing=false;paint(sample(cursor));transition(false);state();}
    }
    section.dataset.cursor=String(cursor);if(playing||motion?.running)raf=requestAnimationFrame(tick);
  }
  function run(){cancelAnimationFrame(raf);lastTime=performance.now();raf=requestAnimationFrame(tick);}
  function pause(){playing=false;cancelAnimationFrame(raf);if(motion)motion.running=false;state();}
  function reset(){motion=null;cursor=0;display(0);paint(sample(0));section.dataset.cursor='0';transition(false);}
  q('.cc-play').addEventListener('click',()=>{if(playing){pause();return;}if(!started||cursor>=frames.length-1)reset();started=true;playing=true;if(motion)motion.running=true;state();run();});
  q('.cc-restart').addEventListener('click',()=>{pause();started=true;reset();});
  const seek=i=>{pause();started=true;cursor=Math.max(0,Math.min(frames.length-1,i));display(cursor);section.dataset.cursor=String(cursor);const to=sample(cursor);
    if(!canPlay||reduce.matches||!positions.size||[...to].some(([id,p])=>p.p<positions.get(id).p)){motion=null;paint(to);transition(false);}
    else{motion={from:new Map(positions),to,elapsed:0,running:true};transition(true);run();}
  };
  q('.cc-prev').addEventListener('click',()=>seek(index-1));q('.cc-next').addEventListener('click',()=>seek(index+1));
  q('.cc-select').addEventListener('change',e=>seek(Number(e.target.value)));q('.cc-timeline').addEventListener('input',e=>seek(Number(e.target.value)));
  q('.cc-speed').addEventListener('change',e=>{speed=Number(e.target.value)||2;});
  q('.cc-season').addEventListener('change',e=>{
    if(!(model.catalog||[]).some(item=>item.key===e.target.value))return;
    pause();const url=new URL(window.location.href);url.searchParams.set('championship',e.target.value);url.hash='championship';window.location.assign(url.href);
  });
  q('.cc-play').disabled=!canPlay;q('.cc-speed').disabled=!canPlay;
  ['.cc-restart','.cc-select','.cc-timeline'].forEach(s=>q(s).disabled=frames.length<=1);
  const onMotion=()=>{if(reduce.matches){motion=null;cursor=index;paint(sample(index));transition(false);}};reduce.addEventListener('change',onMotion);
  const onVisibility=()=>{if(document.hidden)pause();};document.addEventListener('visibilitychange',onVisibility);
  function fit(){const nav=root.querySelector('nav[aria-label="Season sections"]'),chrome=(nav?.getBoundingClientRect().height||70)+(window.innerWidth<520?112:80);section.style.setProperty('--cc-height',`${Math.max(420,window.innerHeight-chrome)}px`);}
  fit();window.addEventListener('resize',fit);display(0);paint(sample(0));section.dataset.cursor='0';transition(false);state();
  if(model.selectedKey&&window.location.hash==='#championship')focusRaf=requestAnimationFrame(()=>{const heading=root.querySelector('#championship');if(heading){heading.style.scrollMarginTop=`${(root.querySelector('nav[aria-label="Season sections"]')?.getBoundingClientRect().height||70)+8}px`;heading.scrollIntoView({block:'start',behavior:'instant'});}});
  return ()=>{disposed=true;cancelAnimationFrame(raf);cancelAnimationFrame(focusRaf);window.removeEventListener('resize',fit);reduce.removeEventListener('change',onMotion);document.removeEventListener('visibilitychange',onVisibility);};
}
'''
