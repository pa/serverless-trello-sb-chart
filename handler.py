#!/usr/bin/env python
from __future__ import print_function
import os
import json
import boto3
import requests
from trello import TrelloClient
from trello import Organization
from trello import Board
from trello import List

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

    existing_webhooks = client.list_hooks(TRELLO_TOKEN)

    # Create Webhook for Trello Organization
    print(client.create_hook(CALLBACK_URL, TRELLO_ORGANIZATION_ID, "Trello Organiztion Webhook", TRELLO_TOKEN))

    # Create Webhook for Exisiting Boards
    print(create_existing_boards_hook(client, existing_webhooks))


    print(type(event))
    print(event)

    if event:
        payload = json.loads(event['payload'])
        print(create_new_board_hook(client, payload, existing_webhooks))
