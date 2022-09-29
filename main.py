#!/usr/bin/env python3

from email.policy import default
import sys
import argparse
from pathlib import Path
from fantasy_stats import FantasyStats
import jinja2
from datetime import datetime
import logging
import json
from fantasy_stats import FantasyStats


def setup_logger():
    formatter = logging.basicConfig(
        level=logging.INFO,
        style="{",
        datefmt="%Y-%m-%d %H:%M:%S",
        format="{asctime} {levelname} {filename}:{lineno}: {message}",
    )
    handler = logging.FileHandler("log.txt", mode="w")
    handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger


def main(credentials: Path, year: int, qb: int, rb: int, wr: int, te: int, flex: int, dst: int, k: int):
    # Creating a logger
    logger = setup_logger()

    outputfile = f"index_{args.year}.html"
    title = f"Make Football Great Again Season {args.year} Stats"

    # League API
    try:
        with open(credentials, "r") as f:
                login = json.load(f)
    except FileNotFoundError:
        sys.exit(f"Credentials file {credentials.absolute()} not found")

    fantasy_stats = FantasyStats(
        league_id=login.get("league_id"),
        year=args.year,
        espn_s2=login.get("espn_s2"),
        swid=login.get("swid"),
        logger=logger,
        qb=qb,
        rb=rb,
        wr=wr,
        flex=flex,
        dst=dst,
        k=k,
    )

    # Compute points for and against
    points_for, points_against = fantasy_stats.print_team_scoring()

    # Find closest games
    close_games = fantasy_stats.get_close_games()

    # Get highest scoring team, yet still lost
    high_score_and_lost = fantasy_stats.get_high_score_and_lost()

    # Get lowest scoring team, yet won the game
    low_score_and_won = fantasy_stats.get_low_score_and_won()

    # Top 5 draft pick games
    missed_per_team = fantasy_stats.print_missed_games_per_team()

    # Analyze over- and under-performing playsers
    over_expectation = fantasy_stats.get_expectation(False)
    under_expectation = fantasy_stats.get_expectation(True)

    # Get list of top players
    top_qb = fantasy_stats.get_top_players("QB")
    top_wr = fantasy_stats.get_top_players("WR")
    top_rb = fantasy_stats.get_top_players("RB")
    top_te = fantasy_stats.get_top_players("TE")
    top_kick = fantasy_stats.get_top_players("K")
    top_d = fantasy_stats.get_top_players("D/ST")

    # Get perfect lineup
    perfect_lineup = fantasy_stats.get_perfect_record()

    now = datetime.now()
    template = jinja2.Environment(loader=jinja2.FileSystemLoader("./")).get_template(
        "fantasy_temp.html"
    )
    output = template.render(
        title=title,
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
        generation_time=now.strftime("%Y-%m-%d %H:%M"),
    )

    with open(outputfile, "w") as f:
        f.write(output)
        logger.info(f"Write to output file")

    logger.info(f"Script completed")


if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Generate HTML for ESPN fantasy football season",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("year", type=int, help="ESPN Fantasy Year")
    parser.add_argument(
        "-c",
        "--credentials",
        type=Path,
        default="credentials.json",
        help="ESPN Credentials file contaning 'league_id', 'espn_s2' and 'swid'")
    parser.add_argument("--qb", type=int, default=1, help="Number of QBs on team")
    parser.add_argument("--rb", type=int, default=2, help="Number of RBs on team")
    parser.add_argument("--wr", type=int, default=3, help="Number of WRs on team")
    parser.add_argument("--te", type=int, default=1, help="Number of TEs on team")
    parser.add_argument("--flex", type=int, default=1, help="Number of Flexs on team")
    parser.add_argument("--dst", type=int, default=1, help="Number of D/STs on team")
    parser.add_argument("--k", type=int, default=1, help="Number of kickers on team")

    args = parser.parse_args()
    main(**vars(args))
