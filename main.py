#!/usr/bin/env python3

import argparse
from numpy import NaN
import pandas as pd
from espn_api.football import League, player
import jinja2
from pandas.core.frame import DataFrame
from datetime import datetime
import logging
from tqdm import tqdm
import pickle
import json
import concurrent.futures


def print_team_scoring(league: League):
    """Prints the top scoring team in descending order"""

    # Save team data to pandas data frame
    data = []
    for team in league.teams:
        data.append([team.team_name, team.points_for, team.points_against])
    df = pd.DataFrame(data, columns=["Team", "Points for", "Points against"])

    points_for = df.sort_values(by=["Points for"], ascending=False)[["Team", "Points for"]].to_html(index=False, classes="my_style")
    points_against = df.sort_values(by=["Points against"], ascending=False)[["Team", "Points against"]].to_html(index=False, classes="my_style")
    return points_for, points_against


def get_games(league: League):
    games = []
    for week in range(1, min(league.settings.reg_season_count + 1, league.current_week)):
        games_in_week = league.box_scores(week=week)
        for game in games_in_week:
            game_stats = []
            if game.home_score < game.away_score:
                game_stats.append(game.away_team.team_name)
                game_stats.append(game.away_score)
                game_stats.append(game.away_projected)
                game_stats.append(game.home_team.team_name)
                game_stats.append(game.home_score)
                game_stats.append(game.home_projected)
                game_stats.append(game.away_lineup)
                game_stats.append(game.home_lineup)
            else:
                game_stats.append(game.home_team.team_name)
                game_stats.append(game.home_score)
                game_stats.append(game.home_projected)
                game_stats.append(game.away_team.team_name)
                game_stats.append(game.away_score)
                game_stats.append(game.away_projected)
                game_stats.append(game.home_lineup)
                game_stats.append(game.away_lineup)

            if game.home_score == 0 and game.away_score == 0:
                game_stats.append(NaN)
            else:
                game_stats.append(abs(game.home_score - game.away_score))

            games.extend([game_stats])

    # print(games)
    df = pd.DataFrame(games, columns=["Winner team",
                                      "Winner score",
                                      "Winner proj",
                                      "Loser team",
                                      "Loser score",
                                      "Loser proj",
                                      "Winner lineup",
                                      "Loser lineup",
                                      "Score diff"])
    return df

def get_close_games(games: DataFrame):
    close_games = games.sort_values(by=["Score diff"], ascending=True)[["Winner team", "Winner score", "Loser team", "Loser score", "Score diff"]].head(10).to_html(index=False, classes="my_style")
    return close_games


def get_high_score_and_lost(games: DataFrame):
    high_score_lost = games.sort_values(by=["Loser score"], ascending=False)[["Winner team", "Winner score", "Loser team", "Loser score"]].head(10).to_html(index=False, classes="my_style")
    return high_score_lost


def get_low_score_and_won(games: DataFrame):
    low_score_won = games.sort_values(by=["Winner score"], ascending=True)[["Winner team", "Winner score", "Loser team", "Loser score"]].head(10).to_html(index=False, classes="my_style")
    return low_score_won


def get_games_played(player_stats, num_of_weeks: int) -> int:
    games_played = 0
    for k, v in player_stats.stats.items():
        # Week 0 corresponds to 'Total'
        if k == 0 or k > num_of_weeks:
            continue

        if v.get('points') > 0:
            games_played += 1
    return games_played


def get_draft_class(league: DataFrame):
    players = []
    for idx, pick in enumerate(league.draft):
        player = []
        player_stats = league.player_info(playerId = pick.playerId)

        player.append(pick.playerName)
        player.append(pick.playerId)
        player.append(pick.team.team_name)
        player.append(pick.round_num)
        games_played = get_games_played(player_stats, league.current_week)
        player.append(games_played)
        player.append(league.settings.reg_season_count - games_played)

        players.extend([player])

    # print(games)
    df = pd.DataFrame(players, columns=["Player Name",
                                        "playerId",
                                        "Team Name",
                                        "Round",
                                        "Games Played",
                                        "Games Missed"])
    return df


def print_missed_games_per_team(players: DataFrame):
    return players[players["Round"] < 6].groupby(["Team Name"], as_index=False).sum()[["Team Name", "Games Played", "Games Missed"]].sort_values(by=["Games Missed"], ascending=False).to_html(index=False, classes="my_style")


def setup_logger():
    formatter = logging.basicConfig(level=logging.INFO, style='{', datefmt='%Y-%m-%d %H:%M:%S', format='{asctime} {levelname} {filename}:{lineno}: {message}')
    handler = logging.FileHandler('log.txt', mode='w')
    handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


def get_player_score(player_stats, num_of_weeks: int) -> int:
    score = 0
    for k, v in player_stats.items():
        # Week 0 corresponds to 'Total'
        if k == 0 or k > num_of_weeks:
            continue

        score += v.get('points')
    return score


def get_player_scoring(player):
    try:
        player_id = int(player)
    except ValueError:
        return None

    player_info = league.player_info(playerId=player_id)
    if player_info == None:
        return None

    player_stat = []
    if player_info.total_points == 0 and player_info.projected_total_points == 0:
        return None

    player_stat.append(player_info.name)
    player_stat.append(player_id)
    player_stat.append(player_info.position)
    player_stat.append(player_info.projected_total_points)
    player_score = get_player_score(player_info.stats, 18)
    player_stat.append(player_score)
    player_stat.append(player_score - player_info.projected_total_points)
    return player_stat


def get_all_player_scoring(league: League):
    players_stat = []
    players_processed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_player = {executor.submit(get_player_scoring, player): player for player in league.player_map}
        for player_stat in concurrent.futures.as_completed(future_player):
            players_processed += 1
            if players_processed % 1000 == 0:
                logger.info(f"Players processed = {players_processed} of {len(league.player_map)}")
            if player_stat.result() is None:
                continue
            players_stat.extend([player_stat.result()])

    df = pd.DataFrame(players_stat, columns=["Player Name",
                                             "playerId",
                                             "Position",
                                             "Projected Points",
                                             "Total Points",
                                             "Diff"])

    return df


def add_draft_info(players: DataFrame, draft: DataFrame) -> DataFrame:
    drafted_by = []
    draft_round = []
    playerIds = players["playerId"].to_list()
    for playerId in playerIds:
        try:
            drafted_by.append(draft[draft["playerId"] == playerId]["Team Name"].values[0])
            draft_round.append(draft[draft["playerId"] == playerId]["Round"].values[0])
        except IndexError:
            drafted_by.append('-')
            draft_round.append('-')

    players.insert(3, "Drafted by", drafted_by, True)
    players.insert(4, "Draft Round", draft_round, True)
    return players


def get_expectation(players: DataFrame, draft: DataFrame, ascending: bool):
    top_players =  players.sort_values(by=["Diff"], ascending=ascending).head(20)
    top_players = add_draft_info(top_players, draft)
    return top_players[["Player Name", "Drafted by", "Draft Round", "Projected Points", "Total Points", "Diff"]].to_html(index=False, classes="my_style")


def get_top_players(players: DataFrame, draft: DataFrame, position: str) -> str:
    top_players = players[players["Position"].str.match(position)].sort_values(by=["Total Points"], ascending=False).head(10)
    top_players = add_draft_info(top_players, draft)
    return top_players[["Player Name", "Drafted by", "Draft Round", "Total Points"]].to_html(index=False, classes="my_style")


def insert_player_score(scores: list, score: float) -> list:
    if len(scores) > 0:
        for idx, value in enumerate(scores):
            if score > value:
                scores.insert(idx, score)
                return scores

    scores.append(score)
    return scores


def get_top_score(scores: list, number: int):
    top_score = 0
    for score in range(number):
        top_score += scores.pop(0)
    return top_score, scores


def get_perfect_score(league, lineup: list) -> float:
    QBs = []
    RBs = []
    WRs = []
    TEs = []
    DSTs = []
    Ks = []

    for player in lineup:
        if player.position == "QB":
            QBs = insert_player_score(QBs, player.points)
        elif player.position == "RB":
            RBs = insert_player_score(RBs, player.points)
        elif player.position == "WR":
            WRs = insert_player_score(WRs, player.points)
        elif player.position == "TE":
            TEs = insert_player_score(TEs, player.points)
        elif player.position == "D/ST":
            DSTs = insert_player_score(DSTs, player.points)
        elif player.position == "K":
            Ks = insert_player_score(Ks, player.points)

    total_score = 0
    QB_score, QBs = get_top_score(QBs, 1)
    RB_score, RBs = get_top_score(RBs, 2)
    WR_score, WRs = get_top_score(WRs, 3)
    TE_score, TEs = get_top_score(TEs, 1)
    DST_score, DSTs = get_top_score(DSTs, 1)
    K_score, Ks = get_top_score(Ks, 1)
    F_score = max(WRs + RBs + TEs)
    total_score = QB_score + RB_score + WR_score + TE_score + DST_score + K_score + F_score
    return total_score


def get_perfect_record(league: League) -> str:
    winners = []
    losers = []
    for week in range(1, min(league.settings.reg_season_count + 1, league.current_week)):
        games_in_week = league.box_scores(week=week)
        for game in games_in_week:
            home_score = get_perfect_score(league, game.home_lineup)
            away_score = get_perfect_score(league, game.away_lineup)
            if home_score > away_score:
                winners.append(game.home_team.team_name)
                losers.append(game.away_team.team_name)
            else:
                losers.append(game.home_team.team_name)
                winners.append(game.away_team.team_name)

    standings = []
    for team in league.teams:
        team_record = []
        team_record.append(team.team_name)
        team_record.append(f"{team.wins}-{team.losses}")
        wins_perfect = winners.count(team.team_name)
        losses_perfect = losers.count(team.team_name)
        team_record.append(f"{wins_perfect}-{losses_perfect}")
        team_record.append(wins_perfect - team.wins)
        standings.extend([team_record])

    df = pd.DataFrame(standings, columns=["Team",
                                          "Record",
                                          "Perfect Record",
                                          "Diff"])

    return df.to_html(index=False, classes="my_style")


if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description='Generate HTML for ESPN fantasy football season')
    parser.add_argument('year', type=int, help="ESPN Fantasy Year")
    parser.add_argument("--lff",
                        "--load-from-file",
                        action='store_true',
                        help='Load fantasy data from file and not from ESPN API. Use for debug only.')
    args = parser.parse_args()

    # Creating a logger
    logger = setup_logger()

    outputfile = f"index_{args.year}.html"
    title = f"Make Football Great Again Season {args.year} Stats"

    # League API
    logger.info(f"Getting League data: Started")
    if args.lff:
        with open('data.pkl', 'rb') as f:
            draft_class, games, players, league = pickle.load(f)
    else:
        with open("credentials.json", "r") as f:
            login = json.load(f)
        league = League(league_id=274452,
                        year=args.year,
                        espn_s2=login.get("espn_s2"),
                        swid=login.get("swid"))
    logger.info(f"Getting League data: Done")

    # Compute points for and against
    points_for, points_against = print_team_scoring(league)

    # Get all games data
    logger.info(f"Getting game data: Started")
    if not args.lff:
        games = get_games(league=league)
    logger.info(f"Getting game data: Done")

    # Find closest games
    close_games = get_close_games(games)

    # Get highest scoring team, yet still lost
    high_score_and_lost = get_high_score_and_lost(games)

    # Get lowest scoring team, yet won the game
    low_score_and_won = get_low_score_and_won(games)

    # Get draft class
    logger.info(f"Getting draft class: Started")
    if not args.lff:
        draft_class = get_draft_class(league=league)
    logger.info(f"Getting draft class: Done")

    missed_per_team = print_missed_games_per_team(draft_class)

    # Analyze over- and under-performing playsers
    logger.info(f"Getting player score data: Started")
    if not args.lff:
        players = get_all_player_scoring(league)

        # Store variables in file
        logger.info(f"Storing data to pickle file")
        with open('data.pkl', 'wb') as f:
            pickle.dump([draft_class, games, players, league], f)
    logger.info(f"Getting player score data: Done")

    over_expectation = get_expectation(players, draft_class, False)
    under_expectation = get_expectation(players, draft_class, True)

    top_qb = get_top_players(players, draft_class, "QB")
    top_wr = get_top_players(players, draft_class, "WR")
    top_rb = get_top_players(players, draft_class, "RB")
    top_te = get_top_players(players, draft_class, "TE")
    top_kick = get_top_players(players, draft_class, "K")
    top_d = get_top_players(players, draft_class, "D/ST")

    perfect_lineup = get_perfect_record(league)

    now = datetime.now()

    template = jinja2.Environment(loader=jinja2.FileSystemLoader('./')).get_template('fantasy_temp.html')
    output = template.render(title=title,
                             points_for=points_for,
                             points_against=points_against,
                             close_games=close_games,
                             high_score_and_lost=high_score_and_lost,
                             low_score_and_won=low_score_and_won,
                             missed_per_team=missed_per_team,
                             over_expectation=over_expectation,
                             under_expectation=under_expectation,
                             top_qb=top_qb,
                             top_wr=top_wr,
                             top_rb=top_rb,
                             top_te=top_te,
                             top_kick=top_kick,
                             top_d=top_d,
                             perfect_lineup=perfect_lineup,
                             generation_time=now.strftime("%Y-%m-%d %H:%M"))

    with open(outputfile,'w') as f:
        f.write(output)
    logger.info(f"Write to output file")

    logger.info(f"Script completed")
