import os

import pytest
from docarray import Document, DocumentArray, dataclass
from docarray.typing import Image, Text
from jina import Flow

from now.app.base.transform_docarray import transform_uni_modal_data
from now.app.search_app import SearchApp
from now.constants import ACCESS_PATHS, EXTERNAL_CLIP_HOST, DatasetTypes
from now.data_loading.data_loading import load_data
from now.demo_data import DemoDatasetNames
from now.executor.indexer.in_memory import InMemoryIndexer
from now.executor.preprocessor import NOWPreprocessor
from now.now_dataclasses import UserInput


@pytest.fixture
def single_modal_data():
    d1 = Document(text='some text', tags={'color': 'red', 'author': 'saba'})
    d2 = Document(text='text some', tags={'color': 'blue', 'author': 'florian'})
    return DocumentArray([d1, d2])


@pytest.fixture
def multi_modal_data(resources_folder_path):
    @dataclass
    class Page:
        main_text: Text
        image: Image
        color: Text

    p1 = Page(
        main_text='main text 1',
        image=os.path.join(resources_folder_path, 'image', 'a.jpg'),
        color='red',
    )
    p2 = Page(
        main_text='not main text',
        image=os.path.join(resources_folder_path, 'image', 'b.jpg'),
        color='blue',
    )
    pages = [p1, p2]

    return DocumentArray([Document(page) for page in pages])


@pytest.mark.parametrize(
    'input_type, num_expected_matches',
    [['demo_dataset', 4], ['single_modal', 2], ['multi_modal', 6]],
)
def test_transform_inside_flow(
    input_type, num_expected_matches, single_modal_data, multi_modal_data, tmpdir
):
    metas = {'workspace': str(tmpdir)}
    user_input = UserInput()
    if input_type == 'demo_dataset':
        app_instance = SearchApp()
        user_input.search_fields = []
        user_input.dataset_type = DatasetTypes.DEMO
        user_input.dataset_name = DemoDatasetNames.TUMBLR_GIFS_10K
        data = load_data(user_input)[:2]
        user_input.search_fields = ['description', 'video']
        user_input.files_to_dataclass_fields = {
            'description': 'description',
            'video': 'video',
        }
    elif input_type == 'single_modal':
        app_instance = SearchApp()
        data = single_modal_data
    else:
        app_instance = SearchApp()
        data = multi_modal_data
        user_input.search_fields = ['main_text', 'image']
        user_input.files_to_dataclass_fields = {
            'main_text': 'main_text',
            'image': 'image',
        }
    query = Document(text='query_text')

    f = (
        Flow()
        .add(
            uses=NOWPreprocessor,
            uses_with={'app': app_instance.app_name},
            uses_metas=metas,
        )
        .add(
            uses='jinahub+docker://CLIPOnnxEncoder/latest-gpu',
            host=EXTERNAL_CLIP_HOST,
            port=443,
            tls=True,
            external=True,
            uses_with={'name': 'ViT-B-32::openai'},
        )
        .add(
            uses=InMemoryIndexer,
            uses_with={
                'columns': [
                    'split',
                    'str',
                    'finetuner_label',
                    'str',
                    'content_type',
                    'str',
                ],
                'dim': 512,
            },
            uses_metas=metas,
        )
    )
    with f:
        f.post(
            '/index',
            data,
            parameters={
                'user_input': user_input.__dict__,
                'access_paths': ACCESS_PATHS,
            },
        )

        query_res = f.post(
            '/search',
            query,
            parameters={
                'user_input': user_input.__dict__,
                'access_paths': ACCESS_PATHS,
            },
            return_results=True,
        )
    assert len(query_res[0].matches) == num_expected_matches
    assert not query_res[0].matches[0].uri.startswith('data:')


def test_uni_to_multi_modal(resources_folder_path, single_modal_data):
    data = single_modal_data
    data.append(
        Document(
            uri=os.path.join(resources_folder_path, 'gif', 'folder1/file.gif'),
            tags={'color': 'red'},
        )
    )
    transformed_data = transform_uni_modal_data(documents=data)

    assert len(transformed_data) == len(data)
    assert 'color' in transformed_data[0].tags
    assert len(transformed_data[1].chunks) == 1
