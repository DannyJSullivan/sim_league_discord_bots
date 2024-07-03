import os
import random
import math
from datetime import datetime

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

# TODO: add media to transactions log

# Discord
token = os.getenv("PBE_BANK_DISCORD_TOKEN")
client = discord.Client()

prefix = os.environ.get("PBE_BANK_PREFIX")
bot = commands.Bot(command_prefix=prefix)


@bot.command(name='b', help='Get your bank balance')
async def bank(ctx):
    if command_has_no_argument(ctx, "b"):
        forum_name = lookup_forum_name(str(ctx.message.author))
        balance = lookup_bank_balance(forum_name)

        if balance is not None:
            await ctx.send(forum_name + "'s bank balance: " + balance)
            return

        await ctx.send("Could not find balance for: " + str(ctx.message.author))
    else:
        forum_name = str(ctx.message.content).replace("$b", "").strip()
        balance = lookup_bank_balance(forum_name)

        if balance is not None:
            await ctx.send(forum_name + "'s bank balance: " + balance)
            return

        await ctx.send("Could not find balance for: " + forum_name)


@bot.command(name='t', help='Get your 10 most recent transactions')
async def transactions(ctx):
    if command_has_no_argument(ctx, "t"):
        forum_name = lookup_forum_name(str(ctx.message.author))

        t = get_all_transactions(forum_name)

        if t is not None:
            await ctx.send("```" + t + "```")
            return

        await ctx.send("Could not find transactions for: " + str(ctx.message.author))
    else:
        forum_name = str(ctx.message.content).replace("$t", "").strip()

        t = get_all_transactions(forum_name)

        if t is not None:
            await ctx.send("```" + t + "```")
            return

        await ctx.send("Could not find transactions for: " + forum_name)


@bot.command(name='m', help='Get your 10 most recent media transactions')
async def media_transactions(ctx):
    if command_has_no_argument(ctx, "m"):
        forum_name = lookup_forum_name(str(ctx.message.author))
        t = format_most_recent_transactions(lookup_media_transactions(forum_name), forum_name, False)

        if t is not None:
            await ctx.send("```" + t + "```")
            return

        await ctx.send("Could not find transactions for: " + str(ctx.message.author))
    else:
        forum_name = str(ctx.message.content).replace("$m", "").strip()
        t = format_most_recent_transactions(lookup_media_transactions(forum_name), forum_name, False)

        if t is not None:
            await ctx.send("```" + t + "```")
            return

        await ctx.send("Could not find transactions for: " + forum_name)


@bot.command(name='g', help='Get your 10 most recent graphic transactions')
async def graphic_transactions(ctx):
    if command_has_no_argument(ctx, "g"):
        forum_name = lookup_forum_name(str(ctx.message.author))
        t = format_most_recent_transactions(lookup_graphic_transactions(forum_name), forum_name, False)

        if t is not None:
            await ctx.send("```" + t + "```")
            return

        await ctx.send("Could not find transactions for: " + str(ctx.message.author))
    else:
        forum_name = str(ctx.message.content).replace("$g", "").strip()
        t = format_most_recent_transactions(lookup_graphic_transactions(forum_name), forum_name, False)

        if t is not None:
            await ctx.send("```" + t + "```")
            return

        await ctx.send("Could not find transactions for: " + forum_name)


@bot.command(name='v', help='Get your 10 most recent video transactions')
async def video_transactions(ctx):
    if command_has_no_argument(ctx, "v"):
        forum_name = lookup_forum_name(str(ctx.message.author))
        t = format_most_recent_transactions(lookup_video_transactions(forum_name), forum_name, False)

        if t is not None:
            await ctx.send("```" + t + "```")
            return

        await ctx.send("Could not find transactions for: " + str(ctx.message.author))
    else:
        forum_name = str(ctx.message.content).replace("$v", "").strip()
        t = format_most_recent_transactions(lookup_video_transactions(forum_name), forum_name, False)

        if t is not None:
            await ctx.send("```" + t + "```")
            return

        await ctx.send("Could not find transactions for: " + forum_name)


@bot.command(name='s', help='Get your total stock value')
async def stock(ctx):
    if command_has_no_argument(ctx, "s"):
        forum_name = lookup_forum_name(str(ctx.message.author))
        balance = lookup_stock_balance(forum_name)

        if balance is not None:
            await ctx.send(forum_name + "'s stock balance: " + balance)
            return

        await ctx.send("Could not find stocks for: " + str(ctx.message.author))
    else:
        forum_name = str(ctx.message.content).replace("$s", "").strip()
        balance = lookup_stock_balance(forum_name)

        if balance is not None:
            await ctx.send(forum_name + "'s stock balance: " + balance)
            return

        await ctx.send("Could not find stocks for: " + forum_name)


@bot.command(name='net', help='Get your net worth')
async def net_worth(ctx):
    if command_has_no_argument(ctx, "net"):
        forum_name = lookup_forum_name(str(ctx.message.author))
        balance = get_net_worth(forum_name)

        if balance is not None:
            await ctx.send(forum_name + "'s net worth: " + balance)
            return

        await ctx.send("Could not find net worth for: " + str(ctx.message.author))
    else:
        forum_name = str(ctx.message.content).replace("$net", "").strip()
        balance = get_net_worth(forum_name)

        if balance is not None:
            await ctx.send(forum_name + "'s net worth: " + balance)
            return

        await ctx.send("Could not find stocks for: " + forum_name)


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

    return "$0"


def lookup_stock_balance(forum_name):
    bank_sheet_id = "1uu3TjEsNEhw4FZCNhXbLsMg-pwLFaW7YSlDNsxqoPTQ"
    bank_sheet_range = 'User SUMMARY!A:K'

    key = json.loads(os.environ.get("GCP_KEY"))
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(key)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    for row in values:
        if row[0].lower() == forum_name.lower():
            return row[1]

    return "$0"


def get_net_worth(forum_name):
    bank_balance = lookup_bank_balance(forum_name)
    stock_balance = lookup_stock_balance(forum_name)

    balance = 0

    balance = balance + int(bank_balance.replace(",", "").replace("$", ""))
    balance = balance + int(stock_balance.replace(",", "").replace("$", ""))

    return "${:0,.0f}".format(balance)


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

    return ts


def lookup_media_transactions(forum_name):
    bank_sheet_id = "15OMqbS-8cA21JFdettLs6A0K4A1l4Vjls7031uAFAkc"
    bank_sheet_range = 'Media Logs!A:R'

    key = json.loads(os.environ.get("GCP_KEY"))
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(key)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    ts = []

    for row in values:
        if row[1].lower() == forum_name.lower():
            ts.append([row[0], row[1], row[15], row[2] + ": " + row[3]])

    return ts


def lookup_graphic_transactions(forum_name):
    bank_sheet_id = "15OMqbS-8cA21JFdettLs6A0K4A1l4Vjls7031uAFAkc"
    bank_sheet_range = 'Graphic Logs!A:F'

    key = json.loads(os.environ.get("GCP_KEY"))
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(key)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    ts = []

    for row in values:
        if len(row) > 1:
            if row[2].lower() == forum_name.lower():
                if len(row) > 5:
                    ts.append([row[0], row[2], row[3], row[5]])
                else:
                    ts.append([row[0], row[2], row[3], "N/A"])

    return ts


def lookup_video_transactions(forum_name):
    bank_sheet_id = "15OMqbS-8cA21JFdettLs6A0K4A1l4Vjls7031uAFAkc"
    bank_sheet_range = 'Video Logs!A:I'

    key = json.loads(os.environ.get("GCP_KEY"))
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(key)

    service = build('sheets', 'v4', credentials=credentials)

    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=bank_sheet_id,
                                range=bank_sheet_range).execute()
    values = result.get('values', [])

    ts = []

    for row in values:
        if len(row) > 1 and row[2].lower() == forum_name.lower():
            ts.append([row[0], row[2], row[6], row[3]])

    return ts


def get_all_transactions(forum_name):
    t1 = lookup_transactions(forum_name)
    t2 = lookup_video_transactions(forum_name)
    t3 = lookup_media_transactions(forum_name)
    t4 = lookup_graphic_transactions(forum_name)

    t_list = []

    for t in t1:
        t_list.append(t)
    for t in t2:
        t_list.append(t)
    for t in t3:
        t_list.append(t)
    for t in t4:
        t_list.append(t)

    try:
        t_list.sort(key=lambda tr: datetime.strptime(tr[0], "%m/%d/%Y"))
        return format_most_recent_transactions(t_list, forum_name, False)
    except:
        return format_most_recent_transactions(t1, forum_name, True)


def format_most_recent_transactions(ts, forum_name, error):
    if len(ts) == 0:
        return "No transactions found for " + forum_name + "."

    uname_len = 0
    if len(forum_name) < len("username"):
        uname_len = len("username") + 2
    else:
        uname_len = len(forum_name) + 2

    t = ''

    if error:
        t += 'There was an error processing some data (probably a date). Here\'s what I could find, excluding medias.' \
             '\n\n'

    t += pad_string_l("date", 10) + "|" + pad_string_r("username", uname_len) + " | " + pad_string_r("net", 11) + " | " \
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
    if ctx.message.content == "$" + command or ctx.message.content == "$" + command + " ":
        return True
    else:
        return False


def get_topic_num_from_url(url):
    return re.split('&showtopic=', url)[1]


def get_normalized_name(name):
    return unidecode(name)


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
