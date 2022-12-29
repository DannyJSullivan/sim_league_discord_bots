import os
import random
import math
import discord
from discord.ext import commands
from discord.ext import tasks
from dotenv import load_dotenv
import pymongo
from bson import ObjectId
import re
from unidecode import unidecode

from oauth2client.service_account import ServiceAccountCredentials
import gspread
import json
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import requests
from bs4 import BeautifulSoup

load_dotenv()

# google sheets
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# gmail account: wsbl-google-sheets@world-sim-basketball-league.iam.gserviceaccount.com

# MongoDB
mongo_uri = os.getenv("MONGO_URI")
client = pymongo.MongoClient(mongo_uri)
db = client.pbe
discord_collection = db.discord
task_collection = db.tasks
player_collection = db.players
bank_collection = db.bank

# TODO: add media to transactions log
# TODO: add tpe ranking for overall and for regression class

# Discord
token = os.getenv("PBE_DISCORD_TOKEN")
client = discord.Client()

prefix = os.environ.get("PBE_PREFIX")
bot = commands.Bot(command_prefix=prefix)

# Claim user


@bot.command(name='claim', help='Claim your forum username')
async def claim_user(ctx):
    doc_id = ""
    exists = False
    cursor = discord_collection.find({"discord": re.compile(str(ctx.message.author), re.IGNORECASE)})

    for document in cursor:
        exists = True
        doc_id = document.get('_id')
        break

    name = str(ctx.message.content).replace("!claim ", "").strip()
    player = get_active_player_by_forum_name(name)

    if player is not None:
        if exists:
            discord_collection.find_one_and_update({"_id": ObjectId(doc_id)},
                                                   {
                                                       "$set": {
                                                           "discord": str(ctx.message.author),
                                                           "forum_name": player['forum_name'],
                                                           "player_name": player['player_name']
                                                       }
                                                   })
            await ctx.send("Updated forum username!")
        else:
            discord_collection.insert_one({
                "discord": str(ctx.message.author),
                "forum_name": player['forum_name'],
                "player_name": player['player_name']
            })
            await ctx.send("Retrieved all user information successfully!")
    else:
        if exists:
            discord_collection.find_one_and_update({"_id": ObjectId(doc_id)},
                                                   {
                                                       "$set": {
                                                           "discord": str(ctx.message.author),
                                                           "forum_name": player['forum_name']
                                                       }
                                                   })
            await ctx.send("Updated forum username!")
        else:
            discord_collection.insert_one({
                "discord": str(ctx.message.author),
                "forum_name": player['forum_name'],
            })
            await ctx.send("Could not find player from the TPE Tracker! If your player is new, you should be added to "
                           "the tracker soon and all your information will be available. If your player name has "
                           "special characters, some may not be recognized. Please claim your player name using "
                           "!cp Your Player Name")


@bot.command(name='u', help='Get your user information. Updates every 5 minutes.')
async def user_overview(ctx):
    if command_has_no_argument(ctx, "u"):
        await ctx.send(get_user_info(str(ctx.message.author), True))
        return
    else:
        name = str(ctx.message.content).replace("!u", "").strip()
        await ctx.send(get_user_info(name, False))
        return


@bot.command(name='tasks', help='Get the links to the active tasks.')
async def active_tasks(ctx):
    embed = discord.Embed(title="Active Tasks",
                          color=0x8C0B0B)
    get_active_tasks(embed)
    await ctx.send(embed=embed)
    return


@bot.command(name='b', help='*DEPRECATED* Get your bank balance')
async def bank(ctx):
    await ctx.send("Call $b to get your balance.")


@bot.command(name='tr', help='*DEPRECATED* Get your 10 most recent transactions')
async def transactions(ctx):
    await ctx.send("Call $t to get your most recent transactions.")

# TODO: do this later
# @bot.command(name='dylan', help='Get dylan\'s info')
# async def active_tasks(ctx):
#     embed = discord.Embed(title="Balance for dylan",
#                           color=0x8C0B0B)
#     accounts = get_all_bank_accounts()
#     balance = 0
#     rank = 0
#     percentile = 0
#
#     for account in accounts:
#         rank += 1
#         if account.get('name').lower() == "dylan":
#             balance = account.get('balance')
#             break
#
#     percentile = 100 - float(rank / len(accounts)) * 100
#
#     embed.add_field(name="Total Balance", value="${:,}".format(balance), inline=False)
#     embed.add_field(name="Rank", value=rank, inline=False)
#     embed.add_field(name="Percentile", value="{0:0.2f}".format(percentile) + "%", inline=False)
#     await ctx.send(embed=embed)
#     return


@bot.command(name='dylan', help='DYLAN')
async def dylan(ctx):
    await ctx.send("dylan is the best!")
    return


def find_player_from_tpe_tracker(player_name):
    resp = {
        "status": "FAILED"
    }

    players = player_collection.find({'player_name': player_name})

    if players.retrieved == 0:
        players = player_collection.find({'normalized_name': get_normalized_name(player_name)})

    if players.retrieved == 0:
        return resp
    else:
        player = players[0]
        resp.__setitem__("status", "SUCCESS")
        resp.__setitem__("regression_season", players[0]['season'])
        resp.__setitem__("team", players[0]['team'])
        resp.__setitem__("name", players[0]['player_name'])
        resp.__setitem__("player_number", players[0]['number'])
        resp.__setitem__("pos", players[0]['position'])
        resp.__setitem__("tpe", players[0]['tpe'])
        resp.__setitem__("last_updated", players[0]['last_updated'])
        resp.__setitem__("profile", players[0]['user_url'])

        page_content = requests.get(players[0]['user_url']).text
        soup = BeautifulSoup(page_content, "html.parser")
        profile_stats = soup.find("div", attrs={"id": "profile-statistics"})

        for stat in profile_stats:
            if "Last Seen: " in stat.text:
                resp.__setitem__("last_seen", stat.text.replace("Last Seen: ", "").strip())
                return resp

        return resp


def get_active_player_by_forum_name(name):
    players = player_collection.find({"forum_name": re.compile(str(name), re.IGNORECASE)})

    player = None
    for p in players:
        if p.get("team") != "Retired":
            player = p

    return player


def find_player_from_bank(forum_name):
    bank_sheet_id = "15OMqbS-8cA21JFdettLs6A0K4A1l4Vjls7031uAFAkc"
    bank_sheet_range = 'Shorrax Import Player Pool!A:H'

    key = json.loads(os.environ.get("GCP_KEY"))
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(key)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    for row in values:
        if handle_special_characters_ignore_case(row[1]) == handle_special_characters_ignore_case(forum_name):
            return handle_special_characters(row[2])

    return None


def find_player_from_bank_by_player_name(player_name):
    bank_sheet_id = "15OMqbS-8cA21JFdettLs6A0K4A1l4Vjls7031uAFAkc"
    bank_sheet_range = 'Shorrax Import Player Pool!A:H'

    key = json.loads(os.environ.get("GCP_KEY"))
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(key)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    for row in values:
        if handle_special_characters_ignore_case(row[2]) == handle_special_characters_ignore_case(player_name):
            return handle_special_characters(row[1])

    return None


def lookup_bank_balance(forum_name):
    bank_sheet_id = "15OMqbS-8cA21JFdettLs6A0K4A1l4Vjls7031uAFAkc"
    bank_sheet_range = 'Shorrax Import Player Pool!A:H'

    key = json.loads(os.environ.get("GCP_KEY"))
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(key)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    for row in values:
        if row[1].lower() == forum_name.lower():
            return row[4]

    return None


def get_all_bank_accounts():
    accounts = []

    bank_sheet_id = "15OMqbS-8cA21JFdettLs6A0K4A1l4Vjls7031uAFAkc"
    bank_sheet_range = 'Shorrax Import Player Pool!A:H'

    key = json.loads(os.environ.get("GCP_KEY"))
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(key)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    for row in values:
        if row[4].lower() != 'balance':
            accounts.append({'name': row[1], 'balance': int(row[4].replace('$', '').replace(',', ''))})

    return sorted(accounts, key=lambda item: item['balance'], reverse=True)


def get_user_info(name, is_discord_name):
    if is_discord_name:
        discord_info = discord_collection.find_one({"discord": name})
        user_info = get_active_player_by_forum_name(discord_info['forum_name'])
        if user_info is not None and user_info['forum_name'] is not None:
            return get_user_overview(user_info, False)
    else:
        # try seeing if the user info exists first
        user_info = get_active_player_by_forum_name(name)
        if user_info is not None and user_info['forum_name'] is not None:
            return get_user_overview(user_info, False)

        user_info = player_collection.find_one({"player_name": name})
        if user_info is not None and user_info['forum_name'] is not None:
            return get_user_overview(user_info, False)

        user_info = player_collection.find_one({"normalized_name": get_normalized_name(name)})
        if user_info is not None and user_info['forum_name'] is not None:
            return get_user_overview(user_info, False)

        # otherwise scrape it real time
        return get_user_overview(name, True)

    return "Error! Could not find player. Please either claim a forum name by using !claim your_forum_name, " \
           "!claim Player Name, or check the spelling of the forum name or player name you supplied."


def get_user_overview(user_info, could_not_find):
    balance = bank_collection.find_one({"username": user_info["forum_name"]})['balance']
    last_seen = get_last_seen(user_info['user_url'])

    return f"""```
{user_info["player_name"]}
---------------
Regression Season: {user_info["season"]}
Team: {user_info["team"]}
Position: {user_info["position"]}
TPE: {user_info["tpe"]}
Forum Name: {user_info["forum_name"]}
Last Seen: {last_seen}
Last Updated: {user_info["last_updated"]}
Balance: {balance}
{get_tasks(user_info["forum_name"])}
```"""


def get_last_seen(url):
    page_content = requests.get(url).text
    soup = BeautifulSoup(page_content, "html.parser")

    profile_stats = soup.find("div", attrs={"id": "profile-statistics"})

    divs = profile_stats.findAll("div", attrs={"class": "row2"})

    if len(divs) >= 4:
        return str(divs[2].text).replace("Last Seen: ", "")

    return "Could not find profile info!"


def get_tasks(forum_name):
    topic_nums = []

    formatted_tasks = "\nTasks\n---------------"

    # activity check (only get the top one)
    ac = "https://probaseballexperience.jcink.net/index.php?showforum=77"

    # point tasks (get all forum topics except for the last one
    pt = "https://probaseballexperience.jcink.net/index.php?showforum=56"

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

    return formatted_tasks


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
            if name != "Introduction PT":
                formatted_tasks += name + ": " + parse_forums_for_forum_name(link, forum_name) + "\n"

    return formatted_tasks


def get_active_tasks(embed):
    task_array = []

    # activity check (only get the top one)
    ac = "https://probaseballexperience.jcink.net/index.php?showforum=77"

    # point tasks (get all forum topics except for the last one
    pt = "https://probaseballexperience.jcink.net/index.php?showforum=56"

    page_content = requests.get(ac).text
    soup = BeautifulSoup(page_content, "html.parser")
    table = soup.find("div", attrs={"id": "topic-list"})
    newest_topic = table.find("tr", attrs={"class": "topic-row"})
    rows = newest_topic.findAll("td", attrs={"class": "row4"})
    link = rows[1].find("a").get("href")
    name = str(rows[1].text).replace("\n", "").split("(")[0].strip()

    task_array.append({"name": name, "link": untrackify(link)})

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
                    task_array.append({"name": name, "link": untrackify(link)})

    for task in task_array:
        embed.add_field(name=task.get('name'), value="[Visit task...](" + task.get('link') + ")")

    return embed


# Removes any session ID (query parameter s with a hex string argument) from a URL
# The default args here are a bit of a hack to ensure the patterns are only compiled once
# head_pattern matches s=<hex string> and an optional & following a ?
# tail_pattern matches &s=<hex string>
def untrackify(url, head_pattern=re.compile(R"(?<=\?)s=[0-9a-f]*&?"), tail_pattern=re.compile(R"&s=[0-9a-f]*")):
    return re.sub(head_pattern, "", re.sub(tail_pattern, "", url))


# TODO: go through every task every 10 minutes and track all the forum names that have completed that task.
#       save them off and then go through the saved data
def get_who_completed_tasks():
    # activity check (only get the top one)
    ac = "https://probaseballexperience.jcink.net/index.php?showforum=77"

    # point tasks (get all forum topics except for the last one
    pt = "https://probaseballexperience.jcink.net/index.php?showforum=56"


def lookup_forum_name(discord_name):
    document = discord_collection.find_one({"discord": re.compile(discord_name, re.IGNORECASE)})
    if document is not None:
        return document.get("forum_name")
    else:
        return None


def lookup_transactions(forum_name):
    bank_sheet_id = "15OMqbS-8cA21JFdettLs6A0K4A1l4Vjls7031uAFAkc"
    bank_sheet_range = 'Logs!A:H'

    key = json.loads(os.environ.get("GCP_KEY"))
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(key)

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


def pad_string_r(value, amount):
    return str(value).rjust(amount)


def pad_string_l(value, amount):
    return str(value).ljust(amount)


def ignore_case(x):
    re.compile(x, re.IGNORECASE)


def command_has_no_argument(ctx, command):
    if ctx.message.content == "!" + command or ctx.message.content == "!" + command + " ":
        return True
    else:
        return False


def get_topic_num_from_url(url):
    return re.split('&showtopic=', url)[1]


def get_normalized_name(name):
    finalized_name = ""
    for s in name:
        if s.isalnum() or s == ' ':
            finalized_name = finalized_name + s

    return unidecode(finalized_name)


def handle_special_characters_ignore_case(name):
    name = name.replace("Ã¶", "ö")
    name = name.replace("Ä", "Đ")
    name = name.replace("Ä‘", "đ")
    name = name.replace("Ä‡", "ć")
    name = name.replace("\"", "")
    name = name.replace("Ã¡", "á")
    name = name.replace("â€™", "’")
    name = name.replace("Å¡", "š")

    return name.lower()


def handle_special_characters(name):
    name = name.replace("Ã¶", "ö")
    name = name.replace("Ä", "Đ")
    name = name.replace("Ä‘", "đ")
    name = name.replace("Ä‡", "ć")
    name = name.replace("\"", "")
    name = name.replace("Ã¡", "á")
    name = name.replace("â€™", "’")
    name = name.replace("Å¡", "š")

    return name


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    bot.run(token)

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
