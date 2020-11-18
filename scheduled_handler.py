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

# Setting Time Zone to CST
cst_timezone = pytz.timezone('US/Central')

# Setting Current Date and Day
current_day = datetime.datetime.now(cst_timezone).strftime("%A")
current_date = datetime.datetime.now(cst_timezone).strftime("%Y-%m-%d")

# Setting Sprint Data and Chart Attachement Response Data File names
sprint_data_file_name = 'sprint_data.json'

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


# Get Our PowerUp ID from the Board
def get_plugin_id(client, board_id):
    """
    Gets Our PowerUp ID from the Board
    :param client: Trello client Object
    :param board_id: The ID of the Board
    :return: returns Plugin/PowerUp Value
    """
    plugins =  client.fetch_json(
        f"boards/{board_id}/plugins",
        http_method="GET",
        headers = {
                "Accept": "application/json"
        },
    )

    for plugin in plugins:
        if plugin['name'] == POWERUP_NAME:
            return plugin['id']


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
    enabled_powerups_data = enabled_powerups(client, board_id)
    plugin_id = get_plugin_id(client, board_id)

    for enabled_powerup in enabled_powerups_data:
        # Check if our PowerUp Enabled or Not
        if plugin_id == enabled_powerup['idPlugin']:
            plugin_data = client.fetch_json(
                f"boards/{board_id}/pluginData",
                http_method="GET",
                headers = {
                        "Accept": "application/json"
                },
                query_params={
                    'idPlugin': plugin_id
                }
            )

            return plugin_data[0]['value']


# Get Stories and Tasks Counts
def get_counts(client, board_id, monitor_lists, done_list, start_day):
    """
    Get List data
    :param client: Trello client Object
    :param board_id: Trello Board ID
    :param monitor_lists: Trello monitor lists from PowerUp Data
    :param start_day: Start day of the Sprint. Eg: Monday
    :return: returns count of User Stories/Defects remaining and completed
    """
    stories_defects_remaining = 0
    stories_defects_done = 0
    tasks_remaining = 0
    ideal_tasks_remaining = 0

    board_object = Board(client, board_id=board_id)
    board_cards = board_object.get_cards()

    for monitor_list in monitor_lists:
        for board_card in board_cards:
            if board_card.idList == monitor_list:
                if board_card.name[:2] in 'T ':
                    tasks_remaining += 1
                elif board_card.name[:2] in ('U ', 'D ', 'C '):
                    stories_defects_remaining += 1
    else:
        for board_card in board_cards:
            if board_card.idList == done_list:
                if board_card.name[:2] in ('U ', 'D ', 'C '):
                    stories_defects_done += 1
                if current_day == start_day:
                    if board_card.name[:2] in 'T ':
                        ideal_tasks_remaining += 1

    if current_day == start_day:
        ideal_tasks_remaining += tasks_remaining

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
    if current_day == start_day:
        sprint_dates.append(start_date.strftime("%Y-%m-%d"))
        business_days_to_add = total_sprint_days
        current_datetime = start_date
        while business_days_to_add > 0:
            current_datetime += datetime.timedelta(days=1)
            weekday = current_datetime.weekday()
            if weekday >= 5: # sunday = 6
                continue
            business_days_to_add -= 1
            sprint_dates.append(current_datetime.strftime("%Y-%m-%d"))
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
def update_sprint_data(start_day, board_id, sprint_dates, stories_defects_remaining, stories_defects_done, tasks_remaining, ideal_tasks_remaining, team_size):
    """
    Create/Update Sprint Data to Json file
    :param start_day: Start day of the Sprint. Eg: Monday
    :param board_id: The ID of the Board
    :param sprint_dates: List of current sprint dates
    :param stories_defects_remaining: Userstories or Defects remaining count
    :param stories_defects_done: Userstories or Defects done count
    :param tasks_remaining: Tasks remaining count
    :param ideal_tasks_remaining: Ideal tasks remaining count
    :param team_size: Total Team Size in the Current Sprint
    :return: returns Sprint Json Data
    """
    sprint_data = {}

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
            sprint_data[board_id].update( { 'ideal_tasks_remaining': 0, sprint_date: { 'stories_defects_remaining': 0, 'stories_defects_done': 0 } } )
        sprint_data[board_id].update( {
                'ideal_tasks_remaining': ideal_tasks_remaining,
                current_date: {
                'stories_defects_remaining': stories_defects_remaining,
                'stories_defects_done': stories_defects_done,
                'tasks_remaining': tasks_remaining,
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
                'team_size': team_size
                }
            }
        )
    with open('/tmp/' + sprint_data_file_name, "w") as sprint_data_file:
        json.dump(sprint_data, sprint_data_file)
    sprint_data_file.close()

    return sprint_data


# Create Sprint Burndown Chart
def create_chart(sprint_data, total_sprint_days, board_id, team_members, team_members_days_ooo, is_show_team_size):
    """
    Creates Sprint Burndown Chart
    :param sprint_data: The Sprint Data
    :param total_sprint_days: Total Sprint Days in the Current Sprint without Weekends Eg: 5 (Multiples of 5)
    :param board_id: The ID of the Board
    :param team_members: Team members on Team for Sprint
    :param team_members_days_ooo: Team Members Days Out of Office
    :param is_show_team_size: To enable Team Size in Sprint Burndown Chart
    :return: returns nothing
    """
    sprint_dates_list = [""]
    stories_defects_remaining_list = [0]
    stories_defects_done_list = [0]
    tasks_remaining_list = []
    team_size_list = [0]

    ideal_tasks_remaining = sprint_data[board_id]['ideal_tasks_remaining']

    tasks_remaining_list.append(ideal_tasks_remaining)

    for key, value in sprint_data[board_id].items():
        if key != 'ideal_tasks_remaining':
            sprint_dates_list.append(key)
            stories_defects_remaining_list.append(value['stories_defects_remaining'])
            stories_defects_done_list.append(value['stories_defects_done'])
            if value.get('tasks_remaining') or value.get('tasks_remaining') == 0:
                tasks_remaining_list.append(value['tasks_remaining'])
            if value.get('team_size') or value.get('team_size') == 0:
                team_size_list.append(value['team_size'])

    team_size_list[0] = team_size_list[1]

    f, ax = plt.subplots()

    x_axis = [item for item in range(0, total_sprint_days + 1)]
    x_axis_label = sprint_dates_list

    y_axis_labels = [0]
    ideal_line_list = [0]
    ax.axhline(y=0,color='#d0e2f6',linewidth=.5, zorder=0)
    for index in range(0, total_sprint_days):
        y_axis_label = y_axis_labels[index] + round((max(tasks_remaining_list)/total_sprint_days) + 0.5)
        ideal_line = ideal_line_list[index] + (ideal_tasks_remaining/total_sprint_days)
        y_axis_labels.append(y_axis_label)
        ideal_line_list.append(ideal_line)
        ax.axhline(y=y_axis_labels[index + 1],color='#d0e2f6',linewidth=.5, zorder=0)

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

    if is_show_team_size:
        plt.fill_between(np.arange(len(team_size_list)), 0, team_size_list, color='#ff9f68', alpha=0.5, lw=0)
        p6, = plt.plot(np.arange(len(team_size_list)),team_size_list,'k--',color='#ff9f68', label='line 1',zorder=1)
        for index in range(0, len(team_size_list)):
            plt.annotate(xy=[index, team_size_list[index]], s=str(team_size_list[index]), color='#ff9f68', size=6, ha='center', va='bottom', textcoords="offset points", xytext=(2, 3))

    p3 = plt.bar(np.arange(len(stories_defects_remaining_list)), stories_defects_remaining_list, color='#c5e3f6',width=-.25,align='edge',zorder=2)
    p4 = plt.bar(np.arange(len(stories_defects_done_list)), stories_defects_done_list, color='#17b978',width=.25,align='edge', zorder=2)
    p5 = plt.bar(np.arange(len(team_members_days_ooo)) -.5, team_members_days_ooo, color='#ffcef3',width=.25,align='edge', zorder=2)
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

    plt.title("Burndown Chart")

    on_team_for_sprint = ['On Team for Sprint', '\n']

    on_team_for_sprint.extend(team_members)

    plt.text(.02, 0.1, "\n".join(on_team_for_sprint), fontsize=5, transform=plt.gcf().transFigure)
    plt.subplots_adjust(left=0.2)

    if is_show_team_size:
        plt.legend([p1,p2,p3, p4, p5, p6], ["Ideal Tasks Remaining","Tasks Remaining","Stories/Defects Remaining", "Stories/Defects Done", "Team Members Days OOO","Team Size"], loc=1, borderaxespad=0,fontsize=6).get_frame().set_alpha(0.5)
    else:
        plt.legend([p1,p2,p3, p4, p5], ["Ideal Tasks Remaining","Tasks Remaining","Stories/Defects Remaining", "Stories/Defects Done", "Team Members Days OOO"], loc=1, borderaxespad=0,fontsize=6).get_frame().set_alpha(0.5)

    plt.savefig('/tmp/' + current_date + '_Sprint_Burndown_Chart_' + board_id, dpi=150)


# Delete previously attached Chart from the card
def delete_chart(client, card_id):
    """
    Deletes already existing Sprint Burndown chart
    :param client: Trello client Object
    :param card_id: The ID of the Card
    :return: returns None
    """
    try:
        card_attachments = client.fetch_json(
            f"cards/{card_id}/attachments",
            http_method="GET",
            headers = {
                    "Accept": "application/json"
                }
        )
        for card_attachment in card_attachments:
            if current_date in card_attachment['name']:
                client.fetch_json(
                        f"cards/{card_id}/attachments/{card_attachment['id']}",
                        http_method="DELETE",
                        headers = {
                                "Accept": "application/json"
                        }
                    )
    except Exception as error:
        print(error)
        pass


# Attach Chart to the Card
def attach_chart(client, card_id, board_id):
    """
    Attaches Sprint Burndown chart to a card
    :param client: Trello client Object
    :param card_id: The ID of the Card
    :param board_id: The ID of the Board
    :return: returns None
    """
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

        # Delete Chart locally
        os.remove(image_path)
    except Exception as error:
        print(error)
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
    Scheduled Event to update Sprint Burndown Chart in Trello
    :param event: Event data
    :param context: This object provides methods and properties that provide information about the invocation, function and execution environment
    :return: returns status
    """
    # Connect to Trello
    client = TrelloClient(
            api_key=TRELLO_API_KEY,
            token=TRELLO_TOKEN
    )


    # S3 Client
    s3 = boto3.resource('s3')

    if current_day not in ('Saturday', 'Sunday'):
        # Get Organizations Boards
        boards = Organization(client, TRELLO_ORGANIZATION_ID).all_boards()

        for board in boards:
            # Download Sprint data and Card Attachment data files from S3
            try:
                s3.Bucket(DEPLOYMENT_BUCKET).download_file(sprint_data_file_name, '/tmp/' + sprint_data_file_name)
            except Exception as error:
                print(error)
                pass

            # Get PowerUp Data
            powerup_data = get_powerup_data(client, board.id)

            # Check PowerUp Data exists
            if powerup_data is not None:
                try:
                    sprint_start_day = json.loads(powerup_data)['sprint_start_day']
                    total_sprint_days = int(json.loads(powerup_data)['total_sprint_days'])

                    # Get monitor lists
                    monitor_lists = json.loads(powerup_data)['selected_list']

                    # Get Done lists
                    done_list = json.loads(powerup_data)['selected_done_list']

                    # Get counts of Stories/Tasks
                    stories_defects_remaining, stories_defects_done, tasks_remaining, ideal_tasks_remaining = get_counts(client, board.id, monitor_lists, done_list, sprint_start_day)

                    print(f'Board ID: {board.id}')
                    print(f'Stories Remaining: {stories_defects_remaining}')
                    print(f'Stories Done: {stories_defects_done}')
                    print(f'Tasks Remaining: {tasks_remaining}')
                    print(f'Ideal Tasks Remaining: {ideal_tasks_remaining}')

                    # Current Sprint Dates
                    sprint_dates = get_sprint_dates(sprint_start_day, (total_sprint_days - 1), board.id)

                    print(f'Start Date: {sprint_dates[0]} End Date: {sprint_dates[len(sprint_dates)-1]}')

                    team_members = json.loads(powerup_data)['team_member_list']

                    is_show_team_size = eval(json.loads(powerup_data).get('is_show_team_size', 'False'))

                    team_members_days_ooo = json.loads(powerup_data)['team_members_days_ooo']

                    team_members_days_ooo = team_members_days_ooo.split(",")

                    team_members_days_ooo_list = [0]
                    for ooo_per_day in team_members_days_ooo:
                        team_members_days_ooo_list.append(float(ooo_per_day.split("-")[1]))

                    team_size = len(team_members)

                    # Update sprint data
                    sprint_data = update_sprint_data(sprint_start_day, board.id, sprint_dates, stories_defects_remaining, stories_defects_done, tasks_remaining, ideal_tasks_remaining, team_size)

                    # Create Sprint Burndown Chart
                    create_chart(sprint_data, total_sprint_days, board.id, team_members, team_members_days_ooo_list, is_show_team_size)

                    attachment_card_id = json.loads(powerup_data)['selected_card_for_attachment']

                    # Delete previously attached Chart from the card
                    delete_chart(client, attachment_card_id)

                    # Attach Chart to Card
                    attach_chart(client, attachment_card_id, board.id)

                    # Upload Sprint data and Card Attachment data files from S3
                    try:
                        s3.Object(DEPLOYMENT_BUCKET, sprint_data_file_name).put(Body=open('/tmp/' + sprint_data_file_name, 'rb'))
                    except Exception as error:
                        print(error)
                        pass

                    # Return Success
                    success()
                except Exception as error:
                    print(error)
                    continue
