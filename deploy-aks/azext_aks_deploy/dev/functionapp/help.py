# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from knack.help_files import helps


def load_functionapp_help():
    helps['functionapp app'] = """
    type: group
    short-summary: Commands to manage Azure Functions app.
    long-summary:
    """

    helps['functionapp app up'] = """
    type: command
    short-summary: Deploy to Azure Functions via GitHub actions.
    long-summary:
    """
