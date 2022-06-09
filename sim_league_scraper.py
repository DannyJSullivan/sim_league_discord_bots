import os
import random
import discord
from discord.ext import commands
from discord.ext import tasks
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
pbe_db = client.pbe
pbe_task_collection = pbe_db.tasks

wsbl_db = client.wsbl
wsbl_task_collection = wsbl_db.tasks


# TODO: store everything in this discord object, forum_name, player_name, page on the tpe-tracker, etc...
# TODO: may just have to get player name,

# Discord
load_dotenv()
token = 'OTc4NzQ0OTI1MDMyMTc3NzQ0.GwXZ_5.sSgi9IjYttrEo3ovzNSu_yvpiBvknd5Qrv079U'
client = discord.Client()


@client.event
async def on_message(message):
    print("retrieving pbe tasks...")
    get_pbe_tasks()

    print("retrieving wsbl tasks...")
    get_wsbl_tasks()

    print("scraping wsbl players...")
    get_wsbl_players()


# TODO: scrape PBE tasks
def get_pbe_tasks():
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

    # update the collection by inserting new tasks and updating old
    update_db(pbe_task_collection, get_topic_num_from_url(link), name, get_completed_forum_names_list(link))

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
                update_db(pbe_task_collection, get_topic_num_from_url(link), name, get_completed_forum_names_list(link))

    return


def get_completed_forum_names_list(link):
    forum_names = []

    page_content = requests.get(link).text
    soup = BeautifulSoup(page_content, "html.parser")

    pages = soup.find("span", attrs={"class": "pagination_pagetxt"}).text
    page_count = re.sub("Pages: \\(", "", pages)
    page_count = re.sub("\\)", "", page_count)
    page_count = int(page_count)

    # go through each page of posts
    for x in range(1, page_count + 1):
        if x == 1:
            page_content = requests.get(link + "&st=0").text
        else:
            page_content = requests.get(link + "&st=" + str(((x - 1) * 15))).text

        soup = BeautifulSoup(page_content, "html.parser")
        names = soup.findAll("span", attrs={"class": "normalname"})

        for n in names:
            forum_names.append(n.text)

    return forum_names


def update_db(collection, topic_num, task, names):
    doc_id = ""
    exists = False
    cursor = collection.find({"topic_num": topic_num})

    for document in cursor:
        exists = True
        doc_id = document.get('_id')
        break

    if exists:
        collection.find_one_and_update({"_id": ObjectId(doc_id)},
                                               {
                                                   "$set": {
                                                       "topic_num": topic_num,
                                                       "task": task,
                                                       "names": names
                                                   }
                                               })
    else:
        collection.insert_one({
            "topic_num": topic_num,
            "task": task,
            "names": names
        })


# TODO: scrape WSBL tasks
def get_wsbl_tasks():
    return


# TODO: scrape WSBL players
def get_wsbl_players():
    return


def ignore_case(x):
    re.compile(x, re.IGNORECASE)


def get_topic_num_from_url(url):
    return re.split('&showtopic=', url)[1]


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    client.run(token)

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
