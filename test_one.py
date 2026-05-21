from data_loader import load_team_season_stats
df = load_team_season_stats("ITA-Serie A", "2425", stat_type="standard")
print("rows:", len(df), "| cols:", len(df.columns))
