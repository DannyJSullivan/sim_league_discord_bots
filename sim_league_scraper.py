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

# TODO: When adding new imports, be sure to add them to the requirements.txt file. Run pip freeze >
#  requirements.txt to do so.

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
wsbl_player_collection = wsbl_db.players

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


def get_tasks(league, ac_link, pt_link):
    collection = None
    if league == "pbe":
        collection = pbe_task_collection
    elif league == "wsbl":
        collection = wsbl_task_collection

    page_content = requests.get(ac_link).text
    soup = BeautifulSoup(page_content, "html.parser")
    table = soup.find("div", attrs={"id": "topic-list"})
    newest_topic = table.find("tr", attrs={"class": "topic-row"})
    rows = newest_topic.findAll("td", attrs={"class": "row4"})
    link = rows[1].find("a").get("href")
    name = str(rows[1].text).replace("\n", "").split("(")[0].strip()

    # update the collection by inserting new tasks and updating old
    update_db(collection, get_topic_num_from_url(link), name, get_completed_forum_names_list(link))

    page_content = requests.get(pt_link).text
    soup = BeautifulSoup(page_content, "html.parser")
    table = soup.find("div", attrs={"id": "topic-list"})
    rows = table.findAll("tr", attrs={"class": "topic-row"})

    for row in rows:
        urls = row.findAll("td", attrs={"class": "row4"})
        if len(urls) > 2:
            link = urls[1].find("a").get("href")
            name = str(urls[1].text).replace("\n", "").split("(Pages")[0].strip()
            if name != "Introduction PT":
                update_db(collection, get_topic_num_from_url(link), name, get_completed_forum_names_list(link))

    return


def get_pbe_tasks():
    # activity check (only get the top one)
    ac = "https://probaseballexperience.jcink.net/index.php?showforum=77"

    # point tasks (get all forum topics except intro PT for PBE)
    pt = "https://probaseballexperience.jcink.net/index.php?showforum=56"

    get_tasks("pbe", ac, pt)
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


def get_wsbl_tasks():
    # activity check (only get the top one)
    ac = "https://worldsimbasketball.jcink.net/index.php?showforum=5"

    # point tasks (get all forum topics except intro PT for PBE)
    pt = "https://worldsimbasketball.jcink.net/index.php?showforum=7"

    get_tasks("wsbl", ac, pt)
    return


# TODO: scrape WSBL players
def get_wsbl_players():
    teams = {}

    # Free Agents
    url_free_agents = "https://worldsimbasketball.jcink.net/index.php?showforum=28"
    teams.__setitem__(url_free_agents, "Free Agents")

    # Retired Players
    url_retired_players = "https://worldsimbasketball.jcink.net/index.php?showforum=29"
    teams.__setitem__(url_retired_players, "Retired")

    # Draftees
    url_draftees_pg = "https://worldsimbasketball.jcink.net/index.php?showforum=96"
    url_draftees_sg = "https://worldsimbasketball.jcink.net/index.php?showforum=97"
    url_draftees_sf = "https://worldsimbasketball.jcink.net/index.php?showforum=98"
    url_draftees_pf = "https://worldsimbasketball.jcink.net/index.php?showforum=99"
    url_draftees_c = "https://worldsimbasketball.jcink.net/index.php?showforum=100"
    teams.__setitem__(url_draftees_pg, "Draftees")
    teams.__setitem__(url_draftees_sg, "Draftees")
    teams.__setitem__(url_draftees_sf, "Draftees")
    teams.__setitem__(url_draftees_pf, "Draftees")
    teams.__setitem__(url_draftees_c, "Draftees")

    # Waivers
    url_waviers = "https://worldsimbasketball.jcink.net/index.php?showforum=107"
    teams.__setitem__(url_waviers, "Waivers")

    # Detroit Generals
    url_detroit = "https://worldsimbasketball.jcink.net/index.php?showforum=18"
    teams.__setitem__(url_detroit, "Detroit Generals")

    # Indiana Haymakers
    url_indiana = "https://worldsimbasketball.jcink.net/index.php?showforum=36"
    teams.__setitem__(url_indiana, "Indiana Haymakers")

    # Lake Superior
    url_lake_superior = "https://worldsimbasketball.jcink.net/index.php?showforum=90"
    teams.__setitem__(url_lake_superior, "Lake Superior Raiders")

    # Mud City
    url_mud_city = "https://worldsimbasketball.jcink.net/index.php?showforum=67"
    teams.__setitem__(url_mud_city, "Mud City Wolves")

    # New Jersey
    url_new_jersey = "https://worldsimbasketball.jcink.net/index.php?showforum=37"
    teams.__setitem__(url_new_jersey, "New Jersey Blackjacks")

    # New York
    url_new_york = "https://worldsimbasketball.jcink.net/index.php?showforum=38"
    teams.__setitem__(url_new_york, "New York Imperials")

    # Seattle
    url_seattle = "https://worldsimbasketball.jcink.net/index.php?showforum=69"
    teams.__setitem__(url_seattle, "Seattle Orcas")

    # Vancouver
    url_vancouver = "https://worldsimbasketball.jcink.net/index.php?showforum=66"
    teams.__setitem__(url_vancouver, "Vancouver Venom")

    # Austin
    url_austin = "https://worldsimbasketball.jcink.net/index.php?showforum=51"
    teams.__setitem__(url_austin, "Austin Vaqueros")

    # Carolina
    url_carolina = "https://worldsimbasketball.jcink.net/index.php?showforum=15"
    teams.__setitem__(url_carolina, "Carolina Reapers")

    # Mexico City
    url_mexico_city = "https://worldsimbasketball.jcink.net/index.php?showforum=68"
    teams.__setitem__(url_mexico_city, "Mexico City Quetzals")

    # Panama
    url_panama = "https://worldsimbasketball.jcink.net/index.php?showforum=89"
    teams.__setitem__(url_panama, "Panama Anteaters")

    # Puerto Rico
    url_puerto_rico = "https://worldsimbasketball.jcink.net/index.php?showforum=88"
    teams.__setitem__(url_puerto_rico, "Puerto Rico Passion")

    # Singapore
    url_singapore = "https://worldsimbasketball.jcink.net/index.php?showforum=91"
    teams.__setitem__(url_singapore, "Singapore Sun Bears")

    # South Beach
    url_south_beach = "https://worldsimbasketball.jcink.net/index.php?showforum=39"
    teams.__setitem__(url_south_beach, "South Beach Sting")

    # Vegas
    url_vegas = "https://worldsimbasketball.jcink.net/index.php?showforum=53"
    teams.__setitem__(url_vegas, "Vegas Volts")

    # Philadelphia
    url_philadelphia = "https://worldsimbasketball.jcink.net/index.php?showforum=131"
    teams.__setitem__(url_philadelphia, "Philadelphia Lightning")

    # Edinburgh
    url_edinburgh = "https://worldsimbasketball.jcink.net/index.php?showforum=125"
    teams.__setitem__(url_edinburgh, "Edinburgh Golden Unicorns")

    # Frankfurt
    url_frankfurt = "https://worldsimbasketball.jcink.net/index.php?showforum=122"
    teams.__setitem__(url_frankfurt, "Frankfurt Falkens")

    # Madrid
    url_madrid = "https://worldsimbasketball.jcink.net/index.php?showforum=128"
    teams.__setitem__(url_madrid, "Madrid Matadors")

    # Ontario
    url_ontario = "https://worldsimbasketball.jcink.net/index.php?showforum=119"
    teams.__setitem__(url_ontario, "Ontario Legends")

    # San Diego
    url_san_diego = "https://worldsimbasketball.jcink.net/index.php?showforum=116"
    teams.__setitem__(url_san_diego, "San Diego Admirals")

    url_list = teams.keys()

    players = []

    for url in url_list:
        temp_players = parse_player_list(url, teams.get(url))

        for t in temp_players:
            players.append(t)

    post_to_db(players)

    return


# return the links to all players
def parse_player_list(url, team):
    print("parsing through team " + team + " at url: " + url)

    page_content = requests.get(url).text
    soup = BeautifulSoup(page_content, "html.parser")

    pages = soup.find("span", attrs={"class": "pagination_pagetxt"})

    page_count = 1

    if pages is not None:
        pages = pages.text
        page_count = re.sub("Pages: \\(", "", pages)
        page_count = re.sub("\\)", "", page_count)
        page_count = int(page_count)

    players = []

    # go through each page of posts
    for x in range(1, page_count + 1):
        new_page = url + "&st=" + str((x - 1) * 15)
        new_page_content = requests.get(new_page).text
        new_soup = BeautifulSoup(new_page_content, "html.parser")

        player_pages = new_soup.findAll("td", attrs={"class": "row4"})

        # go through results, get links to updates
        for p in range(len(player_pages)):
            if player_pages[p].find("a") is not None:
                if "worldsimbasketball.jcink.net/" in player_pages[p].find("a").get("href"):
                    players.append(player_pages[p].find("a").get("href"))

    player_results = []

    for p in players:
        # TODO: for debugging, for actually running use try catch
        # parse_player(p, team)
        try:
            player_results.append(parse_player(p, team))
        except Exception as e:
            print("Error occurred parsing player at url: " + p)
            print(e)

    return player_results


# TODO: strip the arch just for the important stuff, no comparisons (just do if point guard in etc...)
# return the player information
def parse_player(url, team):
    # print("parsing player at url: " + url)
    page_content = requests.get(url).text
    soup = BeautifulSoup(page_content, "html.parser")

    tpe = soup.find("span", attrs={"class": "topic-desc"})

    player_attributes = soup.find("div", attrs={"class": "postcolor"})

    edited = soup.find("span", attrs={"class": "edit"})

    season = soup.find("span", attrs={"class": "topic-title"})

    user_url = soup.find("span", attrs={"class": "normalname"})

    player = Player()

    # set team
    player.team = team

    # set url
    player.url = url

    # set season
    if season is not None:
        s = season.text
        player.season = s[s.find('[') + 1:s.find(']')]

    # get TPE
    if tpe is not None:
        player.tpe_total = int(tpe.text.replace(", TPE:", "").strip())

    # get user profile url
    if user_url is not None:
        player.user_url = user_url.find("a").get("href")

    if edited is not None:
        split = edited.text.split(":")
        d = split[1]

        final_date = ""

        if "Yesterday" in d:
            final_date = datetime.date.today() - datetime.timedelta(days=1)
        elif "Today" in d or "minutes ago" in d or "seconds ago" in d:
            final_date = datetime.date.today()
        else:
            split2 = d.split(",")
            d2 = split2[0].strip()
            split3 = d2.split(" ")
            final_formatted = split3[0] + " "
            if len(split3[1]) < 2:
                final_formatted += "0" + split3[1] + " "
            else:
                final_formatted += split3[1] + " "
            final_formatted += split3[2]

            final_date = datetime.datetime.strptime(final_formatted, "%b %d %Y").date()

        if final_date == "":
            player.last_updated = final_date.strftime("N/A")
        else:
            player.last_updated = final_date.strftime("%m/%d/%Y")
    else:
        player.last_updated = "N/A"

    # TODO: get last edited date (error pops up if recently edited with this method (i.e. 1 minutes ago vs. yesterday vs. 10/10/2021 etc...)
    # if edited is not None:
    #     player.last_updated = edited.text.split(":")[1].strip() + ":" + edited.text.split(":")[2].strip()

    # TODO: FOR DEBUGGING, insert topic name here
    # if "Troy Jones" in soup.find("span", attrs={"class": "topic-title"}).text:
    #    print("TROY JONES!")

    # parse through and get player info and attributes
    if player_attributes is not None:
        player_info = []

        attrs = player_attributes.findAll(text=True)

        # get player information
        for a in attrs:
            if ":" in a:
                player_info.append(a.split(":"))

        # assign info
        for x in player_info:
            if x[0].strip() == "Username":
                player.forum_name = x[1].strip()

            elif x[0] == "Discord":
                player.discord = x[1].strip()

            elif x[0] == "First Name":
                player.first_name = x[1].strip()

            elif x[0] == "Last Name":
                player.last_name = x[1].strip()
                player.name = player.first_name + " " + player.last_name
                player.index_name = get_index_name(player.name)
                player.standard_name = get_normalized_name(player.name)

            elif x[0] == "Position":
                player.position = x[1].strip()

            elif x[0] == "College":
                player.college = x[1].strip()

            elif x[0] == "Age":
                player.age = int(x[1].strip())

            elif x[0] == "Handedness":
                player.handedness = x[1].strip()

            elif x[0] == "Recruited By":
                player.recruited_by = x[1].strip()

            elif x[0] == "Jersey Number":
                player.jersey_num = x[1].strip()

            elif "Height (ft)" in x[0]:
                player.height = x[2].strip()

            elif "Weight (lbs)" in x[0]:
                player.weight = int(x[2].replace("lbs", "").strip())

            elif x[0] == "Birthplace":
                player.birthplace = x[1].strip()

            elif x[0] == "Player Archetype":
                player.arch = x[1].strip()

            elif x[0] == "Banked TPE":
                player.tpe_banked = int(x[1].strip())

            elif len(x) > 3:
                if "FG - Restricted Area" in x[2]:
                    player.fg_ra = int(x[3].strip())

                elif "FG - Inside Paint" in x[2]:
                    player.fg_ip = int(x[3].strip())

                elif "FG - Midrange" in x[2]:
                    player.fg_mr = int(x[3].strip())

                elif "FG - Corner" in x[2]:
                    player.fg_cor = int(x[3].strip())

                elif "FG - Above Break" in x[2]:
                    player.fg_ab = int(x[3].strip())

                elif "Free Throw" in x[2]:
                    player.ft = int(x[3].strip())

                elif "Scoring" in x[2]:
                    player.scoring = int(x[3].strip())

                elif "Passing" in x[2]:
                    player.passing = int(x[3].strip())

                elif "Handling" in x[2]:
                    player.handling = int(x[3].strip())

                elif "Off Rebound" in x[2]:
                    player.off_reb = int(x[3].strip())

                elif "Def Rebound" in x[2]:
                    player.def_reb = int(x[3].strip())

                elif "Blocking" in x[2]:
                    player.blocking = int(x[3].strip())

                elif "Stealing" in x[2]:
                    player.stealing = int(x[3].strip())

                elif "Defender" in x[2]:
                    player.defender = int(x[3].strip())

                elif "Basketball IQ" in x[2] or "Discipline" in x[2]:
                    player.iq = int(x[3].strip())

                elif "Drive and Pass" in x[2]:
                    player.ps_dap = int(x[3].strip())

                elif "Pass" in x[2]:
                    player.ps_pass = int(x[3].strip())

                elif "Drive and Shoot" in x[2]:
                    player.ps_das = int(x[3].strip())

                elif "Post Up" in x[2]:
                    player.ps_pu = int(x[3].strip())

                elif "Pull up Jumper" in x[2]:
                    player.ps_puj = int(x[3].strip())

                elif "Catch and Shoot" in x[2]:
                    player.ps_cas = int(x[3].strip())

                elif "Post" in x[2]:
                    player.fr_post = int(x[3].strip())

                elif "Midrange" in x[2]:
                    player.fr_mr = int(x[3].strip())

                elif "Corner" in x[2]:
                    player.fr_cor = int(x[3].strip())

                elif "Above the Break" in x[2]:
                    player.fr_atb = int(x[3].strip())

    # print(player.forum_name, player.discord, player.first_name, player.last_name, player.position, player.college,
    #       player.age, player.handedness, player.recruited_by, player.jersey_num, player.height, player.weight,
    #       player.birthplace, player.arch, player.tpe_banked, player.tpe_total, player.team, player.last_updated)

    # print(player.__dict__)

    return player


# try to replace any special characters that may arise
def get_index_name(name):
    name = re.sub(r'[^\x00-\x7f]', r'�', name)
    return name


def get_normalized_name(name):
    return unidecode(name)


def post_to_db(players):
    # TODO: go through the list, separate them into insert vs. update, do bulk updates
    # TODO: only perform this after complete list of players has been created... (i.e. everyone has been scraped)
    to_update = []
    to_insert = []

    for player in players:
        player_dict = vars(player)
        try:
            exists = False
            doc_id = ""
            cursor = wsbl_player_collection.find({"forum_name": player.forum_name, "first_name": player.first_name,
                                                  "last_name": player.last_name})
            for document in cursor:
                exists = True
                doc_id = document.get('_id')
                break

            if exists:
                try:
                    wsbl_player_collection.find_one_and_update({"_id": ObjectId(doc_id)}, {"$set": player_dict})
                    print("Updated user: " + player.forum_name + ", " + player.first_name + " " + player.last_name)
                except Exception as e:
                    print("Error occurred inserting players into the database: " + str(e))
            else:
                try:
                    wsbl_player_collection.insert_one(player_dict)
                    print("Inserted user: " + player.forum_name + ", " + player.first_name + " " + player.last_name)
                except Exception as e:
                    print("Error occurred inserting players into the database: " + str(e))

        except Exception as e:
            print("Error occurred retrieving players from the database: " + str(e))

    return


def ignore_case(x):
    re.compile(x, re.IGNORECASE)


def get_topic_num_from_url(url):
    return re.split('&showtopic=', url)[1]


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    client.run(token)

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
