"""SVG championship view and its fixed, dependency-free browser controller."""
from __future__ import annotations

import html

TRACK = "M 510 492 L 790 492 C 929 492 938 356 842 292 L 755 244 C 694 216 668 246 597 233 C 546 222 529 174 480 154 C 420 128 334 132 278 104 C 209 75 144 66 119 113 C 78 170 147 216 170 242 C 207 288 144 319 124 359 C 68 429 117 492 210 492 L 510 492"

NOTES = {
    "sprint_2026": ("Sprint schedule: 2026 F1 venues, unless explicitly set in Excel. China · Miami · Canada · Britain · Netherlands · Singapore.",
                    "Sprints: circuitos da F1 2026, salvo indicação explícita no Excel. China · Miami · Canadá · Grã-Bretanha · Países Baixos · Singapura."),
    "history_unavailable": ("Race-by-race playback is unavailable: the published history is missing or does not reconcile with the calendar. Current published standings are shown.",
                            "Reprodução indisponível: faltam resultados por corrida ou não correspondem ao calendário. A mostrar a classificação publicada atual."),
    "calendar_unavailable": ("The season calendar is unavailable or ambiguous. Remaining points and circuit distances cannot be calculated; published standings are still shown.",
                             "O calendário não está disponível ou é ambíguo. Não é possível calcular os pontos restantes e as distâncias; a classificação publicada continua visível."),
    "scoring_unavailable": ("The scoring rules cannot be verified from this workbook. Configure the league scoring to calculate remaining points. No points target has been assumed.",
                            "Não foi possível verificar as regras de pontuação no Excel. Configura a pontuação da liga para calcular os pontos restantes. Não foi presumido um objetivo."),
    "no_drivers": ("No drivers are recorded for this league yet.", "Ainda não há pilotos registados nesta liga."),
}


def render(model: dict | None, lang="en") -> str:
    if model is None:
        return ""
    pt = lang == "pt"
    esc = lambda value: html.escape(str(value), quote=True)
    title = "O campeonato em pista" if pt else "Championship circuit"
    trees = ""
    # Deterministic small vector scenery; never used to position the data marks.
    for band, count in ((0, 32), (1, 22), (2, 16)):
        for i in range(count):
            x = 22 + ((i * 137 + band * 83) % 956)
            y = (25 + i % 4 * 9) if band == 0 else (590 + i % 3 * 17) if band == 1 else (265 + i % 3 * 22)
            if band == 2 and (x < 245 or x > 700):
                continue
            r = 10 + i % 4 * 2
            trees += f'<ellipse cx="{x+4}" cy="{y+6}" rx="{r}" ry="{r*.7}" fill="#0b1f18" opacity=".5"/><circle cx="{x}" cy="{y}" r="{r}" fill="{["#345d3e","#456e44","#597b4a"][i%3]}"/><circle cx="{x-3}" cy="{y-4}" r="{r*.6}" fill="#729259" opacity=".36"/>'
    notes = "".join(f'<p class="cc-note {"cc-warning" if n != "sprint_2026" else ""}">{esc(NOTES[n][int(pt)])}</p>' for n in model["notes"])
    meta = model["meta"]
    explanation = ("A meta representa os pontos do líder mais o máximo de pontos ainda disponível para um piloto. No fim da época, o campeão chega à meta." if pt else
                   "The finish line represents the leader’s points plus the maximum points still available to one driver. At the end of the season, the champion reaches the finish line.")
    return f'''{STYLE}
    <div class="p-section-label" id="championship"><span>04</span> {title.upper()}</div>
    <section class="cc" aria-label="{title}">
      <header class="cc-header"><div><p class="cc-context">{esc(meta.get('League Name',''))} · {esc(meta.get('SeasonLabel',''))}</p>
        <h2 class="cc-race">{'A carregar a classificação' if pt else 'Loading standings'}</h2><p class="cc-round" aria-live="polite" aria-atomic="true"></p></div>
        <div class="cc-metrics"><div><span>{'Pontos da meta' if pt else 'Finish-line score'}</span><strong class="cc-target">—</strong></div>
        <div><span>{'Máximo ainda disponível' if pt else 'Maximum points remaining'}</span><strong class="cc-remaining">—</strong></div></div>
      </header>
      <div class="cc-layout"><div class="cc-course">
        <div class="cc-map"><svg class="cc-svg" viewBox="0 0 1000 660" aria-label="{'Circuito virtual do campeonato' if pt else 'Virtual championship circuit'}" role="group">
          <defs><linearGradient id="cc-grass" x2=".8" y2="1"><stop stop-color="#35503c"/><stop offset="1" stop-color="#1c332e"/></linearGradient>
          <pattern id="cc-flag" width="14" height="14" patternUnits="userSpaceOnUse"><rect width="14" height="14" fill="#f4f6ed"/><path d="M0 0h7v7H0zM7 7h7v7H7z" fill="#182129"/></pattern>
          <filter id="cc-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-opacity=".4"/></filter></defs>
          <rect width="1000" height="660" rx="18" fill="url(#cc-grass)"/>
          <path d="M0 228 Q300 70 520 345T1000 570 M0 370Q310 210 500 420T1000 630" fill="none" stroke="#688666" stroke-width="45" opacity=".10"/>
          <path d="{TRACK}" fill="#2d4837" stroke="#b7a985" stroke-width="86" stroke-linejoin="round"/>
          <path d="{TRACK}" fill="none" stroke="#e6e6d7" stroke-width="61"/>
          <path d="{TRACK}" fill="none" stroke="#c34942" stroke-width="61" stroke-dasharray="15 15"/>
          <path d="{TRACK}" fill="none" stroke="#cdd0c7" stroke-width="51"/>
          <path class="cc-track" d="{TRACK}" fill="none" stroke="#424b50" stroke-width="47"/>
          <path d="{TRACK}" fill="none" stroke="#9ba49f" stroke-opacity=".24" stroke-width="1" stroke-dasharray="8 10"/>
          <path d="M270 492L340 548H665Q698 548 735 493" fill="none" stroke="#b7bab1" stroke-width="15"/>
          <path d="M270 492L340 548H665Q698 548 735 493" fill="none" stroke="#5c6668" stroke-width="11"/>
          <path d="M340 548H660" stroke="#dfdfca" stroke-width="1" stroke-dasharray="10 8"/>
          <g aria-hidden="true">{trees}<rect x="371" y="565" width="250" height="18" rx="3" fill="#142523"/>
            <path d="M374 559h242v15H374z" fill="#8b9686"/><path d="M385 561h35m8 0h35m8 0h35m8 0h35m8 0h35" stroke="#e5dfbe" stroke-width="8"/>
            <path d="M30 270l39-75 15 8-39 75zM826 190l75 42-8 15-75-42z" fill="#9da894"/><path d="M31 266l36-69m762-5 70 39" stroke="#c56850" stroke-width="10"/></g>
          <rect x="503" y="467" width="14" height="50" fill="url(#cc-flag)"/>
          <path d="M548 492h22m-7-6 7 6-7 6" fill="none" stroke="#ffffff" stroke-width="2" opacity=".65"/>
          <text x="510" y="618" text-anchor="middle" class="cc-map-caption">{'PARTIDA / META' if pt else 'START / FINISH'}</text>
          <g class="cc-grid-dock" hidden><rect x="255" y="285" width="490" height="156" rx="12" fill="#10231feb" stroke="#9ab09a" stroke-opacity=".5"/>
            <path d="M510 441v25" stroke="#ced7bd" stroke-dasharray="3 4"/>
            <text x="500" y="307" text-anchor="middle" class="cc-dock-caption">{'GRELHA · TODOS COM 0 PONTOS' if pt else 'STARTING GRID · ALL ON 0 POINTS'}</text></g>
          <g class="cc-anchors" aria-hidden="true" pointer-events="none"></g><g class="cc-cars"></g>
        </svg><span class="cc-transition" hidden>{'Transição entre classificações' if pt else 'Standings transition'}</span></div>
        <div class="cc-driver-detail" aria-live="off"></div>
      </div>
      <div class="cc-board"><div class="cc-board-heading"><h3>{'Classificação' if pt else 'Standings'}</h3><span>{'Pontos / diferença' if pt else 'Points / gap'}</span></div>
        <div class="cc-list" role="group" aria-label="{'Selecionar piloto' if pt else 'Select driver'}"></div>
      </div></div>
      <div class="cc-controls"><div class="cc-buttons">
        <button class="cc-play cc-primary" type="button">{'Reproduzir' if pt else 'Play'}</button>
        <button class="cc-restart" type="button">{'Recomeçar' if pt else 'Restart'}</button>
        <button class="cc-prev" type="button" aria-label="{'Corrida anterior' if pt else 'Previous race'}">← <span>{'Anterior' if pt else 'Previous'}</span></button>
        <button class="cc-next" type="button" aria-label="{'Corrida seguinte' if pt else 'Next race'}"><span>{'Seguinte' if pt else 'Next'}</span> →</button>
      </div><label class="cc-race-select">{'Corrida' if pt else 'Race'}<select class="cc-select" aria-label="{'Selecionar corrida' if pt else 'Select race'}"></select></label>
      <label>{'Velocidade' if pt else 'Speed'}<select class="cc-speed" aria-label="{'Velocidade de reprodução' if pt else 'Playback speed'}"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select></label></div>
      <label class="cc-timeline-label"><span>{'Época' if pt else 'Season timeline'}</span><input class="cc-timeline" type="range" min="0" max="0" value="0" aria-label="{'Linha temporal da época' if pt else 'Season timeline'}"/></label>
      <p class="cc-explanation">{explanation}</p>
      <p class="cc-note cc-opportunities"></p>
      <p class="cc-note">{'Calendário e resultados publicados, incluindo correções. As animações ligam classificações confirmadas; não representam posições ou ultrapassagens durante um GP. As linhas finas marcam a distância exata dos carros afastados lateralmente.' if pt else 'Published calendar and results, including corrections. Movement connects confirmed standings; it does not represent live positions or overtakes in a GP. Fine lines mark the exact points position of cars offset sideways.'}</p>
      {notes}
    </section>'''


STYLE = '''<style>
.cc{margin:18px 28px 32px;padding:24px;background:#11151c;border:1px solid #2c3440;border-radius:18px;color:#edf1f7;font:14px Inter,system-ui,sans-serif;box-sizing:border-box}
.cc *{box-sizing:border-box}.cc-header{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:22px}.cc-context{margin:0 0 6px;color:#abb7c6;font-size:12px}.cc .cc-race{font:750 clamp(18px,2vw,26px) Inter,system-ui;margin:0 0 6px;letter-spacing:-.03em}.cc-round{font-size:12px;color:#aeb9c9;margin:0;min-height:18px}
.cc-metrics{display:flex;gap:30px;flex-shrink:0}.cc-metrics>div{display:flex;flex-direction:column;gap:4px}.cc-metrics span{font-size:11px;color:#b5c0cf}.cc-metrics strong{font-size:28px;letter-spacing:-.04em;font-variant-numeric:tabular-nums}.cc-target{color:#d9ed9c}
.cc-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(235px,28%);gap:22px;align-items:start}.cc-course{min-width:0}.cc-map{position:relative;overflow:hidden;border-radius:14px;background:#223c30}.cc-svg{display:block;width:100%;height:auto;overflow:visible}.cc-map-caption{fill:#d4ddca;font:600 15px Inter,system-ui;letter-spacing:3px}.cc-dock-caption{fill:#e3ead9;font:600 13px Inter,system-ui;letter-spacing:1px}.cc-grid-dock[hidden]{display:none}
.cc-car{cursor:pointer;outline:none}.cc-car .cc-car-body{filter:url(#cc-shadow)}.cc-car .cc-car-halo{fill:none;stroke:#fff;stroke-width:2;opacity:0}.cc-car[aria-pressed=true] .cc-car-halo,.cc-car:focus-visible .cc-car-halo,.cc-car.cc-hover .cc-car-halo{opacity:1}.cc-car.cc-finished .cc-car-halo{opacity:1;stroke:#e2f3a3;stroke-width:3}.cc-car text{fill:#f6f8fc;font:750 12px Inter,system-ui;paint-order:stroke;stroke:#172328;stroke-width:3;stroke-linejoin:round}.cc-car .cc-label-bg{fill:#0b141bdd;stroke:#bbc7cc55;stroke-width:.7}.cc-car.cc-finished .cc-label-bg{stroke:#d9ed9c;stroke-width:2}.cc-car .cc-hit{fill:transparent}.cc-transition{position:absolute;left:12px;top:12px;background:#14242de8;border-radius:5px;padding:5px 8px;color:#e1e9f0;font-size:11px;pointer-events:none}
.cc-driver-detail{min-height:74px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 2px 0;font-size:12px;color:#c0c9d6}.cc-driver-detail strong{font-size:14px;color:#f5f7fc}.cc-driver-detail .cc-detail-name{display:block;flex:1 1 160px}.cc-driver-detail .cc-detail-stat{display:flex;flex-direction:column;gap:3px;min-width:52px}.cc-detail-stat span{font-size:10px;color:#9ba8bc}.cc-detail-stat b{font-size:13px;color:#edf1f7;font-variant-numeric:tabular-nums}
.cc-board-heading{display:flex;justify-content:space-between;align-items:center;padding:0 2px 10px;border-bottom:1px solid #2b3542}.cc-board-heading h3{margin:0;font:650 14px Inter,system-ui}.cc-board-heading>span{font-size:10px;color:#a7b3c6}.cc-list{max-height:430px;overflow:auto;scrollbar-width:thin;scrollbar-color:#566372 #171d26;padding:6px 3px 4px 0}.cc-row{width:100%;display:grid;grid-template-columns:22px 8px minmax(0,1fr) auto;align-items:center;gap:8px;min-height:43px;padding:7px 8px;border:1px solid transparent;border-radius:7px;background:none;text-align:left;color:#e5ebf4;font:12px Inter,system-ui;cursor:pointer}.cc-row:hover,.cc-row[aria-pressed=true],.cc-row.cc-hover{background:#222d38;border-color:#50606c}.cc-row:focus-visible{outline:2px solid #d9ed9c;outline-offset:-2px}.cc-row .cc-pos{color:#8f9db1;font-variant-numeric:tabular-nums}.cc-row .cc-dot{width:6px;height:20px;border-radius:3px}.cc-row .cc-name{overflow-wrap:anywhere}.cc-row .cc-score{text-align:right;display:flex;gap:10px;align-items:center;font-variant-numeric:tabular-nums}.cc-row .cc-score small{font-size:10px;color:#9eafc3;min-width:24px}
.cc-controls{display:flex;align-items:end;gap:16px;margin-top:20px;padding-top:20px;border-top:1px solid #2b3542;flex-wrap:wrap}.cc-buttons{display:flex;gap:6px;flex-wrap:wrap}.cc button:not(.cc-row),.cc select{min-height:42px;border:1px solid #414d60;border-radius:7px;background:#1b2430;color:#eef3fa;font:600 12px Inter,system-ui;padding:9px 12px;cursor:pointer}.cc button.cc-primary{background:#e10600;border-color:#e10600;min-width:82px}.cc button:disabled,.cc select:disabled{opacity:.4;cursor:default}.cc button:focus-visible,.cc select:focus-visible,.cc input:focus-visible{outline:2px solid #d9ed9c;outline-offset:3px}.cc-controls label{display:flex;flex-direction:column;gap:5px;font-size:10px;color:#aab8cb}.cc-race-select{flex:1;min-width:170px}.cc-select{width:100%}.cc-controls select{color-scheme:dark}.cc-timeline-label{display:flex;align-items:center;gap:16px;color:#abb7c9;font-size:11px;margin:20px 0}.cc-timeline{flex:1;width:0;accent-color:#dcf3a0;cursor:pointer;min-height:24px}.cc-explanation{font-size:12px;color:#d0d8e3;line-height:1.65;margin:16px 0 8px;max-width:1000px}.cc-note{font-size:11px;color:#9caec0;line-height:1.6;margin:6px 0 0}.cc-warning{color:#ffd49d;padding:10px 12px;border-left:2px solid #f3bb75;background:#d3951910;margin-top:10px}
@media(min-width:1400px){.cc-list{max-height:530px}}
@media(max-width:900px){.cc{margin:16px 16px 28px;padding:18px}.cc-header{align-items:start;flex-wrap:wrap}.cc-metrics{gap:24px}.cc-metrics strong{font-size:24px}.cc-layout{grid-template-columns:1fr}.cc-list{max-height:265px;display:grid;grid-template-columns:1fr 1fr;gap:0 12px}.cc-board{margin-top:8px}}
@media(max-width:520px){.cc{margin:14px 8px 24px;padding:14px 10px;border-radius:12px}.cc-header{gap:16px}.cc-metrics{width:100%;justify-content:space-between;padding-top:10px;border-top:1px solid #2b3542}.cc-metrics span{font-size:10px}.cc-layout{gap:8px}.cc-list{grid-template-columns:1fr;max-height:258px}.cc-row{min-height:44px}.cc-controls{gap:12px}.cc-buttons{width:100%;display:grid;grid-template-columns:1fr 1fr 1fr 1fr}.cc button:not(.cc-row){padding:9px 4px;min-height:44px}.cc button.cc-primary{min-width:0}.cc-prev span,.cc-next span{font-size:10px}.cc-driver-detail{gap:12px 15px}.cc-driver-detail .cc-detail-name{flex-basis:100%}.cc-detail-stat{flex:1}.cc-timeline-label{gap:8px;font-size:10px}.cc-car text{font-size:16px}.cc-dock-caption{font-size:16px}}
@media(prefers-reduced-motion:reduce){.cc *{scroll-behavior:auto!important;transition:none!important}}
</style>'''


JS = r'''
function mountChampionship(root, model, pt) {
  const section = root.querySelector('.cc');
  if (!section || !model?.frames?.length) return () => {};
  const q = s => section.querySelector(s), NS = 'http://www.w3.org/2000/svg';
  const frames = model.frames, drivers = new Map(model.drivers.map(d => [d.id,d]));
  const path = q('.cc-track'), length = path.getTotalLength(), cars = new Map(), rows = new Map(), anchors = new Map();
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  const fmt = n => n == null ? '—' : new Intl.NumberFormat(pt?'pt-PT':'en-GB',{maximumFractionDigits:2}).format(n);
  const raceName = f => f.name==='grid' ? (pt?'Grelha de partida':'Starting grid') : f.name==='current' ? (pt?'Classificação atual':'Current standings') : f.name;
  const svgEl = (tag, attrs={}) => {const el=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));return el;};
  const htmlEl = (tag, cls, text) => {const el=document.createElement(tag);if(cls)el.className=cls;if(text!=null)el.textContent=text;return el;};
  let index=model.defaultIndex, playing=false, started=false, timer=0, raf=0, selected=frames[index].standings[0]?.id, hovered=null;
  let positions=new Map(), targetPositions=new Map(), speed=1, disposed=false;
  const stateLabel = () => {q('.cc-play').textContent=playing?(pt?'Pausar':'Pause'):(pt?'Reproduzir':'Play');q('.cc-play').setAttribute('aria-pressed',String(playing));section.dataset.playing=String(playing);};
  const selectDriver = (id, temporary=false) => {if(temporary)hovered=id;else{selected=id;hovered=null;}showDriver();};
  function showDriver() {
    const id=hovered||selected, d=drivers.get(id), entry=frames[index].standings.find(e=>e.id===id);
    if(!d||!entry)return;
    cars.forEach((car,key)=>{car.setAttribute('aria-pressed',String(key===selected));car.classList.toggle('cc-hover',key===hovered);});
    rows.forEach((row,key)=>{row.setAttribute('aria-pressed',String(key===selected));row.classList.toggle('cc-hover',key===hovered);});
    const detail=q('.cc-driver-detail');detail.replaceChildren();
    const name=htmlEl('strong','cc-detail-name',d.name);name.style.borderLeft=`3px solid ${d.color}`;name.style.paddingLeft='10px';detail.append(name);
    [[pt?'Posição':'Position',`P${entry.position}`],[pt?'Pontos':'Points',fmt(entry.points)],
     [pt?'Diferença':'Gap',entry.gap?`\u2212${fmt(entry.gap)}`:'—'],[pt?'Circuito':'Circuit',entry.progress==null?'—':`${fmt(entry.progress*100)}%`]].forEach(([label,value])=>{
      const stat=htmlEl('div','cc-detail-stat');stat.append(htmlEl('span','',label),htmlEl('b','',value));detail.append(stat);
    });
    section.dataset.selectedDriver=id;
  }
  model.drivers.forEach(d=>{
    const anchor=svgEl('g');anchor.append(svgEl('path',{fill:'none',stroke:d.color,'stroke-width':1.2,'stroke-opacity':.55,'stroke-dasharray':'3 4'}),svgEl('circle',{r:2.5,fill:d.color}));
    q('.cc-anchors').append(anchor);anchors.set(d.id,anchor);
    const car=svgEl('g',{class:'cc-car',tabindex:'0',role:'button','data-driver-id':d.id,'aria-pressed':'false'});
    const hit=svgEl('rect',{class:'cc-hit',x:-23,y:-24,width:64,height:46,rx:6});car.append(hit);
    const body=svgEl('g',{class:'cc-car-body'});
    body.append(svgEl('rect',{class:'cc-car-halo',x:-20,y:-12,width:39,height:24,rx:5}));
    [[-14,-10,8,5],[-14,5,8,5],[7,-10,7,5],[7,5,7,5]].forEach(([x,y,w,h])=>body.append(svgEl('rect',{x,y,width:w,height:h,rx:1,fill:'#071014',stroke:'#91a4aa','stroke-width':.6})));
    body.append(svgEl('path',{d:'M-15-5L-5-6 4-4 15-2 17 0 15 2 4 4-5 6-15 5Z',fill:d.color,stroke:'#e5f1ed','stroke-width':.7}),
      svgEl('rect',{x:-15,y:-9,width:3,height:18,rx:1,fill:d.color}),svgEl('rect',{x:12,y:-8,width:3,height:16,rx:1,fill:d.color}),
      svgEl('ellipse',{cx:-3,cy:0,rx:4,ry:3,fill:'#17242e'}));
    car.append(body);
    const label=svgEl('g',{class:'cc-car-label'});label.append(svgEl('rect',{class:'cc-label-bg',x:-20,y:-30,width:42,height:17,rx:3}));
    const text=svgEl('text',{x:1,y:-18,'text-anchor':'middle'});text.textContent=d.label;label.append(text);car.append(label);
    car.addEventListener('click',()=>selectDriver(d.id));car.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();selectDriver(d.id);}});
    car.addEventListener('focus',()=>selectDriver(d.id));car.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')selectDriver(d.id,true);});car.addEventListener('pointerleave',()=>{hovered=null;showDriver();});
    q('.cc-cars').append(car);cars.set(d.id,car);
    const row=htmlEl('button','cc-row');row.type='button';row.dataset.driverId=d.id;
    const dot=htmlEl('span','cc-dot');dot.style.background=d.color;
    const score=htmlEl('span','cc-score');score.append(htmlEl('b','cc-points'),htmlEl('small','cc-gap'));
    row.append(htmlEl('span','cc-pos'),dot,htmlEl('span','cc-name',d.name),score);
    row.addEventListener('click',()=>selectDriver(d.id));row.addEventListener('focus',()=>selectDriver(d.id));
    rows.set(d.id,row);
  });
  frames.forEach((f,i)=>{const option=htmlEl('option','',`${f.round?`R${f.round} · `:''}${raceName(f)}`);option.value=String(i);q('.cc-select').append(option);});
  q('.cc-timeline').max=String(frames.length-1);
  function layout(frame) {
    const result=new Map(), sorted=[...frame.standings].sort((a,b)=>(a.progress||0)-(b.progress||0)||a.position-b.position);
    // A full zero-point field is shown in an infield grid, tethered to the exact
    // start line. This avoids placing 22 indistinguishable cars on top of it.
    const tied=new Map();sorted.forEach(e=>{const key=String(e.progress||0);if(!tied.has(key))tied.set(key,[]);tied.get(key).push(e);});
    const dockGroup=[...tied.values()].sort((a,b)=>b.length-a.length)[0]||[];
    const grid=dockGroup.length>7, dockIds=new Set(grid?dockGroup.map(e=>e.id):[]);
    q('.cc-grid-dock').toggleAttribute('hidden',!grid);
    if(grid){const p=Math.min(1,Math.max(0,dockGroup[0].progress||0)),anchor=path.getPointAtLength(p*length);
      q('.cc-dock-caption').textContent=frame.target==null?(pt?'DISTÂNCIA INDISPONÍVEL':'DISTANCE UNAVAILABLE'):
        dockGroup.every(e=>e.points===0)?(pt?'GRELHA · 0 PONTOS':'STARTING GRID · 0 POINTS'):
        p===0?(pt?'LINHA DE PARTIDA':'START LINE'):`${pt?'DISTÂNCIA PARTILHADA':'SHARED DISTANCE'} · ${fmt(p*100)}%`;
      q('.cc-grid-dock path').setAttribute('d',`M510 441L${anchor.x} ${anchor.y}`);
      dockGroup.forEach((e,i)=>result.set(e.id,{p,lane:0,dock:true,x:286+(i%6)*79,y:334+Math.floor(i/6)*31}));}
    // Reuse a lane once its neighbouring car is far enough away. A transitive
    // cluster must not fan the whole field beyond the SVG edges.
    const occupied=new Map(), laneOrder=[0,-1,1,-2,2,-3,3,-4,4,-5,5,-6,6,-7,7,-8,8];
    const laneEntries=sorted.filter(e=>!dockIds.has(e.id)).sort((a,b)=>Number(b.progress===1&&frame.remaining===0)-Number(a.progress===1&&frame.remaining===0)||a.position-b.position);
    laneEntries.forEach(e=>{const p=Math.min(1,Math.max(0,e.progress||0));
      const anchor=path.getPointAtLength(p*length),b=path.getPointAtLength(Math.max(0,p*length-.5)),a=path.getPointAtLength(Math.min(length,p*length+.5)),angle=Math.atan2(a.y-b.y,a.x-b.x);
      const lane=laneOrder.find(l=>{const x=anchor.x-Math.sin(angle)*l*37,y=anchor.y+Math.cos(angle)*l*37;
        return x>45&&x<955&&y>35&&y<630&&(occupied.get(l)||[]).every(other=>Math.min(Math.abs(p-other),1-Math.abs(p-other))*length>62);
      })??0;
      if(!occupied.has(lane))occupied.set(lane,[]);occupied.get(lane).push(p);result.set(e.id,{p,lane:lane*37,dock:false});
    });
    return result;
  }
  function place(id, position) {
    const point=path.getPointAtLength(position.p*length), before=path.getPointAtLength(Math.max(0,position.p*length-.5)),after=path.getPointAtLength(Math.min(length,position.p*length+.5));
    const angle=Math.atan2(after.y-before.y,after.x-before.x), x=position.dock?position.x:point.x-Math.sin(angle)*position.lane,y=position.dock?position.y:point.y+Math.cos(angle)*position.lane;
    const car=cars.get(id);car.setAttribute('transform',`translate(${x.toFixed(2)} ${y.toFixed(2)})`);
    const anchor=anchors.get(id);anchor.style.display=position.dock||!position.lane?'none':'';
    anchor.querySelector('path').setAttribute('d',`M${point.x} ${point.y}L${x} ${y}`);
    anchor.querySelector('circle').setAttribute('cx',point.x);anchor.querySelector('circle').setAttribute('cy',point.y);
    car.querySelector('.cc-car-body').setAttribute('transform',`rotate(${angle*180/Math.PI})`);
    car.dataset.visualProgress=String(position.p);
    // Grid labels sit beside the car so adjacent grid rows remain clear.
    car.querySelector('.cc-car-label').setAttribute('transform',position.dock?'translate(36 20)':'translate(0 0)');
  }
  function settle() {cancelAnimationFrame(raf);targetPositions.forEach((p,id)=>place(id,p));positions=new Map(targetPositions);q('.cc-transition').hidden=true;}
  function move(frame,animate) {
    cancelAnimationFrame(raf);targetPositions=layout(frame);
    if(!animate||reduce.matches||!positions.size){settle();return;}
    const from=new Map(positions), start=performance.now(), duration=1100/speed;
    q('.cc-transition').hidden=false;
    const tick=now=>{if(disposed)return;const t=Math.min(1,(now-start)/duration), ease=t*t*(3-2*t);
      targetPositions.forEach((to,id)=>{const old=from.get(id)||to;
        // A grid callout merges at zero, then follows the circuit. Actual points
        // and accessible descriptions always remain the selected checkpoint.
        const pathT=old.dock&&!to.dock?Math.max(0,(t-.2)/.8):!old.dock&&to.dock?Math.min(1,t/.8):t;
        const pathEase=pathT*pathT*(3-2*pathT);
        const p={...to,p:old.p+(to.p-old.p)*pathEase,lane:old.lane+(to.lane-old.lane)*ease};
        if(old.dock||to.dock){const a=old.dock?old:{x:path.getPointAtLength(old.p*length).x,y:path.getPointAtLength(old.p*length).y};
          if(t<.2 && old.dock && !to.dock){const anchor=path.getPointAtLength(old.p*length);p.dock=true;p.x=a.x+(anchor.x-a.x)*(t/.2);p.y=a.y+(anchor.y-a.y)*(t/.2);p.p=old.p;}
          if(!old.dock&&to.dock){p.dock=t>=.8;if(p.dock){const anchor=path.getPointAtLength(to.p*length),u=(t-.8)/.2;p.x=anchor.x+(to.x-anchor.x)*u;p.y=anchor.y+(to.y-anchor.y)*u;}}
        }
        place(id,p);positions.set(id,p);
      });
      if(t<1)raf=requestAnimationFrame(tick);else settle();
    };raf=requestAnimationFrame(tick);
  }
  function display(next,animate=false) {
    index=next;const frame=frames[index];section.dataset.frame=String(index);
    q('.cc-race').textContent=raceName(frame);q('.cc-round').textContent=`${frame.round?`${pt?'Ronda':'Round'} ${frame.round} · `:''}${frame.completed} / ${model.totalRaces} ${pt?'corridas concluídas':'races completed'}`;
    q('.cc-target').textContent=fmt(frame.target);q('.cc-remaining').textContent=fmt(frame.remaining);
    q('.cc-opportunities').textContent=frame.remaining==null?'':`${pt?'Ainda por disputar':'Still to race'}: ${frame.remainingRaces} ${pt?'GPs':'Grands Prix'} · ${frame.remainingSprints} Sprints.`;
    q('.cc-select').value=String(index);q('.cc-timeline').value=String(index);q('.cc-timeline').setAttribute('aria-valuetext',raceName(frame));
    q('.cc-prev').disabled=index===0||!model.playback;q('.cc-next').disabled=index===frames.length-1||!model.playback;
    frame.standings.forEach(e=>{const d=drivers.get(e.id),row=rows.get(e.id),car=cars.get(e.id);
      row.querySelector('.cc-pos').textContent=String(e.position).padStart(2,'0');row.querySelector('.cc-points').textContent=fmt(e.points);row.querySelector('.cc-gap').textContent=e.gap?`\u2212${fmt(e.gap)}`:'—';q('.cc-list').append(row);
      const description=`${d.name}, ${fmt(e.points)} ${pt?'pontos':'points'}, P${e.position}, ${pt?'diferença para o líder':'gap to leader'} ${fmt(e.gap)}, ${e.progress==null?'—':fmt(e.progress*100)+'%'} ${pt?'do circuito':'of circuit'}`;
      const finished=e.progress===1&&frame.remaining===0&&frame.target>0;
      car.setAttribute('aria-label',description);row.setAttribute('aria-label',description);car.dataset.progress=String(e.progress??'');car.classList.toggle('cc-finished',finished);
      car.querySelector('text').textContent=d.label+(finished?' \u2713':'');
    });
    move(frame,animate);showDriver();
  }
  function pause(){playing=false;clearTimeout(timer);settle();stateLabel();}
  function schedule(){clearTimeout(timer);timer=setTimeout(()=>{if(!playing||disposed)return;if(index<frames.length-1){display(index+1,true);schedule();}else pause();},2300/speed);}
  q('.cc-play').addEventListener('click',()=>{if(playing){pause();return;}if(!started||index===frames.length-1)display(0,false);started=true;playing=true;stateLabel();schedule();});
  q('.cc-restart').addEventListener('click',()=>{pause();started=true;display(0);});
  const seek=i=>{pause();started=true;display(Math.max(0,Math.min(frames.length-1,i)));};
  q('.cc-prev').addEventListener('click',()=>seek(index-1));q('.cc-next').addEventListener('click',()=>seek(index+1));
  q('.cc-select').addEventListener('change',e=>seek(Number(e.target.value)));q('.cc-timeline').addEventListener('input',e=>seek(Number(e.target.value)));
  q('.cc-speed').addEventListener('change',e=>{speed=Number(e.target.value);if(playing){settle();schedule();}});
  ['.cc-play','.cc-restart','.cc-select','.cc-timeline','.cc-speed'].forEach(s=>{q(s).disabled=!model.playback||frames.length<=1;});
  const onMotion=()=>{if(reduce.matches)settle();};reduce.addEventListener('change',onMotion);
  const onVisibility=()=>{if(document.hidden)pause();};document.addEventListener('visibilitychange',onVisibility);
  display(index);stateLabel();
  return ()=>{disposed=true;clearTimeout(timer);cancelAnimationFrame(raf);reduce.removeEventListener('change',onMotion);document.removeEventListener('visibilitychange',onVisibility);};
}
'''
