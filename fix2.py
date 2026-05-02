import sys
import re

with open("app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix style_pos_column
content = re.sub(
    r'st\.dataframe\(style_pos_column\(loc_st\),\s*use_container_width=True,\s*hide_index=True\)',
    'st.dataframe(style_pos_column(loc_st, is_light=(st.session_state.get("theme_mode", "Dark") == "Light")), use_container_width=True, hide_index=True)',
    content
)

# Fix tab_circuits
tab_circuits_broken = r'd_cir\s*=\s*base_all\.copy\(\)\s*if\s*"IsSeasonFinal"\s*not\s*in\s*d_cir\.columns:\s*d_cir\s*=\s*mark_season_final\(d_cir\)\s*d_cir\s*=\s*d_cir\[\(~d_cir\["IsSeasonFinal"\]\)\s*&\s*\(d_cir\["Finish\s*Pos"\]\s*==\s*1\)\]'
tab_circuits_fixed = 'd_cir = base_all[(~base_all["IsSeasonFinal"]) & (base_all["Finish Pos"] == 1)].copy()'
content = re.sub(tab_circuits_broken, tab_circuits_fixed, content)


missing_code = """
with tab_calendar:
    st.subheader(tr(lang, "calendar_title"))
    cal = calendar_raw.copy()
    if cal.empty:
        st.info(tr(lang, "not_enough"))
    else:
        cal = cal[cal["League Name"] == latest_meta["League Name"]].copy()
        if cal.empty:
            st.info(tr(lang, "not_enough"))
        else:
            cal["Date"] = cal["Date"].dt.strftime("%Y-%m-%d").fillna("-")
            cal["Status"] = cal["Status"].replace({"nan": ""})
            done_mask     = cal["Status"].str.lower().eq("done")
            upcoming_mask = cal["Status"].str.lower().eq("upcoming")

            # ── Next race highlight box ──
            upcoming_rows = cal[upcoming_mask].copy()
            if not upcoming_rows.empty:
                nr = upcoming_rows.iloc[0]
                nr_round  = int(nr["Round"]) if pd.notna(nr.get("Round")) else ""
                nr_gp     = nr.get("GP Name", "")
                nr_circuit= nr.get("Circuit", "")
                nr_date   = nr.get("Date", "")
                circuit_line = f"{nr_circuit} • " if nr_circuit and str(nr_circuit) not in ("", "nan") else ""
                st.markdown(f'''
                <div class="next-race-box">
                  <div class="next-race-label">🔵 {tr(lang, "next_race_label")} — {tr(lang, "round_label")} {nr_round}</div>
                  <div class="next-race-name">{nr_gp}</div>
                  <div class="next-race-sub">{circuit_line}{nr_date}</div>
                </div>
                ''', unsafe_allow_html=True)

            cdone, cup = st.columns(2)
            cdone.metric(tr(lang, "calendar_done"),     int(done_mask.sum()))
            cup.metric(tr(lang,   "calendar_upcoming"), int(upcoming_mask.sum()))

            # ── Calendar table with status pills ──
            show_cols = [c for c in ["Round", "Date", "GP Name", "Circuit", "Status"] if c in cal.columns]
            cal_disp = cal[show_cols].copy()
            def _pill(s: str) -> str:
                s2 = str(s).strip().lower()
                if s2 == "done":     return '<span class="pill-done">Done</span>'
                if s2 == "upcoming": return '<span class="pill-upcoming">Upcoming</span>'
                return '<span class="pill-tbd">—</span>'
            if "Status" in cal_disp.columns:
                cal_disp["Status"] = cal_disp["Status"].apply(_pill)
            st.markdown(cal_disp.to_html(escape=False, index=False), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            download_csv_button(cal[show_cols], "league_calendar.csv", tr(lang, "download"))


with tab_gp:
    d_gp = base_all[~base_all["IsSeasonFinal"]].copy()

    gp_pairs = (
        d_gp[["SeasonLabel", "SeasonNum", "League Name"]]
        .dropna(subset=["SeasonLabel", "League Name"])
        .drop_duplicates()
        .copy()
    )
    gp_pairs["SeasonLeague"] = gp_pairs["SeasonLabel"].astype(str) + " ||| " + gp_pairs["League Name"].astype(str)
    gp_pairs["_SortKey"] = gp_pairs["SeasonNum"].fillna(gp_pairs["SeasonLabel"].map(_season_sort_key))
    gp_pairs = gp_pairs.sort_values(["_SortKey", "SeasonLabel", "League Name"], ascending=[False, False, True])

    seasonleague_options = gp_pairs["SeasonLeague"].unique().tolist()
    options = [tr(lang, "all_gp_label")] + seasonleague_options
    sel_gp_pair = st.selectbox(tr(lang, "season_league_gp"), options, index=0, key="gp_pair")

    df_gp = d_gp.copy()
    gp_all_time = True
    if sel_gp_pair != tr(lang, "all_gp_label"):
        gp_season, gp_league = sel_gp_pair.split(" ||| ", 1)
        df_gp = df_gp[(df_gp["SeasonLabel"] == gp_season) & (df_gp["League Name"] == gp_league)].copy()
        st.caption(f"{gp_season} • {gp_league}")
        gp_all_time = False

    if df_gp.empty:
        st.info(f"{tr(lang, 'no_rows')} {tr(lang, 'empty_hint')}")
    else:
        view = st.radio(tr(lang, "standings_type"), [tr(lang, "drivers"), tr(lang, "constructors")], horizontal=True, key="dash_view")
        view_canon = {tr(lang, "drivers"): "Drivers", tr(lang, "constructors"): "Constructors"}[view]
        entity_col = "Driver" if view_canon == "Drivers" else "Team"

        st_table = standings_table(df_gp, entity=view_canon)
        st.subheader(tr(lang, "standings"))
        show_form_cols = st.toggle(tr(lang, "show_form_cols"), value=False)
        if show_form_cols:
            form = form_table(df_gp, entity_col=entity_col)
            st_table = st_table.merge(form, on=entity_col, how="left") if not form.empty else st_table
        loc_st = localized_table(st_table, lang)
        if "Pos" in loc_st.columns:
            st.dataframe(style_pos_column(loc_st, is_light=(st.session_state.get("theme_mode", "Dark") == "Light")), use_container_width=True, hide_index=True)
        else:
            st.dataframe(loc_st, use_container_width=True, hide_index=True)

        st.subheader(tr(lang, "gp_progression"))
        preset = st.radio(tr(lang, "chart_preset"), ["Top 5", "Top 10", "Custom"], horizontal=True, key="gp_chart_preset")
        if preset == "Top 5":
            top_n = 5
        elif preset == "Top 10":
            top_n = 10
        else:
            top_n = st.slider(tr(lang, "top_n_lines"), 5, 30, 10, key="gp_topn")

        wide, long = cumulative_points_wide(df_gp, entity_col=entity_col, all_time=gp_all_time)
        if not wide.empty and not long.empty:
            last_idx = wide.index.max()
            final = wide.tail(1).T.sort_values(by=last_idx, ascending=False)
            keep = final.head(top_n).index.tolist()
            long_k = long[long[entity_col].isin(keep)].copy()
            order_x = long_k.sort_values("EventIdx")[["EventIdx", "EventLabel"]].drop_duplicates().sort_values("EventIdx")["EventLabel"].tolist()
            last_pts = long_k.sort_values("EventIdx").groupby(entity_col)["CumPoints"].last().sort_values(ascending=False)
            order_entities = last_pts.index.tolist()
            if PLOTLY_OK:
                fig = px.line(long_k, x="EventLabel", y="CumPoints", color=entity_col, markers=True,
                              category_orders={"EventLabel": order_x, entity_col: order_entities},
                              color_discrete_sequence=THEME_CFG["line_palette"],
                              template=THEME_CFG["plotly_template"])
                fig.update_layout(height=550, margin=dict(l=10, r=10, t=10, b=40), legend_title_text="")
                fig.update_xaxes(type="category", title=(tr(lang,"timeline_label") if gp_all_time else tr(lang,"gp_label")),
                                 rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.line_chart(wide[keep].ffill().fillna(0), height=550)

        st.markdown(f"### {tr(lang, 'tension')}")
        _, gp_tension_df, _ = championship_tension(df_gp, entity_col=entity_col)
        if not gp_tension_df.empty and PLOTLY_OK:
            tdf = gp_tension_df.copy()
            tdf["EventLabel"] = "R" + tdf["EventIdx"].astype(int).astype(str)
            fig_tension = go.Figure()
            fig_tension.add_trace(go.Scatter(
                x=tdf["EventLabel"], y=tdf["GapP1P2"],
                mode="lines+markers", name=tr(lang, "gap_p1_p2"),
                fill="tozeroy", fillcolor="rgba(46,204,113,0.1)",
                line={"color": THEME_CFG["positive"], "width": 2},
            ))
            fig_tension.add_trace(go.Scatter(
                x=tdf["EventLabel"], y=tdf["Top3Spread"],
                mode="lines+markers", name=tr(lang, "gap_top3"),
"""

# Find the exact pattern with regex to handle the blank lines
pattern = r'(st\.dataframe\(streak_display,\s*use_container_width=True,\s*hide_index=True\))(\s*fill="tozeroy",\s*fillcolor="rgba\(176,176,176,0\.07\)",\s*line=\{"color": THEME_CFG\["neutral"\],\s*"width": 2\},\s*\)\)\s*fig_tension\.update_layout\(\s*template=THEME_CFG\["plotly_template"\],\s*height=360,\s*margin=dict\(l=10,\s*r=10,\s*t=10,\s*b=10\),\s*legend=dict\(orientation="h",\s*yanchor="bottom",\s*y=1\.02,\s*xanchor="right",\s*x=1\),\s*\)\s*st\.plotly_chart\(fig_tension,\s*use_container_width=True\))'

def repl(match):
    return match.group(1) + "\n\n" + missing_code + match.group(2)

content = re.sub(pattern, repl, content, flags=re.MULTILINE)

with open("app.py", "w", encoding="utf-8") as f:
    f.write(content)
