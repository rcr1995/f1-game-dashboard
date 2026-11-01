"""SVG championship view and its fixed, dependency-free browser controller."""
from __future__ import annotations

import html

TRACK = "M1000 800 L1160 800 C1303 800 1420 680 1420 520 C1420 350 1390 220 1250 220 C1110 220 1020 400 880 400 C740 400 700 200 560 200 L480 200 C300 200 180 340 180 520 C180 680 300 800 480 800 L1000 800"

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
    title = "Evolução do campeonato" if pt else "Championship progress"
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
      <div class="cc-view-switch" role="group" aria-label="{'Visualização do campeonato' if pt else 'Championship view'}">
        <button class="cc-view-circuit" type="button" aria-pressed="false">{'Circuito' if pt else 'Circuit'}</button>
        <button class="cc-view-straight" type="button" aria-pressed="true">{'Reta' if pt else 'Straight'}</button>
        <span>{'Mesmos pontos, duas perspetivas' if pt else 'Same points, two perspectives'}</span>
      </div>
      <div class="cc-layout" hidden><div class="cc-course">
        <div class="cc-map"><svg class="cc-svg" viewBox="0 0 1600 1080" aria-label="{'Circuito virtual do campeonato' if pt else 'Virtual championship circuit'}" role="group">
          <defs><linearGradient id="cc-grass" x2=".8" y2="1"><stop stop-color="#35503c"/><stop offset="1" stop-color="#1c332e"/></linearGradient>
          <pattern id="cc-flag" width="14" height="14" patternUnits="userSpaceOnUse"><rect width="14" height="14" fill="#f4f6ed"/><path d="M0 0h7v7H0zM7 7h7v7H7z" fill="#182129"/></pattern>
          <filter id="cc-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-opacity=".4"/></filter></defs>
          <rect width="1600" height="1080" rx="18" fill="url(#cc-grass)"/>
          <path d="M0 228 Q300 70 520 345T1200 570 M0 370Q310 210 500 420T1200 630" fill="none" stroke="#688666" stroke-width="45" opacity=".10"/>
          <g aria-hidden="true" transform="translate(60 50)">{trees}</g>
          <path d="{TRACK}" fill="#2d4837" stroke="#b7a985" stroke-width="228" stroke-linejoin="round"/>
          <path d="{TRACK}" fill="none" stroke="#e6e6d7" stroke-width="216"/>
          <path d="{TRACK}" fill="none" stroke="#c34942" stroke-width="216" stroke-dasharray="18 18"/>
          <path d="{TRACK}" fill="none" stroke="#cdd0c7" stroke-width="206"/>
          <path class="cc-track" d="{TRACK}" fill="none" stroke="#424b50" stroke-width="200"/>
          <path d="{TRACK}" fill="none" stroke="#9ba49f" stroke-opacity=".24" stroke-width="1" stroke-dasharray="8 10"/>
          <rect x="210" y="940" width="665" height="100" rx="10" fill="#46535a"/>
          <path d="M230 960H900C1000 960 900 800 1000 800" fill="none" stroke="#b8c0b4" stroke-width="32"/>
          <path d="M230 960H900C1000 960 900 800 1000 800" fill="none" stroke="#46535a" stroke-width="27"/>
          <path d="M880 960C980 960 900 700 1000 700L1000 900C950 900 1000 975 880 975Z" fill="#46535a"/>
          <rect x="993" y="700" width="14" height="200" fill="url(#cc-flag)"/>
          <path d="M1070 800h30m-8-6 8 6-8 6" fill="none" stroke="#ffffff" stroke-width="2" opacity=".65"/>
          <text x="1190" y="1018" text-anchor="middle" class="cc-map-caption">{'PARTIDA / META' if pt else 'START / FINISH'}</text>
          <text x="525" y="1070" text-anchor="middle" class="cc-map-caption">{'BOXES · 0 PONTOS' if pt else 'PIT BAYS · 0 POINTS'}</text>
          <g class="cc-grid-slots" aria-hidden="true"></g>
          <g class="cc-anchors" aria-hidden="true" pointer-events="none"></g><g class="cc-cars"></g>
        </svg><span class="cc-transition" hidden>{'Transição entre classificações' if pt else 'Standings transition'}</span></div>
        <div class="cc-driver-detail" aria-live="off"></div>
      </div>
      <div class="cc-board"><div class="cc-board-heading"><h3>{'Classificação' if pt else 'Standings'}</h3><span>{'Pontos / diferença' if pt else 'Points / gap'}</span></div>
        <div class="cc-list" role="group" aria-label="{'Selecionar piloto' if pt else 'Select driver'}"></div>
      </div></div>
      <div class="cc-straight">
        <div class="cc-straight-heading"><span>{'Piloto' if pt else 'Driver'}</span><div class="cc-axis"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div><span>{'Pontos' if pt else 'Points'}</span></div>
        <div class="cc-lanes" role="group" aria-label="{'Reta do campeonato, da esquerda para a direita' if pt else 'Championship straight, left to right'}"></div>
        <p class="cc-note">{'Partida à esquerda, meta à direita. Ordem fixa da classificação mais recente. O centro de cada carro indica o progresso; os números mostram a corrida selecionada.' if pt else 'Start on the left, finish on the right. Names stay in the latest championship order. Each car’s centre marks progress; the numbers show the selected race.'}</p>
      </div>
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
      <p class="cc-note cc-pack-note">{'Cada piloto mantém a sua faixa. Carros sem pontos esperam nas boxes e saem quando pontuam. Correções que reduzem pontos são atualizadas sem condução em marcha-atrás.' if pt else 'Each driver keeps a fixed track lane. Zero-point cars wait in pit bays and join when they score. Points reductions update at the corrected checkpoint without reverse driving.'}</p>
      <p class="cc-note">{'Calendário e resultados publicados, incluindo correções. As animações ligam classificações confirmadas; não representam posições ou ultrapassagens durante um GP.' if pt else 'Published calendar and results, including corrections. Movement connects confirmed standings; it does not represent live positions or overtakes in a GP.'}</p>
      {notes}
    </section>'''


STYLE = '''<style>
.cc{margin:18px 28px 32px;padding:24px;background:#11151c;border:1px solid #2c3440;border-radius:18px;color:#edf1f7;font:14px Inter,system-ui,sans-serif;box-sizing:border-box}
.cc *{box-sizing:border-box}.cc-header{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:22px}.cc-context{margin:0 0 6px;color:#abb7c6;font-size:12px}.cc .cc-race{font:750 clamp(18px,2vw,26px) Inter,system-ui;margin:0 0 6px;letter-spacing:-.03em}.cc-round{font-size:12px;color:#aeb9c9;margin:0;min-height:18px}
.cc-metrics{display:flex;gap:30px;flex-shrink:0}.cc-metrics>div{display:flex;flex-direction:column;gap:4px}.cc-metrics span{font-size:11px;color:#b5c0cf}.cc-metrics strong{font-size:28px;letter-spacing:-.04em;font-variant-numeric:tabular-nums}.cc-target{color:#d9ed9c}
.cc-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(235px,28%);gap:22px;align-items:start}.cc-course{min-width:0}.cc-map{position:relative;overflow:hidden;border-radius:14px;background:#223c30}.cc-svg{display:block;width:100%;height:auto;overflow:visible}.cc-map-caption{fill:#d4ddca;font:600 15px Inter,system-ui;letter-spacing:3px}
.cc-car{cursor:pointer;outline:none}.cc-car .cc-car-body{filter:url(#cc-shadow)}.cc-car .cc-car-halo{fill:none;stroke:#fff;stroke-width:2;opacity:0}.cc-car[aria-pressed=true] .cc-car-halo,.cc-car:focus-visible .cc-car-halo,.cc-car.cc-hover .cc-car-halo{opacity:1}.cc-car.cc-finished .cc-car-halo{opacity:1;stroke:#e2f3a3;stroke-width:3}.cc-car text{fill:#f6f8fc;font:750 10px Inter,system-ui;paint-order:stroke;stroke:#172328;stroke-width:2;stroke-linejoin:round}.cc-car .cc-label-bg{fill:#0b141bee;stroke:#bbc7cc55;stroke-width:.7}.cc-car.cc-finished .cc-label-bg{stroke:#d9ed9c;stroke-width:2}.cc-car .cc-hit{fill:transparent}.cc-transition{position:absolute;left:12px;top:12px;background:#14242de8;border-radius:5px;padding:5px 8px;color:#e1e9f0;font-size:11px;pointer-events:none}
.cc-driver-detail{min-height:74px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 2px 0;font-size:12px;color:#c0c9d6}.cc-driver-detail strong{font-size:14px;color:#f5f7fc}.cc-driver-detail .cc-detail-name{display:block;flex:1 1 160px}.cc-driver-detail .cc-detail-stat{display:flex;flex-direction:column;gap:3px;min-width:52px}.cc-detail-stat span{font-size:10px;color:#9ba8bc}.cc-detail-stat b{font-size:13px;color:#edf1f7;font-variant-numeric:tabular-nums}
.cc-board-heading{display:flex;justify-content:space-between;align-items:center;padding:0 2px 10px;border-bottom:1px solid #2b3542}.cc-board-heading h3{margin:0;font:650 14px Inter,system-ui}.cc-board-heading>span{font-size:10px;color:#a7b3c6}.cc-list{max-height:430px;overflow:auto;scrollbar-width:thin;scrollbar-color:#566372 #171d26;padding:6px 3px 4px 0}.cc-row{width:100%;display:grid;grid-template-columns:22px 8px minmax(0,1fr) auto;align-items:center;gap:8px;min-height:43px;padding:7px 8px;border:1px solid transparent;border-radius:7px;background:none;text-align:left;color:#e5ebf4;font:12px Inter,system-ui;cursor:pointer}.cc-row:hover,.cc-row[aria-pressed=true],.cc-row.cc-hover{background:#222d38;border-color:#50606c}.cc-row:focus-visible{outline:2px solid #d9ed9c;outline-offset:-2px}.cc-row .cc-pos{color:#8f9db1;font-variant-numeric:tabular-nums}.cc-row .cc-dot{width:6px;height:20px;border-radius:3px}.cc-row .cc-name{overflow-wrap:anywhere}.cc-row .cc-score{text-align:right;display:flex;gap:10px;align-items:center;font-variant-numeric:tabular-nums}.cc-row .cc-score small{font-size:10px;color:#9eafc3;min-width:24px}
.cc-controls{display:flex;align-items:end;gap:16px;margin-top:20px;padding-top:20px;border-top:1px solid #2b3542;flex-wrap:wrap}.cc-buttons{display:flex;gap:6px;flex-wrap:wrap}.cc button:not(.cc-row):not(.cc-lane),.cc select{min-height:42px;border:1px solid #414d60;border-radius:7px;background:#1b2430;color:#eef3fa;font:600 12px Inter,system-ui;padding:9px 12px;cursor:pointer}.cc .cc-controls button.cc-primary{background:#e10600;border-color:#e10600;min-width:82px}.cc button:disabled,.cc select:disabled{opacity:.4;cursor:default}.cc button:focus-visible,.cc select:focus-visible,.cc input:focus-visible{outline:2px solid #d9ed9c;outline-offset:3px}.cc-controls label{display:flex;flex-direction:column;gap:5px;font-size:10px;color:#aab8cb}.cc-race-select{flex:1;min-width:170px}.cc-select{width:100%}.cc-controls select{color-scheme:dark}.cc-timeline-label{display:flex;align-items:center;gap:16px;color:#abb7c9;font-size:11px;margin:20px 0}.cc-timeline{flex:1;width:0;accent-color:#dcf3a0;cursor:pointer;min-height:24px}.cc-explanation{font-size:12px;color:#d0d8e3;line-height:1.65;margin:16px 0 8px;max-width:1000px}.cc-note{font-size:11px;color:#9caec0;line-height:1.6;margin:6px 0 0}.cc-warning{color:#ffd49d;padding:10px 12px;border-left:2px solid #f3bb75;background:#d3951910;margin-top:10px}
.cc [hidden]{display:none!important}.cc-view-switch{display:flex;align-items:center;gap:6px;margin-bottom:16px}.cc-view-switch span{margin-left:auto;color:#aab8cb;font-size:11px}.cc .cc-view-switch button{min-width:96px}.cc .cc-view-switch button[aria-pressed=true]{background:#d9ed9c;border-color:#d9ed9c;color:#14231d}.cc-grid-caption{fill:#d6e2c9;font:600 15px Inter,system-ui;letter-spacing:2px}.cc-anchor path{opacity:0}.cc-anchor.cc-active path{opacity:.9}.cc-anchor circle{opacity:.8}.cc-controls{margin:0 0 16px;padding:14px 0;border-top:1px solid #2b3542;border-bottom:1px solid #2b3542}.cc-timeline-label{margin:0 0 18px}
.cc-straight-heading,.cc .cc-lane{display:grid;grid-template-columns:150px minmax(0,1fr) 90px;gap:16px}.cc-straight-heading{font-size:11px;color:#aab8cb;padding:0 10px 12px}.cc-straight-heading>span:last-child{text-align:right}.cc-axis{display:flex;justify-content:space-between;margin:0 21px;position:relative}.cc-axis span{width:0;display:flex;justify-content:center;white-space:nowrap}.cc-lanes{--cc-lane-height:44px;position:relative;height:calc(var(--cc-count)*var(--cc-lane-height) + 2px);border:1px solid #38434e;border-radius:10px;overflow:hidden;overflow-anchor:none}.cc .cc-lane{position:absolute;left:0;top:0;width:100%;height:var(--cc-lane-height);min-height:44px;will-change:transform;padding:3px 9px;border:0;border-bottom:1px solid #36434b;border-radius:0;background:#29353b;text-align:left;align-items:center;font:12px Inter,system-ui;color:#e5ebf4;cursor:pointer}.cc .cc-lane:nth-child(even){background:#303d44}.cc .cc-lane:last-child{border-bottom:0}.cc .cc-lane[aria-pressed=true],.cc .cc-lane:focus-visible{z-index:100}.cc .cc-lane:hover,.cc .cc-lane[aria-pressed=true],.cc .cc-lane.cc-hover{background:#40514f;box-shadow:inset 3px 0 var(--driver-color)}.cc .cc-lane:focus-visible{outline:2px solid #d9ed9c;outline-offset:-2px}.cc-lane-name{display:flex;gap:9px;align-items:center;min-width:0}.cc-lane-name b{color:#abb9c8;font:11px Inter,system-ui;min-width:21px}.cc-lane-name span{overflow-wrap:anywhere}.cc-lane-track{position:relative;height:36px;margin:0 21px;background:repeating-linear-gradient(90deg,#ffffff22 0 1px,transparent 1px 25%);border-left:1px solid #bac7cd;border-right:3px solid #e5ecd8}.cc-lane-track:after{content:'';position:absolute;right:-5px;top:0;bottom:0;width:8px;background:repeating-conic-gradient(#eff3e9 0 25%,#263137 0 50%) 0 0/8px 8px}.cc-lane-trail{position:absolute;left:0;top:14px;height:8px;background:var(--driver-color);opacity:.24;border-radius:4px}.cc-lane-car{position:absolute;top:50%;width:38px;height:26px;transform:translate(-50%,-50%);overflow:visible;z-index:1;filter:drop-shadow(0 2px 2px #0008)}.cc-lane[aria-pressed=true] .cc-car-halo,.cc-lane.cc-hover .cc-car-halo{opacity:1}.cc-lane .cc-car-halo{fill:none;stroke:#fff;stroke-width:2;opacity:0}.cc-lane.cc-finished .cc-car-halo{opacity:1;stroke:#d9ed9c}.cc-lane-score{display:flex;justify-content:end;gap:10px;align-items:center;font-variant-numeric:tabular-nums}.cc-lane-score small{color:#b6c4d2;font-size:10px;min-width:28px;text-align:right}.cc-lane-score b{font-size:12px}.cc-lane-progress{display:none}.cc-lane[aria-pressed=true] .cc-lane-progress{display:block;font-size:10px;color:#d9ed9c}.cc-straight .cc-note{margin-top:10px}
@media(min-width:1400px){.cc-list{max-height:530px}}
@media(max-width:900px){.cc{margin:16px 16px 28px;padding:18px}.cc-header{align-items:start;flex-wrap:wrap}.cc-metrics{gap:24px}.cc-metrics strong{font-size:24px}.cc-layout{grid-template-columns:1fr}.cc-list{max-height:265px;display:grid;grid-template-columns:1fr 1fr;gap:0 12px}.cc-board{margin-top:8px}}
@media(max-width:520px){.cc{margin:14px 8px 24px;padding:14px 10px;border-radius:12px}.cc-header{gap:16px}.cc-metrics{width:100%;justify-content:space-between;padding-top:10px;border-top:1px solid #2b3542}.cc-metrics span{font-size:10px}.cc-layout{gap:8px}.cc-list{grid-template-columns:1fr;max-height:258px}.cc-row{min-height:44px}.cc-controls{gap:12px}.cc-buttons{width:100%;display:grid;grid-template-columns:1fr 1fr 1fr 1fr}.cc button:not(.cc-row):not(.cc-lane){padding:9px 4px;min-height:44px}.cc .cc-controls button.cc-primary{min-width:0}.cc-prev span,.cc-next span{font-size:10px}.cc-driver-detail{gap:12px 15px}.cc-driver-detail .cc-detail-name{flex-basis:100%}.cc-detail-stat{flex:1}.cc-timeline-label{gap:8px;font-size:10px}.cc-view-switch span{display:none}.cc-straight-heading,.cc .cc-lane{grid-template-columns:86px minmax(0,1fr) 52px;gap:5px}.cc-straight-heading{padding-left:4px;padding-right:4px}.cc-lanes{--cc-lane-height:48px}.cc .cc-lane{padding:4px;font-size:10px;min-height:48px}.cc-lane-name{gap:4px}.cc-lane-name b{min-width:17px;font-size:10px}.cc-lane-score{gap:2px;flex-direction:column;align-items:end}.cc-lane-score small{font-size:9px}.cc-lane-car{width:32px}.cc-axis,.cc-lane-track{margin-left:17px;margin-right:17px}.cc-axis{font-size:9px}.cc .cc-view-switch button{flex:1}}
@media(prefers-reduced-motion:reduce){.cc *{scroll-behavior:auto!important;transition:none!important}}

/* The field and controls share one viewport-sized panel. */
.cc{display:flex;flex-direction:column;height:var(--cc-height,calc(100svh - 145px));min-height:420px;max-height:1000px;padding:10px 14px;margin-top:8px;margin-bottom:12px;overflow:hidden}
.cc-header{margin-bottom:7px;gap:12px;flex-shrink:0}.cc-context{font-size:10px;margin-bottom:2px}.cc .cc-race{font-size:19px;margin-bottom:2px}.cc-round{font-size:10px;min-height:14px}.cc-metrics{gap:20px}.cc-metrics span{font-size:9px}.cc-metrics strong{font-size:23px}.cc-view-switch{margin-bottom:6px;gap:5px;flex-shrink:0}.cc-view-switch span{font-size:10px}
.cc button:not(.cc-row):not(.cc-lane),.cc select{min-height:28px;padding:4px 9px;font-size:11px}.cc .cc-controls button.cc-primary{min-width:68px}.cc .cc-view-switch button{min-width:80px}.cc-controls{gap:10px;margin:0 0 5px;padding:5px 0;flex-shrink:0}.cc-controls label{font-size:9px;gap:2px}.cc-timeline-label{margin:0 0 5px;min-height:20px;font-size:10px;flex-shrink:0}.cc-timeline{min-height:20px}.cc-straight{display:flex;flex:1;flex-direction:column;min-height:0}.cc-straight-heading{padding:0 7px 4px;font-size:9px;flex-shrink:0}.cc-lanes{height:auto;min-height:0;flex:1}.cc .cc-lane{height:calc((100% - 2px)/var(--cc-count));min-height:0;padding:0 7px;font-size:11px;will-change:auto}.cc-lane-name{gap:6px;white-space:nowrap;overflow:hidden}.cc-lane-name span{overflow:hidden;text-overflow:ellipsis;overflow-wrap:normal}.cc-lane-name b{font-size:9px;min-width:17px}.cc-lane-track{height:100%;min-height:0}.cc-lane-car{width:28px;height:18px}.cc-lane-trail{top:calc(50% - 2px);height:4px}.cc-lane-score b{font-size:10px}.cc-lane-score small{font-size:9px}.cc-lane-progress{display:none!important}.cc-straight>.cc-note{display:none}
.cc-driver-detail{min-height:25px;flex-shrink:0;gap:6px;padding:5px 0 0;font-size:10px;flex-wrap:nowrap}.cc-driver-detail strong{font-size:11px}.cc-driver-detail .cc-detail-name{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.cc-driver-detail .cc-detail-stat{min-width:45px;gap:1px}.cc-detail-stat span{font-size:8px}.cc-detail-stat b{font-size:10px}.cc-explanation{font-size:9px;line-height:1.3;margin:5px 0 0;flex-shrink:0}.cc>.cc-note{display:none}.cc>.cc-warning{display:block;font-size:9px;line-height:1.25;padding:3px 5px;margin:2px 0 0}.cc-layout{flex:1;min-height:0;align-items:stretch;gap:12px}.cc-course{min-height:0;display:flex}.cc-map{width:100%;height:100%;display:flex;align-items:center;justify-content:center}.cc-svg{max-height:100%;width:100%;height:100%;object-fit:contain;overflow:hidden}.cc-board{min-height:0;display:flex;flex-direction:column}.cc-board-heading{padding-bottom:4px;flex-shrink:0}.cc-board-heading h3{font-size:11px}.cc-list{max-height:none;overflow:hidden;flex:1;display:flex;flex-direction:column;padding:0}.cc-row{min-height:0;flex:1;padding:0 4px;font-size:10px;gap:5px;grid-template-columns:17px 6px minmax(0,1fr) auto}.cc-row .cc-dot{height:10px;width:4px}.cc-row .cc-score{gap:6px}.cc-row .cc-score small{font-size:8px;min-width:20px}.cc-car-label{opacity:0;pointer-events:none}.cc-car[aria-pressed=true] .cc-car-label,.cc-car.cc-hover .cc-car-label,.cc-car:focus-visible .cc-car-label{opacity:1}.cc-car .cc-car-halo{stroke-width:3}.cc-car text{font-size:11px}
@media(max-width:900px){.cc{margin-left:8px;margin-right:8px;padding:8px 10px}.cc-layout{grid-template-columns:minmax(0,1fr) 185px}.cc-board{margin-top:0}.cc-list{display:flex;gap:0}.cc-header{flex-wrap:nowrap}.cc-metrics strong{font-size:20px}}
@media(max-width:520px){.cc{height:var(--cc-height,calc(100svh - 210px));padding:7px 6px;min-height:450px}.cc-header{gap:6px;flex-wrap:wrap;margin-bottom:4px}.cc-context{font-size:8px}.cc .cc-race{font-size:15px}.cc-round{font-size:9px}.cc-metrics{width:100%;flex-direction:row;justify-content:space-between;border:0;padding:0;gap:8px}.cc-metrics>div{flex-direction:row;align-items:center;gap:6px}.cc-metrics span{font-size:8px;max-width:80px}.cc-metrics strong{font-size:18px}.cc-view-switch{margin-bottom:3px}.cc .cc-view-switch button{min-height:27px;padding:3px}.cc-controls{gap:4px;display:grid;grid-template-columns:minmax(0,1fr) 52px;padding:4px 0;margin-bottom:3px}.cc-buttons{grid-column:1/-1;gap:4px}.cc button:not(.cc-row):not(.cc-lane){min-height:27px;padding:3px;font-size:10px}.cc .cc-controls button.cc-primary{min-width:0}.cc-controls select{min-height:27px;padding:3px;font-size:10px}.cc-controls label{font-size:8px}.cc-race-select{min-width:0}.cc-timeline-label{font-size:9px;min-height:18px}.cc-straight-heading,.cc .cc-lane{grid-template-columns:86px minmax(0,1fr) 42px;gap:3px}.cc-straight-heading{padding-left:3px;padding-right:3px;font-size:8px}.cc .cc-lane{font-size:9px;min-height:0;padding:0 3px}.cc-lane-name{gap:3px}.cc-lane-name b{font-size:8px;min-width:13px}.cc-axis,.cc-lane-track{margin:0 12px}.cc-lane-car{width:22px;height:100%;max-height:14px}.cc-lane-score{flex-direction:row;gap:3px;align-items:center}.cc-lane-score b{font-size:9px}.cc-lane-score small{font-size:7px;min-width:16px}.cc-driver-detail{gap:4px;min-height:26px}.cc-driver-detail .cc-detail-name{flex-basis:auto;font-size:9px}.cc-driver-detail .cc-detail-stat{min-width:31px;flex:0}.cc-detail-stat span{font-size:7px}.cc-detail-stat b{font-size:9px}.cc-explanation{font-size:8px;margin-top:3px}.cc-layout{grid-template-columns:1fr;grid-template-rows:minmax(0,1fr) minmax(0,1fr);gap:4px}.cc-list{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:repeat(11,minmax(0,1fr));grid-auto-flow:column}.cc-row{font-size:9px;gap:3px;min-height:0}.cc-row .cc-score small{display:none}.cc-board-heading{display:none}}
</style>'''


JS = r'''
// Monotone cubic interpolation meets every published checkpoint with continuous
// velocity. Only the start/end or a genuinely flat/reversing series has to stop.
function championshipSeries(values) {
  const delta=values.slice(1).map((v,i)=>v-values[i]);
  const slopes=values.map((_,i)=>{
    if(i===0||i===values.length-1)return 0;
    const a=delta[i-1],b=delta[i];
    return a*b>0?2*a*b/(a+b):0;
  });
  return cursor=>{
    if(values.length===1)return values[0];
    const x=Math.max(0,Math.min(values.length-1,cursor)),i=Math.min(values.length-2,Math.floor(x)),t=x-i;
    const t2=t*t,t3=t2*t;
    return (2*t3-3*t2+1)*values[i]+(t3-2*t2+t)*slopes[i]+(-2*t3+3*t2)*values[i+1]+(t3-t2)*slopes[i+1];
  };
}
function advanceChampionship(cursor,elapsed,speed,last) {
  return Math.min(last,Math.max(0,cursor+Math.max(0,elapsed)*speed/2400));
}
// Every driver retains one lateral lane; rank never changes track distance.
function championshipTrackLayout(standings, order, length) {
  return new Map(standings.map(e=>{
    const row=order.indexOf(e.id),p=Math.max(0,Math.min(1,e.progress||0));
    return [e.id,{p,s:p*length,lane:(row-(order.length-1)/2)*8,pit:!(e.points>0),pitIndex:row,row}];
  }));
}
function championshipPitDistance(p,length,pitLength,firstProgress) {
  return firstProgress>0&&p>=firstProgress?p*length:p*length-pitLength*Math.pow(1-(firstProgress>0?p/firstProgress:0),3);
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
  // Corrections are shown at their checkpoint, never as reverse driving.
  return i<values.length-1&&values[i+1]<values[i]?values[i]:championshipSeries(values)(at);
}
function mountChampionship(root, model, pt) {
  const section = root.querySelector('.cc');
  if (!section || !model?.frames?.length) return () => {};
  const q = s => section.querySelector(s), NS = 'http://www.w3.org/2000/svg';
  const frames = model.frames, order=frames[frames.length-1].standings.map(e=>e.id), drivers = new Map(model.drivers.map(d => [d.id,d]));
  const path = q('.cc-track'), length = path.getTotalLength(), cars = new Map(), rows = new Map(), anchors = new Map(), lanes = new Map();
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  const fmt = n => n == null ? '—' : new Intl.NumberFormat(pt?'pt-PT':'en-GB',{maximumFractionDigits:2}).format(n);
  const raceName = f => f.name==='grid' ? (pt?'Grelha de partida':'Starting grid') : f.name==='current' ? (pt?'Classificação atual':'Current standings') : f.name;
  const svgEl = (tag, attrs={}) => {const el=document.createElementNS(NS,tag);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));return el;};
  const htmlEl = (tag, cls, text) => {const el=document.createElement(tag);if(cls)el.className=cls;if(text!=null)el.textContent=text;return el;};
  let index=model.defaultIndex, playing=false, started=false, raf=0, selected=frames[index].standings[0]?.id, hovered=null;
  let positions=new Map(), speed=1, disposed=false, view='straight',cursor=index,lastTime=0,motion=null;
  const segments=Math.ceil(length/2),samples=Array.from({length:segments+1},(_,i)=>path.getPointAtLength(i*length/segments));
  const tangents=samples.map((_,i)=>{
    const before=samples[(i-1+segments)%segments],after=samples[(i+1)%segments],dx=after.x-before.x,dy=after.y-before.y,n=Math.hypot(dx,dy)||1;
    return {x:dx/n,y:dy/n};
  });
  // A distance may be negative for grid slots behind the start. Only geometry
  // wraps: a champion retains p=1, a finished state and the finish-line marker.
  function pointAt(s,lane=0){
    const offset=v=>{
      const distance=((v%length)+length)%length,u=distance/length*segments,i=Math.min(segments-1,Math.floor(u)),t=u-i;
      const before=samples[i],after=samples[i+1],tx=tangents[i].x*(1-t)+tangents[i+1].x*t,ty=tangents[i].y*(1-t)+tangents[i+1].y*t,n=Math.hypot(tx,ty)||1;
      return {x:before.x+(after.x-before.x)*t-ty/n*lane,y:before.y+(after.y-before.y)*t+tx/n*lane};
    };
    const point=offset(s),before=offset(s-1),after=offset(s+1);
    return {...point,angle:Math.atan2(after.y-before.y,after.x-before.x)};
  }
  const pitRoutes=new Map(order.map((id,i)=>{
    const x=230+i*28,lane=(i-(order.length-1)/2)*8,endY=800+lane,route=[{x,y:1010}];
    const cubic=(a,b,c,d)=>{for(let j=1;j<=60;j++){const t=j/60,u=1-t;route.push({x:u*u*u*a.x+3*u*u*t*b.x+3*u*t*t*c.x+t*t*t*d.x,y:u*u*u*a.y+3*u*u*t*b.y+3*u*t*t*c.y+t*t*t*d.y});}};
    cubic({x,y:1010},{x,y:990},{x:x+20,y:960},{x:x+40,y:960});
    route.push({x:900,y:960});
    cubic({x:900,y:960},{x:1000,y:960},{x:900,y:endY},{x:1000,y:endY});
    let total=0;route.forEach((p,i)=>{if(i)total+=Math.hypot(p.x-route[i-1].x,p.y-route[i-1].y);p.distance=total;});
    const first=frames.find(f=>f.standings.find(e=>e.id===id)?.points>0)?.standings.find(e=>e.id===id)?.progress||0;
    return [id,{route,total,first}];
  }));
  function travelDistance(id,p){
    const route=pitRoutes.get(id);
    return championshipPitDistance(p,length,route.total,route.first);
  }
  function pitPoint(id,s){
    const {route,total}=pitRoutes.get(id),d=Math.max(0,Math.min(total,total+s));
    let i=1;while(i<route.length-1&&route[i].distance<d)i++;
    const a=route[i-1],b=route[i],t=(d-a.distance)/(b.distance-a.distance||1);
    return {x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t,angle:Math.atan2(b.y-a.y,b.x-a.x)};
  }
  // Put shared playback controls above either view, including a long lane list.
  section.insertBefore(q('.cc-controls'),q('.cc-layout'));
  section.insertBefore(q('.cc-timeline-label'),q('.cc-layout'));
  section.insertBefore(q('.cc-driver-detail'),q('.cc-explanation'));
  const stateLabel = () => {q('.cc-play').textContent=playing?(pt?'Pausar':'Pause'):(pt?'Reproduzir':'Play');q('.cc-play').setAttribute('aria-pressed',String(playing));section.dataset.playing=String(playing);};
  const selectDriver = (id, temporary=false) => {if(temporary)hovered=id;else{selected=id;hovered=null;}showDriver();};
  function showDriver() {
    const id=hovered||selected, d=drivers.get(id), entry=frames[index].standings.find(e=>e.id===id);
    if(!d||!entry)return;
    cars.forEach((car,key)=>{car.setAttribute('aria-pressed',String(key===selected));car.classList.toggle('cc-hover',key===hovered);});
    rows.forEach((row,key)=>{row.setAttribute('aria-pressed',String(key===selected));row.classList.toggle('cc-hover',key===hovered);});
    lanes.forEach((row,key)=>{row.setAttribute('aria-pressed',String(key===selected));row.classList.toggle('cc-hover',key===hovered);});
    anchors.forEach((anchor,key)=>anchor.classList.toggle('cc-active',key===(hovered||selected)));
    const detail=q('.cc-driver-detail');detail.replaceChildren();
    const name=htmlEl('strong','cc-detail-name',d.name);name.style.borderLeft=`3px solid ${d.color}`;name.style.paddingLeft='10px';detail.append(name);
    [[pt?'Posição':'Position',`P${entry.position}`],[pt?'Pontos':'Points',fmt(entry.points)],
     [pt?'Diferença':'Gap',entry.gap?`\u2212${fmt(entry.gap)}`:'—'],[pt?'Circuito':'Circuit',entry.progress==null?'—':`${fmt(entry.progress*100)}%`]].forEach(([label,value])=>{
      const stat=htmlEl('div','cc-detail-stat');stat.append(htmlEl('span','',label),htmlEl('b','',value));detail.append(stat);
    });
    section.dataset.selectedDriver=id;
  }
  model.drivers.forEach(d=>{
    const anchor=svgEl('g',{class:'cc-anchor'});anchor.append(svgEl('path',{fill:'none',stroke:d.color,'stroke-width':1.3,'stroke-dasharray':'3 4'}),svgEl('circle',{r:2.5,fill:d.color}));
    q('.cc-anchors').append(anchor);anchors.set(d.id,anchor);
    const car=svgEl('g',{class:'cc-car',tabindex:'0',role:'button','data-driver-id':d.id,'aria-pressed':'false'});
    const hit=svgEl('rect',{class:'cc-hit',x:-21,y:-4,width:42,height:8,rx:6});car.append(hit);
    const body=svgEl('g',{class:'cc-car-body'});
    body.append(svgEl('rect',{class:'cc-car-halo',x:-20,y:-12,width:39,height:24,rx:5}));
    [[-14,-10,8,5],[-14,5,8,5],[7,-10,7,5],[7,5,7,5]].forEach(([x,y,w,h])=>body.append(svgEl('rect',{x,y,width:w,height:h,rx:1,fill:'#071014',stroke:'#91a4aa','stroke-width':.6})));
    body.append(svgEl('path',{d:'M-15-5L-5-6 4-4 15-2 17 0 15 2 4 4-5 6-15 5Z',fill:d.color,stroke:'#e5f1ed','stroke-width':.7}),
      svgEl('rect',{x:-15,y:-9,width:3,height:18,rx:1,fill:d.color}),svgEl('rect',{x:12,y:-8,width:3,height:16,rx:1,fill:d.color}),
      svgEl('ellipse',{cx:-3,cy:0,rx:4,ry:3,fill:'#17242e'}));
    car.append(body);
    const label=svgEl('g',{class:'cc-car-label'});label.append(svgEl('rect',{class:'cc-label-bg',x:-18,y:-24,width:36,height:13,rx:3}));
    const text=svgEl('text',{x:0,y:-14,'text-anchor':'middle'});text.textContent=d.label;label.append(text);car.append(label);
    car.addEventListener('click',()=>selectDriver(d.id));car.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();selectDriver(d.id);}});
    car.addEventListener('focus',()=>selectDriver(d.id));car.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')selectDriver(d.id,true);});car.addEventListener('pointerleave',()=>{hovered=null;showDriver();});
    q('.cc-cars').append(car);cars.set(d.id,car);
    const row=htmlEl('button','cc-row');row.type='button';row.dataset.driverId=d.id;
    const dot=htmlEl('span','cc-dot');dot.style.background=d.color;
    const score=htmlEl('span','cc-score');score.append(htmlEl('b','cc-points'),htmlEl('small','cc-gap'));
    row.append(htmlEl('span','cc-pos'),dot,htmlEl('span','cc-name',d.name),score);
    row.addEventListener('click',()=>selectDriver(d.id));row.addEventListener('focus',()=>selectDriver(d.id));
    rows.set(d.id,row);
    const lane=htmlEl('button','cc-lane');lane.type='button';lane.dataset.driverId=d.id;lane.style.setProperty('--driver-color',d.color);
    const laneName=htmlEl('span','cc-lane-name');laneName.append(htmlEl('b','cc-lane-rank'),htmlEl('span','',d.name));
    const track=htmlEl('span','cc-lane-track'),trail=htmlEl('span','cc-lane-trail');track.append(trail);
    const sprite=svgEl('svg',{class:'cc-lane-car',viewBox:'-23 -15 46 30','aria-hidden':'true'});sprite.append(body.cloneNode(true));track.append(sprite);
    const laneScore=htmlEl('span','cc-lane-score'),lanePoints=htmlEl('span');lanePoints.append(htmlEl('b','cc-lane-points'),htmlEl('span','cc-lane-progress'));
    laneScore.append(lanePoints,htmlEl('small','cc-lane-gap'));lane.append(laneName,track,laneScore);
    lane.addEventListener('click',()=>selectDriver(d.id));lane.addEventListener('focus',()=>selectDriver(d.id));
    lane.addEventListener('pointerenter',e=>{if(e.pointerType==='mouse')selectDriver(d.id,true);});lane.addEventListener('pointerleave',()=>{hovered=null;showDriver();});
    lanes.set(d.id,lane);
  });
  q('.cc-lanes').style.setProperty('--cc-count',String(model.drivers.length));
  order.forEach(id=>{q('.cc-lanes').append(lanes.get(id));q('.cc-list').append(rows.get(id));});
  order.forEach((id,i)=>{
    const x=230+i*28;
    q('.cc-grid-slots').append(svgEl('path',{d:`M${x} 1010V960`,stroke:'#687b80','stroke-width':12}));
    q('.cc-grid-slots').append(svgEl('rect',{x:x-11,y:993,width:22,height:35,fill:'none',stroke:'#c4d0bf','stroke-width':1}));
  });
  frames.forEach((f,i)=>{const option=htmlEl('option','',`${f.round?`R${f.round} · `:''}${raceName(f)}`);option.value=String(i);q('.cc-select').append(option);});
  q('.cc-timeline').max=String(frames.length-1);
  const layouts=frames.map(frame=>{
    const result=championshipTrackLayout(frame.standings,order,length);
    return result;
  });
  const curves=new Map(model.drivers.map(d=>[d.id,Object.fromEntries(['p','s','lane','row'].map(key=>[key,championshipSeries(layouts.map(frame=>frame.get(d.id)[key]))]))]));
  function sample(at){
    return new Map(model.drivers.map(d=>{
      const curve=curves.get(d.id),position=Object.fromEntries(Object.entries(curve).map(([key,get])=>[key,get(at)]));
      const values=layouts.map(f=>f.get(d.id).p),p=championshipForwardProgress(values,at);
      const opacity=championshipCorrectionOpacity(values,at);
      return [d.id,{...position,p,s:p*length,lane:layouts[0].get(d.id).lane,row:layouts[0].get(d.id).row,opacity}];
    }));
  }
  function place(id, position) {
    const lane=lanes.get(id),car=cars.get(id);
    lane.style.transform=`translateY(${position.row*100}%)`;
    lane.querySelector('.cc-lane-car').style.left=`${position.p*100}%`;
    lane.querySelector('.cc-lane-trail').style.width=`${position.p*100}%`;
    lane.dataset.visualProgress=String(position.p);lane.dataset.visualRank=String(position.row+1);
    car.dataset.visualProgress=String(position.p);car.dataset.lane=String(position.lane);car.style.opacity=String(position.opacity??1);
    // The default view only animates lightweight row transforms and car progress.
    // Hidden circuit geometry is repainted when that view is selected.
    if(view!=='circuit')return;
    const travel=travelDistance(id,position.p),point=travel<0?pitPoint(id,travel):pointAt(travel,position.lane),exact=pointAt(position.p*length);
    car.dataset.trackDistance=String(travel);car.dataset.inPit=String(travel<0);
    car.setAttribute('transform',`translate(${point.x.toFixed(2)} ${point.y.toFixed(2)})`);
    car.querySelector('.cc-car-body').setAttribute('transform',`rotate(${point.angle*180/Math.PI}) scale(1 .30)`);
    car.querySelector('.cc-hit').setAttribute('transform',`rotate(${point.angle*180/Math.PI})`);
    const anchor=anchors.get(id);anchor.style.display='none';
    let line=`M${exact.x} ${exact.y}`;
    const delta=position.s-position.p*length,steps=Math.max(1,Math.ceil(Math.abs(delta)/15));
    for(let i=0;i<=steps;i++){const a=pointAt(position.p*length+delta*i/steps,position.lane);line+=`L${a.x} ${a.y}`;}
    anchor.querySelector('path').setAttribute('d',line);
    anchor.querySelector('circle').setAttribute('cx',exact.x);anchor.querySelector('circle').setAttribute('cy',exact.y);
  }
  function paint(next){positions=next;positions.forEach((p,id)=>place(id,p));}
  function transition(active){q('.cc-transition').hidden=!active;section.dataset.transition=String(active);}
  function display(next) {
    const focused=section.getRootNode().activeElement;
    index=next;const frame=frames[index];section.dataset.frame=String(index);

    q('.cc-race').textContent=raceName(frame);q('.cc-round').textContent=`${frame.round?`${pt?'Ronda':'Round'} ${frame.round} · `:''}${frame.completed} / ${model.totalRaces} ${pt?'corridas concluídas':'races completed'}`;
    q('.cc-target').textContent=fmt(frame.target);q('.cc-remaining').textContent=fmt(frame.remaining);
    q('.cc-opportunities').textContent=frame.remaining==null?'':`${pt?'Ainda por disputar':'Still to race'}: ${frame.remainingRaces} ${pt?'GPs':'Grands Prix'} · ${frame.remainingSprints} Sprints.`;
    q('.cc-select').value=String(index);q('.cc-timeline').value=String(index);q('.cc-timeline').setAttribute('aria-valuetext',raceName(frame));
    q('.cc-prev').disabled=index===0||!model.playback;q('.cc-next').disabled=index===frames.length-1||!model.playback;
    frame.standings.forEach(e=>{const d=drivers.get(e.id),row=rows.get(e.id),car=cars.get(e.id),lane=lanes.get(e.id);
      row.querySelector('.cc-pos').textContent=String(order.indexOf(e.id)+1).padStart(2,'0');row.querySelector('.cc-points').textContent=fmt(e.points);row.querySelector('.cc-gap').textContent=e.gap?`\u2212${fmt(e.gap)}`:'—';
      const description=`${d.name}, ${fmt(e.points)} ${pt?'pontos':'points'}, P${e.position}, ${pt?'diferença para o líder':'gap to leader'} ${fmt(e.gap)}, ${e.progress==null?'—':fmt(e.progress*100)+'%'} ${pt?'do circuito':'of circuit'}`;
      const finished=e.progress===1&&frame.remaining===0&&frame.target>0;
      car.setAttribute('aria-label',description);row.setAttribute('aria-label',description);car.dataset.progress=String(e.progress??'');car.classList.toggle('cc-finished',finished);
      car.querySelector('text').textContent=d.label+(finished?' \u2713':'');
      lane.dataset.position=String(e.position);lane.dataset.latestPosition=String(order.indexOf(e.id)+1);
      lane.setAttribute('aria-label',description);lane.title=description;lane.dataset.progress=String(e.progress??'');lane.classList.toggle('cc-finished',finished);
      lane.querySelector('.cc-lane-rank').textContent=`${order.indexOf(e.id)+1}`;lane.querySelector('.cc-lane-points').textContent=fmt(e.points);
      lane.querySelector('.cc-lane-gap').textContent=e.gap?`\u2212${fmt(e.gap)}`:'—';lane.querySelector('.cc-lane-progress').textContent=e.progress==null?'—':`${fmt(e.progress*100)}%`;
    });
    if(focused&&section.contains(focused)&&focused!==section.getRootNode().activeElement)focused.focus({preventScroll:true});
    showDriver();
  }
  function tick(now){
    if(disposed)return;
    const elapsed=Math.max(0,now-lastTime);lastTime=now;
    if(motion?.running){
      motion.elapsed+=elapsed;const t=Math.min(1,motion.elapsed/600),ease=t*t*(3-2*t);
      const next=new Map();motion.to.forEach((to,id)=>{
        const from=motion.from.get(id)||to,p={...to};
        for(const key of ['p','s','lane','row'])p[key]=from[key]+(to[key]-from[key])*ease;
        next.set(id,p);
      });paint(next);
      if(t===1){motion=null;transition(false);}
    }else if(playing){
      cursor=advanceChampionship(cursor,elapsed,speed,frames.length-1);
      const checkpoint=reduce.matches?Math.floor(cursor):Math.ceil(cursor-1e-9),changed=checkpoint!==index;
      if(changed)display(checkpoint);
      if(!reduce.matches||changed)paint(sample(reduce.matches?checkpoint:cursor));
      transition(!reduce.matches&&cursor<frames.length-1);
      if(cursor===frames.length-1){playing=false;paint(sample(cursor));transition(false);stateLabel();}
    }
    section.dataset.cursor=String(cursor);
    if(playing||motion?.running)raf=requestAnimationFrame(tick);
  }
  function run(){cancelAnimationFrame(raf);lastTime=performance.now();raf=requestAnimationFrame(tick);}
  function pause(){playing=false;cancelAnimationFrame(raf);if(motion)motion.running=false;stateLabel();}
  function reset(){motion=null;cursor=0;display(0);paint(sample(0));section.dataset.cursor='0';transition(false);}
  q('.cc-play').addEventListener('click',()=>{
    if(playing){pause();return;}
    if(!started||cursor>=frames.length-1)reset();
    started=true;playing=true;if(motion)motion.running=true;stateLabel();run();
  });
  q('.cc-restart').addEventListener('click',()=>{pause();started=true;reset();});
  const seek=i=>{
    pause();started=true;cursor=Math.max(0,Math.min(frames.length-1,i));display(cursor);section.dataset.cursor=String(cursor);
    const to=sample(cursor);
    if(reduce.matches||!positions.size||[...to].some(([id,p])=>p.p<positions.get(id).p)){motion=null;paint(to);transition(false);}
    else{motion={from:new Map(positions),to,elapsed:0,running:true};transition(true);run();}
  };
  q('.cc-prev').addEventListener('click',()=>seek(index-1));q('.cc-next').addEventListener('click',()=>seek(index+1));
  q('.cc-select').addEventListener('change',e=>seek(Number(e.target.value)));q('.cc-timeline').addEventListener('input',e=>seek(Number(e.target.value)));
  q('.cc-speed').addEventListener('change',e=>{speed=Number(e.target.value)||1;});
  ['.cc-play','.cc-restart','.cc-select','.cc-timeline','.cc-speed'].forEach(s=>{q(s).disabled=!model.playback||frames.length<=1;});
  function setView(next){
    view=next;section.dataset.view=view;hovered=null;
    q('.cc-layout').hidden=view==='straight';q('.cc-straight').hidden=view!=='straight';q('.cc-pack-note').hidden=view==='straight';
    q('.cc-view-circuit').setAttribute('aria-pressed',String(view==='circuit'));
    q('.cc-view-straight').setAttribute('aria-pressed',String(view==='straight'));positions.forEach((p,id)=>place(id,p));showDriver();
  }
  q('.cc-view-circuit').addEventListener('click',()=>setView('circuit'));
  q('.cc-view-straight').addEventListener('click',()=>setView('straight'));
  setView('straight');
  const onMotion=()=>{if(reduce.matches){motion=null;cursor=index;paint(sample(index));transition(false);}};reduce.addEventListener('change',onMotion);
  const onVisibility=()=>{if(document.hidden)pause();};document.addEventListener('visibilitychange',onVisibility);
  function fit(){
    const nav=root.querySelector('nav[aria-label="Season sections"]'),chrome=(nav?.getBoundingClientRect().height||70)+(window.innerWidth<520?112:80);
    section.style.setProperty('--cc-height',`${Math.max(420,window.innerHeight-chrome)}px`);
  }
  fit();window.addEventListener('resize',fit);
  display(index);paint(sample(cursor));section.dataset.cursor=String(cursor);transition(false);stateLabel();
  return ()=>{disposed=true;cancelAnimationFrame(raf);window.removeEventListener('resize',fit);reduce.removeEventListener('change',onMotion);document.removeEventListener('visibilitychange',onVisibility);};
}
'''
