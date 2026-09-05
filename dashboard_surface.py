"""Content-height public HTML surface: no nested frame, eval or remote script execution."""
from __future__ import annotations
import re
import streamlit as st

JS = r"""
export default function ({parentElement, data}) {
  const root = parentElement.querySelector('.surface');
  const parsed = new DOMParser().parseFromString(data.html, 'text/html');
  // Generated markup is data, never executable code. Only the fixed handlers below run.
  parsed.querySelectorAll('script,iframe,object,embed,base,meta,link').forEach(el=>el.remove());
  parsed.querySelectorAll('*').forEach(el=>Array.from(el.attributes).forEach(attr=>{
    if (attr.name.startsWith('on') || /^(javascript|vbscript):/i.test(attr.value.trim())) el.removeAttribute(attr.name);
  }));
  root.replaceChildren(...Array.from(parsed.head.children), ...Array.from(parsed.body.children));
  const pt = data.lang === 'pt';
  const find = id => root.querySelector('#'+id);
  const timers = [];
  const listen = (el, name, fn) => el?.addEventListener(name, fn);
  root.querySelectorAll('[data-section]').forEach(btn=>listen(btn,'click',()=>{
    const target = find(btn.dataset.section);
    target?.scrollIntoView({block:'start',behavior:'smooth'});
  }));
  const toggles = {'btn-full-standings':'standings-extra','btn-full-c-standings':'c-standings-extra',
    'btn-full-team-chart':'team-chart-extra','btn-full-results':'race-extra','btn-full-calendar':'cal-extra','btn-all-drivers':'drivers-extra'};
  root.querySelectorAll('[id^="btn-full-"]').forEach(btn=>{
    const extra = 'extra-'+btn.id.replace('btn-full-',''); if(find(extra)) toggles[btn.id]=extra;
  });
  Object.entries(toggles).forEach(([button,id])=>{
    const btn=find(button), extra=find(id); if(!btn||!extra)return;
    const label=btn.textContent; btn.setAttribute('role','button');btn.tabIndex=0;
    const toggle=()=>{const open=extra.style.display==='none';extra.style.display=open?(id==='drivers-extra'?'flex':'block'):'none';btn.textContent=open?(pt?'Mostrar menos':'Show less'):label;btn.setAttribute('aria-expanded',String(open));};
    listen(btn,'click',toggle);listen(btn,'keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();toggle();}});
  });
  ['race','sprint','weekend'].forEach(view=>listen(find('tab-btn-'+view),'click',()=>{
    ['race','sprint','weekend'].forEach(v=>{const panel=find('latest-race-view-'+v),btn=find('tab-btn-'+v);
      if(panel)panel.style.display=v===view?'block':'none';if(btn)btn.style.background=v===view?'#e10600':'#222';});
  }));
  root.querySelectorAll('.si-section').forEach(section=>listen(section.querySelector('.si-search'),'input',e=>{
    let visible=0; section.querySelectorAll('tbody tr').forEach(row=>{row.hidden=!row.dataset.driver.includes(e.target.value.trim().toLocaleLowerCase());if(!row.hidden)visible++;});
    const empty=section.querySelector('.si-empty');if(empty)empty.hidden=!!visible;
  }));
  // Native top-layer popovers cannot be covered by the sticky menu or clipped by cards.
  let active=null,activeTrigger=null,pinned=false,closeTimer;
  const hide=()=>{if(active){active.hidePopover();active=null;}activeTrigger?.setAttribute('aria-expanded','false');activeTrigger=null;pinned=false;};
  root.querySelectorAll('.p-cal-event').forEach(item=>{
    const trigger=item.querySelector('.p-cal-track-trigger'), popup=item.querySelector('.p-cal-popup');if(!trigger||!popup)return;
    popup.setAttribute('popover','manual');popup.setAttribute('role','dialog');
    const close=document.createElement('button');close.className='popup-close';close.textContent='×';close.setAttribute('aria-label',pt?'Fechar resultados':'Close results');popup.prepend(close);
    // Popover is moved out of closed <details> so native details layout cannot hide it.
    root.appendChild(popup);
    const show=(pin=false)=>{clearTimeout(closeTimer);if(active!==popup){hide();active=popup;popup.showPopover();}pinned=pin;
      activeTrigger=trigger;trigger.setAttribute('aria-expanded','true');};
    listen(trigger,'pointerenter',e=>{if(e.pointerType==='mouse'&&!pinned)show();});
    const leave=()=>{if(!pinned)closeTimer=setTimeout(hide,180);};
    listen(trigger,'pointerleave',leave);listen(popup,'pointerenter',()=>clearTimeout(closeTimer));listen(popup,'pointerleave',leave);
    listen(trigger,'click',e=>{e.preventDefault();if(active===popup&&pinned)hide();else show(true);});
    listen(close,'click',hide);
  });
  const keydown=e=>{if(e.key==='Escape')hide();};document.addEventListener('keydown',keydown);
  const outside=e=>{if(active&&!e.composedPath().includes(active)&&!e.composedPath().some(el=>el.classList?.contains('p-cal-track-trigger')))hide();};
  document.addEventListener('click',outside);
  if(data.target){const tick=()=>{const seconds=Math.max(0,Math.floor((Date.parse(data.target)-Date.now())/1000));
    [Math.floor(seconds/86400),Math.floor(seconds/3600)%24,Math.floor(seconds/60)%60,seconds%60].forEach((n,i)=>{const el=find(['cd-days','cd-hours','cd-minutes','cd-seconds'][i]);if(el)el.textContent=String(n).padStart(2,'0');});};tick();timers.push(setInterval(tick,1000));}
  return ()=>{hide();clearTimeout(closeTimer);timers.forEach(clearInterval);document.removeEventListener('keydown',keydown);document.removeEventListener('click',outside);};
}
"""

CSS = """
:host {display:block;min-width:0;color:#fafafa;font-family:system-ui}
.surface {width:100%;min-width:0;display:flow-root}
.surface .p-section-nav {position:sticky;top:0;z-index:20;flex-wrap:wrap}
.surface .p-section-nav a {font:600 12px system-ui;color:#c5cada;padding:10px 16px;text-decoration:none;border:1px solid #303643;border-radius:24px}
.surface [id] {scroll-margin-top:95px}
.surface .si-table-scroll {max-height:none;overflow-x:auto;overflow-y:hidden}
.surface .p-calendar-grid {grid-template-columns:minmax(0,1.5fr) minmax(0,1fr)}
.surface .p-cal-track {flex:3;white-space:normal;overflow:visible}
.surface .p-cal-track-trigger {white-space:normal;overflow:visible;text-overflow:clip;text-align:left}
.surface .p-cal-track-trigger > span:not(.p-cal-info) {overflow:visible;text-overflow:clip;white-space:normal;overflow-wrap:anywhere}
.surface .p-cal-winner {flex:1.5}
.surface .p-cal-popup[popover] {display:none;position:fixed;inset:0;margin:auto;width:min(760px,calc(100vw - 32px));height:fit-content;max-height:calc(100dvh - 40px);box-sizing:border-box;z-index:1000;visibility:visible;opacity:1;pointer-events:auto;overflow:hidden}
.surface .p-cal-popup:popover-open {display:block}
.surface .p-cal-popup-body {max-height:calc(100dvh - 180px);overflow:auto}
.surface .popup-close {float:right;border:0;background:transparent;color:white;font-size:26px;cursor:pointer}
.surface .p-btn {text-decoration:none}
@media(max-width:850px){.surface .p-calendar-grid {grid-template-columns:1fr}.surface .p-section-nav a {padding:8px 10px;font-size:10px}}
"""

def render(html: str, *, lang: str, key: str) -> None:
    target = re.search(r'var targetIso = "([^"]*)"', html)
    # Styles and scripts in the source are isolated; executable behavior comes from JS only.
    component = st.components.v2.component('f1_public_surface', html='<div class="surface"></div>', js=JS, css=CSS)
    component(key=key, data={'html':html, 'lang':lang, 'target':target.group(1) if target else ''},
              height='content', width='stretch')
