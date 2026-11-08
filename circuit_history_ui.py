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


def _head_to_head_html(rows, venue, pt):
    """Compact card comparison and a fully labelled, mobile-readable table."""
    if not rows:
        return '', ''
    esc = lambda value: escape(str(value if value is not None else ''), quote=True)
    title = 'Frente a frente' if pt else 'Head-to-head'
    labels = {'driver': 'Piloto' if pt else 'Driver',
              'starts': 'Resultados GP' if pt else 'GP results',
              'wins': 'Vitórias' if pt else 'Wins',
              'podiums': 'Pódios' if pt else 'Podiums',
              'best_lap': 'Melhor volta' if pt else 'Best lap'}
    best = {}
    for field in ('wins', 'podiums'):
        values = [row.get(field) for row in rows if isinstance(row.get(field), (int, float))]
        maximum = max(values, default=0)
        if maximum > 0:
            best[field] = maximum
    laps = [row.get('best_lap_ms') for row in rows
            if isinstance(row.get('best_lap_ms'), (int, float)) and row['best_lap_ms'] > 0]
    if laps:
        best['best_lap'] = min(laps)

    def number(row, field):
        value = row.get(field)
        if field in ('wins', 'podiums') and row.get('has_results') is False:
            return '—'
        return '—' if value is None else esc(value)

    def highlighted(row, field):
        value = row.get('best_lap_ms') if field == 'best_lap' else row.get(field)
        return field in best and value == best[field]

    def lead_description(row, field):
        if not highlighted(row, field):
            return ''
        tied = sum(highlighted(item, field) for item in rows) > 1
        description = ('Melhor valor guardado entre estes três pilotos' if pt else
                       'Best saved value among these three drivers')
        if tied:
            description += ' (empatado)' if pt else ' (tied)'
        return f'<span class="ch-sr-only"> · {description}</span>'

    no_results = 'Sem resultados guardados' if pt else 'No saved results'
    preview = ''.join(
        f'<tr><th scope="row" title="{no_results if row.get("has_results") is False else ""}">' + esc(row.get('driver')) + '</th>'
        + ''.join(f'<td class="{"ch-best" if highlighted(row, field) else ""}">'
                  + number(row, field) + lead_description(row, field) + '</td>'
                  for field in ('wins', 'podiums')) + '</tr>' for row in rows)
    preview = (f'<table class="ch-compare-preview"><caption>{title}</caption>'
               f'<thead><tr><th scope="col" class="ch-sr-only">{labels["driver"]}</th>'
               f'<th scope="col">{labels["wins"]}</th><th scope="col">{labels["podiums"]}</th>'
               '</tr></thead><tbody>' + preview + '</tbody></table>')
    full_rows = []
    for row in rows:
        driver_context = f'<small>{no_results}</small>' if row.get('has_results') is False else ''
        unresolved = row.get('unresolved_results', 0)
        if unresolved:
            driver_context += (f'<small>{esc(unresolved)} '
                               + ('resultados por confirmar · totais parciais' if pt else 'unresolved results · partial totals')
                               + '</small>')
        cells = [f'<th scope="row">{esc(row.get("driver"))}{driver_context}</th>']
        for field in ('starts', 'wins', 'podiums'):
            cells.append(f'<td data-label="{labels[field]}" class="{"ch-best" if highlighted(row, field) else ""}">'
                         + number(row, field) + lead_description(row, field) + '</td>')
        lap = esc(row.get('best_lap') or '—')
        context = [row.get('best_lap_season')]
        if row.get('best_lap_type') in ('R', 'SR'):
            context.append(('Sprint' if row['best_lap_type'] == 'SR' else ('Corrida' if pt else 'Race')))
        if row.get('best_lap'):
            context += [row.get('best_lap_league'), row.get('best_lap_game')]
            details = ' · '.join(esc(value) for value in context if value)
            lap = f'<strong>{lap}</strong>' + (f'<small>{details}</small>' if details else '')
        cells.append(f'<td data-label="{labels["best_lap"]}" class="{"ch-best" if highlighted(row, "best_lap") else ""}">'
                     + lap + lead_description(row, 'best_lap') + '</td>')
        full_rows.append('<tr>' + ''.join(cells) + '</tr>')
    note = ('Resultados GP, vitórias e pódios: só corridas principais. As melhores voltas incluem corridas e Sprints. '
            'Os valores refletem apenas os resultados guardados; 0 resultados GP significa que não há classificação de GP registada.' if pt else
            'GP results, wins and podiums: main races only. Best laps include Races and Sprints. '
            'Values reflect saved results only; 0 GP results means no recorded GP classification.')
    comparison = (f'<section class="ch-comparison"><h3>{title}</h3><p class="ch-muted">{note}</p>'
                  '<div class="ch-table-wrap"><table class="ch-h2h-table">'
                  f'<caption class="ch-sr-only">{title} · {esc(venue)}</caption><thead><tr>'
                  + ''.join(f'<th scope="col">{label}</th>' for label in labels.values())
                  + '</tr></thead><tbody>' + ''.join(full_rows) + '</tbody></table></div></section>')
    return preview, comparison


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
        preview, comparison = _head_to_head_html(card.get('head_to_head'), venue, pt)
        country = card.get('country_pt' if pt else 'country_en', '')
        total_races = card.get('race_count', count) + card.get('unresolved_events', 0)
        race_label = (f'{total_races} {"corrida de GP" if total_races == 1 else "corridas de GP"}' if pt else
                      f'{total_races} GP {"race" if total_races == 1 else "races"}')
        card_meta = ' · '.join(esc(value) for value in (country, race_label) if value)
        action = ('Vencedores e frente a frente' if pt else 'Winner history & head-to-head')
        accessible_venue = card['circuit_name'] or label
        comparison_description = (f'<span class="ch-sr-only" id="{dialog_id}-comparison-help">'
                                  + ('Inclui estatísticas frente a frente dos três pilotos.' if pt else
                                     'Includes head-to-head statistics for the three drivers.') + '</span>') if comparison else ''
        described = f' aria-describedby="{dialog_id}-comparison-help"' if comparison else ''
        gallery.append(f'''<article class="p-track-card" data-circuit-key="{esc(card['key'])}">
          <h3 class="p-track-title">{esc(label).upper()}</h3>
          <div class="p-track-country">{esc(venue)} {_flag_img(gp, height=14)}</div>
          <div class="ch-card-meta">{card_meta}</div>
          {image}{circuit_lap_records_html(gp, record_venue, lang, records, scope_label=scope_label)}
          <div class="p-track-stats"><div class="ch-stat-label">{'VENCEDORES DO GP' if pt else 'GP WINNERS'}</div>{leaders}</div>
          {preview}
          {comparison_description}
          <button type="button" class="ch-open" data-history-id="{dialog_id}" aria-haspopup="dialog" aria-controls="{dialog_id}"
            aria-label="{esc(('Ver todos os vencedores em ' if pt else 'View all race winners at ') + accessible_venue)}"{described}>{action} <span aria-hidden="true">↗</span></button>
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
        if comparison:
            body = comparison + f'<section class="ch-winner-history"><h3>{"Todos os vencedores do GP" if pt else "All GP winners"}</h3>' + body + '</section>'
        summary = (f'{count} {"corrida" if count == 1 else "corridas"} · {distinct} {"piloto vencedor" if distinct == 1 else "pilotos vencedores"} · {scope_text}' if pt else
                   f'{count} {"race" if count == 1 else "races"} · {distinct} winning {"driver" if distinct == 1 else "drivers"} · {scope_text}')
        dialogs.append(f'''<dialog class="ch-dialog" id="{dialog_id}" aria-labelledby="{title_id}" aria-describedby="{summary_id}">
          <header class="ch-dialog-header"><div><p class="ch-kicker">{'HISTÓRICO DO CIRCUITO' if pt else 'CIRCUIT HISTORY'}</p>
          <h2 id="{title_id}">{esc(label)} · {'Vencedores do GP' if pt else 'GP winners'}</h2>
          <p class="ch-venue">{esc(venue)}</p><p id="{summary_id}" class="ch-muted">{summary}</p></div>
          <button type="button" class="ch-close" aria-label="{'Fechar histórico de vencedores' if pt else 'Close winner history'}" autofocus>×</button></header>
          <div class="ch-dialog-body">{body}</div>
          <footer class="ch-dialog-footer">{'Histórico de vencedores: só corridas principais. Sprints excluídos. — indica que a data não foi registada.' if pt else 'Winner history: Main races only. Sprints excluded. — means the date was not recorded.'}</footer>
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
.ch-card-meta{font:10px system-ui;color:#8f9bad;line-height:1.5;margin:-2px 0 2px}
.ch-no-map{height:144px;display:grid;place-items:center;color:#8993a4;font-size:12px}
.p-track-stats{margin-top:10px;padding-top:10px;border-top:1px solid #292a30;min-height:85px;display:flex;flex-direction:column;align-items:center;gap:5px;font:12px system-ui}
.ch-stat-label{font-size:10px;letter-spacing:.08em;color:#939aa9;margin-bottom:4px}.ch-leader{font-weight:600;line-height:1.5}.ch-leader-1{color:#ffd34f}.ch-leader-2{color:#e0e4ed}.ch-leader-3{color:#d58c54}
.ch-compare-preview{width:100%;border-collapse:collapse;margin:14px 0 2px;text-align:left;font:11px system-ui;border-top:1px solid #292a30;font-variant-numeric:tabular-nums}.ch-compare-preview caption{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#a7b4c8;text-align:left;padding:12px 0 5px;caption-side:top}.ch-compare-preview th,.ch-compare-preview td{padding:4px 3px;font-weight:500}.ch-compare-preview thead th{text-align:right;color:#8f9bad;font-size:10px}.ch-compare-preview tbody td{text-align:right;width:58px}.ch-compare-preview tbody th{color:#dae1ed;font-weight:600}.ch-best{color:#dcf3a0!important;font-weight:750!important}
.ch-open{margin-top:auto;padding:14px 0 0;border:0;background:transparent;color:#c5cedd;font:600 11px system-ui;cursor:pointer}.ch-open:after{content:'';position:absolute;inset:0;border-radius:12px}.ch-open:focus-visible{outline:none}
.ch-dialog{box-sizing:border-box;width:min(960px,calc(100vw - 32px));max-width:960px;max-height:calc(100dvh - 32px);margin:auto;padding:0;border:1px solid #46505f;border-radius:16px;background:#121722;color:#edf1f8;box-shadow:0 24px 80px #000a;font:13px system-ui;overflow:hidden}
.ch-dialog[open]{display:flex;flex-direction:column}.ch-dialog::backdrop{background:#05070bc9;backdrop-filter:blur(4px)}.ch-dialog *{box-sizing:border-box}
.ch-dialog-header{display:flex;justify-content:space-between;align-items:start;gap:16px;padding:22px 24px 16px;border-bottom:1px solid #303848;flex-shrink:0}.ch-kicker{font-size:10px;letter-spacing:.14em;color:#f17a74;margin:0 0 8px;font-weight:700}
.ch-dialog h2{font-size:22px;margin:0 0 6px;line-height:1.25}.ch-venue{margin:0 0 8px;color:#c4cdde;font-size:13px}.ch-muted{color:#a4b0c4;font-size:12px;margin:0;line-height:1.5}
.ch-close{flex:none;display:grid;place-items:center;width:36px;height:36px;border:1px solid #455267;border-radius:8px;background:#202b3a;color:#f5f7fb;cursor:pointer;font:26px system-ui}.ch-close:focus-visible{outline:2px solid #dcf3a0;outline-offset:2px}
.ch-dialog-body{overflow:auto;min-height:0;padding:6px 24px 12px}.ch-table{width:100%;border-collapse:collapse;text-align:left}.ch-table th{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:#9eacc3;padding:12px 9px;background:#121722;position:sticky;top:0}.ch-table td{padding:13px 9px;border-bottom:1px solid #2b3442;font-variant-numeric:tabular-nums;vertical-align:top;overflow-wrap:anywhere}.ch-table td:first-child{font-weight:700;color:#f5d773}.ch-table td:nth-child(5){white-space:nowrap}
.ch-dialog-body h3{font-size:15px;margin:18px 0 8px;line-height:1.35}.ch-comparison{padding-bottom:16px;border-bottom:1px solid #303848}.ch-h2h-table{width:100%;border-collapse:collapse;text-align:left;margin-top:10px;font-variant-numeric:tabular-nums}.ch-h2h-table thead th{font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:#9eacc3;padding:10px 8px;white-space:nowrap}.ch-h2h-table tbody th,.ch-h2h-table td{padding:12px 8px;border-bottom:1px solid #2b3442;vertical-align:top}.ch-h2h-table tbody th{font-weight:700;color:#e4eaf5;min-width:116px}.ch-h2h-table td:nth-child(n+2):nth-child(-n+4){text-align:center}.ch-h2h-table th:nth-child(n+2):nth-child(-n+4){text-align:center}.ch-h2h-table small{display:block;font-size:10px;line-height:1.5;font-weight:400;color:#9eacc3;margin-top:4px}.ch-h2h-table td:last-child{min-width:160px}.ch-h2h-table strong{white-space:nowrap}
.ch-dialog-footer{padding:12px 24px 16px;color:#a4b0c4;border-top:1px solid #303848;font-size:11px;line-height:1.5;flex-shrink:0}.ch-sr-only{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
@media(max-width:600px){.ch-dialog{width:calc(100vw - 20px);max-height:calc(100dvh - 20px);border-radius:12px}.ch-dialog-header{padding:16px;gap:8px}.ch-dialog h2{font-size:19px}.ch-dialog-body{padding:0 16px 8px}.ch-dialog-footer{padding:10px 16px}.ch-table thead{display:none}.ch-table tbody tr{display:grid;grid-template-columns:1fr 1fr;gap:10px 16px;padding:14px 0;border-bottom:1px solid #303848}.ch-table td{display:flex;flex-direction:column;gap:3px;border:0;padding:0;font-size:12px;min-width:0}.ch-table td:first-child{grid-column:1/-1;font-size:15px}.ch-table td:before{content:attr(data-label);font-size:9px;font-weight:500;color:#9eacc3;letter-spacing:.05em;text-transform:uppercase}.ch-table td:nth-child(5){white-space:normal}.p-track-card{padding:20px 16px}}
@media(max-width:600px){.ch-h2h-table thead{display:none}.ch-h2h-table tbody tr{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px 8px;padding:14px 0;border-bottom:1px solid #303848}.ch-h2h-table tbody th{grid-column:1/-1;padding:0;border:0;font-size:14px;min-width:0}.ch-h2h-table td{display:flex;flex-direction:column;gap:4px;padding:0;border:0;min-width:0;text-align:left!important;font-size:13px}.ch-h2h-table td:last-child{grid-column:1/-1;min-width:0}.ch-h2h-table td:before{content:attr(data-label);color:#9eacc3;font-size:9px;font-weight:500;letter-spacing:.05em;text-transform:uppercase}.ch-h2h-table td small{margin-top:0}.ch-h2h-table tbody th small{font-size:10px}}
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
