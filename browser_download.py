"""Deliver validated bytes over the active session, without instance-local media URLs."""

from __future__ import annotations

import base64
from pathlib import PurePath

import streamlit as st

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

HTML = '<a class="excel-download" role="button"></a><span class="download-note" role="status"></span>'
CSS = """
.excel-download {display:flex;justify-content:center;align-items:center;gap:10px;
 padding:14px 20px;border:1px solid #51596b;border-radius:10px;color:inherit;
 background:rgba(120,130,160,.08);text-decoration:none;font:600 15px system-ui;cursor:pointer}
.excel-download:hover {border-color:#e10600;background:rgba(225,6,0,.12)}
.excel-download:focus-visible {outline:3px solid #ff5757;outline-offset:3px}
.download-note {display:block;font:12px system-ui;margin-top:6px;color:inherit}
"""
JS = """
export default function(component) {
  const {data, parentElement} = component;
  const link = parentElement.querySelector('.excel-download');
  const status = parentElement.querySelector('.download-note');
  let url;
  try {
    const raw = atob(data.content);
    const bytes = Uint8Array.from(raw, ch => ch.charCodeAt(0));
    url = URL.createObjectURL(new Blob([bytes], {type: data.mime}));
    link.href = url;
    link.download = data.filename;
    link.textContent = data.label;
    link.title = data.help;
  } catch (_) {
    link.removeAttribute('href');
    link.setAttribute('aria-disabled', 'true');
    link.textContent = data.error;
  }
  return () => { if (url) URL.revokeObjectURL(url); };
}
"""


def render_excel_download(content: bytes, filename: str, *, label: str, help_text: str,
                          error_text: str, key: str = "race_import_excel_download") -> None:
    # Enforce the capability boundary even if a future caller forgets its gate.
    import admin_auth

    if not admin_auth.is_current_admin():
        st.stop()
    if not isinstance(content, bytes) or not content or len(content) > 32 * 1024 * 1024:
        raise ValueError("Invalid workbook download")
    if PurePath(filename).name != filename or not filename.lower().endswith(".xlsx"):
        raise ValueError("Invalid workbook filename")
    component = st.components.v2.component(
        "f1_excel_download", html=HTML, css=CSS, js=JS, isolate_styles=True,
    )
    component(key=key, data={
        "content": base64.b64encode(content).decode("ascii"),
        "filename": filename, "mime": XLSX_MIME, "label": label,
        "help": help_text, "error": error_text,
    }, width="stretch", height="content")
