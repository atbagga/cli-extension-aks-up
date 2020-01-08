# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from knack.prompting import prompt
from knack.log import get_logger
from knack.util import CLIError

from azext_aks_deploy.dev.common.git import get_repository_url_from_local_repo, uri_parse
from azext_aks_deploy.dev.common.github_api_helper import (Files, get_work_flow_check_runID,
                                                     get_check_run_status_and_conclusion, get_github_pat_token)
from azext_aks_deploy.dev.common.github_workflow_helper import poll_workflow_status
from azext_aks_deploy.dev.common.github_azure_secrets import get_azure_credentials
from azext_aks_deploy.dev.common.utils import get_repo_name_from_repo_url
from azext_aks_deploy.dev.common.kubectl import get_deployment_IP_port
from azext_aks_deploy.dev.common.const import ( APP_NAME_DEFAULT, APP_NAME_PLACEHOLDER,
                                                ACR_PLACEHOLDER, RG_PLACEHOLDER, PORT_NUMBER_DEFAULT,
                                                CLUSTER_PLACEHOLDER, RELEASE_PLACEHOLDER, RELEASE_NAME)
from azext_aks_deploy.dev.aks.docker_helm_template import get_docker_templates,get_helm_charts

logger = get_logger(__name__)

def aks_deploy(aks_cluster=None, acr=None, repository=None, port=None, skip_secrets_generation=False, do_not_wait=False):
    """Build and Deploy to AKS via GitHub actions
    :param aks_cluster: Name of the cluster to select for deployment.
    :type aks_cluster: str
    :param acr: Name of the Azure Container Registry to be used for pushing the image.
    :type acr: str
    :param repository: GitHub repository URL e.g. https://github.com/azure/azure-cli.
    :type repository: str
    :param port: Port on which your application runs. Default is 8080
    :type port:str
    :param skip_secrets_generation : Flag to skip generating Azure credentials.
    :type skip_secrets_generation: bool
    :param do_not_wait : Do not wait for workflow completion.
    :type do_not_wait bool
    """
    if repository is None:
        repository = get_repository_url_from_local_repo()
        logger.debug('Github Remote url detected local repo is {}'.format(repository))
    if not repository:
        repository = prompt('GitHub Repository url (e.g. https://github.com/atbagga/aks-deploy):')
    if not repository:
        raise CLIError('The following arguments are required: --repository.')
    repo_name = get_repo_name_from_repo_url(repository)

    from azext_aks_deploy.dev.common.github_api_helper import get_languages_for_repo, push_files_github
    get_github_pat_token(repo_name,display_warning=True)
    logger.warning('Setting up your workflow.')                                                           

    languages = get_languages_for_repo(repo_name)
    if not languages:
        raise CLIError('Language detection has failed on this repository.')
    
    language = choose_supported_language(languages)
    if language:
        logger.warning('%s repository detected.', language)
    else:
        logger.debug('Languages detected : {} '.format(languages))
        raise CLIError('The languages in this repository are not yet supported from up command.')

    from azext_aks_deploy.dev.common.azure_cli_resources import (get_default_subscription_info,
                                                                 get_aks_details,
                                                                 get_acr_details,
                                                                 configure_aks_credentials)
    cluster_details = get_aks_details(aks_cluster)
    logger.debug(cluster_details)
    acr_details = get_acr_details(acr)
    logger.debug(acr_details)
    print('')

    if port is None:
        port = PORT_NUMBER_DEFAULT
    if 'Dockerfile' not in languages.keys():
        # check in docker file and docker ignore  
        docker_files = get_docker_templates(language, port)
        if docker_files:
            push_files_github(docker_files, repo_name, 'master', True, 
                            message="Checking in docker files for K8s deployment workflow.")
    else:
        logger.warning('Using the Dockerfile found in the repository {}'.format(repo_name))

    if 'Smarty' not in languages.keys():
        # check in helm charts
        helm_charts = get_helm_charts(language, acr_details, port)
        if helm_charts:
            push_files_github(helm_charts, repo_name, 'master', True, 
                                message="Checking in helm charts for K8s deployment workflow.")

    # create azure service principal and display json on the screen for user to configure it as Github secrets
    if not skip_secrets_generation:
        get_azure_credentials()
        
    print('')
    files = get_yaml_template_for_repo(language, cluster_details, acr_details, repo_name)
    # File checkin
    for file_name in files:
        logger.debug("Checkin file path: {}".format(file_name.path))
        logger.debug("Checkin file content: {}".format(file_name.content))

    workflow_commit_sha = push_files_github(files, repo_name, 'master', True, message="Setting up K8s deployment workflow.")
    print('Creating workflow...')
    check_run_id = get_work_flow_check_runID(repo_name,workflow_commit_sha)
    workflow_url = 'https://github.com/{repo_id}/runs/{checkID}'.format(repo_id=repo_name,checkID=check_run_id)
    print('GitHub Action workflow has been created - {}'.format(workflow_url))

    if not do_not_wait:
        poll_workflow_status(repo_name,check_run_id)
        configure_aks_credentials(cluster_details['name'],cluster_details['resourceGroup'])
        deployment_ip, port = get_deployment_IP_port(RELEASE_NAME,language)
        print('Your app is deployed at: http://{ip}:{port}'.format(ip=deployment_ip,port=port))
    return


def get_yaml_template_for_repo(language, cluster_details, acr_details, repo_name):
    files_to_return = []
    # Read template file
    from azext_aks_deploy.dev.resources.resourcefiles import DEPLOY_TO_AKS_TEMPLATE
    files_to_return.append(Files(path='.github/workflows/main.yml',
        content=DEPLOY_TO_AKS_TEMPLATE
            .replace(APP_NAME_PLACEHOLDER, APP_NAME_DEFAULT)
            .replace(ACR_PLACEHOLDER, acr_details['name'])
            .replace(CLUSTER_PLACEHOLDER, cluster_details['name'])
            .replace(RELEASE_PLACEHOLDER, RELEASE_NAME)
            .replace(RG_PLACEHOLDER, cluster_details['resourceGroup'])))
    return files_to_return
       

def choose_supported_language(languages):
    # check if top three languages are supported or not
    list_languages = list(languages.keys())
    first_language = list_languages[0]
    if 'JavaScript' == first_language or 'Java' == first_language or 'Python' == first_language:
        return first_language
    elif len(list_languages) >= 1 and ( 'JavaScript' == list_languages[1] or 'Java' == list_languages[1] or 'Python' == list_languages[1]):
        return list_languages[1]
    elif len(list_languages) >= 2 and ( 'JavaScript' == list_languages[2] or 'Java' == list_languages[2] or 'Python' == list_languages[2]):
        return list_languages[2]
    return None



