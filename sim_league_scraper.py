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
import datetime

from oauth2client.service_account import ServiceAccountCredentials
import gspread
import json
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import requests
import time
from bs4 import BeautifulSoup

load_dotenv()

# TODO: When adding new imports, be sure to add them to the requirements.txt file. Run pip freeze >
#  requirements.txt to do so.

# google sheets
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# gmail account: wsbl-google-sheets@world-sim-basketball-league.iam.gserviceaccount.com

# MongoDB
mongo_uri = os.getenv("MONGO_URI")
client = pymongo.MongoClient(mongo_uri)
pbe_db = client.pbe
pbe_task_collection = pbe_db.tasks
pbe_player_collection = pbe_db.players
pbe_bank_collection = pbe_db.bank

wsbl_db = client.wsbl
wsbl_task_collection = wsbl_db.tasks
wsbl_player_collection = wsbl_db.players

# TODO: store everything in this discord object, forum_name, player_name, page on the tpe-tracker, etc...
# TODO: may just have to get player name,

# Discord
token = os.getenv("SIM_LEAGUE_SCRAPER_DISCORD_TOKEN")
client = discord.Client()


@tasks.loop(minutes=10.0, count=None)
async def update_sim_league_stuff():
    channel_id = os.getenv("STATUS_CHANNEL_ID")
    channel = client.get_channel(id=int(channel_id))

    await channel.send("Updating sim league info...")

    # TODO: uncomment this...
    print("retrieving pbe tasks...")
    get_pbe_tasks()
    print("done getting tasks!")

    print("retrieving pbe players...")
    get_pbe_players()
    print("done getting players!")

    print("scraping bank...")
    scrape_bank()
    print("done scraping bank!")

    # TODO: see if this needs to be added again...
    # sleep for 5 mins (300 secs)
    # time.sleep(300)
    # print("done sleeping. should be restarting!")

    await channel.send("Updated!")


@client.event
async def on_ready():
    client.loop.create_task(update_sim_league_stuff())


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
        # make sure thread is not locked
        if row.find("img", attrs={"title": "Locked thread"}) is None:
            urls = row.findAll("td", attrs={"class": "row4"})
            if len(urls) > 2:
                link = urls[1].find("a").get("href")
                name = str(urls[1].text).replace("\n", "").split("(Pages")[0].strip()
                if "Due: " in name:
                    name = name.split("Due: ")[0].strip()
                if "DEADLINE " in name:
                    name = name.split("DEADLINE ")[0].strip()
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

    page_count = 1
    if soup.find("span", attrs={"class": "pagination_pagetxt"}) is not None:
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


def get_pbe_players():
    # teams
    teams = []

    # PBE
    # Legends Conference East
    buf = "https://probaseballexperience.jcink.net/index.php?showforum=248"
    nyv = "https://probaseballexperience.jcink.net/index.php?showforum=65"
    obx = "https://probaseballexperience.jcink.net/index.php?showforum=71"
    prv = "https://probaseballexperience.jcink.net/index.php?showforum=59"
    teams.append(buf)
    teams.append(nyv)
    teams.append(obx)
    teams.append(prv)

    # Legends Conference West
    boi = "https://probaseballexperience.jcink.net/index.php?showforum=163"
    mau = "https://probaseballexperience.jcink.net/index.php?showforum=237"
    sas = "https://probaseballexperience.jcink.net/index.php?showforum=62"
    van = "https://probaseballexperience.jcink.net/index.php?showforum=68"
    teams.append(boi)
    teams.append(mau)
    teams.append(sas)
    teams.append(van)

    # Champions Conference East
    det = "https://probaseballexperience.jcink.net/index.php?showforum=214"
    ind = "https://probaseballexperience.jcink.net/index.php?showforum=234"
    lun = "https://probaseballexperience.jcink.net/index.php?showforum=160"
    nas = "https://probaseballexperience.jcink.net/index.php?showforum=177"
    teams.append(det)
    teams.append(ind)
    teams.append(lun)
    teams.append(nas)

    # Champions Conference West
    cun = "https://probaseballexperience.jcink.net/index.php?showforum=175"
    dvs = "https://probaseballexperience.jcink.net/index.php?showforum=74"
    nola = "https://probaseballexperience.jcink.net/index.php?showforum=212"
    sea = "https://probaseballexperience.jcink.net/index.php?showforum=253"
    teams.append(cun)
    teams.append(dvs)
    teams.append(nola)
    teams.append(sea)

    # MiLPBE
    # East
    chi = "https://probaseballexperience.jcink.net/index.php?showforum=204"
    fla = "https://probaseballexperience.jcink.net/index.php?showforum=152"
    lou = "https://probaseballexperience.jcink.net/index.php?showforum=245"
    prr = "https://probaseballexperience.jcink.net/index.php?showforum=191"
    scs = "https://probaseballexperience.jcink.net/index.php?showforum=138"
    teams.append(chi)
    teams.append(fla)
    teams.append(lou)
    teams.append(prr)
    teams.append(scs)

    # West
    ama = "https://probaseballexperience.jcink.net/index.php?showforum=155"
    anc = "https://probaseballexperience.jcink.net/index.php?showforum=140"
    bcb = "https://probaseballexperience.jcink.net/index.php?showforum=242"
    cal = "https://probaseballexperience.jcink.net/index.php?showforum=206"
    kck = "https://probaseballexperience.jcink.net/index.php?showforum=188"
    teams.append(ama)
    teams.append(anc)
    teams.append(bcb)
    teams.append(cal)
    teams.append(kck)

    # Unassigned Players
    draftees = "https://probaseballexperience.jcink.net/index.php?showforum=181"
    free_agents = "https://probaseballexperience.jcink.net/index.php?showforum=7"
    retired = "https://probaseballexperience.jcink.net/index.php?showforum=10"
    teams.append(draftees)
    teams.append(free_agents)
    # TODO: make some conditional here, only run it more if there's people who didn't exist before... so basically
    #  check and see if the person was retired before, or maybe the last modified date?
    teams.append(retired)

    for team in teams:
        scrape_roster(team)

    print("finished scraping players!")

    return


def scrape_roster(url):
    print("parsing through team at url: " + url)

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
            if player_pages[p].find("a") is not None \
                    and " - " in player_pages[p].find("a").text:
                if "probaseballexperience.jcink.net/" in player_pages[p].find("a").get("href"):
                    players.append(player_pages[p].find("a").get("href"))

    player_results = []

    for player in players:
        p = scrape_pbe_player(player)
        if p is not None:
            player_results.append(p)

    print("saving players...")
    save_players(player_results)

    return


def scrape_pbe_player(url):
    # TODO: add try catch here so we can finish scraping even if errors...
    # TODO: for info converting to int in first section, default to zero if no empty string
    try:
        # print("\tupdating player at: " + url)
        player = {}

        page_content = requests.get(url).text
        soup = BeautifulSoup(page_content, "html.parser")

        tpe = soup.find("span", attrs={"class": "topic-desc"})

        player_attributes = soup.find("div", attrs={"class": "postcolor"})

        edited = soup.find("span", attrs={"class": "edit"})

        season = soup.find("span", attrs={"class": "topic-title"})

        user_url = soup.find("span", attrs={"class": "normalname"})

        navstrip = soup.find("div", attrs={"id": "navstrip"})

        team = navstrip.findAll("a")[2].text

        league_full = navstrip.findAll("a")[1].text.replace("Clubhouses", "").strip()

        league = ""
        conference = ""
        division = ""

        player.update({'player_forum_url': url})
        player.update({'player_forum_code': url.split("showtopic=")[1]})
        if "Unassigned" not in team:
            player.update({'team': team})
        player.update({'forum_name': user_url.text})

        if "MiLPBE" in league_full:
            player.update({'league': 'MiLPBE'})
            player.update({'conference': league_full.split(" ")[1]})
            player.update({'division': ''})
        elif "Unassigned" in team:
            player.update({'team': navstrip.findAll("a")[3].text.replace("Players", "").strip()})
            player.update({'league': ''})
            player.update({'conference': ''})
            player.update({'division': ''})
        else:
            player.update({'league': 'PBE'})
            player.update({'conference': league_full.split(" ")[0]})
            player.update({'division': league_full.split(" ")[2]})

        if season is not None:
            s = season.text
            if "[GM" in season.text or "(GM" in season.text or "gm bot" in season.text.lower():
                return
            player.update({'season': s[s.find('[') + 1:s.find(']')]})

        if tpe is not None:
            player.update({'tpe': int(tpe.text.replace(", TPE:", "").strip())})

        if user_url is not None:
            player.update({'user_url': user_url.find("a").get("href")})
            player.update({'user_forum_code': player.get('user_url').split("showuser=")[1]})

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
                player.update({'last_updated': final_date.strftime("N/A")})
            else:
                player.update({'last_updated': final_date.strftime("%m/%d/%Y")})
        else:
            player.update({'last_updated': "N/A"})

        # TODO: debug line
        # if player.get('forum_name') == "CoreyMilhouse":
        #     print('STOP!')

        if player_attributes is not None:
            attrs = player_attributes.findAll(text=True)

            counter = 0

            # assign info
            for x in attrs:
                value = ""
                value2 = ""
                if ":" in x:
                    if counter + 1 < len(attrs):
                        value = attrs[counter + 1].strip()
                    else:
                        value = attrs[counter].strip()
                    split_size = len(x.split(":"))
                    value2 = x.split(":")[split_size - 1].strip()

                    # if "Username:" in x:
                    #     player.update({'forum_name': value})

                    if "Player Name:" in x:
                        player.update({'player_name': value})
                        player.update({'normalized_name': get_normalized_name(value)})

                    elif "First Name:" in x:
                        player.update({'player_name': value})

                    elif "Last Name:" in x:
                        name = player.get('player_name') + " " + value
                        player.update({'player_name': name})
                        player.update({'normalized_name': get_normalized_name(name)})

                    elif "Name:" in x and "Username:" not in x:
                        player.update({'player_name': value})
                        player.update({'normalized_name': get_normalized_name(value)})

                    elif "Number:" in x:
                        if value != "" and value.isdigit():
                            player.update({'number': int(value)})
                        else:
                            player.update({'number': 0})

                    elif "Position:" in x:
                        player.update({'position': value})

                    elif "College:" in x:
                        player.update({'college': value})

                    elif "Throws:" in x:
                        player.update({'throws': value})

                    elif "Bats:" in x:
                        player.update({'bats': value})

                    elif "Recruited By:" in x:
                        player.update({'recruited_by': value})

                    elif "Height:" in x:
                        player.update({'height': value})

                    elif "Weight:" in x:
                        player.update({'weight': value})

                    elif "Birthplace:" in x:
                        player.update({'birthplace': value})

                    elif "Player Render:" in x:
                        player.update({'player_render': value})

                    elif "Discord name:" in x:
                        player.update({'discord': value})

                    elif "Hitting:" in x:
                        player.update({'hitting': value})

                    elif "Bank:" in x or "Banked:" in x or "Banked TPE:" in x:
                        if value.isdigit():
                            player.update({'tpe_banked': int(value)})
                        else:
                            player.update({'tpe_banked': int(value2)})

                    elif "Archetype" in x:
                        if "(" in value:
                            player.update({'archetype': value.split("(")[0].strip()})
                        else:
                            player.update({'archetype': value})

                    elif "BABIP vs LHP" in x:
                        player.update({'babip_lhp': int(value2)})

                    elif "BABIP vs RHP" in x:
                        player.update({'babip_rhp': int(value2)})

                    elif "Avoid K's vs LHP" in x:
                        player.update({'ak_lhp': int(value2)})

                    elif "Avoid K's vs RHP" in x:
                        player.update({'ak_rhp': int(value2)})

                    elif "Gap vs LHP" in x:
                        player.update({'gap_lhp': int(value2)})

                    elif "Gap vs RHP" in x:
                        player.update({'gap_rhp': int(value2)})

                    elif "Power vs LHP" in x:
                        player.update({'power_lhp': int(value2)})

                    elif "Power vs RHP" in x:
                        player.update({'power_rhp': int(value2)})

                    elif "Eye/Patience vs LHP" in x:
                        player.update({'ep_lhp': int(value2)})

                    elif "Eye/Patience vs RHP" in x:
                        player.update({'ep_rhp': int(value2)})

                    elif "Speed (Base & Run)" in x:
                        player.update({'speed': int(value2)})

                    elif "Stealing Ability" in x:
                        player.update({'steal': int(value2)})

                    elif "Bunting (Both)" in x:
                        player.update({'bunt': int(value2)})

                    elif "Fielding Range" in x:
                        player.update({'field_range': int(value2)})

                    elif "Fielding Error" in x:
                        player.update({'field_error': int(value2)})

                    elif "Fielding/Catching Arm" in x:
                        player.update({'arm': int(value2)})

                    elif "Double Play" in x:
                        player.update({'double_play': int(value2)})

                    elif "Catcher Abilit:" in x:
                        player.update({'c_ability': int(value2)})

                    elif "1st Position" in x:
                        player.update({'pos_1': value2})

                    elif "2nd Position" in x:
                        player.update({'pos_2': value2})

                    elif "3rd Position" in x:
                        player.update({'pos_3': value2})

                    elif "Velocity" in x:
                        player.update({'velo': value2})

                    elif "Movement vs LHB" in x or "Movement vs. LHB" in x:
                        player.update({'mov_lhb': int(value2)})

                    elif "Movement vs RHB" in x or "Movement vs. RHB" in x:
                        player.update({'mov_rhb': int(value2)})

                    elif "Control vs LHB" in x or "Control vs. LHB" in x:
                        player.update({'con_lhb': int(value2)})

                    elif "Control vs RHB" in x or "Control vs. RHB" in x:
                        player.update({'con_rhb': int(value2)})

                    elif "Stamina" in x:
                        player.update({'stamina': int(value2)})

                    elif "Holding Runners" in x:
                        player.update({'hold_runners': int(value2)})

                    elif "GB%" in x:
                        player.update({'gb_pct': int(value2)})

                    elif "Fastball:" in x:
                        player.update({'fastball': int(value2)})

                    elif "Sinker:" in x:
                        player.update({'sinker': int(value2)})

                    elif "Cutter:" in x:
                        player.update({'cutter': int(value2)})

                    elif "Curveball:" in x:
                        player.update({'curveball': int(value2)})

                    elif "Slider:" in x:
                        player.update({'slider': int(value2)})

                    elif "Changeup:" in x:
                        player.update({'changeup': int(value2)})

                    elif "Splitter:" in x:
                        player.update({'splitter': int(value2)})

                    elif "Forkball:" in x:
                        player.update({'forkball': int(value2)})

                    elif "Circle Change:" in x:
                        player.update({'circle_change': int(value2)})

                    elif "Screwball:" in x:
                        player.update({'screwball': int(value2)})

                    elif "Knuckle Curve:" in x:
                        player.update({'knuckle_curve': int(value2)})

                    elif "Knuckleball:" in x:
                        player.update({'knuckleball': int(value2)})

                counter = counter + 1

        return player
    except Exception as e:
        print("Error occurred scraping player at url: " + url)
        print(str(e))
        return None


def save_players(players):
    for player in players:
        try:
            exists = False
            doc_id = ""
            cursor = pbe_player_collection.find({"player_forum_code": player.get('player_forum_code'),
                                                 "user_forum_code": player.get('user_forum_code')})
            for document in cursor:
                exists = True
                doc_id = document.get('_id')
                break

            if exists:
                try:
                    pbe_player_collection.find_one_and_update({"_id": ObjectId(doc_id)}, {"$set": player})
                    # print("Updated user: " + player.get('forum_name') + ", " + player.get('player_name'))
                except Exception as e:
                    print("Error occurred updating player into the database: " + str(e))
                    print("Player: " + str(player))
            else:
                try:
                    pbe_player_collection.insert_one(player)
                    # print("Inserted user: " + player.get('forum_name') + ", " + player.get('player_name'))
                except Exception as e:
                    print("Error occurred inserting player into the database: " + str(e))
                    print("Player: " + str(player))

        except Exception as e:
            print("Error occurred retrieving players from the database: " + str(e))

    return


def scrape_bank():
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
        if row[0] != "Team Name":
            try:
                account = {}
                account.update({'username': row[1]})
                account.update({'player_name': row[2]})
                account.update({'balance': row[4]})
                save_bank_account(account)
            except Exception as ex:
                print("Error when scraping the bank...: ", ex)

    return


def save_bank_account(account):
    try:
        exists = False
        doc_id = ""
        cursor = pbe_bank_collection.find({"username": account.get('username')})
        for document in cursor:
            exists = True
            doc_id = document.get('_id')
            break

        if exists:
            try:
                pbe_bank_collection.find_one_and_update({"_id": ObjectId(doc_id)}, {"$set": account})
            except Exception as e:
                print("Error occurred updating bank account into the database: " + str(e))
        else:
            try:
                pbe_bank_collection.insert_one(account)
            except Exception as e:
                print("Error occurred updating bank account into the database: " + str(e))

    except Exception as e:
        print("Error occurred updating bank account into the database: " + str(e))

    return


def get_wsbl_tasks():
    return
    # activity check (only get the top one)
    # ac = "https://worldsimbasketball.jcink.net/index.php?showforum=5"
    #
    # # point tasks (get all forum topics except intro PT for PBE)
    # pt = "https://worldsimbasketball.jcink.net/index.php?showforum=7"
    #
    # get_tasks("wsbl", ac, pt)
    # return


# TODO: scrape WSBL players
def get_wsbl_players():
    return
    # teams = {}
    #
    # # Free Agents
    # url_free_agents = "https://worldsimbasketball.jcink.net/index.php?showforum=28"
    # teams.__setitem__(url_free_agents, "Free Agents")
    #
    # # Retired Players
    # url_retired_players = "https://worldsimbasketball.jcink.net/index.php?showforum=29"
    # teams.__setitem__(url_retired_players, "Retired")
    #
    # # Draftees
    # url_draftees_pg = "https://worldsimbasketball.jcink.net/index.php?showforum=96"
    # url_draftees_sg = "https://worldsimbasketball.jcink.net/index.php?showforum=97"
    # url_draftees_sf = "https://worldsimbasketball.jcink.net/index.php?showforum=98"
    # url_draftees_pf = "https://worldsimbasketball.jcink.net/index.php?showforum=99"
    # url_draftees_c = "https://worldsimbasketball.jcink.net/index.php?showforum=100"
    # teams.__setitem__(url_draftees_pg, "Draftees")
    # teams.__setitem__(url_draftees_sg, "Draftees")
    # teams.__setitem__(url_draftees_sf, "Draftees")
    # teams.__setitem__(url_draftees_pf, "Draftees")
    # teams.__setitem__(url_draftees_c, "Draftees")
    #
    # # Waivers
    # url_waviers = "https://worldsimbasketball.jcink.net/index.php?showforum=107"
    # teams.__setitem__(url_waviers, "Waivers")
    #
    # # Detroit Generals
    # url_detroit = "https://worldsimbasketball.jcink.net/index.php?showforum=18"
    # teams.__setitem__(url_detroit, "Detroit Generals")
    #
    # # Indiana Haymakers
    # url_indiana = "https://worldsimbasketball.jcink.net/index.php?showforum=36"
    # teams.__setitem__(url_indiana, "Indiana Haymakers")
    #
    # # Lake Superior
    # url_lake_superior = "https://worldsimbasketball.jcink.net/index.php?showforum=90"
    # teams.__setitem__(url_lake_superior, "Lake Superior Raiders")
    #
    # # Mud City
    # url_mud_city = "https://worldsimbasketball.jcink.net/index.php?showforum=67"
    # teams.__setitem__(url_mud_city, "Mud City Wolves")
    #
    # # New Jersey
    # url_new_jersey = "https://worldsimbasketball.jcink.net/index.php?showforum=37"
    # teams.__setitem__(url_new_jersey, "New Jersey Blackjacks")
    #
    # # New York
    # url_new_york = "https://worldsimbasketball.jcink.net/index.php?showforum=38"
    # teams.__setitem__(url_new_york, "New York Imperials")
    #
    # # Seattle
    # url_seattle = "https://worldsimbasketball.jcink.net/index.php?showforum=69"
    # teams.__setitem__(url_seattle, "Seattle Orcas")
    #
    # # Vancouver
    # url_vancouver = "https://worldsimbasketball.jcink.net/index.php?showforum=66"
    # teams.__setitem__(url_vancouver, "Vancouver Venom")
    #
    # # Austin
    # url_austin = "https://worldsimbasketball.jcink.net/index.php?showforum=51"
    # teams.__setitem__(url_austin, "Austin Vaqueros")
    #
    # # Carolina
    # url_carolina = "https://worldsimbasketball.jcink.net/index.php?showforum=15"
    # teams.__setitem__(url_carolina, "Carolina Reapers")
    #
    # # Mexico City
    # url_mexico_city = "https://worldsimbasketball.jcink.net/index.php?showforum=68"
    # teams.__setitem__(url_mexico_city, "Mexico City Quetzals")
    #
    # # Panama
    # url_panama = "https://worldsimbasketball.jcink.net/index.php?showforum=89"
    # teams.__setitem__(url_panama, "Panama Anteaters")
    #
    # # Puerto Rico
    # url_puerto_rico = "https://worldsimbasketball.jcink.net/index.php?showforum=88"
    # teams.__setitem__(url_puerto_rico, "Puerto Rico Passion")
    #
    # # Singapore
    # url_singapore = "https://worldsimbasketball.jcink.net/index.php?showforum=91"
    # teams.__setitem__(url_singapore, "Singapore Sun Bears")
    #
    # # South Beach
    # url_south_beach = "https://worldsimbasketball.jcink.net/index.php?showforum=39"
    # teams.__setitem__(url_south_beach, "South Beach Sting")
    #
    # # Vegas
    # url_vegas = "https://worldsimbasketball.jcink.net/index.php?showforum=53"
    # teams.__setitem__(url_vegas, "Vegas Volts")
    #
    # # Philadelphia
    # url_philadelphia = "https://worldsimbasketball.jcink.net/index.php?showforum=131"
    # teams.__setitem__(url_philadelphia, "Philadelphia Lightning")
    #
    # # Edinburgh
    # url_edinburgh = "https://worldsimbasketball.jcink.net/index.php?showforum=125"
    # teams.__setitem__(url_edinburgh, "Edinburgh Golden Unicorns")
    #
    # # Music City (Formerly Frankfurt Falkens 2001-2022)
    # url_music_city = "https://worldsimbasketball.jcink.net/index.php?showforum=122"
    # teams.__setitem__(url_music_city, "Music City Mountaineers")
    #
    # # Madrid
    # url_madrid = "https://worldsimbasketball.jcink.net/index.php?showforum=128"
    # teams.__setitem__(url_madrid, "Madrid Matadors")
    #
    # # Columbus Cosmos (Formerly Ontario Legends 2001-2022)
    # url_columbus = "https://worldsimbasketball.jcink.net/index.php?showforum=119"
    # teams.__setitem__(url_columbus, "Columbus Cosmos")
    #
    # # San Diego
    # url_san_diego = "https://worldsimbasketball.jcink.net/index.php?showforum=116"
    # teams.__setitem__(url_san_diego, "San Diego Admirals")
    #
    # url_list = teams.keys()
    #
    # players = []
    #
    # for url in url_list:
    #     temp_players = parse_player_list(url, teams.get(url))
    #
    #     for t in temp_players:
    #         players.append(t)
    #
    # post_to_db(players)
    #
    # return


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


class Player:
    url: ""
    user_url: ""
    last_updated: ""
    forum_name: ""
    index_name: ""
    standard_name: ""
    discord: ""
    season: ""
    first_name: ""
    last_name: ""
    name: ""
    position: ""
    college: ""
    age: 0
    handedness: ""
    recruited_by: ""
    jersey_num: 0
    height: ""
    weight: 0
    birthplace: ""
    arch: ""

    team: ""
    last_updated: ""
    tpe_total: 0
    tpe_banked: 0

    fg_ra: 0
    fg_ip: 0
    fg_mr: 0
    fg_cor: 0
    fg_ab: 0
    ft: 0
    scoring: 0
    passing: 0
    handling: 0
    off_reb: 0
    def_reb: 0
    blocking: 0
    stealing: 0
    defender: 0
    iq: 0

    ps_pass: 0
    ps_dap: 0
    ps_das: 0
    ps_pu: 0
    ps_puj: 0
    ps_cas: 0

    fr_post: 0
    fr_mr: 0
    fr_cor: 0
    fr_atb: 0


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
    finalized_name = ""
    for s in name:
        if s.isalnum() or s == ' ':
            finalized_name = finalized_name + s

    return unidecode(finalized_name)


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
