"""
Test the dialog.py module.

Patches the `prompt` method to mock user input via the command line.
"""
import os
from typing import Dict

import pytest
from docarray.typing import Image, Text, Video
from pytest_mock import MockerFixture

from now.constants import DEFAULT_FLOW_NAME, Apps, DatasetTypes
from now.demo_data import DemoDatasetNames
from now.dialog import configure_user_input
from now.now_dataclasses import UserInput

SEARCH_FIELDS_MODALITIES = {'text': Text, 'uri': Image}
FILTER_FIELDS_MODALITIES = {
    'uri': 'str',
    'text': 'str',
    'original_height': 'dict',
    'similarity': 'dict',
    'NSFW': 'dict',
    'height': 'dict',
    'original_width': 'dict',
    'width': 'dict',
}


class CmdPromptMock:
    def __init__(self, predefined_answers: Dict[str, str]):
        self._answers = predefined_answers

    def __call__(self, question: Dict):
        return {question['name']: self._answers[question['name']]}


MOCKED_DIALOGS_WITH_CONFIGS = [
    (
        {
            'app': Apps.SEARCH_APP,
            'flow_name': DEFAULT_FLOW_NAME,
            'dataset_type': DatasetTypes.DEMO,
            'dataset_name': DemoDatasetNames.TLL,
            'search_fields_modalities': {'label': Text, 'image': Image},
            'search_fields': ['label'],
            'filter_fields': [],
            'filter_fields_modalities': {'label': 'text'},
            'cluster': 'new',
            'deployment_type': 'local',
        },
        {},
    ),
    (
        {
            'app': Apps.SEARCH_APP,
            'flow_name': DEFAULT_FLOW_NAME,
            'dataset_type': DatasetTypes.DEMO,
            'dataset_name': DemoDatasetNames.NIH_CHEST_XRAYS,
            'search_fields_modalities': {'label': Text, 'image': Image},
            'search_fields': ['image'],
            'filter_fields': [],
            'filter_fields_modalities': {'label': 'text'},
            'cluster': 'new',
            'deployment_type': 'local',
        },
        {},
    ),
    (
        {
            'app': Apps.SEARCH_APP,
            'flow_name': DEFAULT_FLOW_NAME,
            'dataset_type': DatasetTypes.PATH,
            'dataset_path': os.path.join(
                os.path.dirname(__file__), '..', 'resources', 'image'
            ),
            'search_fields': ['.jpg'],
            'search_fields_modalities': {'.jpg': Image},
            'cluster': 'new',
            'deployment_type': 'local',
        },
        {},
    ),
    (
        {
            'flow_name': DEFAULT_FLOW_NAME,
            'dataset_type': DatasetTypes.DEMO,
            'dataset_name': DemoDatasetNames.DEEP_FASHION,
            'search_fields': ['image'],
            'search_fields_modalities': {'label': Text, 'image': Image},
            'filter_fields': [],
            'filter_fields_modalities': {'label': 'text'},
            'cluster': 'new',
            'deployment_type': 'local',
        },
        {'app': Apps.SEARCH_APP},
    ),
    (
        {},
        {
            'app': Apps.SEARCH_APP,
            'flow_name': 'testapp',
            'dataset_type': DatasetTypes.DEMO,
            'dataset_name': DemoDatasetNames.RAP_LYRICS,
            'search_fields': ['lyrics'],
            'search_fields_modalities': {'lyrics': Text, 'title': Text},
            'filter_fields': ['title'],
            'filter_fields_modalities': {'lyrics': 'text', 'title': 'text'},
            'cluster': 'new',
            'deployment_type': 'local',
        },
    ),
    (
        {},
        {
            'app': Apps.SEARCH_APP,
            'flow_name': 'testapp',
            'dataset_type': DatasetTypes.DEMO,
            'dataset_name': DemoDatasetNames.TUMBLR_GIFS_10K,
            'search_fields': ['video'],
            'search_fields_modalities': {'video': Video, 'description': Text},
            'filter_fields': ['title'],
            'filter_fields_modalities': {'description': 'text'},
            'cluster': 'new',
            'deployment_type': 'local',
        },
    ),
    (
        {
            'app': Apps.SEARCH_APP,
            'flow_name': 'test this name *',
            'dataset_type': DatasetTypes.DEMO,
            'dataset_name': DemoDatasetNames.DEEP_FASHION,
            'search_fields': ['image'],
            'search_fields_modalities': {'label': Text, 'image': Image},
            'filter_fields': [],
            'filter_fields_modalities': {'label': 'text'},
            'cluster': 'new',
            'deployment_type': 'local',
        },
        {'flow_name': 'testthisname'},
    ),
]


@pytest.mark.parametrize(
    ('mocked_user_answers', 'configure_kwargs'),
    MOCKED_DIALOGS_WITH_CONFIGS,
)
def test_configure_user_input(
    mocker: MockerFixture,
    mocked_user_answers: Dict[str, str],
    configure_kwargs: Dict,
):
    # expected user input
    expected_user_input = UserInput()
    expected_user_input.__dict__.update(mocked_user_answers)
    expected_user_input.__dict__.update(configure_kwargs)
    expected_user_input.__dict__.pop('app')

    # mocked user input
    mocker.patch('now.utils.prompt', CmdPromptMock(mocked_user_answers))
    user_input = configure_user_input(**configure_kwargs)
    user_input.__dict__.update({'jwt': None, 'admin_emails': None})
    user_input.__dict__.update({'app_instance': None})

    assert user_input == expected_user_input
