#!/usr/bin/env python3

import pandas as pd
from pandas.core.frame import DataFrame
from numpy import NaN
from espn_api.football import League
import requests
from natsort import natsort_keygen


class FantasyStats:
    def __init__(
        self,
        league_id,
        year,
        espn_s2,
        swid,
        logger,
        player_per_call=1000,
        qb=1,
        rb=2,
        wr=3,
        te=1,
        flex=1,
        dst=1,
        k=1,
    ) -> None:
        self.players_per_call = player_per_call
        self.num_qb = qb
        self.num_rb = rb
        self.num_wr = wr
        self.num_te = te
        self.num_flex = flex
        self.num_dst = dst
        self.num_k = k
        self.logger = logger
        self.year = year

        self.logger.info(f"Getting League data: Started")
        self.league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
        self.logger.info(f"Getting League data: Done")

        self.team_map = self._get_team_map()
        self.team_bye = self._get_team_byes()

        self.logger.info(f"Current week: {self.league.current_week}")
        self.logger.info(f"Total weeks: {self.league.settings.reg_season_count}")

        self.finished_weeks = self._get_finished_weeks()

        self.player_ids = self._get_player_ids()

        self.games = self._get_games()

        self._get_team_owner()

        self.draft_class = self._get_draft_class()

        self.players = self._get_all_player_scoring()

        self.logger.info(f"Fantasy stats init: Done")

    def _get_team_owner(self):
        self._team_owner_map = {}
        for member in self.league.members:
            id = member.get('id')
            name = f"{member.get('firstName')} {member.get('lastName')}"
            self._team_owner_map[id] = name

    def _get_team_byes(self):
        bye_week_map = {}
        res = requests.get(
            "https://fantasy.espn.com/apis/v3/games/ffl/seasons/2022?view=proTeamSchedules_wl"
        )
        if res.ok:
            teams = res.json().get("settings").get("proTeams")
            bye_week_map = {team["abbrev"].upper(): team["byeWeek"] for team in teams}
            bye_week_map.update({"OAK": bye_week_map.get("LV")})
            bye_week_map.update({"None": 0})
        else:
            self.logger.warn("Could not get team bye weeks")
        return bye_week_map

    def _get_team_map(self):
        self.logger.info(f"Generating team id mapping: Started")
        team_map = {team.team_id: team.team_name for team in self.league.teams}
        self.logger.info(f"Generating team id mapping: Done")
        return team_map

    def _get_player_ids(self):
        self.logger.info(f"Getting player ids: Started")
        pro_players = self.league.espn_request.get_pro_players()
        player_ids = []
        for player in pro_players:
            player_ids.append(player.get("id"))
        self.logger.info(f"Getting player ids: Done")
        return player_ids

    def print_player_injuries(self):
        injured_players = self.draft_class[self.draft_class["Games Missed"] > 0]
        injured_key_players = injured_players[injured_players["Round"] < 6].sort_values(
            by=["Round", "Games Missed"], ascending=[True, False]
        )[["Player Name", "Team Name", "Round", "Games Played", "Games Missed"]]
        return injured_key_players.to_html(index=False, classes="my_style")

    def print_team_scoring(self):
        """Prints the top scoring team in descending order"""

        # Save team data to pandas data frame
        data = []
        for team in self.league.teams:
            data.append([team.team_name, team.points_for, team.points_against])
        df = pd.DataFrame(data, columns=["Team", "Points for", "Points against"])

        points_for = df.sort_values(by=["Points for"], ascending=False)[
            ["Team", "Points for"]
        ].to_html(index=False, classes="my_style")
        points_against = df.sort_values(by=["Points against"], ascending=False)[
            ["Team", "Points against"]
        ].to_html(index=False, classes="my_style")
        return points_for, points_against

    def _get_games(self):
        self.logger.info(f"Getting games: Started")
        games = []
        for week in range(
            1, min(self.league.settings.reg_season_count + 1, self.league.current_week)
        ):
            games_in_week = self.league.box_scores(week=week)
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

        df = pd.DataFrame(
            games,
            columns=[
                "Winner team",
                "Winner score",
                "Winner proj",
                "Loser team",
                "Loser score",
                "Loser proj",
                "Winner lineup",
                "Loser lineup",
                "Score diff",
            ],
        )
        self.logger.info(f"Getting games: Done")
        return df

    def _get_games_played(self, player) -> int:
        games_played = 0
        for k, v in player.stats.items():
            # Week 0 corresponds to 'Total'
            if k == 0 or k > self.finished_weeks:
                continue

            if len(v.get("breakdown")) > 0:
                games_played += 1
        return games_played

    def _get_draft_class(self):
        self.logger.info(f"Getting draft class: Started")
        draft_ids = []
        for pick in self.league.draft:
            draft_ids.append(pick.playerId)
        players = self.league.player_info(playerId=draft_ids)

        players_stats = []
        for pick in self.league.draft:
            for player in players:
                if player.playerId == pick.playerId:
                    player_stats = []
                    player_stats.append(f"{pick.playerName} ({player.proTeam})")
                    player_stats.append(pick.playerId)
                    player_stats.append(pick.team.team_name)
                    player_stats.append(pick.round_num)
                    games_played = self._get_games_played(player)
                    player_stats.append(games_played)
                    break

            if len(self.team_bye) > 0:
                if self.team_bye.get(player.proTeam) > self.finished_weeks:
                    player_stats.append(self.finished_weeks - games_played)
                else:
                    player_stats.append(self.finished_weeks - games_played - 1)
            else:
                player_stats.append(self.finished_weeks - games_played)
            players_stats.extend([player_stats])

        # print(games)
        df = pd.DataFrame(
            players_stats,
            columns=[
                "Player Name",
                "playerId",
                "Team Name",
                "Round",
                "Games Played",
                "Games Missed",
            ],
        )
        self.logger.info(f"Getting draft class: Done")
        return df

    def _get_player_scoring(self, player_ids: list):
        players = self.league.player_info(playerId=player_ids)
        if players == None:
            return []

        players_stats = []
        for player in players:
            if player.total_points == 0 and player.projected_total_points == 0:
                continue

            player_stats = []
            if player.proTeam != "None":
                player_stats.append(f"{player.name} ({player.proTeam})")
            else:
                player_stats.append(f"{player.name} (-)")
            player_stats.append(player.playerId)
            player_stats.append(self.team_map.get(player.onTeamId, "-"))
            player_stats.append(player.position)
            player_stats.append(player.projected_total_points)
            player_score = self._get_player_score(player.stats)
            player_stats.append(player_score)
            player_stats.append(player_score - player.projected_total_points)
            players_stats.append(player_stats)
        return players_stats

    def _get_all_player_scoring(self):
        self.logger.info(f"Getting player score data: Started")
        players_stats = []
        num_lists = int(
            (len(self.player_ids) + self.players_per_call - 1) / self.players_per_call
        )
        player_id_lists = [self.player_ids[i::num_lists] for i in range(num_lists)]
        for list in player_id_lists:
            players_stats.extend(self._get_player_scoring(list))

        df = pd.DataFrame(
            players_stats,
            columns=[
                "Player Name",
                "playerId",
                "Current Team",
                "Position",
                "Projected Points",
                "Total Points",
                "Diff",
            ],
        )
        self.logger.info(f"Getting player score data: Done")
        return df

    def _get_player_score(self, player_stats) -> int:
        score = 0
        for week in player_stats.keys():
            if week == 0:
                # Week 0 corresponds to 'Total'
                continue
            score += player_stats[week].get("points")
        return score

    def _add_draft_info(self, players) -> DataFrame:
        drafted_by = []
        draft_round = []
        player_ids = players["playerId"].to_list()
        for player_id in player_ids:
            try:
                drafted_by.append(
                    self.draft_class[self.draft_class["playerId"] == player_id][
                        "Team Name"
                    ].values[0]
                )
                draft_round.append(
                    self.draft_class[self.draft_class["playerId"] == player_id][
                        "Round"
                    ].values[0]
                )
            except IndexError:
                drafted_by.append("-")
                draft_round.append("-")

        players.insert(3, "Drafted by", drafted_by, True)
        players.insert(4, "Draft Round", draft_round, True)
        return players

    def _get_perfect_score(self, lineup: list) -> float:
        QBs = []
        RBs = []
        WRs = []
        TEs = []
        DSTs = []
        Ks = []

        for player in lineup:
            if player.position == "QB":
                QBs = self._insert_player_score(QBs, player.points)
            elif player.position == "RB":
                RBs = self._insert_player_score(RBs, player.points)
            elif player.position == "WR":
                WRs = self._insert_player_score(WRs, player.points)
            elif player.position == "TE":
                TEs = self._insert_player_score(TEs, player.points)
            elif player.position == "D/ST":
                DSTs = self._insert_player_score(DSTs, player.points)
            elif player.position == "K":
                Ks = self._insert_player_score(Ks, player.points)

        total_score = 0
        QB_score, QBs = self._get_top_score(QBs, self.num_qb)
        RB_score, RBs = self._get_top_score(RBs, self.num_rb)
        WR_score, WRs = self._get_top_score(WRs, self.num_wr)
        TE_score, TEs = self._get_top_score(TEs, self.num_te)
        DST_score, DSTs = self._get_top_score(DSTs, self.num_dst)
        K_score, Ks = self._get_top_score(Ks, self.num_k)
        F_score = max(WRs + RBs + TEs)
        total_score = (
            QB_score + RB_score + WR_score + TE_score + DST_score + K_score + F_score
        )
        return total_score

    def _insert_player_score(self, scores: list, score: float) -> list:
        if len(scores) > 0:
            for idx, value in enumerate(scores):
                if score > value:
                    scores.insert(idx, score)
                    return scores

        scores.append(score)
        return scores

    def _get_top_score(self, scores: list, number: int):
        top_score = 0
        for _ in range(number):
            try:
                top_score += scores.pop(0)
            except IndexError:
                # Skip if list is empty
                continue
        return top_score, scores

    def get_close_games(self):
        close_games = (
            self.games.sort_values(by=["Score diff"], ascending=True)[
                [
                    "Winner team",
                    "Winner score",
                    "Loser team",
                    "Loser score",
                    "Score diff",
                ]
            ]
            .head(10)
            .to_html(index=False, classes="my_style")
        )
        return close_games

    def get_high_score_and_lost(self):
        high_score_lost = (
            self.games.sort_values(by=["Loser score"], ascending=False)[
                ["Winner team", "Winner score", "Loser team", "Loser score"]
            ]
            .head(10)
            .to_html(index=False, classes="my_style")
        )
        return high_score_lost

    def get_low_score_and_won(self):
        low_score_won = (
            self.games.sort_values(by=["Winner score"], ascending=True)[
                ["Winner team", "Winner score", "Loser team", "Loser score"]
            ]
            .head(10)
            .to_html(index=False, classes="my_style")
        )
        return low_score_won

    def print_missed_games_per_team(self):
        return (
            self.draft_class[self.draft_class["Round"] < 6]
            .groupby(["Team Name"], as_index=False)
            .sum(numeric_only=True)[["Team Name", "Games Played", "Games Missed"]]
            .sort_values(by=["Games Missed"], ascending=False)
            .to_html(index=False, classes="my_style")
        )

    def get_expectation(self, ascending: bool):
        top_players = self.players.sort_values(by=["Diff"], ascending=ascending).head(
            20
        )
        top_players = self._add_draft_info(top_players)
        return top_players[
            [
                "Player Name",
                "Drafted by",
                "Draft Round",
                "Current Team",
                "Projected Points",
                "Total Points",
                "Diff",
            ]
        ].to_html(index=False, classes="my_style")

    def get_top_players(self, position: str) -> str:
        top_players = (
            self.players[self.players["Position"].str.match(position)]
            .sort_values(by=["Total Points"], ascending=False)
            .head(10)
        )
        top_players = self._add_draft_info(top_players)
        return top_players[
            ["Player Name", "Drafted by", "Draft Round", "Current Team", "Total Points"]
        ].to_html(index=False, classes="my_style")

    def get_perfect_record(self) -> str:
        winners = []
        losers = []
        for week in range(
            1, min(self.league.settings.reg_season_count + 1, self.league.current_week)
        ):
            games_in_week = self.league.box_scores(week=week)
            for game in games_in_week:
                home_score = self._get_perfect_score(game.home_lineup)
                away_score = self._get_perfect_score(game.away_lineup)
                if home_score > away_score:
                    winners.append(game.home_team.team_name)
                    losers.append(game.away_team.team_name)
                else:
                    losers.append(game.home_team.team_name)
                    winners.append(game.away_team.team_name)

        standings = []
        for team in self.league.teams:
            team_record = []
            team_record.append(team.team_name)
            team_record.append(f"{team.wins}-{team.losses}")
            wins_perfect = winners.count(team.team_name)
            losses_perfect = losers.count(team.team_name)
            team_record.append(f"{wins_perfect}-{losses_perfect}")
            team_record.append(wins_perfect - team.wins)
            standings.extend([team_record])

        df = pd.DataFrame(
            standings, columns=["Team", "Record", "Perfect Record", "Diff"]
        ).sort_values(by=["Perfect Record"], key=natsort_keygen(), ascending=False)

        return df.to_html(index=False, classes="my_style")

    def _get_finished_weeks(self):
        team = self.league.teams[0]
        return team.wins + team.losses + team.ties

    def get_league_overview(self):
        league_overview = []
        for team in self.league.teams:
            team_info = []
            team_info.append(f"{team.team_name} ({team.team_abbrev})")
            team_info.append(team.standing)
            team_info.append(f"{team.playoff_pct:.2f}")
            team_info.append(team.division_name)
            team_info.append(f"{team.wins}-{team.losses}-{team.ties}")
            team_info.append(team.points_for)
            team_info.append(team.points_against)
            team_info.append(team.acquisitions)
            owners = [self._team_owner_map[owner] for owner in team.owners]
            team_info.append(", ".join(owners))
            league_overview.extend([team_info])

        df = pd.DataFrame(
            league_overview,
            columns=[
                "Team",
                "Standing",
                "Playoff %",
                "Division",
                "Record",
                "Points for",
                "Points against",
                "Transactions",
                "Owner",
            ],
        ).sort_values(by=["Standing"], ascending=True)

        return df.to_html(index=False, classes="my_style")
