from typing import Callable

import pytest
import requests
from docarray import Document, DocumentArray
from docarray.typing import Text
from starlette import status

from now.now_dataclasses import UserInput


def test_text_index_fails_with_no_flow_running(client: requests.Session):
    with pytest.raises(ConnectionError):
        client.post(
            f'/api/v1/search-app/index',
            json={'data': [({'query_text': {'text': 'Hello'}}, {})]},
        )


def test_text_search_fails_with_no_flow_running(
    client: requests.Session, base64_image_string: str
):
    with pytest.raises(ConnectionError):
        client.post(
            f'/api/v1/search-app/search',
            json={'query': {'query_image': {'blob': base64_image_string}}},
        )


def test_text_search_fails_with_incorrect_query(client):
    with pytest.raises(ValueError):
        client.post(
            f'/api/v1/search-app/search',
            json={
                'data': [
                    (
                        {
                            'query_text': {'text': 'Hello'},
                            'query_image': {'uri': 'example.png'},
                        },
                        {},
                    )
                ]
            },
        )


def test_text_search_fails_with_emtpy_query(client: requests.Session):
    with pytest.raises(ValueError):
        client.post(
            f'/api/v1/search-app/search',
            json={},
        )


def test_text_index(
    client_with_mocked_jina_client: Callable[[DocumentArray], requests.Session],
):
    import deployment.bff.app.v1.routers.search as bff_search

    def _mocked_fetch_user_input(data):
        return UserInput(
            search_fields_modalities={'title': Text}, search_fields=['title']
        )

    bff_search.fetch_user_input = _mocked_fetch_user_input

    response = client_with_mocked_jina_client(DocumentArray()).post(
        '/api/v1/search-app/index',
        json={'data': [({'title': {'text': 'Hello'}}, {'tag': 'val'})]},
    )
    assert response.status_code == status.HTTP_200_OK


def test_text_search_calls_flow(
    client_with_mocked_jina_client: Callable[[DocumentArray], requests.Session],
    sample_search_response_text: DocumentArray,
    base64_image_string: str,
):
    response = client_with_mocked_jina_client(sample_search_response_text).post(
        '/api/v1/search-app/search',
        json={'query': {'query_image': {'blob': base64_image_string}}},
    )

    assert response.status_code == status.HTTP_200_OK
    results = DocumentArray.from_json(response.content)
    # the mock writes the call args into the response tags
    assert results[0].tags['url'] == '/search'
    assert results[0].tags['parameters']['limit'] == 10


def test_text_search_parse_response(
    client_with_mocked_jina_client: Callable[[DocumentArray], requests.Session],
    sample_search_response_text: DocumentArray,
    base64_image_string: str,
):
    response_raw = client_with_mocked_jina_client(sample_search_response_text).post(
        '/api/v1/search-app/search',
        json={'query': {'query_image': {'blob': base64_image_string}}},
    )

    assert response_raw.status_code == status.HTTP_200_OK
    results = DocumentArray()
    # todo: use multimodal doc in the future
    for response_json in response_raw.json():
        content = list(response_json['fields'].values())[0]
        doc = Document(
            id=response_json['id'],
            tags=response_json['tags'],
            scores=response_json['scores'],
            **content,
        )
        results.append(doc)
    assert len(results) == len(sample_search_response_text[0].matches)
    assert results[0].text == sample_search_response_text[0].matches[0].text
