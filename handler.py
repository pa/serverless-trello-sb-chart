#!/usr/bin/env python
from __future__ import print_function
import os
import base64
import json
import boto3
import requests

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

# Get Monitor Lists Method
def get_monitor_lists(client, payload):
    """
    Gets the lists that needs to be monitored
    :param client: Trello client Object
    :param payload: Trello Webhook Payload from API Gateway
    :return: returns webhook creation response
    """
    return client.fetch_json(
        f"boards/{payload['action']['data']['board']['id']}/pluginData",
        http_method="GET",
        headers = {
                "Accept": "application/json"
            },
        query_params={
            'name': POWERUP_NAME
        }
    )


# Create Webhook for Existing Organization Boards
def create_existing_boards_hook(client):
    """
    Create Webhooks for Organization Boards
    :param client: Trello client Object
    :return: returns status of the Webhook Creation
    """
    boards = client.list_boards()
    for board in boards:
        try:
            return create_webhook(client, CALLBACK_URL, board.id, f'{board.name} Trello Board Webhook')
        except Exception as e:
            print(f' {e}: Error creating webhook for the Trello Board ID - {board.id}')
            continue


# Create Webhook for New Organization Boards
def create_new_board_hook(client, payload):
    """
    Create Webhooks for Organization Boards
    :param client: Trello client Object
    :param payload: Trello Webhook Payload from API Gateway
    :return: returns status of the Webhook Creation
    """
    try:
        if payload['action']['type'] == "addToOrganizationBoard":
            return create_webhook(client, CALLBACK_URL, payload['action']['data']['board']['id'], f"{payload['action']['data']['board']['name']} Trello Board Webhook")
    except Exception as e:
        print(f"{e}: Error creating webhook for the Trello Board ID - {payload['action']['data']['board']['name']}")


# Get Stories and Tasks Counts
def get_counts(client, payload):
    """
    Get List data
    :param client: Trello client Object
    :param payload: Trello Webhook Payload from API Gateway
    :return: returns count of User Stories/Defects remaining and completed
    """
    stories_defects_remaining = 0
    stories_defects_done = 0
    tasks_remaining = 0

    board_object = Board(client, board_id=payload['action']['data']['board']['id'])
    board_lists = board_object.all_lists()
    monitor_lists = get_monitor_lists(client, payload)

    for monitor_list in monitor_lists:
        for board_list in board_lists:
            cards_list = List(board_object, board_list.id).list_cards()
            if board_list == monitor_list:
                for card in cards_list:
                    if card.name[:2] in 'T ':
                        tasks_remaining += 1
                        print("Tasks " + card.name)
                    elif card.name[:2] in ('U ', 'D '):
                        stories_defects_remaining += 1
                        print("Userstory/Defect " + card.name)
                break
            else:
                if board_list[-4:] == monitor_list:
                    if card.name[:2] in ('U ', 'D '):
                        stories_defects_done += 1
                        print("Done List - Userstory/Defect " + card.name)
                        break


# Check if cards updated in Board lists
def verify_list_action(client, payload):
    """
    Get counts when there is a update to the List
    :param client: Trello client Object
    :param payload: Trello Webhook Payload from API Gateway
    :return: returns count of User Stories/Defects remaining and completed
    """
    monitor_lists = get_monitor_lists(client, payload)

    if (payload['action']['type'] == "updateCard"):
        list_action_before = payload['action']['data']['listBefore']['name']
        list_action_after = payload['action']['data']['listAfter']['name']
        for monitor_list in monitor_lists:
            if list_action_before or list_action_after in (monitor_list):
                get_counts(client, payload)
                break
            else:
                continue


# Get Team members Out Of Office
def get_team_members_ooo(api_token, org_name, start_date, end_date):
    """
    Gets Team Memnber Out Of Office
    :param api_token: API Token for connecting BambooHR. To generate an API key, users should log in and click their name in the upper right-hand corner of any page to get to the user context menu
    :param org_name: BambooHR Organization Name
    :param start_date: A start date in the form YYYY-MM-DD
    :param end_date: A end date in the form YYYY-MM-DD
    :return: returns List of Team Members OOO and Count
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
    team_members = response.json()
    team_member_ooo_array = []
    for team_member in team_members:
        if team_member['type'] == 'timeOff':
            team_member_ooo_array.append(team_member['name'])
        elif team_member['type'] == 'holiday':
            continue
    team_member_ooo = list(dict.fromkeys(team_member_ooo_array))
    team_member_ooo_count = len(list(dict.fromkeys(team_member_ooo_array)))

    return team_member_ooo, team_member_ooo_count


# Success Status Method
def success():
    """
    Success Status Method
    :return: returns Success Status Code
    """
    return {"statusCode": 200}


def lambda_handler(event, context):
    """
    Extracts Trello Webhook Payload information and automates Trello
    :param event: Event data from API Gateway contains Trello Webhook Payload
    :param context: This object provides methods and properties that provide information about the invocation, function and execution environment
    :return: returns nothing
    """
    print(TRELLO_API_KEY)
    print(TRELLO_TOKEN)
    print(BAMBOOHR_API_TOKEN)
    print(CALLBACK_URL)
    print(POWERUP_NAME)

    return success()
