# TODO: add error handling, log the proper info...
# TODO: add playoff stats
# TODO: figure out special characters...
# TODO: make command !l to get league leaders, take args for specific stats
# TODO: make command !s to get league standings

import os
import random
import discord
from discord.ext import commands
from dotenv import load_dotenv
import pymongo
from bson import ObjectId
import re

from oauth2client.service_account import ServiceAccountCredentials
import gspread
import json
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import requests
from bs4 import BeautifulSoup

# google sheets
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# gmail account: wsbl-google-sheets@world-sim-basketball-league.iam.gserviceaccount.com

# MongoDB
client = pymongo.MongoClient(
    "mongodb://test:test@cluster0-shard-00-00.k0fe1.mongodb.net:27017,cluster0-shard-00-01.k0fe1.mongodb.net:27017,"
    "cluster0-shard-00-02.k0fe1.mongodb.net:27017/myFirstDatabase?ssl=true&replicaSet=Cluster0-shard-0&authSource"
    "=admin&retryWrites=true&w=majority")
db = client.wsbl
discord_collection = db.discord
player_collection = db.players
stat_collection = db.player_season_stats
player_page_collection = db.player_page
task_collection = db.tasks

# Discord
load_dotenv()
token = ('OTE0OTcyNDMxNDk4NzY4Mzg0.YaU0ew.zyuqoI3AUxyCp29f5W1cT8Rn2ZQ')
client = discord.Client()

bot = commands.Bot(command_prefix='!')


# Claim forum username
@bot.command(name='cf', help='Claim your forum username')
async def claim_forum(ctx):
    doc_id = ""
    exists = False
    cursor = discord_collection.find({"discord": re.compile(str(ctx.message.author), re.IGNORECASE)})
    for document in cursor:
        exists = True
        doc_id = document.get('_id')
        break

    if exists:
        discord_collection.find_one_and_update({"_id": ObjectId(doc_id)},
                                               {
                                                   "$set": {
                                                       "discord": str(ctx.message.author),
                                                       "forum_name": str(ctx.message.content).replace("!cf ", "")
                                                   }
                                               })
        await ctx.send("Updated forum username!")
    else:
        discord_collection.insert_one({"discord": str(ctx.message.author),
                                       "forum_name": str(ctx.message.content).replace("!cf ", "")})
        await ctx.send("Claimed forum username!")


# Claim player
@bot.command(name='cp', help='Claim your player name')
async def claim_player(ctx):
    # TODO: handle weird characters for players...
    # TODO: actually, should just make a normalized/lookup value to match the names with weird characters
    doc_id = ""
    exists = False
    cursor = discord_collection.find({"discord": re.compile(str(ctx.message.author), re.IGNORECASE)})
    for document in cursor:
        exists = True
        doc_id = document.get('_id')
        break

    if exists:
        discord_collection.find_one_and_update({"_id": ObjectId(doc_id)},
                                               {
                                                   "$set": {
                                                       "discord": str(ctx.message.author),
                                                       "player_name": str(ctx.message.content).replace("!cp ", "")
                                                   }
                                               })
        await ctx.send("Updated player!")
    else:
        discord_collection.insert_one({"discord": str(ctx.message.author),
                                       "player_name": str(ctx.message.content).replace("!cp ", "")})
        await ctx.send("Claimed player!")


@bot.command(name='p', help='Replies with the latest regular season stats for your player')
async def stats(ctx):
    if command_has_no_argument(ctx, "p"):
        forum_name = lookup_forum_name(str(ctx.message.author))
        player_name = lookup_player_name(str(ctx.message.author))

        latest_season = 0

        # lookup player name from the players collection first to get the index name
        index_player = player_collection.find_one({"standard_name": re.compile(player_name, re.IGNORECASE)})
        if index_player is not None:
            player_name = index_player['index_name']
        else:
            index_player = player_collection.find_one({"name": re.compile(player_name, re.IGNORECASE)})
            player_name = index_player['index_name']

        cursor = player_page_collection.find({"name": re.compile(player_name, re.IGNORECASE)})
        for document in cursor:
            if document.get("season") != "CAREER" and int(document.get("season")) > latest_season:
                latest_season = int(document.get("season"))

        document = player_page_collection.find_one(
            {"name": re.compile(player_name, re.IGNORECASE), "season": str(latest_season), "playoffs": False})

        if document is not None:
            await ctx.send(player_name + ": " + str(document.get("url") + "\n```" + format_stats(document) + "```"))
            return

        await ctx.send("Could not find stats for: " + str(ctx.message.author))
    else:
        latest_season = 0

        name = str(ctx.message.content).replace("!p ", "").strip()

        # lookup player name from the players collection first to get the index name
        index_player = player_collection.find_one({"standard_name": re.compile(name, re.IGNORECASE)})
        if index_player is not None:
            name = index_player['index_name']
        else:
            index_player = player_collection.find_one({"name": re.compile(name, re.IGNORECASE)})
            if index_player is not None:
                name = index_player['index_name']

        cursor = player_page_collection.find({"name": re.compile(name, re.IGNORECASE)})
        for document in cursor:
            if document.get("season") != "CAREER" and int(document.get("season")) > latest_season:
                latest_season = int(document.get("season"))

        document = player_page_collection.find_one(
            {"name": re.compile(name, re.IGNORECASE), "season": str(latest_season), "playoffs": False})

        if document is not None:
            await ctx.send(name + ": " + str(document.get("url") + "\n```" + format_stats(document) + "```"))
            return

        # if user only has forum name attached, find player by forum name
        cursor = player_collection.find({"forum_name": re.compile(name, re.IGNORECASE)})
        player_name = ""
        for document in cursor:
            if int(document.get("season").replace("S", "")) > latest_season:
                latest_season = int(document.get("season").replace("S", ""))
                player_name = document.get("name")

        cursor = player_page_collection.find({"name": re.compile(player_name, re.IGNORECASE)})
        for document in cursor:
            if document.get("season") != "CAREER" and int(document.get("season")) > latest_season:
                latest_season = int(document.get("season"))
        document = player_page_collection.find_one(
            {"name": re.compile(player_name, re.IGNORECASE), "season": str(latest_season), "playoffs": False})

        if document is not None:
            await ctx.send(player_name + ": " + str(document.get("url") + "\n```" + format_stats(document) + "```"))
            return

        await ctx.send("Could not find stats for: " + name)


def format_stats(stats):
    pos = ""
    team = stats['team']
    # TODO: does this have to change?
    rel = player_collection.find_one({"name": stats['name']})
    if rel is not None:
        pos = rel['position'] + " - "
        team = rel['team']

    formatted = stats['name'] + " - " + pos + team + " - " + stats['season'] + "\n"
    formatted += "---------------------------------\n"
    formatted += "|   G   |   GS  |  MPG  |  PPG  |\n"
    formatted += format_stat(stats['g'], True) + format_stat(stats['gs'], False) + format_stat(stats['mpg'], False) \
                 + format_stat(stats['ppg'], False) + "\n---------------------------------\n"
    formatted += "|  APG  |  RPG  |  DRPG |  ORPG |\n"
    formatted += format_stat(stats['apg'], True) + format_stat(stats['rpg'], False) + \
                 format_stat(stats['drpg'], False) + format_stat(stats['orpg'], False) + \
                 "\n---------------------------------\n"
    formatted += "|  SPG  |  BPG  |  TOPG |  PTS  |\n"
    formatted += format_stat(stats['spg'], True) + format_stat(stats['bpg'], False) \
                 + format_stat(stats['topg'], False) + format_stat(stats['points'], False) + \
                 "\n---------------------------------\n"
    formatted += "|  ASTS |  DREB |  OREB |  SPG  |\n"
    formatted += format_stat(stats['assists'], True) + format_stat(stats['drebs'], False) + format_stat(stats['orebs'],
                                                                                                        False) \
                 + format_stat(stats['spg'], False) + "\n---------------------------------\n"
    formatted += "|  STLS |  BLKS |  TOs  |   DQ  |\n"
    formatted += format_stat(stats['steals'], True) + format_stat(stats['blocks'], False) + \
                 format_stat(stats['tos'], False) + format_stat(stats['dq'], False) + \
                 "\n---------------------------------\n"
    formatted += "|  PER  |  TS%  |  EFF  |\n"
    formatted += format_stat(stats['per'], True) + format_stat_percent(stats['ts_pct'], False) + \
                 format_stat(stats['eff'], False) + "\n-------------------------\n"
    formatted += "|  FGM  |  FGA  |  FG%  |\n"
    formatted += format_stat(stats['fgm'], True) + format_stat(stats['fga'], False) + \
                 format_stat_percent(stats['fg_pct'], False) + "\n-------------------------\n"
    formatted += "|  3PM  |  3PA  |  3P%  |\n"
    formatted += format_stat(stats['three_pm'], True) + format_stat(stats['three_pa'], False) + \
                 format_stat_percent(stats['three_pct'], False) + "\n-------------------------\n"
    return formatted


def format_stat_percent(stat, is_beginning):
    stat = round(stat * 100, 2)
    stat_str = str(stat) + "%"
    string = stat_str.rjust(7, " ")
    if is_beginning:
        return "|" + string + "|"

    return string + "|"


def format_stat(stat, is_beginning):
    string = str(stat).rjust(7, " ")
    if is_beginning:
        return "|" + string + "|"

    return string + "|"


@bot.command(name='tpe', help='Get your TPE')
async def tpe(ctx):
    if command_has_no_argument(ctx, "tpe"):
        forum_name = lookup_forum_name(str(ctx.message.author))
        player_name = lookup_player_name(str(ctx.message.author))

        document = player_collection.find_one({"discord": re.compile(str(ctx.message.author), re.IGNORECASE),
                                               "forum_name": re.compile(forum_name, re.IGNORECASE),
                                               "name": re.compile(player_name, re.IGNORECASE)})
        if document is not None:
            await ctx.send(player_name + ": " + str(document.get("tpe_total")) + " TPE")
            return

        document = player_collection.find_one({"forum_name": re.compile(forum_name, re.IGNORECASE),
                                               "name": re.compile(player_name, re.IGNORECASE)})
        if document is not None:
            await ctx.send(player_name + ": " + str(document.get("tpe_total")) + " TPE")
            return

        document = player_collection.find_one({"standard_name": re.compile(player_name, re.IGNORECASE)})
        if document is not None:
            await ctx.send(player_name + ": " + str(document.get("tpe_total")) + " TPE")
            return

        document = player_collection.find_one({"name": re.compile(player_name, re.IGNORECASE)})
        if document is not None:
            await ctx.send(player_name + ": " + str(document.get("tpe_total")) + " TPE")
            return

        document = player_collection.find_one({"forum_name": re.compile(forum_name, re.IGNORECASE)})
        if document is not None:
            await ctx.send(forum_name + ": " + str(document.get("tpe_total")) + " TPE")
            return

        await ctx.send("Could not find TPE for: " + str(ctx.message.author))
    else:
        name = str(ctx.message.content).replace("!tpe", "").strip()
        by_forum_name = player_collection.find_one({"forum_name": re.compile(name, re.IGNORECASE)})
        by_standard_player_name = player_collection.find_one({"standard_name": re.compile(name, re.IGNORECASE)})
        by_player_name = player_collection.find_one({"name": re.compile(name, re.IGNORECASE)})

        if by_forum_name is not None:
            await ctx.send(name + ": " + str(by_forum_name.get("tpe_total")) + " TPE")
            return

        if by_standard_player_name is not None:
            await ctx.send(name + ": " + str(by_standard_player_name.get("tpe_total")) + " TPE")
            return

        if by_player_name is not None:
            await ctx.send(name + ": " + str(by_player_name.get("tpe_total")) + " TPE")
            return

        await ctx.send("Could not find TPE for: " + name)


@bot.command(name='b', help='Get your bank balance')
async def bank(ctx):
    if command_has_no_argument(ctx, "b"):
        forum_name = lookup_forum_name(str(ctx.message.author))
        balance = lookup_bank_balance(forum_name)

        if balance is not None:
            await ctx.send(forum_name + ": " + balance)
            return

        await ctx.send("Could not find balance for: " + str(ctx.message.author))
    else:
        forum_name = str(ctx.message.content).replace("!b", "").strip()
        balance = lookup_bank_balance(forum_name)

        if balance is not None:
            await ctx.send(forum_name + ": " + balance)
            return

        await ctx.send("Could not find balance for: " + forum_name)


@bot.command(name='t', help='Get your 10 most recent transactions')
async def transactions(ctx):
    if command_has_no_argument(ctx, "t"):
        forum_name = lookup_forum_name(str(ctx.message.author))
        t = lookup_transactions(forum_name)

        if t is not None:
            await ctx.send("```" + t + "```")
            return

        await ctx.send("Could not find transactions for: " + str(ctx.message.author))
    else:
        forum_name = str(ctx.message.content).replace("!t", "").strip()
        t = lookup_transactions(forum_name)

        if t is not None:
            await ctx.send("```" + t + "```")
            return

        await ctx.send("Could not find transactions for: " + forum_name)


@bot.command(name='tasks', help='Get the links to the active tasks.')
async def active_tasks(ctx):
    embed = discord.Embed(title="Active Tasks",
                          color=0x14488F)
    get_active_tasks(embed)
    await ctx.send(embed=embed)
    return


def lookup_forum_name(discord_name):
    document = discord_collection.find_one({"discord": re.compile(discord_name, re.IGNORECASE)})
    if document is not None:
        return document.get("forum_name")
    else:
        return None


def lookup_player_name(discord_name):
    document = discord_collection.find_one({"discord": re.compile(discord_name, re.IGNORECASE)})
    if document is not None:
        return document.get("player_name")
    else:
        return None


def command_has_no_argument(ctx, command):
    if ctx.message.content == "!" + command or ctx.message.content == "!" + command + " ":
        return True
    else:
        return False


def lookup_bank_balance(forum_name):
    bank_sheet_id = "1BM-GFR5ddXPgsoYAhtGlkrkBHOY6AuLPXBFayIGDTqA"
    bank_sheet_range = 'Master Sheet!A:H'

    credentials = ServiceAccountCredentials.from_json_keyfile_name("token.json", scopes)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    for row in values:
        if row[1].lower() == forum_name.lower():
            return row[4]

    return None


def lookup_transactions(forum_name):
    bank_sheet_id = "1BM-GFR5ddXPgsoYAhtGlkrkBHOY6AuLPXBFayIGDTqA"
    bank_sheet_range = 'Transaction Logs!A:H'

    credentials = ServiceAccountCredentials.from_json_keyfile_name("token.json", scopes)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    ts = []

    for row in values:
        if row[2].lower() == forum_name.lower():
            if len(row) < 8:
                ts.append([row[0], row[2], row[6], "N/A"])
            else:
                ts.append([row[0], row[2], row[6], row[7]])

    if len(ts) == 0:
        return "No transactions found for " + forum_name + "."

    uname_len = 0
    if len(forum_name) < len("username"):
        uname_len = len("username") + 2
    else:
        uname_len = len(forum_name) + 2

    t = pad_string_l("date", 10) + "|" + pad_string_r("username", uname_len) + " | " + pad_string_r("net", 11) + " | " \
        + pad_string_l("source", 0) + "\n--------------------------------------------------------------\n"

    if len(ts) <= 10:
        for row in ts:
            t += (pad_string_l(row[0], 10) + "|" + pad_string_r(row[1], uname_len) + " | " + pad_string_r(row[2], 11) +
                  " | " + pad_string_l(row[3], 0) + "\n")
    else:
        for row in ts[len(ts) - 10:]:
            t += (pad_string_l(row[0], 10) + "|" + pad_string_r(row[1], uname_len) + " | " + pad_string_r(row[2], 11) +
                  " | " + pad_string_l(row[3], 0) + "\n")

    return t


@bot.command(name='u', help='Get your user information.')
async def user_overview(ctx):
    if command_has_no_argument(ctx, "u"):
        await ctx.send(get_user_info(str(ctx.message.author), True))
        return
    else:
        name = str(ctx.message.content).replace("!u", "").strip()
        await ctx.send(get_user_info(name, False))
        return


def get_user_info(name, is_discord_name):
    overview = ""
    player = None
    if is_discord_name:
        user_info = discord_collection.find_one({"discord": name})
        if user_info is not None:
            if user_info.get('forum_name') is not None and user_info.get('player_name') is not None:
                player = player_collection.find_one({"forum_name": re.compile(user_info['forum_name'], re.IGNORECASE),
                                                     "standard_name": re.compile(user_info['player_name'],
                                                                                 re.IGNORECASE)})
            if player is None and user_info.get('forum_name') is not None:
                player = player_collection.find_one({"forum_name": re.compile(user_info['forum_name'], re.IGNORECASE)})
            if player is None and user_info.get('player_name') is not None:
                player = player_collection.find_one(
                    {"standard_name": re.compile(user_info['player_name'], re.IGNORECASE)})
            if player is None:
                return "```Could not find information for " + name + "```"
    else:
        player = player_collection.find_one({"forum_name": re.compile(name, re.IGNORECASE)})
        if player is None:
            player = player_collection.find_one({"standard_name": re.compile(name, re.IGNORECASE)})
        if player is None:
            return "```Could not find information for " + name + "```"

    overview += "```"
    overview += player['name'] + "\n---------------\n"
    overview += "Season: " + player['season'] + "\n"
    overview += "Team: " + player['team'] + "\n"
    overview += "Position: " + player['position'] + "\n"
    overview += "Archetype: " + str(player['arch']).split("(")[0].strip() + "\n"
    overview += "TPE: " + str(player['tpe_total']) + " (" + str(player['tpe_banked']) + " banked)\n"
    overview += "Forum Name: " + player['forum_name'] + "\n"
    overview += "Last Seen: " + str(get_last_seen(player['user_url'])) + "\n"
    overview += "Last Updated: " + str(
        get_last_updated(player['forum_name'], player['standard_name'])) + "\n"
    overview += "Balance: " + lookup_bank_balance(player['forum_name']) + "\n"
    overview += "\nTasks\n----------------" + get_tasks(player['forum_name'])

    return overview


def get_last_seen(url):
    page_content = requests.get(url).text
    soup = BeautifulSoup(page_content, "html.parser")

    profile_stats = soup.find("div", attrs={"id": "profile-statistics"})

    divs = profile_stats.findAll("div", attrs={"class": "row2"})

    if len(divs) >= 4:
        return str(divs[2].text).replace("Last Seen: ", "")

    return "Could not find profile info!"


def get_last_updated(forum_name, player_name):
    player = player_collection.find_one({"normal_name": player_name})
    if player is not None:
        return player['last_updated']

    player = player_collection.find_one({"forum_name": forum_name})
    if player is not None:
        return player['last_updated']

    return "Could not find last updated date!"


def get_tasks(forum_name):
    topic_nums = []

    formatted_tasks = ""

    # activity check
    ac = "https://worldsimbasketball.jcink.net/index.php?showforum=5"

    # point tasks
    pt = "https://worldsimbasketball.jcink.net/index.php?showforum=7"

    page_content = requests.get(ac).text
    soup = BeautifulSoup(page_content, "html.parser")
    table = soup.find("div", attrs={"id": "topic-list"})
    newest_topic = table.find("tr", attrs={"class": "topic-row"})
    rows = newest_topic.findAll("td", attrs={"class": "row4"})
    link = rows[1].find("a").get("href")
    name = str(rows[1].text).replace("\n", "").split("(")[0].strip()

    topic_nums.append(get_topic_num_from_url(link))

    page_content = requests.get(pt).text
    soup = BeautifulSoup(page_content, "html.parser")
    table = soup.find("div", attrs={"id": "topic-list"})
    rows = table.findAll("tr", attrs={"class": "topic-row"})

    for row in rows:
        # make sure thread is not locked
        if row.find("img", attrs={"title": "Locked thread"}) is None:
            urls = row.findAll("td", attrs={"class": "row4"})
            if len(urls) > 2:
                link = urls[1].find("a").get("href")
                name = str(urls[1].text).replace("\n", "").split("(Pages")[0].strip()
                if name != "Introduction PT":
                    topic_nums.append(get_topic_num_from_url(link))

    for topic_num in topic_nums:
        formatted_tasks = did_user_complete_task(forum_name, topic_num, formatted_tasks)

    return formatted_tasks + "```"


def did_user_complete_task(user, task, formatted_tasks):
    task = task_collection.find_one({"topic_num": task})

    if task is not None:
        formatted_tasks += "\n" + task['task'] + ": "

        for forum_name in task['names']:
            if user.lower() == forum_name.lower():
                formatted_tasks += "✅"
                return formatted_tasks

        formatted_tasks += "❌"

    return formatted_tasks


def parse_forums_for_forum_name(forum_link, forum_name):
    page_content = requests.get(forum_link).text
    soup = BeautifulSoup(page_content, "html.parser")

    pages = soup.find("span", attrs={"class": "pagination_pagetxt"}).text
    page_count = re.sub("Pages: \\(", "", pages)
    page_count = re.sub("\\)", "", page_count)
    page_count = int(page_count)

    # go through each page of posts
    for x in range(1, page_count + 1):
        if x == 1:
            page_content = requests.get(forum_link + "&st=0").text
        else:
            page_content = requests.get(forum_link + "&st=" + str(((x - 1) * 15))).text

        soup = BeautifulSoup(page_content, "html.parser")
        names = soup.findAll("span", attrs={"class": "normalname"})

        for n in names:
            name = str(n.text).lower()
            if str(n.text).lower() == forum_name.lower():
                return "✅"

    return "❌"


def get_all_open_pts(active_rows, forum_name):
    formatted_tasks = ""
    for row in active_rows:
        urls = row.findAll("td", attrs={"class": "row4"})
        if len(urls) > 2:
            link = urls[1].find("a").get("href")
            name = str(urls[1].text).replace("\n", "").split("(Pages")[0].strip()
            formatted_tasks += name + ": " + parse_forums_for_forum_name(link, forum_name) + "\n"

    return formatted_tasks


def get_active_tasks(embed):
    task_array = []

    # activity check
    ac = "https://worldsimbasketball.jcink.net/index.php?showforum=5"

    # point tasks
    pt = "https://worldsimbasketball.jcink.net/index.php?showforum=7"

    page_content = requests.get(ac).text
    soup = BeautifulSoup(page_content, "html.parser")
    table = soup.find("div", attrs={"id": "topic-list"})
    newest_topic = table.find("tr", attrs={"class": "topic-row"})
    rows = newest_topic.findAll("td", attrs={"class": "row4"})
    link = rows[1].find("a").get("href")
    name = str(rows[1].text).replace("\n", "").split("(")[0].strip()

    task_array.append({"name": name, "link": link})

    page_content = requests.get(pt).text
    soup = BeautifulSoup(page_content, "html.parser")
    table = soup.find("div", attrs={"id": "topic-list"})
    rows = table.findAll("tr", attrs={"class": "topic-row"})

    for row in rows:
        # make sure thread is not locked
        if row.find("img", attrs={"title": "Locked thread"}) is None:
            urls = row.findAll("td", attrs={"class": "row4"})
            if len(urls) > 2:
                link = urls[1].find("a").get("href")
                name = str(urls[1].text).replace("\n", "").split("(Pages")[0].strip()
                if name != "Introduction PT":
                    task_array.append({"name": name, "link": link})

    for task in task_array:
        embed.add_field(name=task.get('name'), value="[Visit task...](" + task.get('link') + ")")

    return embed


def pad_string_r(value, amount):
    return str(value).rjust(amount)


def pad_string_l(value, amount):
    return str(value).ljust(amount)


def get_topic_num_from_url(url):
    return re.split('&showtopic=', url)[1]


def ignore_case(x):
    re.compile(x, re.IGNORECASE)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    bot.run(token)

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
