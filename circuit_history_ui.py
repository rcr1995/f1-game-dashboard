"""Accessible circuit gallery and complete main-race winner histories."""
from datetime import date
from html import escape

from circuit_records import league_lap_records
from puskas_html import (CIRCUIT_SVG_MAP, CIRCUIT_LAP_RECORDS_CSS,
                         _flag_img, _tr_gp, circuit_lap_records_html)


def _date_label(value, pt):
    if not value:
        return '—'
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return '—'
    months = ('jan fev mar abr mai jun jul ago set out nov dez' if pt else
              'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec').split()
    return f'{parsed.day:02d} {months[parsed.month - 1]} {parsed.year}'


def render(cards, results, lang='en', scope_label=None):
    pt = lang == 'pt'
    esc = lambda value: escape(str(value if value is not None else ''), quote=True)
    records = league_lap_records(results)
    scope_text = esc(scope_label) if scope_label else ('todas as ligas e épocas' if pt else 'all leagues and seasons')
    gallery, dialogs = [], []
    columns = [('driver', 'Vencedor' if pt else 'Winner'),
               ('league', 'Liga' if pt else 'League'),
               ('season', 'Época' if pt else 'Season'),
               ('round', 'Ronda' if pt else 'Round'),
               ('date', 'Data' if pt else 'Date'),
               ('game', 'Jogo' if pt else 'Game')]
    for index, card in enumerate(cards):
        gp = card['gp_name']
        venue = card['circuit_name'] or ('Circuito não registado' if pt else 'Circuit not recorded')
        record_venue = card['circuit_name'] or '__unrecorded__'
        label = _tr_gp(lang, gp)
        winners = card['winners']
        count = len(winners)
        distinct = len({row['driver'] for row in winners})
        dialog_id = f'ch-history-{index}'
        title_id = dialog_id + '-title'
        summary_id = dialog_id + '-summary'
        svg = CIRCUIT_SVG_MAP.get(gp, '') if card.get('venue_recorded', True) else ''
        image = (f'<img class="p-track-image" src="{esc(svg)}" alt="" loading="lazy" />' if svg else
                 f'<div class="ch-no-map">{"Traçado indisponível" if pt else "Layout unavailable"}</div>')
        leaders = ''.join(f'<div class="ch-leader ch-leader-{rank}">{medal} {esc(row["driver"])} '
                          f'<span>({row["wins"]} 🏆)</span></div>'
                          for rank, (medal, row) in enumerate(zip(('🥇', '🥈', '🥉'), card['leaders'][:3]), 1))
        if not leaders:
            leaders = f'<p class="ch-muted">{"Sem vencedores de corrida registados." if pt else "No saved main-race winners."}</p>'
        action = ('Ver histórico de vencedores' if pt else 'View winner history')
        accessible_venue = card['circuit_name'] or label
        gallery.append(f'''<article class="p-track-card" data-circuit-key="{esc(card['key'])}">
          <h3 class="p-track-title">{esc(label).upper()}</h3>
          <div class="p-track-country">{esc(venue)} {_flag_img(gp, height=14)}</div>
          {image}{circuit_lap_records_html(gp, record_venue, lang, records, scope_label=scope_label)}
          <div class="p-track-stats"><div class="ch-stat-label">{'VENCEDORES DO GP' if pt else 'GP WINNERS'}</div>{leaders}</div>
          <button type="button" class="ch-open" data-history-id="{dialog_id}" aria-haspopup="dialog" aria-controls="{dialog_id}"
            aria-label="{esc(('Ver todos os vencedores em ' if pt else 'View all race winners at ') + accessible_venue)}">{action} <span aria-hidden="true">↗</span></button>
        </article>''')
        rows = []
        for winner in winners:
            cells = ''.join(f'<td data-label="{esc(header)}">{esc(_date_label(winner.get(key), pt) if key == "date" else winner.get(key) or "—")}</td>'
                            for key, header in columns)
            rows.append(f'<tr>{cells}</tr>')
        body = ('<div class="ch-table-wrap"><table class="ch-table"><caption class="ch-sr-only">'
                + esc(('Vencedores de corrida em ' if pt else 'Race winners at ') + venue)
                + '</caption><thead><tr>' + ''.join(f'<th scope="col">{header}</th>' for _, header in columns)
                + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>') if rows else leaders
        if card.get('unresolved_events'):
            missing = card['unresolved_events']
            body += f'<p class="ch-muted">{missing} {"corridas sem vencedor confirmado nos dados guardados." if pt else "races have no confirmed winner in the saved data."}</p>'
        summary = (f'{count} {"corrida" if count == 1 else "corridas"} · {distinct} {"piloto vencedor" if distinct == 1 else "pilotos vencedores"} · {scope_text}' if pt else
                   f'{count} {"race" if count == 1 else "races"} · {distinct} winning {"driver" if distinct == 1 else "drivers"} · {scope_text}')
        dialogs.append(f'''<dialog class="ch-dialog" id="{dialog_id}" aria-labelledby="{title_id}" aria-describedby="{summary_id}">
          <header class="ch-dialog-header"><div><p class="ch-kicker">{'HISTÓRICO DO CIRCUITO' if pt else 'CIRCUIT HISTORY'}</p>
          <h2 id="{title_id}">{esc(label)} · {'Vencedores do GP' if pt else 'GP winners'}</h2>
          <p class="ch-venue">{esc(venue)}</p><p id="{summary_id}" class="ch-muted">{summary}</p></div>
          <button type="button" class="ch-close" aria-label="{'Fechar histórico de vencedores' if pt else 'Close winner history'}" autofocus>×</button></header>
          <div class="ch-dialog-body">{body}</div>
          <footer class="ch-dialog-footer">{'Só corridas principais. Sprints excluídos. — indica que a data não foi registada.' if pt else 'Main races only. Sprints excluded. — means the date was not recorded.'}</footer>
        </dialog>''')
    help_text = (('Seleciona um circuito para ver os vencedores de corridas da liga/época selecionada.' if pt else
                  'Select a circuit to see main-race winners for the selected league/season.') if scope_label else
                 ('Seleciona um circuito para ver todos os vencedores de corridas nas ligas guardadas.' if pt else
                  'Select a circuit to see every main-race winner across the saved leagues.'))
    return (STYLE + CIRCUIT_LAP_RECORDS_CSS
            + f'<p class="ch-gallery-help">{help_text}</p>'
            + '<div class="p-tracks-grid">' + ''.join(gallery) + '</div>' + ''.join(dialogs))


STYLE = '''<style>
.p-tracks-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr));gap:16px;margin:18px 0 30px}
.ch-gallery-help{font:13px system-ui;color:#acb5c5;margin:6px 0}
.p-track-card{position:relative;display:flex;flex-direction:column;align-items:stretch;background:#111115;border:1px solid #282a31;border-radius:12px;padding:20px 16px;text-align:center;color:#eef1f8;transition:transform .18s,border-color .18s,box-shadow .18s}
.p-track-card:hover{transform:translateY(-3px);border-color:#e10600;box-shadow:0 8px 22px #e1060018}.p-track-card:focus-within{outline:2px solid #dcf3a0;outline-offset:3px}
.p-track-title{font:800 22px 'Teko','Arial Narrow',system-ui;margin:0 0 5px;line-height:1.15;letter-spacing:.7px;color:white}
.p-track-country{font:11px system-ui;color:#aab0bc;min-height:30px;line-height:1.4}.p-track-image{width:100%;height:120px;object-fit:contain;margin:12px 0;filter:drop-shadow(0 0 5px #ffffff33)}
.ch-no-map{height:144px;display:grid;place-items:center;color:#8993a4;font-size:12px}
.p-track-stats{margin-top:10px;padding-top:10px;border-top:1px solid #292a30;min-height:85px;display:flex;flex-direction:column;align-items:center;gap:5px;font:12px system-ui}
.ch-stat-label{font-size:10px;letter-spacing:.08em;color:#939aa9;margin-bottom:4px}.ch-leader{font-weight:600;line-height:1.5}.ch-leader-1{color:#ffd34f}.ch-leader-2{color:#e0e4ed}.ch-leader-3{color:#d58c54}
.ch-open{margin-top:auto;padding:14px 0 0;border:0;background:transparent;color:#c5cedd;font:600 11px system-ui;cursor:pointer}.ch-open:after{content:'';position:absolute;inset:0;border-radius:12px}.ch-open:focus-visible{outline:none}
.ch-dialog{box-sizing:border-box;width:min(960px,calc(100vw - 32px));max-width:960px;max-height:calc(100dvh - 32px);margin:auto;padding:0;border:1px solid #46505f;border-radius:16px;background:#121722;color:#edf1f8;box-shadow:0 24px 80px #000a;font:13px system-ui;overflow:hidden}
.ch-dialog[open]{display:flex;flex-direction:column}.ch-dialog::backdrop{background:#05070bc9;backdrop-filter:blur(4px)}.ch-dialog *{box-sizing:border-box}
.ch-dialog-header{display:flex;justify-content:space-between;align-items:start;gap:16px;padding:22px 24px 16px;border-bottom:1px solid #303848;flex-shrink:0}.ch-kicker{font-size:10px;letter-spacing:.14em;color:#f17a74;margin:0 0 8px;font-weight:700}
.ch-dialog h2{font-size:22px;margin:0 0 6px;line-height:1.25}.ch-venue{margin:0 0 8px;color:#c4cdde;font-size:13px}.ch-muted{color:#a4b0c4;font-size:12px;margin:0;line-height:1.5}
.ch-close{flex:none;display:grid;place-items:center;width:36px;height:36px;border:1px solid #455267;border-radius:8px;background:#202b3a;color:#f5f7fb;cursor:pointer;font:26px system-ui}.ch-close:focus-visible{outline:2px solid #dcf3a0;outline-offset:2px}
.ch-dialog-body{overflow:auto;min-height:0;padding:6px 24px 12px}.ch-table{width:100%;border-collapse:collapse;text-align:left}.ch-table th{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:#9eacc3;padding:12px 9px;background:#121722;position:sticky;top:0}.ch-table td{padding:13px 9px;border-bottom:1px solid #2b3442;font-variant-numeric:tabular-nums;vertical-align:top;overflow-wrap:anywhere}.ch-table td:first-child{font-weight:700;color:#f5d773}.ch-table td:nth-child(5){white-space:nowrap}
.ch-dialog-footer{padding:12px 24px 16px;color:#a4b0c4;border-top:1px solid #303848;font-size:11px;line-height:1.5;flex-shrink:0}.ch-sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
@media(max-width:600px){.ch-dialog{width:calc(100vw - 20px);max-height:calc(100dvh - 20px);border-radius:12px}.ch-dialog-header{padding:16px;gap:8px}.ch-dialog h2{font-size:19px}.ch-dialog-body{padding:0 16px 8px}.ch-dialog-footer{padding:10px 16px}.ch-table thead{display:none}.ch-table tbody tr{display:grid;grid-template-columns:1fr 1fr;gap:10px 16px;padding:14px 0;border-bottom:1px solid #303848}.ch-table td{display:flex;flex-direction:column;gap:3px;border:0;padding:0;font-size:12px;min-width:0}.ch-table td:first-child{grid-column:1/-1;font-size:15px}.ch-table td:before{content:attr(data-label);font-size:9px;font-weight:500;color:#9eacc3;letter-spacing:.05em;text-transform:uppercase}.ch-table td:nth-child(5){white-space:normal}.p-track-card{padding:20px 16px}}
@media(prefers-reduced-motion:reduce){.p-track-card{transition:none}.p-track-card:hover{transform:none}}
</style>'''


JS = r'''
function mountCircuitHistory(root) {
  const dialogs=[...root.querySelectorAll('.ch-dialog')],triggers=[...root.querySelectorAll('.ch-open')];
  const disposers=[];let active=null,opener=null;
  const listen=(el,event,fn)=>{el.addEventListener(event,fn);disposers.push(()=>el.removeEventListener(event,fn));};
  triggers.forEach(trigger=>listen(trigger,'click',()=>{
    const dialog=dialogs.find(item=>item.id===trigger.dataset.historyId);if(!dialog)return;
    if(active?.open)active.close();active=dialog;opener=trigger;dialog.showModal();
  }));
  dialogs.forEach(dialog=>{
    listen(dialog.querySelector('.ch-close'),'click',()=>dialog.close());
    listen(dialog,'click',event=>{if(event.target!==dialog)return;const box=dialog.getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)dialog.close();});
    listen(dialog,'close',()=>{if(active===dialog){active=null;const previous=opener;opener=null;previous?.focus();}});
  });
  return ()=>{opener=null;if(active?.open)active.close();disposers.forEach(dispose=>dispose());};
}
'''
