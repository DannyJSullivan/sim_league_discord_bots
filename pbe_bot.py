import os
import random
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
db = client.pbe
discord_collection = db.discord
task_collection = db.tasks

# TODO: store everything in this discord object, forum_name, player_name, page on the tpe-tracker, etc...
# TODO: may just have to get player name,

# Discord
load_dotenv()
token = 'OTc4NzMzNjczNjA2MTcyNzEz.G1a7Ne.v6-hZsJfL9SC8mqdD6mJbmfSRT02oQ322j3NRA'
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

    forum_name = str(ctx.message.content).replace("!cf ", "")
    player_name = find_player_from_bank(forum_name)
    result = find_player_from_tpe_tracker(player_name)

    got_from_tpe_tracker = False

    if result.get("status") == "SUCCESS":
        got_from_tpe_tracker = True

    if got_from_tpe_tracker:
        if exists:
            discord_collection.find_one_and_update({"_id": ObjectId(doc_id)},
                                                   {
                                                       "$set": {
                                                           "discord": str(ctx.message.author),
                                                           "forum_name": forum_name,
                                                           "regression_season": result.get("regression_season"),
                                                           "team": result.get("team"),
                                                           "player_name": result.get("name"),
                                                           "pos": result.get("pos"),
                                                           "tpe": result.get("tpe"),
                                                           "last_updated": result.get("last_updated"),
                                                           "player_number": result.get("player_number"),
                                                           "profile": result.get("profile"),
                                                           "last_seen": result.get("last_seen")
                                                       }
                                                   })
            await ctx.send("Updated forum username!")
        else:
            discord_collection.insert_one({
                "discord": str(ctx.message.author),
                "forum_name": forum_name,
                "regression_season": result.get("regression_season"),
                "team": result.get("team"),
                "player_name": result.get("name"),
                "tpe_tracker_link": result.get("tpe_tracker_link"),
                "pos": result.get("pos"),
                "tpe": result.get("tpe"),
                "last_updated": result.get("last_updated"),
                "player_number": result.get("player_number"),
                "profile": result.get("profile"),
                "last_seen": result.get("last_seen")
            })
            await ctx.send("Retrieved all user information successfully!")
    else:
        if exists:
            discord_collection.find_one_and_update({"_id": ObjectId(doc_id)},
                                                   {
                                                       "$set": {
                                                           "discord": str(ctx.message.author),
                                                           "forum_name": forum_name
                                                       }
                                                   })
            await ctx.send("Updated forum username!")
        else:
            discord_collection.insert_one({
                "discord": str(ctx.message.author),
                "forum_name": forum_name,
            })
            await ctx.send("Could not find player from the TPE Tracker! If your player is new, you should be added to "
                           "the tracker soon and all your information will be available. If your player name has "
                           "special characters, some may not be recognized. Please claim your player name using "
                           "!cp Your Player Name")


# Claim player
@bot.command(name='cp', help='Claim your player name')
async def claim_player(ctx):
    player_name = str(ctx.message.content).replace("!cp ", "")

    result = find_player_from_tpe_tracker(player_name)

    if result.get("status") == "FAILURE":
        await ctx.send("Could not find player from the TPE Tracker! If your player is new, you should be added to "
                       "the tracker soon and all your information will be available. If your player name has "
                       "special characters, some may not be recognized. Please claim your player name using "
                       "!cp Your Player Name")

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
                                                       "regression_season": result.get("regression_season"),
                                                       "team": result.get("team"),
                                                       "player_name": result.get("name"),
                                                       "pos": result.get("pos"),
                                                       "tpe": result.get("tpe"),
                                                       "last_updated": result.get("last_updated"),
                                                       "player_number": result.get("player_number"),
                                                       "profile": result.get("profile"),
                                                       "last_seen": result.get("last_seen")
                                                   }
                                               })
        await ctx.send("Updated player!")
    else:
        discord_collection.insert_one({
            "discord": str(ctx.message.author),
            "regression_season": result.get("regression_season"),
            "team": result.get("team"),
            "player_name": result.get("name"),
            "tpe_tracker_link": result.get("tpe_tracker_link"),
            "pos": result.get("pos"),
            "tpe": result.get("tpe"),
            "last_updated": result.get("last_updated"),
            "player_number": result.get("player_number"),
            "profile": result.get("profile"),
            "last_seen": result.get("last_seen")
        })
        await ctx.send("Claimed player!")


@bot.command(name='u', help='Get your user information (NOTE: This one takes some extra time since it has to scrape the'
                            ' forum. Please be patient.)')
async def user_overview(ctx):
    if command_has_no_argument(ctx, "u"):
        await ctx.send(get_user_info(str(ctx.message.author), True))
        return
    else:
        name = str(ctx.message.content).replace("!u", "").strip()
        await ctx.send(get_user_info(name, False))
        return


def find_player_from_tpe_tracker(player_name):
    tpe_tracker = 'http://pbe-tpe-tracker.herokuapp.com/players'
    pbe_topic_url = 'https://probaseballexperience.jcink.net/index.php?showtopic='
    page_content = requests.get(tpe_tracker).text
    soup = BeautifulSoup(page_content, "html.parser")
    table = soup.find("tbody")
    rows = table.findAll("tr")

    resp = {
        "status": "FAILED"
    }

    # TODO: visit link in team name, go to profile, get forum_name so this can easily be claimed by one action
    # TODO: if person is not in the TPE tracker, check the bank maybe?
    # TODO: add some error messaging asking if they are new or if they have special characters in their name to also claim their player name
    # TODO: if none of the extra fields are provided (i.e. we can't find them in the bank or tpe tracker yet), keep trying every time they call the bot
    # TODO: add a refresh option to look up the player name again in case forum name changes
    # TODO: should have them claim their forum_name first, do a lookup in the bank since that gets updated first it seems

    for row in rows:
        row_data = row.findAll("td")
        for data in row_data:
            try:
                test = handle_special_characters(player_name)
                if handle_special_characters(data.text) == handle_special_characters(player_name):
                    resp.__setitem__("status", "SUCCESS")
                    resp.__setitem__("regression_season", row_data[0].text)
                    resp.__setitem__("team", row_data[1].text)
                    resp.__setitem__("name", row_data[2].text)
                    resp.__setitem__("player_number", row_data[2].find("a").get("href").replace("/players/", ""))
                    resp.__setitem__("pos", row_data[3].text)
                    resp.__setitem__("tpe", row_data[4].text)
                    resp.__setitem__("last_updated", row_data[5].text)
                    break
            except:
                return resp

    if resp.get("status", "SUCCESS"):
        page_content = requests.get(pbe_topic_url + resp.get("player_number")).text
        soup = BeautifulSoup(page_content, "html.parser")
        profile_url = soup.find("span", attrs={"class": "normalname"}).find("a").get("href")
        resp.__setitem__("profile", profile_url)
        page_content = requests.get(profile_url).text
        soup = BeautifulSoup(page_content, "html.parser")
        profile_stats = soup.find("div", attrs={"id": "profile-statistics"})

        for stat in profile_stats:
            if "Last Seen: " in stat.text:
                resp.__setitem__("last_seen", stat.text.replace("Last Seen: ", "").strip())
                return resp


    return resp


def find_player_from_bank(forum_name):
    bank_sheet_id = "15OMqbS-8cA21JFdettLs6A0K4A1l4Vjls7031uAFAkc"
    bank_sheet_range = 'Shorrax Import Player Pool!A:H'

    credentials = ServiceAccountCredentials.from_json_keyfile_name("token.json", scopes)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    for row in values:
        if row[1].lower() == forum_name.lower():
            return row[2]

    return None


def lookup_bank_balance(forum_name):
    bank_sheet_id = "15OMqbS-8cA21JFdettLs6A0K4A1l4Vjls7031uAFAkc"
    bank_sheet_range = 'Shorrax Import Player Pool!A:H'

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


def get_user_info(name, is_discord_name):
    if is_discord_name:
        user_info = discord_collection.find_one({"discord": name})
        if user_info is not None and user_info['forum_name'] is not None:
            return get_user_overview(user_info, False)
    else:
        # try seeing if the user info exists first
        user_info = discord_collection.find_one({"forum_name": name})
        if user_info is not None and user_info['forum_name'] is not None:
            return get_user_overview(user_info, False)

        user_info = discord_collection.find_one({"player_name": name})
        if user_info is not None and user_info['forum_name'] is not None:
            return get_user_overview(user_info, False)

        # otherwise scrape it real time
        return get_user_overview(name, True)

    return "Error! Could not find player. Please either claim a forum name by using !cf your_forum_name or check the " \
           "spelling of the forum name or player name you supplied."


def get_user_overview(user_info, is_forum_name):
    overview = ""
    # is forum name is true if all lookups fail
    if is_forum_name:
        forum_name = user_info
        player_name = find_player_from_bank(forum_name)
        balance = lookup_bank_balance(forum_name)
        user_info = find_player_from_tpe_tracker(player_name)

        if user_info.get("status") == "FAILED":
            return "Could not find player from the TPE Tracker! If the player is new, they should be added to " \
                   "the tracker soon and all their information will be available. If the player name has " \
                   "special characters, some may not be recognized."

        overview += '```' + player_name + '\n---------------\nRegression Season: ' \
                    + user_info['regression_season'] + '\nTeam: ' + user_info['team'] + '\nPosition: ' \
                    + user_info['pos'] + '\nTPE: ' + user_info['tpe'] + '\nForum Name: ' + forum_name \
                    + '\nLast Seen: ' + user_info['last_seen'] + '\nLast Updated: ' + user_info['last_updated'] \
                    + '\nBalance: ' + balance
        overview += get_tasks(forum_name)
        return overview
    else:
        balance = lookup_bank_balance(user_info['forum_name'])
        overview += '```' + user_info['player_name'] + '\n---------------\nRegression Season: ' \
                    + user_info['regression_season'] + '\nTeam: ' + user_info['team'] + '\nPosition: ' \
                    + user_info['pos'] + '\nTPE: ' + user_info['tpe'] + '\nForum Name: ' + user_info['forum_name'] \
                    + '\nLast Seen: ' + user_info['last_seen'] + '\nLast Updated: ' + user_info['last_updated'] \
                    + '\nBalance: ' + balance + "\nDiscord: " + user_info['discord']
        overview += get_tasks(user_info['forum_name'])
        return overview


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

    formatted_tasks = "\n\nTasks\n---------------"

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
            if name != "Introduction PT":
                formatted_tasks += name + ": " + parse_forums_for_forum_name(link, forum_name) + "\n"

    return formatted_tasks


# TODO: go through every task every 10 minutes and track all the forum names that have completed that task.
#       save them off and then go through the saved data
def get_who_completed_tasks():
    # activity check (only get the top one)
    ac = "https://probaseballexperience.jcink.net/index.php?showforum=77"

    # point tasks (get all forum topics except for the last one
    pt = "https://probaseballexperience.jcink.net/index.php?showforum=56"


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
    return unidecode(name)


def handle_special_characters(name):
    name = name.replace("Ã¶", "ö")
    name = name.replace("Ä", "Đ")
    name = name.replace("Ä‘", "đ")
    name = name.replace("Ä‡", "ć")
    name = name.replace("\"", "")
    name = name.replace("Ã¡", "á")
    name = name.replace("â€™", "’")
    name = name.replace("Å¡", "š")

    return name.lower()


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    bot.run(token)

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
