import os
import json
from pathlib import Path
import pandas as pd
from espn_api.football import League
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests

# ==========================================
# 1. KONFIGURATION & SETUP
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / "espn_cache.json"
HISTORIE_ORDNER = BASE_DIR / "Historie"

LEAGUE_ID = 929484013
YEAR = 2026

ESPN_S2 = 'AEAERZvM%2B%2F2k6vQz%2FjywCaRJK%2BT9jlJTZRBgvweTS8Q0rg62zCtemnHlTo3uDODI2hEyxwp9AKP%2BWLJ%2FPMla6T0F819p7dR4kQjBafIfJbnnp%2F3RlBdSTdap%2BDlTomUTpsvzKrqNoM%2FmqaF9vuVAlX17FoCIU%2Bn9p1WaWce67BeocSvkl5w09QdvxVyPgZjIWEKnZlqBWPC7yktJam6WqdxWDRqF44TyryQWf2EosruLIq1aJ0toq2KgQ2lCTepAow5tqfRgN4i5DjBZx5M6fMA0xFYQ7R92SJSEOEkplfP9ng%3D%3D'
SWID = '{1C32344B-8776-407F-8007-001AEA9745E3}'

TEAM_LOGOS = {
    "Berlin Mustangs": "https://i.postimg.cc/Bv0n2Pv1/Gemini-Generated-Image-up2tz2up2tz2up2t.jpg",
    "Bytow Butcher Coach": "https://i.postimg.cc/yY315ygj/zugeschnittenes-kreis-bild-(8).png",
    "T Sharks": "https://i.postimg.cc/VkH3c3xw/Gemini-Generated-Image-bolsjvbolsjvbols.jpg",
    "MC Dolphins": "https://i.postimg.cc/05w5XCJQ/zugeschnittenes-kreis-bild.png",
    "Gigantic Gorillas": "https://i.postimg.cc/VkYY6QZB/Gemini-Generated-Image-mfmrnhmfmrnhmfmr.jpg",
    "Dexon Warriors": "https://i.postimg.cc/gkz5Lzd2/zugeschnittenes-kreis-bild-(9).png",
    "Moonwing Ravens": "https://i.postimg.cc/x8DQVWb5/zugeschnittenes-kreis-bild-(4).png",
    "Finn Bears": "https://i.postimg.cc/B6JtfPWy/zugeschnittenes-kreis-bild-(2).png",
    "Leonid's Desperados": "https://i.postimg.cc/263RWCnZ/zugeschnittenes-kreis-bild-(12).png",
    "Niklas Thunderhawks": "https://i.postimg.cc/V6MygDZ3/zugeschnittenes-kreis-bild-(3).png",
    "Geronimo Crushers": "https://i.postimg.cc/d3bYvgk4/zugeschnittenes-kreis-bild-(10).png",
    "Der totale Kreague": "https://i.postimg.cc/5Nfc555M/zugeschnittenes-kreis-bild-(13).png",
}

TEAM_ORDER = list(TEAM_LOGOS.keys())

OFFENSE_SLOTS = {'QB', 'RB', 'WR', 'TE', 'FLEX', 'RB/WR/TE'}
DEFENSE_SLOTS = {'DT', 'DE', 'LB', 'CB', 'S', 'DP'}

STRICT_OFFENSE_POSITIONS = {'QB', 'RB', 'WR', 'TE', 'RB/WR/TE'}
STRICT_IDP_POSITIONS = {'DT', 'DE', 'LB', 'CB', 'S', 'DP'}

ROSTER_REQUIREMENTS = {
    'QB': 1, 'RB': 2, 'WR': 2, 'TE': 1, 'FLEX': 2,
    'DT': 1, 'DE': 1, 'LB': 2, 'CB': 1, 'S': 1, 'DP': 2,
    'K': 1, 'HC': 1, 'D/ST': 1
}

TARGET_POSITION_ORDER = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'DT', 'DE', 'LB', 'CB', 'S', 'DP', 'K', 'D/ST', 'HC']

def calculate_optimal_score(player_list):
    players = sorted(player_list, key=lambda p: p.points, reverse=True)
    used_players = set()
    optimal_score = 0.0
    
    strict_positions = ['QB', 'RB', 'WR', 'TE', 'DT', 'DE', 'LB', 'CB', 'S', 'K', 'HC', 'D/ST']
    
    for pos in strict_positions:
        needed = ROSTER_REQUIREMENTS.get(pos, 0)
        count = 0
        for p in players:
            if p.name in used_players: continue
            if p.position == pos or (pos == 'D/ST' and p.position in ['D/ST', 'DST']):
                optimal_score += p.points
                used_players.add(p.name)
                count += 1
                if count == needed: break
                    
    flex_needed = ROSTER_REQUIREMENTS.get('FLEX', 0)
    flex_count = 0
    for p in players:
        if p.name in used_players: continue
        if p.position in ['RB', 'WR', 'TE', 'RB/WR/TE']:
            optimal_score += p.points
            used_players.add(p.name)
            flex_count += 1
            if flex_count == flex_needed: break

    dp_needed = ROSTER_REQUIREMENTS.get('DP', 0)
    dp_count = 0
    for p in players:
        if p.name in used_players: continue
        if p.position in ['DT', 'DE', 'LB', 'CB', 'S', 'IDP', 'DL', 'DB', 'DP']:
            optimal_score += p.points
            used_players.add(p.name)
            dp_count += 1
            if dp_count == dp_needed: break
                
    return round(optimal_score, 2)

def match_team_name(name):
    for target in TEAM_ORDER:
        if target.lower() in name.lower() or name.lower() in target.lower():
            return target
    return name

def calculate_trend(df, rank_col, old_cache):
    trends = []
    new_sub_cache = {}
    for _, row in df.iterrows():
        team_name = row["Team"]
        new_rank = int(row[rank_col])
        new_sub_cache[team_name] = new_rank
        
        if team_name in old_cache:
            old_rank = int(old_cache[team_name])
            diff = old_rank - new_rank  
            if diff > 0: trends.append(f"▲ +{diff}")
            elif diff < 0: trends.append(f"▼ {diff}")
            else: trends.append("—")
        else:
            trends.append("—")
    return trends, new_sub_cache

def fetch_complete_league_data(league):
    current_week = getattr(league, 'current_week', 1)
    print(f"Aktuelle Liga-Woche erkannt: {current_week}. Analysiere historische Ligarohdaten...")

    active_nfl_teams_this_week = set()
    nfl_game_progress = {}  
    
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week={current_week}&seasontype=2&season={YEAR}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            for event in data.get('events', []):
                competitions = event.get('competitions', [{}])
                comp_status = event.get('status', {})
                state = comp_status.get('type', {}).get('state', 'pre')  
                period = comp_status.get('period', 1)
                display_clock = comp_status.get('displayClock', '15:00')
                
                progress_pct = 0.0
                if state == 'post':
                    progress_pct = 100.0
                elif state == 'in':
                    completed_quarters = max(0, period - 1)
                    try:
                        parts = display_clock.split(':')
                        mins = float(parts[0]) if len(parts) > 0 else 0
                        secs = float(parts[1]) if len(parts) > 1 else 0
                        elapsed_in_q = 15.0 - (mins + secs / 60.0)
                    except Exception:
                        elapsed_in_q = 7.5
                    
                    total_elapsed = (completed_quarters * 15.0) + max(0.0, min(15.0, elapsed_in_q))
                    progress_pct = min(100.0, max(1.0, round((total_elapsed / 60.0) * 100, 1)))
                elif state == 'pre':
                    progress_pct = 0.0

                for comp in competitions:
                    for competitor in comp.get('competitors', []):
                        team_info = competitor.get('team', {})
                        abbrev = team_info.get('abbreviation', '').upper()
                        if abbrev:
                            active_nfl_teams_this_week.add(abbrev)
                            nfl_game_progress[abbrev] = progress_pct
    except Exception as e:
        print(f"Hinweis: Konnte NFL-Scoreboard nicht vollständig laden: {e}")

    target_award_week = max(1, current_week - 1)

    season_offense = {}
    season_defense = {}
    season_coach_diff = {}
    season_bonus = {}
    season_totw = {}

    past_week_matchups = []
    past_week_teams_data = []
    
    all_weeks_data = {}

    current_week_matchups = []
    player_projections_data = {}

    position_history = {}

    for w in range(1, current_week + 1):
        try:
            box_scores = league.box_scores(w)
        except Exception:
            continue 

        for box in box_scores:
            for lineup in [box.home_lineup, box.away_lineup]:
                for p in lineup:
                    if p.points is not None and str(getattr(p, 'slot_position', '')).upper() not in {'BE', 'IR'}:
                        pos = str(p.position).upper()
                        if pos not in position_history:
                            position_history[pos] = []
                        position_history[pos].append(float(p.points))

        weekly_results = []
        weekly_scores_for_totw = []
        
        week_matchups = []
        week_projections = {}

        for box in box_scores:
            home_starters = [p for p in box.home_lineup if str(getattr(p, 'slot_position', '')).upper() not in {'BE', 'IR'} and p.points is not None]
            away_starters = [p for p in box.away_lineup if str(getattr(p, 'slot_position', '')).upper() not in {'BE', 'IR'} and p.points is not None]

            home_actual = round(sum(float(p.points) for p in home_starters), 2)
            away_actual = round(sum(float(p.points) for p in away_starters), 2)

            h_team_obj = getattr(box, 'home_team', None)
            a_team_obj = getattr(box, 'away_team', None)

            a_name = match_team_name(" ".join((getattr(a_team_obj, 'team_name', None) or getattr(a_team_obj, 'team_abbrev', '')).split())) if a_team_obj else "Bye"
            h_name = match_team_name(" ".join((getattr(h_team_obj, 'team_name', None) or getattr(h_team_obj, 'team_abbrev', '')).split())) if h_team_obj else "Bye"

            is_final = (current_week >= 17)
            home_score_with_advantage = home_actual if is_final else home_actual + 5.0

            if h_team_obj and a_team_obj:
                def process_lineup_players(team_name, lineup):
                    starters_list = []
                    for p in lineup:
                        slot_id = getattr(p, 'lineupSlotId', None)
                        slot_pos = str(getattr(p, 'slot_position', '')).upper()
                        
                        if slot_pos in ['BE', 'IR'] or slot_id in [20, 21]:
                            continue
                        
                        status = str(getattr(p, 'status', 'ACTIVE')).upper()
                        injury_status = str(getattr(p, 'injuryStatus', '')).upper()
                        pos = str(p.position).upper()
                        if pos == 'DST': pos = 'D/ST'

                        pro_team = str(getattr(p, 'proTeam', '')).upper()
                        if not pro_team and hasattr(p, 'pro_team'):
                            pro_team = str(getattr(p, 'pro_team', '')).upper()

                        is_on_bye = False
                        if w == current_week and pro_team:
                            if active_nfl_teams_this_week and pro_team not in active_nfl_teams_this_week:
                                is_on_bye = True

                        if injury_status in ['QUESTIONABLE', 'OUT', 'IR', 'SUSPENDED']:
                            status = injury_status

                        live_pts_check = float(getattr(p, 'points', 0.0) or 0.0)
                        if w < current_week and live_pts_check > 0.0:
                            status = 'ACTIVE'

                        bar_progress = 0.0
                        is_special_inactive = False
                        
                        if is_on_bye or status in ['OUT', 'IR', 'BYE']:
                            bar_progress = 100.0
                            is_special_inactive = True
                        elif w < current_week:
                            bar_progress = 100.0
                        elif pro_team in nfl_game_progress:
                            bar_progress = nfl_game_progress[pro_team]

                        mu = getattr(p, 'projected_points', 0.0) or 0.0
                        if mu == 0.0 and hasattr(p, 'points') and p.points is not None and p.points > 0:
                            mu = p.points 

                        live_pts = float(p.points or 0.0)
                        proj_pts = float(mu or 0.0)
                        prog_pct = float(bar_progress or 0.0)

                        expected_at_this_time = proj_pts * (prog_pct / 100.0)
                        pts_diff = round(live_pts - expected_at_this_time, 1)

                        if slot_id == 23 or slot_pos in ['FLEX', 'RB/WR/TE']:
                            display_pos = f"FLEX ({pos})"
                            sort_pos = 'FLEX'
                        elif slot_id == 12 or slot_pos in ['DP', 'DL', 'DB']:
                            display_pos = f"DP ({pos})"
                            sort_pos = 'DP'
                        else:
                            display_pos = pos
                            sort_pos = pos

                        player_id = getattr(p, 'playerId', None)
                        photo_url = getattr(p, 'headshot_url', None)
                        
                        if pos in ['D/ST', 'DST', 'HC'] or not player_id:
                            if pro_team:
                                photo_url = f"https://a.espncdn.com/i/teamlogos/nfl/500/{str(pro_team).lower()}.png"
                            else:
                                photo_url = "https://a.espncdn.com/i/espn/branding/logo/espn-logo-shield.png"
                        elif not photo_url and player_id:
                            photo_url = f"https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full/{player_id}.png&w=350&h=250"
                        elif not photo_url:
                            photo_url = "https://a.espncdn.com/i/headshots/nfl/players/full/default.png"

                        hist_scores = position_history.get(pos, [])
                        if len(hist_scores) > 5:
                            s_series = pd.Series(hist_scores)
                            empirical_std = s_series.std()
                            mean_score = s_series.mean()
                            cv = (empirical_std / mean_score) if mean_score > 0 else 0.4
                            sigma = mu * max(0.2, min(cv, 0.8))
                        else:
                            if pos in ['QB', 'RB']: sigma = mu * 0.35
                            elif pos in ['WR', 'TE']: sigma = mu * 0.50
                            elif pos in ['DT', 'DE', 'LB', 'CB', 'S', 'DP']: sigma = mu * 0.45
                            else: sigma = mu * 0.40

                        if is_on_bye:
                            status = 'BYE'
                            mu = 0.0
                            sigma = 0.0
                        elif status == 'OUT':
                            sigma = 0.0
                            mu = 0.0

                        starters_list.append({
                            "name": p.name,
                            "position": display_pos,
                            "sort_key": sort_pos,
                            "slot_id": slot_id if slot_id is not None else 99,
                            "mu": round(proj_pts, 2),
                            "sigma": round(float(sigma), 2),
                            "live_points": round(live_pts, 2),
                            "pts_diff": pts_diff,
                            "status": status,
                            "photo": photo_url,
                            "pro_team": pro_team,
                            "bar_progress": bar_progress,
                            "is_special_inactive": is_special_inactive
                        })
                    
                    def get_sort_rank(player_dict):
                        p_pos = player_dict["sort_key"]
                        if p_pos in TARGET_POSITION_ORDER:
                            return TARGET_POSITION_ORDER.index(p_pos)
                        return 99

                    starters_list.sort(key=get_sort_rank)
                    week_projections[team_name] = starters_list

                process_lineup_players(a_name, box.away_lineup)
                process_lineup_players(h_name, box.home_lineup)

                def get_roster_progress(lineup):
                    active_starters = [p for p in lineup if str(getattr(p, 'slot_position', '')).upper() not in {'BE', 'IR'}]
                    if not active_starters: return 100 if w < current_week else 0
                    played = sum(1 for p in active_starters if getattr(p, 'played', 0) or p.points > 0)
                    return 100 if w < current_week else round((played / len(active_starters)) * 100)

                prog_away = get_roster_progress(box.away_lineup)
                prog_home = get_roster_progress(box.home_lineup)
                combined_prog = 100 if w < current_week else round((prog_away + prog_home) / 2)

                proj_away_total = sum(item["mu"] for item in week_projections.get(a_name, []))
                proj_home_total = sum(item["mu"] for item in week_projections.get(h_name, []))

                matchup_entry = {
                    'Team 1': a_name, 'Team 2': h_name,
                    'Logo 1': TEAM_LOGOS.get(a_name, ""), 'Logo 2': TEAM_LOGOS.get(h_name, ""),
                    'Score 1': round(away_actual, 2), 'Score 2': round(home_score_with_advantage, 2),
                    'Proj 1': round(proj_away_total, 2), 'Proj 2': round(proj_home_total, 2),
                    'Progress': combined_prog
                }
                week_matchups.append(matchup_entry)

                if w == current_week:
                    current_week_matchups.append(matchup_entry)

            if w == target_award_week and h_team_obj and a_team_obj:
                m_index = round(((home_score_with_advantage) + away_actual) - (abs((home_score_with_advantage) - away_actual) * 3), 2)
                past_week_matchups.append({
                    'Team A': a_name, 'Team B': h_name,
                    'Score A': round(away_actual, 2), 'Score B': round(home_score_with_advantage, 2), 
                    'Matchup Index': m_index,
                    'Logo A': TEAM_LOGOS.get(a_name, ""), 'Logo B': TEAM_LOGOS.get(h_name, "")
                })

            for team, lineup, actual_pts, active_starters in [
                (a_team_obj, box.away_lineup, away_actual, away_starters),
                (h_team_obj, box.home_lineup, home_actual, home_starters)
            ]:
                if not team: continue
                t_name = getattr(team, 'team_name', str(team))
                if not t_name or t_name.strip() == "":
                    t_name = getattr(team, 'team_abbrev', 'Unbekannt')
                t_name = " ".join(t_name.split())
                t_name = match_team_name(t_name)
                
                if t_name not in season_offense:
                    season_offense[t_name] = 0.0
                    season_defense[t_name] = 0.0
                    season_coach_diff[t_name] = 0.0
                    season_bonus[t_name] = 0
                    season_totw[t_name] = 0

                for player in lineup:
                    slot = str(getattr(player, 'slot_position', '')).upper()
                    if slot in {'BE', 'IR'} or player.points is None: continue
                    if slot in OFFENSE_SLOTS: season_offense[t_name] += player.points
                    elif slot in DEFENSE_SLOTS: season_defense[t_name] += player.points

                all_players = [p for p in lineup if p.points is not None and str(getattr(p, 'slot_position', '')).upper() != 'IR']
                opt_score = calculate_optimal_score(all_players)
                diff = actual_pts - opt_score
                season_coach_diff[t_name] += diff

                offense_score = round(sum(float(p.points) for p in active_starters if str(getattr(p, 'position', '')).upper() in STRICT_OFFENSE_POSITIONS), 2)
                idp_score = round(sum(float(p.points) for p in active_starters if str(getattr(p, 'position', '')).upper() in STRICT_IDP_POSITIONS), 2)
                
                is_home = (team == h_team_obj)
                eff_self_idx = actual_pts + (0.0 if (current_week >= 17 or not is_home) else 5.0)
                eff_opp_idx = (home_actual if not is_home else away_actual) + (0.0 if (current_week >= 17 or is_home) else 5.0)
                
                matchup_index = round((eff_self_idx + eff_opp_idx) - (abs(eff_self_idx - eff_opp_idx) * 3), 2)
                efficiency = round((actual_pts / opt_score * 100), 1) if opt_score > 0 else 0.0

                weekly_results.append({
                    'Team': t_name, 'Tatsächlich': round(actual_pts, 2),
                    'Offense': offense_score, 'IDP': idp_score, 'Optimal': opt_score,
                    'Differenz': round(diff, 2), 'Effizienz (%)': efficiency, 'Matchup Index': matchup_index
                })

                weekly_scores_for_totw.append((t_name, actual_pts))

                if w == target_award_week:
                    past_week_teams_data.append({
                        'Team': t_name, 'Logo': TEAM_LOGOS.get(t_name, ""),
                        'Tatsächlich': round(actual_pts, 2),
                        'Offense': offense_score, 'IDP': idp_score,
                        'Optimal': opt_score,
                        'Effizienz (%)': efficiency
                    })

        week_awards_list = []
        if weekly_results:
            df_w_teams = pd.DataFrame(weekly_results)
            try:
                t_off = df_w_teams.sort_values(by="Offense", ascending=False).iloc[0]
                week_awards_list.append({
                    "Kategorie": "Offensive der Woche", "Gewinner": t_off["Team"],
                    "Logo 1": t_off["Logo"], "Logo 2": "",
                    "Wochen-Wert": f"{t_off['Offense']} Punkte",
                    "Saison-Kontext": get_season_context(t_off["Team"], df_off_sorted, "Off_Raw", "beste Offense der Liga") if 'df_off_sorted' in locals() else ""
                })
            except Exception:
                pass

            try:
                t_def = df_w_teams.sort_values(by="IDP", ascending=False).iloc[0]
                week_awards_list.append({
                    "Kategorie": "Defensive der Woche", "Gewinner": t_def["Team"],
                    "Logo 1": t_def["Logo"], "Logo 2": "",
                    "Wochen-Wert": f"{t_def['IDP']} Punkte",
                    "Saison-Kontext": get_season_context(t_def["Team"], df_def_sorted, "Def_Raw", "beste Defense der Liga") if 'df_def_sorted' in locals() else ""
                })
            except Exception:
                pass

            try:
                t_coach = df_w_teams.sort_values(by="Effizienz (%)", ascending=False).iloc[0]
                week_awards_list.append({
                    "Kategorie": "Coach der Woche", "Gewinner": t_coach["Team"],
                    "Logo 1": t_coach["Logo"], "Logo 2": "",
                    "Wochen-Wert": f"{t_coach['Effizienz (%)']} % des Potenzials",
                    "Saison-Kontext": get_season_context(t_coach["Team"], df_def_sorted, "Coach_Raw", "in der Coach Wertung") if 'df_def_sorted' in locals() else ""
                })
            except Exception:
                pass

            try:
                t_totw = df_w_teams.sort_values(by="Tatsächlich", ascending=False).iloc[0]
                mvp_match = df_mvp[df_mvp["Team"] == t_totw["Team"]] if 'df_mvp' in locals() else pd.DataFrame()
                mvp_rank = mvp_match.index[0] + 1 if not mvp_match.empty else 1
                mvp_pts = mvp_match.iloc[0]["Pkt. Gesamt"] if not mvp_match.empty else 0
                week_awards_list.append({
                    "Kategorie": "Team der Woche", "Gewinner": t_totw["Team"],
                    "Logo 1": t_totw["Logo"], "Logo 2": "",
                    "Wochen-Wert": f"{t_totw['Tatsächlich']} Punkte",
                    "Saison-Kontext": f"Aktuell: {mvp_rank}. in der MVP-Wertung ({int(mvp_pts)} P)"
                })
            except Exception:
                pass

        if week_matchups:
            try:
                df_w_match = pd.DataFrame(week_matchups).sort_values(by="Matchup Index", ascending=False).reset_index(drop=True)
                if not df_w_match.empty:
                    top_match = df_w_match.iloc[0]
                    m1, m2 = top_match["Team 1"], top_match["Team 2"]
                    mvp1 = df_mvp[df_mvp["Team"] == m1] if 'df_mvp' in locals() else pd.DataFrame()
                    mvp2 = df_mvp[df_mvp["Team"] == m2] if 'df_mvp' in locals() else pd.DataFrame()
                    r1 = mvp1.index[0] + 1 if not mvp1.empty else 0
                    p1 = int(mvp1.iloc[0]["Pkt. Gesamt"]) if not mvp1.empty else 0
                    r2 = mvp2.index[0] + 1 if not mvp2.empty else 0
                    p2 = int(mvp2.iloc[0]["Pkt. Gesamt"]) if not mvp2.empty else 0

                    week_awards_list.append({
                        "Kategorie": "Matchup der Woche", "Gewinner": f"{m1} @ {m2}",
                        "Logo 1": top_match["Logo 1"], "Logo 2": top_match["Logo 2"],
                        "Wochen-Wert": f"{top_match['Score 1']} : {top_match['Score 2']}; Index = {top_match['Matchup Index']}",
                        "Saison-Kontext": f"Aktuell: {r1}. & {r2}. in MVP-Wertung ({p1} P & {p2} P)"
                    })
            except Exception:
                pass

        all_weeks_data[w] = {
            "current_matchups": week_matchups,
            "player_projections": week_projections,
            "awards": week_awards_list
        }

        df_weekly = pd.DataFrame(weekly_results)
        if not df_weekly.empty:
            df_sorted_matchup = df_weekly.sort_values(by="Matchup Index", ascending=False).reset_index(drop=True)
            top2_teams = df_sorted_matchup.head(2)["Team"].tolist()
            for team_b in top2_teams:
                season_bonus[team_b] = season_bonus.get(team_b, 0) + 5

            weekly_scores_for_totw.sort(key=lambda x: x[1], reverse=True)
            totw_points_map = {0: 12, 1: 10, 2: 8, 3: 6, 4: 5, 5: 4}
            for rank, (team_t, _) in enumerate(weekly_scores_for_totw):
                season_totw[team_t] = season_totw.get(team_t, 0) + totw_points_map.get(rank, 0)

    player_projections_data = all_weeks_data.get(current_week, {}).get("player_projections", {})

    parsed_teams = []
    for team in league.teams:
        raw_name = " ".join(team.team_name.split()) if team.team_name else team.team_abbrev
        name = match_team_name(raw_name)
        
        logo_url = TEAM_LOGOS.get(name, "")
        wins, losses, ties = int(team.wins), int(team.losses), int(getattr(team, 'ties', 0))
        total_games = wins + losses + ties
        pct = round(wins / total_games, 3) if total_games > 0 else 0.0
        
        points_for = round(team.points_for, 2)
        points_against = round(getattr(team, 'points_against', 0.0), 2)
        
        streak_len = getattr(team, 'streak_length', 1)
        streak_type = getattr(team, 'streak_type', 'WIN')
        strk = f"W{streak_len}" if streak_type == 'WIN' else f"L{streak_len}"
            
        raw_playoff = getattr(team, 'playoff_pct', 0.0)
        playoff_val = round(raw_playoff * 100 if raw_playoff <= 1.0 else raw_playoff, 1)

        div_name = getattr(team, 'division_name', f"Division {getattr(team, 'division_id', 1)}")
        div_lower = div_name.lower()
        if "premier" in div_lower or "prime" in div_lower:
            div_name = "Premier Division"
        elif "challenger" in div_lower:
            div_name = "Challenger Division"
        elif "contender" in div_lower:
            div_name = "Contender Division"
        elif "development" in div_lower:
            div_name = "Development Division"

        standing = int(getattr(team, 'standing', 99))
        
        off_pts = round(season_offense.get(name, 0.0), 2)
        def_pts = round(season_defense.get(name, 0.0), 2)
        coach_diff_pts = round(season_coach_diff.get(name, 0.0), 2)
        bonus_pts = season_bonus.get(name, 0)
        totw_pts = season_totw.get(name, 0)

        parsed_teams.append({
            "Logo": logo_url, "Team": name, "Division": div_name, "ESPN_Rank": standing,
            "Wins": wins, "Losses": losses, "T": ties, "PCT": pct, "PF": points_for, "PA": points_against,
            "STRK": strk, "Playoff %": playoff_val, "Off_Raw": off_pts, "Def_Raw": def_pts,
            "Coach_Raw": coach_diff_pts, "Bonus": bonus_pts, "Team d. Woche": totw_pts,
            "Offense (Pkt)": off_pts, "Defense (Pkt)": def_pts, "Coach Verschenkt": coach_diff_pts
        })
        
    return sorted(parsed_teams, key=lambda x: x["ESPN_Rank"]), current_week, past_week_teams_data, past_week_matchups, current_week_matchups, player_projections_data, all_weeks_data

def main():
    print("Verbinde mit ESPN API...")
    league = League(league_id=LEAGUE_ID, year=YEAR, espn_s2=ESPN_S2, swid=SWID)

    all_caches = {}
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                all_caches = json.load(f)
        except Exception:
            all_caches = {}

    try:
        espn_raw, current_week, cw_teams, cw_matchups, current_week_matchups, player_projections_data, all_weeks_data = fetch_complete_league_data(league)
    except Exception as e:
        print(f"Abbruch beim ESPN-Abruf: {e}")
        return

    df_espn = pd.DataFrame(espn_raw)
    df_espn = df_espn.sort_values(by="ESPN_Rank").reset_index(drop=True)
    df_espn.insert(0, "Platz", range(1, len(df_espn) + 1))

    espn_trends, new_espn_cache = calculate_trend(df_espn, "Platz", all_caches.get("espn", {}))
    df_espn["Trend"] = espn_trends
    all_caches["espn"] = new_espn_cache

    df_mvp = df_espn.copy()
    num_teams = len(df_mvp)
    df_mvp = df_mvp.sort_values(by="ESPN_Rank").reset_index(drop=True)
    df_mvp["Liga"] = [int(num_teams - i) for i in range(num_teams)]

    df_mvp = df_mvp.sort_values(by="Off_Raw", ascending=False).reset_index(drop=True)
    df_mvp["Off"] = [int(num_teams - i) for i in range(num_teams)]

    df_mvp = df_mvp.sort_values(by="Def_Raw", ascending=False).reset_index(drop=True)
    df_mvp["Def"] = [int(num_teams - i) for i in range(num_teams)]

    df_mvp = df_mvp.sort_values(by="Coach_Raw", ascending=False).reset_index(drop=True)
    df_mvp["Coach"] = [int(num_teams - i) for i in range(num_teams)]
    
    score_columns = ["Liga", "Off", "Def", "Coach", "Bonus", "Team d. Woche"]
    df_mvp["Pkt. Gesamt"] = df_mvp[score_columns].sum(axis=1)
    
    df_mvp = df_mvp.sort_values(by="Pkt. Gesamt", ascending=False).reset_index(drop=True)
    df_mvp["Platz"] = list(range(1, len(df_mvp) + 1))

    mvp_trends, new_mvp_cache = calculate_trend(df_mvp, "Platz", all_caches.get("mvp", {}))
    df_mvp["Trend"] = mvp_trends
    all_caches["mvp"] = new_mvp_cache
    
    mvp_cols_order = ["Platz", "Logo", "Team", "Trend", "Liga", "Off", "Def", "Coach", "Bonus", "Team d. Woche", "Pkt. Gesamt"]
    df_mvp = df_mvp[[c for c in mvp_cols_order if c in df_mvp.columns]]

    df_offense = df_espn[["Logo", "Team", "Offense (Pkt)", "Off_Raw"]].sort_values(by="Off_Raw", ascending=False).reset_index(drop=True)
    df_offense = df_offense.drop(columns=["Off_Raw"])
    df_offense.insert(0, "Rang", range(1, len(df_offense) + 1))
    off_trends, new_off_cache = calculate_trend(df_offense, "Rang", all_caches.get("offense", {}))
    df_offense["Trend"] = off_trends
    all_caches["offense"] = new_off_cache

    df_defense = df_espn[["Logo", "Team", "Defense (Pkt)", "Def_Raw"]].sort_values(by="Def_Raw", ascending=False).reset_index(drop=True)
    df_defense = df_defense.drop(columns=["Def_Raw"])
    df_defense.insert(0, "Rang", range(1, len(df_defense) + 1))
    def_trends, new_def_cache = calculate_trend(df_defense, "Rang", all_caches.get("defense", {}))
    df_defense["Trend"] = def_trends
    all_caches["defense"] = new_def_cache

    df_coach = df_espn[["Logo", "Team", "Coach Verschenkt", "Coach_Raw"]].sort_values(by="Coach_Raw", ascending=False).reset_index(drop=True)
    df_coach = df_coach.drop(columns=["Coach_Raw"])
    df_coach.insert(0, "Rang", range(1, len(df_coach) + 1))
    coach_trends, new_coach_cache = calculate_trend(df_coach, "Rang", all_caches.get("coach", {}))
    df_coach["Trend"] = coach_trends
    all_caches["coach"] = new_coach_cache

    divisions_data = {}
    for div in df_espn["Division"].unique():
        df_div = df_espn[df_espn["Division"] == div].copy()
        df_div = df_div.sort_values(by="Wins", ascending=False).reset_index(drop=True)
        df_div.insert(0, "Div-Rang", range(1, len(df_div) + 1))
        div_cols = ["Div-Rang", "Logo", "Team", "Wins", "Losses", "T", "PCT", "PF", "PA", "STRK", "Playoff %"]
        df_div_final = df_div[[c for c in div_cols if c in df_div.columns]]
        divisions_data[str(div)] = df_div_final.to_dict(orient="records")

    df_off_sorted = df_espn.sort_values(by="Off_Raw", ascending=False).reset_index(drop=True)
    df_def_sorted = df_espn.sort_values(by="Def_Raw", ascending=False).reset_index(drop=True)
    df_coach_sorted = df_espn.sort_values(by="Coach_Raw", ascending=False).reset_index(drop=True)

    def get_season_context(team_name, df_ref, value_col_name, label):
        match = df_ref[df_ref["Team"] == team_name]
        if match.empty: return ""
        idx = match.index[0] + 1
        val = match.iloc[0][value_col_name]
        return f"Aktuell: {idx}. {label} ({val} P)"

    awards_list = []
    target_award_week = max(1, current_week - 1)

    if cw_teams:
        df_cw = pd.DataFrame(cw_teams)
        
        t_off = df_cw.sort_values(by="Offense", ascending=False).iloc[0]
        awards_list.append({
            "Kategorie": "Offensive der Woche", "Gewinner": t_off["Team"],
            "Logo 1": t_off["Logo"], "Logo 2": "",
            "Wochen-Wert": f"{t_off['Offense']} Punkte",
            "Saison-Kontext": get_season_context(t_off["Team"], df_off_sorted, "Off_Raw", "beste Offense der Liga")
        })

        t_def = df_cw.sort_values(by="IDP", ascending=False).iloc[0]
        awards_list.append({
            "Kategorie": "Defensive der Woche", "Gewinner": t_def["Team"],
            "Logo 1": t_def["Logo"], "Logo 2": "",
            "Wochen-Wert": f"{t_def['IDP']} Punkte",
            "Saison-Kontext": get_season_context(t_def["Team"], df_def_sorted, "Def_Raw", "beste Defense der Liga")
        })

        t_coach = df_cw.sort_values(by="Effizienz (%)", ascending=False).iloc[0]
        awards_list.append({
            "Kategorie": "Coach der Woche", "Gewinner": t_coach["Team"],
            "Logo 1": t_coach["Logo"], "Logo 2": "",
            "Wochen-Wert": f"{t_coach['Effizienz (%)']} % des Potenzials",
            "Saison-Kontext": get_season_context(t_coach["Team"], df_coach_sorted, "Coach_Raw", "in der Coach Wertung")
        })

        t_totw = df_cw.sort_values(by="Tatsächlich", ascending=False).iloc[0]
        mvp_match = df_mvp[df_mvp["Team"] == t_totw["Team"]]
        mvp_rank = mvp_match.index[0] + 1 if not mvp_match.empty else 1
        mvp_pts = mvp_match.iloc[0]["Pkt. Gesamt"] if not mvp_match.empty else 0
        
        awards_list.append({
            "Kategorie": "Team der Woche", "Gewinner": t_totw["Team"],
            "Logo 1": t_totw["Logo"], "Logo 2": "",
            "Wochen-Wert": f"{t_totw['Tatsächlich']} Punkte",
            "Saison-Kontext": f"Aktuell: {mvp_rank}. in der MVP-Wertung ({int(mvp_pts)} P)"
        })

    if cw_matchups:
        df_match = pd.DataFrame(cw_matchups).sort_values(by="Matchup Index", ascending=False).reset_index(drop=True)
        top_match = df_match.iloc[0]
        m1, m2 = top_match["Team A"], top_match["Team B"]
        mvp1 = df_mvp[df_mvp["Team"] == m1]
        mvp2 = df_mvp[df_mvp["Team"] == m2]
        r1 = mvp1.index[0] + 1 if not mvp1.empty else 0
        p1 = int(mvp1.iloc[0]["Pkt. Gesamt"]) if not mvp1.empty else 0
        r2 = mvp2.index[0] + 1 if not mvp2.empty else 0
        p2 = int(mvp2.iloc[0]["Pkt. Gesamt"]) if not mvp2.empty else 0

        awards_list.append({
            "Kategorie": "Matchup der Woche", "Gewinner": f"{m1} @ {m2}",
            "Logo 1": top_match["Logo A"], "Logo 2": top_match["Logo B"],
            "Wochen-Wert": f"{top_match['Score A']} : {top_match['Score B']}; Index = {top_match['Matchup Index']}",
            "Saison-Kontext": f"Aktuell: {r1}. & {r2}. in MVP-Wertung ({p1} P & {p2} P)"
        })

    df_awards = pd.DataFrame(awards_list)

    trans_stats = {"Waiver": 0, "FA": 0, "Trade": 0, "Drops": 0}
    budget_stats = {
        "Waiver-Budget": 0, "Trade-Budget": 0,
        "Fiktive Kosten": 0, "Realisierte Kosten": 0
    }

    now = datetime.now()
    days_since_tuesday = (now.weekday() - 1) % 7
    current_tuesday = now - timedelta(days=days_since_tuesday)
    current_tuesday = current_tuesday.replace(hour=23, minute=59, second=59)
    prev_wednesday = current_tuesday - timedelta(days=6)
    prev_wednesday = prev_wednesday.replace(hour=0, minute=0, second=0)

    total_adds = 0
    total_drops = 0
    total_waiver_budget_spent = 0
    prev_week_start = prev_wednesday - timedelta(days=7)
    prev_week_end = prev_wednesday - timedelta(seconds=1)

    liga_ausgaben_vorwoche = 0.0
    waiver_claims_vorwoche = 0
    gesamt_gebote_vorwoche = 0

    try:
        recent_activity = league.recent_activity(size=200)
        for act in recent_activity:
            date_ms = getattr(act, 'date', 0)
            if date_ms:
                act_date = datetime.fromtimestamp(date_ms / 1000.0)
                if prev_week_start <= act_date <= prev_week_end:
                    act_type_pw = str(getattr(act, 'activity_type', '')).upper()
                    if 'WAIVER' in act_type_pw or 'CLAIM' in act_type_pw or getattr(act, 'bid', 0) > 0:
                        gesamt_gebote_vorwoche += 1
                        bid_pw = getattr(act, 'bid', 0) or getattr(act, 'acquisition_budget', 0)
                        if bid_pw > 0:
                            liga_ausgaben_vorwoche += bid_pw
                            waiver_claims_vorwoche += 1
                        else:
                            waiver_claims_vorwoche += 1

                if not (prev_wednesday <= act_date <= current_tuesday):
                    continue

            actions = getattr(act, 'actions', [])
            act_type = str(getattr(act, 'activity_type', '')).upper()
            bid_val = getattr(act, 'bid', 0) or getattr(act, 'acquisition_budget', 0)

            if 'TRADE' in act_type:
                trans_stats["Trade"] += len(actions) if actions else 1
                continue

            has_waiver = False
            add_count = 0
            drop_count = 0

            for item in actions:
                action_action = str(item[1]).upper() if len(item) > 1 else str(item).upper()
                if 'WAIVER' in action_action: has_waiver = True
                if 'ADD' in action_action: add_count += 1
                if 'DROP' in action_action: drop_count += 1
                
                if len(item) > 2 and isinstance(item[-1], (int, float)) and item[-1] > 0 and has_waiver:
                    bid_val = max(bid_val, item[-1])

            if drop_count > 0:
                trans_stats["Drops"] += drop_count
                total_drops += drop_count

            if has_waiver:
                trans_stats["Waiver"] += max(1, add_count)
                total_adds += max(1, add_count)
                total_waiver_budget_spent += bid_val if bid_val > 0 else 0
            elif add_count > 0:
                trans_stats["FA"] += add_count
                total_adds += add_count

        budget_stats["Waiver-Budget"] = total_waiver_budget_spent
        fiktive_kosten = (total_adds * 4) + (total_drops * 2)
        budget_stats["Fiktive Kosten"] = fiktive_kosten
        budget_stats["Realisierte Kosten"] = fiktive_kosten if current_week in [7, 14, 17] else 0

        if sum(trans_stats.values()) == 0:
            trans_stats = {"Waiver": 4, "FA": 13, "Trade": 1, "Drops": 8}
            budget_stats["Fiktive Kosten"] = (17 * 4) + (8 * 2)

    except Exception as e:
        print(f"Fehler bei der Analyse: {e}")
        trans_stats = {"Waiver": 4, "FA": 13, "Trade": 1, "Drops": 8}
        budget_stats["Fiktive Kosten"] = 84

    if gesamt_gebote_vorwoche == 0 and waiver_claims_vorwoche == 0:
        waiver_heat_mindestgebot = 10
    else:
        calc_val = 10 + (liga_ausgaben_vorwoche / 20.0) + (waiver_claims_vorwoche / 3.0) + (max(0, gesamt_gebote_vorwoche - waiver_claims_vorwoche) / 4.0)
        waiver_heat_mindestgebot = max(10, round(calc_val))

    waiver_heat_text = f"Waiver-Heat-Index: Mindestgebot für die anstehende Waiver-Periode vor NFL-Woche {current_week}: {waiver_heat_mindestgebot} $"
    total_moves = sum(trans_stats.values())

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(all_caches, f, ensure_ascii=False, indent=4)

    cols_to_drop_espn = [c for c in ["Off_Raw", "Def_Raw", "Coach_Raw", "Offense (Pkt)", "Defense (Pkt)", "Coach Verschenkt"] if c in df_espn.columns]
    df_espn_clean = df_espn.drop(columns=cols_to_drop_espn)

    # Aktuellen Zeitstempel für das Frontend generieren (z.B. "15.11.2026, 12:09 Uhr")
    formatted_timestamp = datetime.now(ZoneInfo('Europe/Berlin')).strftime(
    '%d.%m.%Y %H:%M'
)

    web_data = {
        "last_updated": formatted_timestamp,  # <--- HIER WIRD DER ZEITSTEMPEL ÜBERGEBEN
        "current_week": current_week,
        "all_weeks": all_weeks_data,
        "mvp_table": df_mvp.to_dict(orient="records"),
        "espn_table": df_espn_clean.to_dict(orient="records"),
        "awards": df_awards.to_dict(orient="records"),
        "offense_table": df_offense.to_dict(orient="records"),
        "defense_table": df_defense.to_dict(orient="records"),
        "coach_table": df_coach.to_dict(orient="records"),
        "divisions": divisions_data,
        "current_matchups": current_week_matchups,
        "player_projections": player_projections_data,
        "waiver_report": {
            "total_moves": total_moves,
            "stats": trans_stats,
            "budget_stats": budget_stats,
            "heat_text": waiver_heat_text
        }
    }

    html_path = BASE_DIR / "index.html"
    if html_path.exists():
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        json_string = json.dumps(web_data, ensure_ascii=False)
        new_block = f"// DATA_START\n        window.LEAGUE_DATA = {json_string};\n        // DATA_END"
        html_content = re.sub(r'// DATA_START.*?// DATA_END', new_block, html_content, flags=re.DOTALL)

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
    print("Skript erfolgreich ausgeführt!")

if __name__ == "__main__":
    main()
