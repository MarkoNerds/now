"""
This module implements a command-line dialog with the user.
Its goal is to configure a UserInput object with users specifications.
Optionally, values can be passed from the command-line when jina-now is launched. In that case,
the dialog won't ask for the value.
"""
from __future__ import annotations, print_function, unicode_literals

import importlib
import os
import uuid

from hubble import AuthenticationRequiredError
from kubernetes import client, config

from now.common.detect_schema import (
    set_field_names_from_docarray,
    set_field_names_from_local_folder,
    set_field_names_from_s3_bucket,
)
from now.constants import Apps, DatasetTypes
from now.demo_data import AVAILABLE_DATASETS
from now.deployment.deployment import cmd
from now.log import yaspin_extended
from now.now_dataclasses import DialogOptions, UserInput
from now.utils import (
    _get_context_names,
    get_info_hubble,
    jina_auth_login,
    sigmap,
    to_camel_case,
)

NEW_CLUSTER = {'name': '🐣 create new', 'value': 'new'}
AVAILABLE_SOON = 'will be available in upcoming versions'


# Make sure you add this dialog option to your app in order of dependency, i.e., if some dialog option depends on other
# than the parent should be called first before the dependant can called.


def _create_app_from_user_input(user_input: UserInput, **kwargs):
    if len(user_input.search_fields) != 1:
        raise ValueError(
            'Currently only one search field is supported. Please choose one field.'
        )
    if user_input.search_fields[0] not in user_input.search_fields_modalities.keys():
        raise ValueError(
            f'Search field specified is not among the search candidate fields. Please '
            f'choose one of the following: {user_input.search_fields_modalities.keys()}'
        )
    _search_modality = user_input.search_fields_modalities[user_input.search_fields[0]]
    app_name = Apps.SEARCH_APP
    user_input.app_instance = construct_app(app_name)


APP_NAME = DialogOptions(
    name='flow_name',
    prompt_message='Choose a name for your application:',
    prompt_type='input',
    is_terminal_command=True,
    post_func=lambda user_input, **kwargs: clean_flow_name(user_input),
)


def clean_flow_name(user_input: UserInput):
    """
    Clean the flow name to make it valid, removing special characters and spaces.
    """
    user_input.flow_name = ''.join(
        [c for c in user_input.flow_name if c.isalnum() or c == '-']
    ).lower()


DATASET_TYPE = DialogOptions(
    name='dataset_type',
    prompt_message='How do you want to provide input? (format: https://docarray.jina.ai/)',
    choices=[
        {'name': 'Demo dataset', 'value': DatasetTypes.DEMO},
        {
            'name': 'DocumentArray name (recommended)',
            'value': DatasetTypes.DOCARRAY,
        },
        {
            'name': 'Local folder',
            'value': DatasetTypes.PATH,
        },
        {
            'name': 'S3 bucket',
            'value': DatasetTypes.S3_BUCKET,
        },
        {
            'name': 'Elasticsearch',
            'value': DatasetTypes.ELASTICSEARCH,
            'disabled': AVAILABLE_SOON,
        },
    ],
    prompt_type='list',
    is_terminal_command=True,
    post_func=lambda user_input, **kwargs: check_login_dataset(user_input),
)


def check_login_dataset(user_input: UserInput):
    if (
        user_input.dataset_type in [DatasetTypes.DEMO, DatasetTypes.DOCARRAY]
        and user_input.jwt is None
    ):
        _jina_auth_login(user_input)


def _get_demo_data_choices(user_input: UserInput, **kwargs):
    all_demo_datasets = []
    for demo_datasets in AVAILABLE_DATASETS.values():
        all_demo_datasets.extend(demo_datasets)
    return [
        {'name': demo_data.display_name, 'value': demo_data.name}
        for demo_data in all_demo_datasets
    ]


DEMO_DATA = DialogOptions(
    name='dataset_name',
    prompt_message='What demo dataset do you want to use?',
    choices=lambda user_input, **kwargs: _get_demo_data_choices(user_input),
    prompt_type='list',
    depends_on=DATASET_TYPE,
    is_terminal_command=True,
    description='Select one of the available demo datasets',
    conditional_check=lambda user_input, **kwargs: user_input.dataset_type
    == DatasetTypes.DEMO,
    post_func=lambda user_input, **kwargs: set_field_names_from_docarray(user_input),
)

DOCARRAY_NAME = DialogOptions(
    name='dataset_name',
    prompt_message='Please enter your DocumentArray name:',
    prompt_type='input',
    depends_on=DATASET_TYPE,
    conditional_check=lambda user_input: user_input.dataset_type
    == DatasetTypes.DOCARRAY,
    post_func=lambda user_input, **kwargs: set_field_names_from_docarray(user_input),
)

DATASET_PATH = DialogOptions(
    name='dataset_path',
    prompt_message='Please enter the path to the local folder:',
    prompt_type='input',
    depends_on=DATASET_TYPE,
    is_terminal_command=True,
    conditional_check=lambda user_input: user_input.dataset_type == DatasetTypes.PATH,
    post_func=lambda user_input, **kwargs: set_field_names_from_local_folder(
        user_input
    ),
)

DATASET_PATH_S3 = DialogOptions(
    name='dataset_path',
    prompt_message='Please enter the S3 URI to the folder:',
    prompt_type='input',
    depends_on=DATASET_TYPE,
    conditional_check=lambda user_input: user_input.dataset_type
    == DatasetTypes.S3_BUCKET,
)

AWS_ACCESS_KEY_ID = DialogOptions(
    name='aws_access_key_id',
    prompt_message='Please enter the AWS access key ID:',
    prompt_type='input',
    depends_on=DATASET_TYPE,
    conditional_check=lambda user_input: user_input.dataset_type
    == DatasetTypes.S3_BUCKET,
)

AWS_SECRET_ACCESS_KEY = DialogOptions(
    name='aws_secret_access_key',
    prompt_message='Please enter the AWS secret access key:',
    prompt_type='input',
    depends_on=DATASET_TYPE,
    conditional_check=lambda user_input: user_input.dataset_type
    == DatasetTypes.S3_BUCKET,
)

AWS_REGION_NAME = DialogOptions(
    name='aws_region_name',
    prompt_message='Please enter the AWS region:',
    prompt_type='input',
    depends_on=DATASET_TYPE,
    conditional_check=lambda user_input: user_input.dataset_type
    == DatasetTypes.S3_BUCKET,
    post_func=lambda user_input, **kwargs: set_field_names_from_s3_bucket(user_input),
)

# --------------------------------------------- #


SEARCH_FIELDS = DialogOptions(
    name='search_fields',
    choices=lambda user_input, **kwargs: [
        {'name': field, 'value': field}
        for field in user_input.search_fields_modalities.keys()
    ],
    prompt_message='Please select the index fields:',
    prompt_type='checkbox',
    is_terminal_command=True,
    post_func=_create_app_from_user_input,
    argparse_kwargs={
        'type': lambda s: s.split(',') if s else UserInput().search_fields
    },
)

FILTER_FIELDS = DialogOptions(
    name='filter_fields',
    choices=lambda user_input, **kwargs: [
        {'name': field, 'value': field}
        for field in user_input.filter_fields_modalities.keys()
        if field not in user_input.search_fields
    ],
    prompt_message='Please select the filter fields',
    prompt_type='checkbox',
    depends_on=DATASET_TYPE,
    conditional_check=lambda user_input: user_input.filter_fields_modalities is not None
    and len(
        set(user_input.filter_fields_modalities.keys()) - set(user_input.search_fields)
    )
    > 0,
)

ES_INDEX_NAME = DialogOptions(
    name='es_index_name',
    prompt_message='Please enter the name of your Elasticsearch index:',
    prompt_type='input',
    depends_on=DATASET_TYPE,
    conditional_check=lambda user_input: user_input.dataset_type
    == DatasetTypes.ELASTICSEARCH,
)

ES_HOST_NAME = DialogOptions(
    name='es_host_name',
    prompt_message='Please enter the address of your Elasticsearch node:',
    prompt_type='input',
    depends_on=DATASET_TYPE,
    conditional_check=lambda user_input: user_input.dataset_type
    == DatasetTypes.ELASTICSEARCH,
)

ES_ADDITIONAL_ARGS = DialogOptions(
    name='es_additional_args',
    prompt_message='Please enter additional arguments for your Elasticsearch node if there are any:',
    prompt_type='input',
    depends_on=DATASET_TYPE,
    conditional_check=lambda user_input: user_input.dataset_type
    == DatasetTypes.ELASTICSEARCH,
)

# --------------------------------------------- #

DEPLOYMENT_TYPE = DialogOptions(
    name='deployment_type',
    prompt_message='Where do you want to deploy your search engine?',
    prompt_type='list',
    choices=[
        {
            'name': '⛅️ Jina Cloud',
            'value': 'remote',
        },
        {
            'name': '📍 Local',
            'value': 'local',
        },
    ],
    is_terminal_command=True,
    description='Options are `local` or `remote`. Select `local` if you want your search engine to be deployed on a local '
    'cluster. Select `remote` to deploy it on Jina Cloud',
    post_func=lambda user_input, **kwargs: check_login_deployment(user_input),
)


def check_login_deployment(user_input: UserInput):
    if user_input.deployment_type == 'remote' and user_input.jwt is None:
        _jina_auth_login(user_input)


LOCAL_CLUSTER = DialogOptions(
    name='cluster',
    prompt_message='On which cluster do you want to deploy your search engine?',
    prompt_type='list',
    choices=lambda user_input, **kwargs: _construct_local_cluster_choices(
        user_input, **kwargs
    ),
    depends_on=DEPLOYMENT_TYPE,
    is_terminal_command=True,
    description='Reference an existing `local` cluster or select `new` to create a new one. '
    'Use this only when the `--deployment-type=local`',
    conditional_check=lambda user_inp: user_inp.deployment_type == 'local',
    post_func=lambda user_input, **kwargs: user_input.app_instance.run_checks(
        user_input
    ),
)


SECURED = DialogOptions(
    name='secured',
    prompt_message='Do you want to secure the Flow?',
    prompt_type='list',
    choices=[
        {'name': '⛔ no', 'value': False},
        {'name': '✅ yes', 'value': True},
    ],
    depends_on=DEPLOYMENT_TYPE,
    is_terminal_command=True,
    conditional_check=lambda user_inp: user_inp.deployment_type == 'remote',
)

API_KEY = DialogOptions(
    name='api_key',
    prompt_message='Do you want to generate an API key to access this deployment?',
    prompt_type='list',
    choices=[
        {'name': '✅ yes', 'value': uuid.uuid4().hex},
        {'name': '⛔ no', 'value': False},
    ],
    depends_on=SECURED,
    is_terminal_command=True,
    description='Pass an API key to access the Flow once the deployment is complete. ',
    conditional_check=lambda user_inp: str(user_inp.secured).lower() == 'true',
    post_func=lambda user_input, **kwargs: _set_value_to_none(user_input),
)

ADDITIONAL_USERS = DialogOptions(
    name='additional_user',
    prompt_message='Do you want to provide additional users access to this flow?',
    prompt_type='list',
    choices=[
        {'name': '✅ yes', 'value': True},
        {'name': '⛔ no', 'value': False},
    ],
    depends_on=SECURED,
    conditional_check=lambda user_inp: str(user_inp.secured).lower() == 'true',
)

USER_EMAILS = DialogOptions(
    name='user_emails',
    prompt_message='Please enter email addresses (separated by commas) '
    'to grant access to this Flow.\nAdditionally, you can specify comma-separated domain names'
    ' such that all users from that domain can access this Flow, e.g. `jina.ai`\n',
    prompt_type='input',
    depends_on=ADDITIONAL_USERS,
    conditional_check=lambda user_inp: user_inp.additional_user,
    post_func=lambda user_input, **kwargs: _add_additional_users(user_input, **kwargs),
)


def _set_value_to_none(user_input: UserInput):
    if not user_input.api_key:
        user_input.api_key = None


def _add_additional_users(user_input: UserInput, **kwargs):
    user_input.user_emails = (
        [email.strip() for email in kwargs['user_emails'].split(',')]
        if kwargs['user_emails']
        else []
    )


def _check_if_namespace_exist():
    config.load_kube_config()
    v1 = client.CoreV1Api()
    return 'nowapi' in [item.metadata.name for item in v1.list_namespace().items]


def construct_app(app_name: str):
    return getattr(
        importlib.import_module(f'now.app.{app_name}.app'),
        f'{to_camel_case(app_name)}',
    )()


def _jina_auth_login(user_input: UserInput, **kwargs):
    try:
        jina_auth_login()
    except AuthenticationRequiredError:
        with yaspin_extended(
            sigmap=sigmap, text='Log in to Jina AI Cloud', color='green'
        ) as spinner:
            cmd('jina auth login')
        spinner.ok('🛠️')

    get_info_hubble(user_input)
    os.environ['JCLOUD_NO_SURVEY'] = '1'


def _construct_local_cluster_choices(user_input: UserInput, **kwargs):
    active_context = kwargs.get('active_context')
    contexts = kwargs.get('contexts')
    context_names = _get_context_names(contexts, active_context)
    choices = [NEW_CLUSTER]
    # filter contexts with `gke`
    if len(context_names) > 0 and len(context_names[0]) > 0:
        context_names = [
            context
            for context in context_names
            if 'gke' not in context and _cluster_running(context)
        ]
        choices = context_names + choices
    return choices


def _cluster_running(cluster):
    config.load_kube_config(context=cluster)
    v1 = client.CoreV1Api()
    try:
        v1.list_namespace()
    except Exception as e:
        return False
    return True


app_config = [APP_NAME]
data_type = [DATASET_TYPE]
data_fields = [SEARCH_FIELDS, FILTER_FIELDS]
data_demo = [DEMO_DATA]
data_da = [DOCARRAY_NAME, DATASET_PATH]
data_s3 = [DATASET_PATH_S3, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION_NAME]
data_es = [
    ES_HOST_NAME,
    ES_INDEX_NAME,
    ES_ADDITIONAL_ARGS,
]
cluster = [DEPLOYMENT_TYPE, LOCAL_CLUSTER]
remote_cluster = [SECURED, API_KEY, ADDITIONAL_USERS, USER_EMAILS]

base_options = (
    data_type
    + data_demo
    + data_da
    + data_s3
    + data_es
    + data_fields
    + app_config
    + cluster
    + remote_cluster
)
