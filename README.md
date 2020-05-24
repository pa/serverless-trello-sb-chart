# Serverless Trello Sprint Burndown Chart

Serverless repository for Creating Trello Sprint Burndown Chart

It mainly works on two different triggers,

  1. When triggered by a Trello Webhook, Sprint Burndown Chart will be created when on creation or update to the card in the Trello List.
  2. When triggered by Event Bridge Event Rule, Checks all boards and create Sprint Burn Down chart.

## Installation

### Prerequisite

- [python3](https://www.python.org/downloads/)

- [serverless.com](https://www.serverless.com/framework/docs/getting-started/)

- Install Serverless [Plugins](https://www.serverless.com/framework/docs/providers/aws/cli-reference/plugin-install/)

  ```bash
  serverless plugin install --name serverless-python-requirements
  serverless plugin install --name serverless-pseudo-parameters
  ```

- Export environment variables

  ```bash
  export TRELLO_ORGANIZATION_ID=<Trello Organization ID>
  export POWERUP_NAME=<Power Up Name used in Trello>
  ```

- Create Parameters in AWS Parameter Store

  - First Generate API Key and Token, Goto [https://trello.com/app-key](https://trello.com/app-key) copy the Key replace it with `substituteKeyHere` in the below URL

    ```bash
    https://trello.com/1/authorize?key=substituteKeyHere&name=Sprint+Burndown+Chart&expiration=never&response_type=token&scope=read,write
    ```

  - Then open above URL in the browser, click `Allow` and Copy the Token

  - Create SecureString Type Trello API Key Parameter `/Serverless/Trello/ApiKey` with value from First Step

  - Create SecureString Type Trello Token Parameter `/Serverless/Trello/Token` with value from Second Step

### Power-Up setup in Glitch

To setup Power-Up in Glitch follow the steps [here](power-up/README.md)

### Serverless Deployment

- To Deploy,

  ```bash
  serverless deploy or sls deploy
  ```

- To Remove,

  ```bash
  serverless remove or sls remove
  ```
