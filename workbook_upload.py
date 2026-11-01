"""Protected, reviewed whole-workbook replacement; transfers remain session-local."""
from __future__ import annotations
import base64
import hashlib
from io import BytesIO
from zipfile import ZipFile
import openpyxl
import streamlit as st
import admin_auth
import calendar_review
import public_workbook
import race_github

LIMIT = 10 * 1024 * 1024
KEY = 'race_import_excel_upload'

def validate(content: bytes) -> None:
    public_workbook.validate_snapshot(content)
    with ZipFile(BytesIO(content)) as archive:
        if any(name.lower().startswith(('xl/externallinks/', 'xl/embeddings/')) or 'vbaproject' in name.lower() for name in archive.namelist()):
            raise ValueError('Macros, embedded objects and external workbook links are not accepted.')

def compare(previous: bytes, candidate: bytes) -> dict:
    validate(candidate)
    books = [openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=False) for data in (previous, candidate)]
    try:
        before, after = books
        missing = set(before.sheetnames) - set(after.sheetnames)
        if missing:
            raise ValueError('The uploaded Excel is missing existing worksheets: ' + ', '.join(sorted(missing)))
        summary=[]; sample=[]
        from itertools import zip_longest
        for sheet in after:
            old = before[sheet.title].iter_rows(values_only=True) if sheet.title in before.sheetnames else []
            changed=deleted=0
            for rowno, (left,right) in enumerate(zip_longest(old,sheet.iter_rows(values_only=True),fillvalue=()),1):
                for colno,(a,b) in enumerate(zip_longest(left,right,fillvalue=None),1):
                    if a == b: continue
                    changed+=1
                    if a is not None and b is None: deleted+=1
                    if len(sample)<100:
                        sample.append({'Sheet':sheet.title,'Cell':f'{openpyxl.utils.get_column_letter(colno)}{rowno}','Before':str(a) if a is not None else '', 'After':str(b) if b is not None else ''})
            summary.append({'Sheet':sheet.title,'Changed cells':changed,'Cleared cells':deleted})
        return {'summary':summary,'sample':sample,'digest':hashlib.sha256(candidate).hexdigest(),
                'calendar':calendar_review.review_calendar(previous, candidate)}
    finally:
        for book in books: book.close()

def publish(config, content: bytes, *, expected_sha: str, approved_digest: str, approved: bool,
            calendar_acknowledged: bool = False):
    if not admin_auth.is_current_admin() or not approved:
        raise PermissionError('Admin sign-in and explicit approval are required.')
    if hashlib.sha256(content).hexdigest() != approved_digest:
        raise ValueError('The approved Excel has changed. Review it again.')
    client = race_github.GitHubAppClient(config)
    token = client.create_installation_token()
    remote = client._fetch_with_token(token)
    if remote.blob_sha != expected_sha:
        raise race_github.GitHubConflictError('GitHub changed after preview. Download the latest Excel and review again.')
    review = compare(remote.content,content)
    if calendar_review.needs_acknowledgement(review['calendar']) and not calendar_acknowledged:
        raise ValueError('Review and acknowledge the calendar warnings before publishing.')
    if remote.content == content:
        raise ValueError('This Excel is already published.')
    return client._publish_updated_workbook(token=token,remote=remote,updated_bytes=content,
        message='Admin: publish reviewed Excel adjustments',operation='publish reviewed Excel')

UPLOAD_JS = r"""
export default function({parentElement,data,setStateValue}) {
 const input=parentElement.querySelector('input'),label=parentElement.querySelector('label'),status=parentElement.querySelector('p');
 label.firstChild.textContent=data.label; input.setAttribute('aria-label',data.label);
 input.onchange=async()=>{setStateValue('file',null);const file=input.files[0];if(!file)return;
   if(!/\.xlsx$/i.test(file.name)||file.size>10485760||!file.size){status.textContent=data.invalid;return;}
   try {const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
    if(input.files[0]!==file)return;
    setStateValue('file',{name:file.name,content:btoa(binary)});status.textContent=file.name;
   }catch(_){status.textContent=data.invalid;}
 };
}
"""

def _row_ranges(rows):
    """Condense adjacent Excel row numbers while preserving gaps."""
    from itertools import groupby
    spans = []
    for _, group in groupby(enumerate(sorted(rows)), key=lambda item: item[1] - item[0]):
        numbers = [number for _, number in group]
        spans.append(str(numbers[0]) if len(numbers) == 1 else f'{numbers[0]}–{numbers[-1]}')
    return ', '.join(spans) or '—'


_CALENDAR_MESSAGES = {
    'name': ('GP names differ. Check the GP Name in Leagues and Calendar.',
             'Os nomes do GP diferem. Verifica GP Name em Leagues e Calendar.'),
    'missing_round': ('No Calendar entry for this round.', 'A ronda não consta de Calendar.'),
    'ambiguous_round': ('The calendar has no unique GP for this round.', 'O calendário não identifica um único GP para esta ronda.'),
    'status': ('Race results exist. Check whether the Calendar status should be Done.',
               'Há resultados de corrida. Verifica se o estado em Calendar deve ser Done.'),
    'missing_race': ('Calendar says Done, but there are no main Race results.',
                     'Calendar indica Done, mas não há resultados da corrida principal.'),
    'missing_winner': ('No Race driver has Finish Pos 1.', 'Nenhum piloto da corrida tem Finish Pos 1.'),
    'multiple_winners': ('More than one Race result has Finish Pos 1.', 'Mais de um resultado da corrida tem Finish Pos 1.'),
    'invalid_classification': ('The calendar cannot display this classification. Check for repeated drivers or invalid or repeated positions.',
                               'O calendário não consegue mostrar a classificação. Verifica pilotos repetidos e posições inválidas ou repetidas.'),
}


def _calendar_table(issues, pt):
    st.dataframe([{
        'Ronda' if pt else 'Round': issue.round_number,
        'Evento' if pt else 'Event': 'Sprint' if issue.event == 'SR' else ('Corrida' if pt else 'Race'),
        'GP em Leagues' if pt else 'GP in Leagues': issue.uploaded or '—',
        'GP em Calendar' if pt else 'GP in Calendar': issue.expected or '—',
        'Linhas em Leagues' if pt else 'Leagues rows': _row_ranges(issue.rows),
        'Verificar' if pt else 'Check': _CALENDAR_MESSAGES[issue.problem][int(pt)],
        'Época / Liga' if pt else 'Season / League': f'{issue.game} · {issue.season} · {issue.league}',
    } for issue in issues], hide_index=True, width='stretch')


def _render_calendar_review(review, pt):
    st.subheader('Verificação do calendário' if pt else 'Calendar check')
    if review['new_unchecked']:
        st.warning('Não foi possível identificar o calendário destas épocas. Verifica a liga, o jogo e a época antes de publicar.'
                   if pt else 'These seasons have no uniquely matching calendar. Check their league, game and season before publishing.')
        st.text('\n'.join(review['new_unchecked']))
    if review['new']:
        st.warning('Há novos avisos ou avisos alterados. Corrige as linhas indicadas e volta a carregar o Excel, ou confirma que pretendes publicar assim.'
                   if pt else 'New or changed calendar warnings. Correct the listed rows and upload again, or acknowledge them to publish as reviewed.')
        _calendar_table(review['new'], pt)
    elif not review['new_unchecked']:
        st.caption('Não há novos avisos nas rondas comparadas.' if pt else 'No new warnings for the rounds compared.')
    if review['existing']:
        with st.expander('Avisos já presentes no Excel publicado' if pt else 'Warnings already in the published workbook'):
            _calendar_table(review['existing'], pt)
    if review['unchecked']:
        with st.expander('Épocas sem calendário identificável' if pt else 'Seasons without a uniquely matching calendar'):
            st.text('\n'.join(review['unchecked']))


def render(config, *, lang: str) -> None:
    if not admin_auth.is_current_admin():
        st.stop()
    pt=lang=='pt'
    st.subheader('Upload latest Excel' if not pt else 'Carregar Excel mais recente')
    st.caption('Escolhe um ficheiro .xlsx (até 10 MB), revê as alterações e aprova a publicação. A versão anterior fica no histórico do GitHub.' if pt else
               'Choose an .xlsx file (up to 10 MB), review the changes, then approve publication. The previous version remains in GitHub history.')
    component=st.components.v2.component('f1_excel_upload',html='<label>Excel <input type="file" accept=".xlsx" /></label><p role="status"></p>',js=UPLOAD_JS,
        css='label,p {font:14px system-ui;color:#fafafa} input {display:block;margin:12px 0} input::file-selector-button {padding:12px;color:white;background:#20232c;border:1px solid #555;border-radius:8px}')
    result=component(key=KEY,data={'label':'Escolher Excel' if pt else 'Choose Excel','invalid':'Ficheiro .xlsx inválido (máx. 10 MB).' if pt else 'Choose a valid .xlsx file (max. 10 MB).'},on_file_change=lambda:st.session_state.pop(KEY+'_preview',None),height='content')
    payload = result.get('file') if hasattr(result,'get') else None
    if not payload: return
    try:
        encoded=payload.get('content','')
        if not isinstance(encoded,str) or len(encoded)>LIMIT*4//3+4: raise ValueError('Excel exceeds 10 MB.')
        content=base64.b64decode(encoded,validate=True)
        if not isinstance(payload.get('name'),str) or not payload['name'].lower().endswith('.xlsx'): raise ValueError('Choose an .xlsx file.')
        preview=st.session_state.get(KEY+'_preview')
        refresh = st.button('Atualizar pré-visualização' if pt else 'Refresh preview')
        if refresh or not preview or preview['digest'] != hashlib.sha256(content).hexdigest():
            with st.spinner('A comparar com o calendário…' if pt else 'Checking the workbook against the calendar…'):
                remote=race_github.fetch_remote_workbook(config)
                preview=compare(remote.content,content)
                preview['sha']=remote.blob_sha
                st.session_state[KEY+'_preview']=preview
        _render_calendar_review(preview['calendar'], pt)
        st.table(preview['summary'])
        with st.expander('Ver alterações nas células' if pt else 'View changed cells'):
            st.caption('Primeiras 100 alterações de células; estilos e fórmulas do ficheiro carregado também serão substituídos.' if pt else 'First 100 cell changes; uploaded formatting and formulas will also replace the current file.')
            st.table(preview['sample'])
        review_key = preview['sha']+'_'+preview['digest']
        acknowledged = False
        requires_ack = calendar_review.needs_acknowledgement(preview['calendar'])
        if requires_ack:
            acknowledged = st.checkbox('Revi os avisos do calendário e pretendo publicar este Excel assim.'
                if pt else 'I reviewed the calendar warnings and want to publish this workbook as shown.',
                key=KEY+'_calendar_'+review_key)
        approved=st.checkbox('Aprovo substituir o Excel completo no GitHub, incluindo as células removidas acima.' if pt else 'I approve replacing the entire GitHub Excel, including the cleared cells shown above.',key=KEY+'_approve_'+review_key)
        ready = approved and (not requires_ack or acknowledged)
        if st.button('Publicar Excel aprovado' if pt else 'Publish approved Excel',disabled=not ready):
            # Consume the preview before any uncertain network response; never silently retry a write.
            st.session_state.pop(KEY+'_preview',None)
            _,url,_=publish(config,content,expected_sha=preview['sha'],approved_digest=preview['digest'],
                            approved=approved,calendar_acknowledged=acknowledged)
            admin_auth.clear_race_import_state(st.session_state)
            st.success('Excel publicado. O Dashboard irá carregar esta versão.' if pt else 'Excel published. The Dashboard will load this version.')
            st.link_button('GitHub commit',url)
            st.stop()
    except (ValueError,TypeError,KeyError,race_github.GitHubPersistenceError,OSError) as exc:
        st.session_state.pop(KEY+'_preview',None)
        st.error(('Não foi possível publicar. Descarrega o Excel mais recente e revê novamente.' if pt else 'Unable to publish. Download the latest Excel and review again.') + (' ' + str(exc) if isinstance(exc,ValueError) else ''))
