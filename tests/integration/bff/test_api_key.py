import hubble
import requests
from tests.integration.bff.conftest import (
    BASE_URL,
    HOST,
    PORT,
    SEARCH_URL,
    get_flow,
    index_data,
)
from tests.integration.test_end_to_end import assert_search

from now.admin.utils import get_default_request_body

API_KEY = 'my_key'
update_api_keys_url = f'{BASE_URL}/admin/updateApiKeys'
update_emails_url = f'{BASE_URL}/admin/updateUserEmails'


def get_request_body():
    request_body = get_default_request_body('local', True, None)
    request_body['host'] = HOST
    request_body['port'] = PORT
    return request_body


def test_add_key(start_bff):
    client = hubble.Client(
        token=get_request_body()['jwt']['token'], max_retries=None, jsonify=True
    )
    admin_email = client.get_user_info()['data'].get('email')

    f = get_flow(
        preprocessor_args={'admin_emails': [admin_email]},
        indexer_args={'admin_emails': [admin_email]},
    )
    with f:
        index_data(f, jwt=get_request_body()['jwt'])

        request_body = get_request_body()
        print('# Test adding user email')
        request_body['user_emails'] = ['florian.hoenicke@jina.ai']
        response = requests.post(
            update_emails_url,
            json=request_body,
        )
        assert response.status_code == 200

        print('# test api keys')
        print('# search with invalid api key')
        request_body = get_request_body()
        request_body['query'] = {'query_text': {'text': 'girl on motorbike'}}
        del request_body['jwt']
        request_body['api_key'] = API_KEY
        request_body['limit'] = 9
        assert_search(SEARCH_URL, request_body, expected_status_code=500)
        print('# add api key')
        request_body_update_keys = get_request_body()
        request_body_update_keys['api_keys'] = [API_KEY]
        response = requests.post(
            update_api_keys_url,
            json=request_body_update_keys,
        )
        if response.status_code != 200:
            print(response.text)
            print(response.json()['message'])
            raise Exception(f'Response status is {response.status_code}')
        print('# the same search should work now')
        assert_search(SEARCH_URL, request_body)
