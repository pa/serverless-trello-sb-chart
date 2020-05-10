#!/usr/bin/env python
from __future__ import print_function
import os
import re
import json
import boto3
import requests
import datetime
import pytz
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from trello import TrelloClient
from trello import Organization
from trello import Board
from trello import List
from difflib import SequenceMatcher
from botocore.exceptions import ClientError


# Get the SSM Parameter Keys
try:
    TRELLO_API_KEY_SSM_PARAMETER_KEY = os.getenv('TRELLO_API_KEY_SSM_PARAMETER_KEY')
except Exception:
    TRELLO_API_KEY_SSM_PARAMETER_KEY = '/Serverless/Trello/ApiKey'

try:
    TRELLO_TOKEN_SSM_PARAMETER_KEY = os.getenv('TRELLO_TOKEN_SSM_PARAMETER_KEY')
except Exception:
    TRELLO_TOKEN_SSM_PARAMETER_KEY = '/Serverless/Trello/Token'

try:
    TRELLO_ORGANIZATION_ID = os.getenv('TRELLO_ORGANIZATION_ID')
except Exception:
    print('Trello Organization ID missing in Lambda Environment Variable')

try:
    BAMBOOHR_API_TOKEN_SSM_PARAMETER_KEY = os.getenv('BAMBOOHR_API_TOKEN_SSM_PARAMETER_KEY')
except Exception:
    BAMBOOHR_API_TOKEN_SSM_PARAMETER_KEY = '/Serverless/BambooHR/ApiToken'

try:
    BAMBOOHR_ORG_NAME = os.getenv('BAMBOOHR_ORG_NAME')
except Exception:
    print('BambooHR Organization Name value missing in Lambda Environment Variable')

try:
    CALLBACK_URL = os.getenv('CALLBACK_URL')
except Exception:
    print('CALLBACK_URL value missing in Lambda Environment Variable')

try:
    POWERUP_NAME = os.getenv('POWERUP_NAME')
except Exception:
    print('Power-Up Name value missing in Lambda Environment Variable')

try:
    DEPLOYMENT_BUCKET = os.getenv('DEPLOYMENT_BUCKET')
except Exception:
    print('Deployment Bucket Name value missing in Lambda Environment Variable')

sprint_data_file_name = 'sprint_data.json'
chart_attachment_data_file_name = 'chart_attachment_data.json'

# Boto3 SSM module
ssm = boto3.client('ssm')

# Get ssm parameter values
TRELLO_API_KEY = format(
    ssm.get_parameter(
        Name=TRELLO_API_KEY_SSM_PARAMETER_KEY,
        WithDecryption=True
        )['Parameter']['Value']
    )

TRELLO_TOKEN = format(
    ssm.get_parameter(
        Name=TRELLO_TOKEN_SSM_PARAMETER_KEY,
        WithDecryption=True
        )['Parameter']['Value']
    )

BAMBOOHR_API_TOKEN = format(
    ssm.get_parameter(
        Name=BAMBOOHR_API_TOKEN_SSM_PARAMETER_KEY,
        WithDecryption=True
        )['Parameter']['Value']
    )

# Setting Time Zone to CST
cst_timezone = pytz.timezone('US/Central')

# Get all Plugins/PowerUps from Board
def get_plugins(client, board_id):
    """
    Gets Plugin/PowerUp data from the board
    :param client: Trello client Object
    :param board_id: The ID of the Board
    :return: returns Plugin/PowerUp Value
    """
    return client.fetch_json(
        f"boards/{board_id}/pluginData",
        http_method="GET",
        headers = {
                "Accept": "application/json"
        },
        query_params={
            'name': POWERUP_NAME
        }
    )


# Get all Enabled PowerUps from the Board
def enabled_powerups(client, board_id):
    """
    Gets Enabled Plugin/PowerUp from the board
    :param client: Trello client Object
    :param board_id: The ID of the Board
    :return: returns Enabled Plugin/PowerUp Data
    """
    return client.fetch_json(
        f"boards/{board_id}/boardPlugins",
        http_method="GET",
        headers = {
                "Accept": "application/json"
            }
    )


# Get PowerUp Data that is required for monitoring the Board
def get_powerup_data(client, board_id):
    """
    Get PowerUp Data from the board
    :param client: Trello client Object
    :param board_id: The ID of the Board
    :return: returns PowerUp Data for monitoring boards
    """
    # Get Enabled PowerUps in the Board
    enabled_powerups_list = []
    enabled_powerups_data = enabled_powerups(client, board_id)
    [enabled_powerups_list.append(enabled_powerup['idPlugin']) for enabled_powerup in enabled_powerups_data]

    # Check if our PowerUp Enabled or Not
    plugins_data = get_plugins(client, board_id)
    for plugin_data in plugins_data:
        if plugin_data['idPlugin'] in enabled_powerups_list:
            return plugin_data['value']


# Create Webhook for Existing Organization Boards
def create_existing_boards_hook(client, existing_webhooks):
    """
    Create Webhooks for Organization Boards
    :param client: Trello client Object
    :param existing_webhooks: Already existing webhooks for the TRELLO_TOKEN
    :return: returns status of the Webhook Creation
    """
    boards = Organization(client, TRELLO_ORGANIZATION_ID).all_boards()
    is_create_board_webhook = False
    for board in boards:
        for webhook in existing_webhooks:
            # Check is webhook created for Organization ID
            if webhook.callback_url == CALLBACK_URL and webhook.id_model == board.id:
                is_create_board_webhook = False
                break
            else:
                is_create_board_webhook = True
        try:
            if bool(is_create_board_webhook):
                client.create_hook(CALLBACK_URL, board.id, f'{board.name} Trello Board Webhook', TRELLO_TOKEN)
        except Exception as e:
            print(f' {e}: Error creating webhook for the Trello Board - {board.name}')
            continue
    return 'Created webhooks for already existing boards'


# Create Webhook for New Organization Boards
def create_new_board_hook(client, payload, existing_webhooks):
    """
    Create Webhooks for Organization Boards
    :param client: Trello client Object
    :param payload: Trello Webhook Payload from API Gateway
    :param existing_webhooks: Already existing webhooks for the TRELLO_TOKEN
    :return: returns status of the Webhook Creation
    """
    is_create_board_webhook = False
    try:
        for webhook in existing_webhooks:
            # Check is webhook created for Organization ID
            if webhook.callback_url == CALLBACK_URL and webhook.id_model == payload['action']['data']['board']['id']:
                is_create_board_webhook = False
                break
            else:
                is_create_board_webhook = True
        if bool(is_create_board_webhook):
            if payload['action']['type'] == "addToOrganizationBoard":
                return client.create_hook(CALLBACK_URL, payload['action']['data']['board']['id'], f"{payload['action']['data']['board']['name']} Trello Board Webhook", TRELLO_TOKEN)
    except Exception as e:
        print(f"{e}: Error creating webhook for the Trello Board ID - {payload['action']['data']['board']['name']}")


# Get Stories and Tasks Counts
def get_counts(client, payload, monitor_lists, start_day):
    """
    Get List data
    :param client: Trello client Object
    :param payload: Trello Webhook Payload from API Gateway
    :param monitor_lists: Trello monitor lists from PowerUp Data
    :return: returns count of User Stories/Defects remaining and completed
    """
    current_date = datetime.datetime.now(cst_timezone)
    stories_defects_remaining = 0
    stories_defects_done = 0
    tasks_remaining = 0
    ideal_tasks_remaining = 0

    board_object = Board(client, board_id=payload['action']['data']['board']['id'])
    board_lists = board_object.all_lists()

    for monitor_list in monitor_lists:
        for board_list in board_lists:
            cards_list = List(board_object, board_list.id).list_cards()
            # Get count of Tasks and Userstory/Defect Remaining
            if board_list.id == monitor_list:
                for card in cards_list:
                    if card.name[:2] in 'T ':
                        tasks_remaining += 1
                        print("Tasks " + card.name)
                    elif card.name[:2] in ('U ', 'D '):
                        stories_defects_remaining += 1
                        print("Userstory/Defect " + card.name)
                break

    if current_date.strftime("%A") == start_day:
        ideal_tasks_remaining = tasks_remaining

    for board_list in board_lists:
        # Get count of Userstories/Defects Done
        if (board_list.name)[-4:] == "Done":
            cards_list = List(board_object, board_list.id).list_cards()
            for card in cards_list:
                if card.name[:2] in ('U ', 'D '):
                    stories_defects_done += 1
                    print("Done List - Userstory/Defect " + card.name)
                if current_date.strftime("%A") == start_day:
                    if card.name[:2] in 'T ':
                        ideal_tasks_remaining += 1
            break

    return stories_defects_remaining, stories_defects_done, tasks_remaining, ideal_tasks_remaining


# Get Sprint Dates
def get_sprint_dates(start_day, total_sprint_days, board_id):
    """
    Gets Sprint dates based on the Start day and Total Sprint days
    :param start_day: Start day of the Sprint. Eg: Monday
    :param total_sprint_days: Total days of a Sprint. Value starts from 0. So if Sprint has 5 days then total_sprint_days=4
    :param board_id: The ID of the Board
    :return: returns list of Sprint dates
    """
    sprint_dates = []
    start_date = datetime.datetime.now(cst_timezone)
    if start_date.strftime("%A") == start_day:
        sprint_dates.append(start_date.strftime("%Y-%m-%d"))
        business_days_to_add = total_sprint_days
        current_date = start_date
        while business_days_to_add > 0:
            current_date += datetime.timedelta(days=1)
            weekday = current_date.weekday()
            if weekday >= 5: # sunday = 6
                continue
            business_days_to_add -= 1
            sprint_dates.append(current_date.strftime("%Y-%m-%d"))
    else:
        for key, value in json.load(open('/tmp/' + sprint_data_file_name, 'r'))[board_id].items():
            if key != 'ideal_tasks_remaining':
                try:
                    sprint_dates.append(key)
                except Exception as error:
                    print(error)
                    continue

    return sprint_dates


# Create/Update Sprint Data
def update_sprint_data(start_day, board_id, sprint_dates, stories_defects_remaining, stories_defects_done, tasks_remaining, ideal_tasks_remaining, team_size, team_members_ooo_count):
    """
    Create/Update Sprint Data to Json file
    :param start_day: Start day of the Sprint. Eg: Monday
    :param board_id: The ID of the Board
    :param sprint_dates: List of current sprint dates
    :param stories_defects_remaining: Userstories or Defects remaining count
    :param stories_defects_done: Userstories or Defects done count
    :param tasks_remaining: Tasks remaining count
    :param ideal_tasks_remaining: Ideal tasks remaining count
    :return: returns Sprint Json Data
    """
    sprint_data = {}
    current_day = datetime.datetime.now(cst_timezone).strftime("%A")
    current_date = datetime.datetime.now(cst_timezone).strftime("%Y-%m-%d")
    # Create Sprint data json file
    if os.path.isfile('/tmp/' + sprint_data_file_name):
        sprint_data = json.load(open('/tmp/' + sprint_data_file_name, 'r'))
    else:
        with open('/tmp/' + sprint_data_file_name, "w") as sprint_data_file:
            json.dump({}, sprint_data_file)
        sprint_data_file.close()

    # Update Sprint Data in json file
    if current_day == start_day:
        sprint_data.update({ board_id: {} })
        for sprint_date in sprint_dates:
            sprint_data[board_id].update( { 'ideal_tasks_remaining': 0, sprint_date: { 'stories_defects_remaining': 0, 'stories_defects_done': 0, 'team_members_ooo_count': 0 } } )
        sprint_data[board_id].update( {
                'ideal_tasks_remaining': ideal_tasks_remaining,
                current_date: {
                'stories_defects_remaining': stories_defects_remaining,
                'stories_defects_done': stories_defects_done,
                'tasks_remaining': tasks_remaining,
                'team_members_ooo_count': team_members_ooo_count,
                'team_size': team_size
                }
            }
        )
    else:
        sprint_data[board_id].update( {
                current_date: {
                'stories_defects_remaining': stories_defects_remaining,
                'stories_defects_done': stories_defects_done,
                'tasks_remaining': tasks_remaining,
                'team_members_ooo_count': team_members_ooo_count,
                'team_size': team_size
                }
            }
        )
    with open('/tmp/' + sprint_data_file_name, "w") as sprint_data_file:
        json.dump(sprint_data, sprint_data_file)
    sprint_data_file.close()

    return sprint_data


# Get Organization members Out Of Office
def get_org_members_ooo(api_token, org_name, start_date, end_date):
    """
    Gets Organization Memnber Out Of Office
    :param api_token: API Token for connecting BambooHR. To generate an API key, users should log in and click their name in the upper right-hand corner of any page to get to the user context menu
    :param org_name: BambooHR Organization Name
    :param start_date: A start date in the form YYYY-MM-DD
    :param end_date: A end date in the form YYYY-MM-DD
    :return: returns List of Organization Members OOO and Count
    """
    url = 'https://{0}:x@api.bamboohr.com/api/gateway.php/{1}/v1/time_off/whos_out/'.format(api_token, org_name)

    querystring = {
        "start": start_date,
        "end": end_date
        }

    headers = {
        'accept': "application/json"
        }

    response = requests.request("GET", url, headers=headers, params=querystring)
    org_members = response.json()
    org_members_ooo_array = []
    for org_member in org_members:
        if org_member['type'] == 'timeOff':
            org_members_ooo_array.append(org_member['name'])
        elif org_member['type'] == 'holiday':
            continue
    org_members_ooo = list(dict.fromkeys(org_members_ooo_array))

    return org_members_ooo


# Create Sprint Burndown Chart
def create_chart(sprint_data, total_sprint_days, board_id):
    """
    Creates Sprint Burndown Chart
    :param sprint_data: The Sprint Data
    :param board_id: The ID of the Board
    :return: returns nothing
    """
    sprint_dates_list = [""]
    stories_defects_remaining_list = [0]
    stories_defects_done_list = [0]
    tasks_remaining_list = []
    members_ooo_count_list = [0]
    team_size_list = [0]

    ideal_tasks_remaining = sprint_data[board_id]['ideal_tasks_remaining']

    tasks_remaining_list.append(ideal_tasks_remaining)

    for key, value in sprint_data[board_id].items():
        if key != 'ideal_tasks_remaining':
            try:
                sprint_dates_list.append(key)
                stories_defects_remaining_list.append(value['stories_defects_remaining'])
                stories_defects_done_list.append(value['stories_defects_done'])
                members_ooo_count_list.append(value['team_members_ooo_count'])
                tasks_remaining_list.append(value['tasks_remaining'])
                team_size_list.append(value['team_size'])
            except Exception as error:
                print(error)
                continue

    team_size_list[0] = team_size_list[1]

    f, ax = plt.subplots()

    x_axis = [item for item in range(0, total_sprint_days + 1)]
    x_axis_label = sprint_dates_list

    y_axis_labels = [0]
    ideal_line_list = [0]
    ax.axhline(y=0,color='#d0e2f6',linewidth=.5, zorder=0)
    for index in range(0, total_sprint_days):
        y_axis_label = y_axis_labels[index] + round(max(tasks_remaining_list)/total_sprint_days)
        ideal_line = ideal_line_list[index] + (ideal_tasks_remaining/total_sprint_days)
        y_axis_labels.append(y_axis_label)
        ideal_line_list.append(ideal_line)
        ax.axhline(y=y_axis_labels[index],color='#d0e2f6',linewidth=.5, zorder=0)

    ax.set_xticks(x_axis)
    ax.set_xticklabels(x_axis_label,rotation=40,ha='right')
    ax.set_yticks(y_axis_labels)
    ax.set_yticklabels(y_axis_labels)


    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)

    plt.tick_params(
        axis='both',       # changes apply to the x-axis
        which='both',      # both major and minor ticks are affected
        bottom=False,      # ticks along the bottom edge are off
        left=False,        # ticks along the top edge are off
        labelbottom=True,
        labelsize=6,
        pad=4
    )


    plt.fill_between(np.arange(len(team_size_list)), 0, team_size_list, color='#ff9f68', alpha=0.5, lw=0)

    p6, = plt.plot(np.arange(len(team_size_list)),team_size_list,'k--',color='#ff9f68', label='line 1',zorder=1)
    p3 = plt.bar(np.arange(len(stories_defects_remaining_list)), stories_defects_remaining_list, color='#c5e3f6',width=.25,align='edge',zorder=2)
    p4 = plt.bar(np.arange(len(stories_defects_done_list)), stories_defects_done_list, color='#17b978',width=-.25,align='edge', zorder=2)
    p5 = plt.bar(np.arange(len(members_ooo_count_list)) -.5, members_ooo_count_list, color='#ffcef3',width=.25,align='edge', zorder=2)
    p1, = plt.plot(x_axis,[element for element in reversed(ideal_line_list)],'k',label='line 3',linewidth=.7, zorder=4)
    p2, = plt.plot(np.arange(len(tasks_remaining_list)),tasks_remaining_list,'--',color='#482ff7', label='line 1', zorder=5)

    def autolabel(rects):
        """Attach a text label above each bar in *rects*, displaying its height."""
        for rect in rects:
            height = rect.get_height()
            if height != 0:
                ax.annotate('{}'.format(height),
                            xy=(rect.get_x() + rect.get_width() / 2, height /2),
                            xytext=(0, -3),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom', size=6)

    autolabel(p3)
    autolabel(p4)
    autolabel(p5)

    for index in range(0, len(tasks_remaining_list)):
        plt.annotate(xy=[index, tasks_remaining_list[index]], s=str(tasks_remaining_list[index]), color='#482ff7', size=6, ha='center', va='bottom', textcoords="offset points", xytext=(2, 3))

    for index in range(0, len(team_size_list)):
        plt.annotate(xy=[index, team_size_list[index]], s=str(team_size_list[index]), color='#ff9f68', size=6, ha='center', va='bottom', textcoords="offset points", xytext=(2, 3))

    plt.title("Sprint Burndown Chart")

    plt.legend([p1,p2,p3, p4, p5, p6], ["Ideal Tasks Remaining","Tasks Remaining","Stories/Defects Remaining", "Stories/Defects Done", "Team Members OOO","Team Size"], loc=1, borderaxespad=0,fontsize=6).get_frame().set_alpha(0.5)

    plt.savefig('/tmp/' + datetime.datetime.now(cst_timezone).strftime("%Y-%m-%d") + '_Sprint_Burndown_Chart_' + board_id, dpi=150)


# Delete previously attached Chart from the card
def delete_chart(client, card_id, board_id):
    """
    Deletes already existing Sprint Burndown chart
    :param client: Trello client Object
    :param card_id: The ID of the Card
    :param board_id: The ID of the Board
    :return: returns None
    """
    if os.path.isfile('/tmp/chart_attachment_data.json'):
        try:
            chart_attachment_data = json.load(open('/tmp/chart_attachment_data.json', 'r'))
            current_date = datetime.datetime.now(cst_timezone).strftime("%Y-%m-%d")
            attachment_id_list = chart_attachment_data[board_id][current_date]['previous_attachment_id']

            print(attachment_id_list)
            for attachment_id in attachment_id_list:
                response = client.fetch_json(
                    f"cards/{card_id}/attachments/{attachment_id}",
                    http_method="DELETE",
                    headers = {
                            "Accept": "application/json"
                    }
                )
                print(response)
            attachment_id_list.clear()
        except Exception as error:
            print(error)
            pass
    else:
        print('Previously attached chart data file not found')


# Attach Chart to the Card
def attach_chart(client, start_day, card_id, board_id):
    """
    Attaches Sprint Burndown chart to a card
    :param client: Trello client Object
    :param start_day: Start day of the Sprint. Eg: Monday
    :param card_id: The ID of the Card
    :param board_id: The ID of the Board
    :return: returns None
    """
    chart_attachment_data = {}
    attachment_id_list = []
    current_day = datetime.datetime.now(cst_timezone).strftime("%A")
    current_date = datetime.datetime.now(cst_timezone).strftime("%Y-%m-%d")
    image_path = '/tmp/' + current_date + '_Sprint_Burndown_Chart_' + board_id + '.png'
    try:
        attachment_response = client.fetch_json(
            f"cards/{card_id}/attachments",
            http_method="POST",
            files = {
                'file': (current_date + '_Sprint_Burndown_Chart.png', open(image_path, 'rb')),
            },
            headers = {
                    "Accept": "application/json"
            }
        )

        print(attachment_response['id'])

        if os.path.isfile('/tmp/chart_attachment_data.json'):
            chart_attachment_data = json.load(open('/tmp/chart_attachment_data.json', 'r'))
            attachment_id_list.extend(chart_attachment_data[board_id][current_date]['previous_attachment_id'])
        else:
            with open('/tmp/chart_attachment_data.json', "w") as chart_attachment_data_file:
                json.dump({}, chart_attachment_data_file)
            chart_attachment_data_file.close()

        # Update Chart Attachment Data in json file
        if current_day == start_day:
            chart_attachment_data.update({ board_id: {} })
            chart_attachment_data[board_id].update(
                {
                    current_date: {
                        'previous_attachment_id': attachment_id_list.append(attachment_response['id'])
                    }
                }
            )
        else:
            chart_attachment_data[board_id].update(
                {
                    current_date: {
                        'previous_attachment_id': attachment_id_list.append(attachment_response['id'])
                    }
                }
            )
        with open('/tmp/chart_attachment_data.json', "w") as chart_attachment_data_file:
            json.dump(chart_attachment_data, chart_attachment_data_file)
        chart_attachment_data_file.close()
    except Exception as e:
        print(e)
        pass


# Success Status Method
def success():
    """
    Success Status Method
    :return: returns Success Status Code
    """
    return {"statusCode": 200}


def trelloSprintBurndown(event, context):
    """
    Extracts Trello Webhook Payload information and automates Trello
    :param event: Event data from API Gateway contains Trello Webhook Payload
    :param context: This object provides methods and properties that provide information about the invocation, function and execution environment
    :return: returns nothing
    """
    # Connect to Trello
    client = TrelloClient(
            api_key=TRELLO_API_KEY,
            token=TRELLO_TOKEN
    )

    print(type(event))
    print(event)

    existing_webhooks = client.list_hooks(TRELLO_TOKEN)

    # S3 Client
    s3 = boto3.resource('s3')

    if event:
        if datetime.datetime.now(cst_timezone).strftime("%A") not in ('Saturday', 'Sunday'):
            payload = json.loads(event['payload'])

            board_id = payload['action']['data']['board']['id']

            # Create Webhook for new board
            if payload['action']['type'] == 'addToOrganizationBoard':
                print(create_new_board_hook(client, payload, existing_webhooks))

            if payload['action']['type'] in ('updateCard', 'createCard'):
                # Download Sprint data and Card Attachment data files from S3
                try:
                    s3.Bucket(DEPLOYMENT_BUCKET).download_file(sprint_data_file_name, '/tmp/' + sprint_data_file_name)
                    s3.Bucket(DEPLOYMENT_BUCKET).download_file(chart_attachment_data_file_name, '/tmp/' + chart_attachment_data_file_name)
                except Exception as e:
                    print(e)
                    pass

                # Get PowerUp Data
                powerup_data = get_powerup_data(client, board_id)

                # Check PowerUp Data exists
                if powerup_data is not None:
                    print(json.loads(powerup_data))

                    sprint_start_day = json.loads(powerup_data)['sprint_start_day']
                    total_sprint_days = json.loads(powerup_data)['total_sprint_days']

                    # Get monitor lists
                    monitor_lists = json.loads(powerup_data)['selected_list']

                    # Get counts of Stories/Tasks
                    stories_defects_remaining, stories_defects_done, tasks_remaining, ideal_tasks_remaining = get_counts(client, payload, monitor_lists, sprint_start_day)

                    print(f'Stories Remaining: {stories_defects_remaining}')
                    print(f'Stories Done: {stories_defects_done}')
                    print(f'Tasks Remaining: {tasks_remaining}')
                    print(f'Ideal Tasks Remaining: {ideal_tasks_remaining}')
                    print(board_id)

                    # CST Current Time
                    print(datetime.datetime.now(cst_timezone))

                    # CST Day and Date
                    print(datetime.datetime.now(cst_timezone).strftime("%A"))
                    print(datetime.datetime.now(cst_timezone).strftime("%Y-%m-%d"))

                    # Current Sprint Dates
                    sprint_dates = get_sprint_dates(sprint_start_day, (total_sprint_days - 1), board_id)

                    print(sprint_dates)

                    print(f'Start Date: {sprint_dates[0]} End Date: {sprint_dates[len(sprint_dates)-1]}')

                    # Get Organization members Out of Office
                    org_members_ooo = get_org_members_ooo(BAMBOOHR_API_TOKEN, BAMBOOHR_ORG_NAME, sprint_dates[0], sprint_dates[len(sprint_dates)-1])

                    team_members = json.loads(powerup_data)['team_member_list']
                    team_size = len(team_members)

                    # Get Team members Out of Office
                    team_members_ooo = []
                    for team_member in team_members:
                        for org_member_ooo in org_members_ooo:
                            member_sequence = SequenceMatcher(a=team_member, b=org_member_ooo)
                            print(f'Team Member Compare ratio: {member_sequence.ratio()}')
                            if member_sequence.ratio() >= 0.3:
                                print(member_sequence.ratio())
                                team_members_ooo.append(team_member)

                    # Update sprint data
                    sprint_data = update_sprint_data(sprint_start_day, board_id, sprint_dates, stories_defects_remaining, stories_defects_done, tasks_remaining, ideal_tasks_remaining, team_size, len(team_members_ooo))

                    print(sprint_data)

                    # Create Sprint Burndown Chart
                    create_chart(sprint_data, total_sprint_days, board_id)

                    attachment_card_id = json.loads(powerup_data)['selected_card_for_attachment']

                    # Delete previously attached Chart from the card
                    delete_chart(client, attachment_card_id, board_id)

                    # Attach Chart to Card
                    attach_chart(client, sprint_start_day, attachment_card_id, board_id)

                    # Upload Sprint data and Card Attachment data files from S3
                    try:
                        s3.Object(DEPLOYMENT_BUCKET, sprint_data_file_name).put(Body=open('/tmp/' + sprint_data_file_name, 'rb'))
                        s3.Object(DEPLOYMENT_BUCKET, chart_attachment_data_file_name).put(Body=open('/tmp/' + chart_attachment_data_file_name, 'rb'))
                    except Exception as e:
                        print(e)
                        pass

                    print(json.load(open('/tmp/sprint_data.json', 'r')))

                    print(json.load(open('/tmp/chart_attachment_data.json', 'r')))
    else:
        # Create Webhook for Trello Organization
        print(client.create_hook(CALLBACK_URL, TRELLO_ORGANIZATION_ID, "Trello Organiztion Webhook", TRELLO_TOKEN))

        # Create Webhook for Exisiting Boards
        print(create_existing_boards_hook(client, existing_webhooks))