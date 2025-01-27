import base64
import os
from copy import deepcopy
from tempfile import TemporaryDirectory

import filetype
from docarray import Document, DocumentArray
from fastapi import HTTPException, status
from jina import Client
from jina.excepts import BadServer

from now.now_dataclasses import UserInput


def field_dict_to_mm_doc(
    field_dict: dict, data_class: type, field_names_to_dataclass_fields={}
) -> Document:
    """Converts a dictionary of field names to their values to a document.

    :param field_dict: key-value pairs of field names and their values
    :param data_class: @docarray.dataclass class which encapsulates the fields of the multimodal document
    :param field_names_to_dataclass_fields: mapping of field names to data class fields (e.g. {'title': 'text_0'})
    :return: multi-modal document
    """
    if len(field_dict) != 1:
        raise ValueError(
            f"Multi-modal document isn't supported yet. "
            f"Can only set one value but have {list(field_dict.keys())}"
        )

    with TemporaryDirectory() as tmp_dir:
        try:
            if field_names_to_dataclass_fields:
                field_dict_orig = deepcopy(field_dict)
                field_dict = {
                    field_name_data_class: field_dict_orig[file_name]
                    for file_name, field_name_data_class in field_names_to_dataclass_fields.items()
                }
            data_class_kwargs = {}
            for field_name_data_class, field_value in field_dict.items():
                # save blob into a temporary file such that it can be loaded by the multimodal class
                if field_value.blob:
                    base64_decoded = base64.b64decode(field_value.blob.encode('utf-8'))
                    file_ending = filetype.guess(base64_decoded).extension
                    file_path = os.path.join(
                        tmp_dir, field_name_data_class + '.' + file_ending
                    )
                    with open(file_path, 'wb') as f:
                        f.write(base64_decoded)
                    field_value.blob = None
                    field_value.uri = file_path
                data_class_kwargs[field_name_data_class] = field_value.content
            doc = Document(data_class(**data_class_kwargs))
        except BaseException as e:
            raise HTTPException(
                status_code=500,
                detail=f'Not a correctly encoded request. Please see the error stack for more information. \n{e}',
            )

    return doc


def get_jina_client(host: str, port: int) -> Client:
    if 'wolf.jina.ai' in host or 'dev.jina.ai' in host:
        return Client(host=host)
    else:
        return Client(host=host, port=port)


def jina_client_post(
    request_model,
    endpoint: str,
    inputs: DocumentArray,
    parameters=None,
    *args,
    **kwargs,
) -> DocumentArray:
    """Posts to the endpoint of the Jina client.

    :param request_model: contains the request model of the flow
    :param endpoint: endpoint which shall be called, e.g. '/index' or '/search'
    :param inputs: document(s) which shall be passed in
    :param parameters: parameters to pass to the executors, e.g. jwt for securitization or limit for search
    :param args: any additional arguments passed to the `client.post` method
    :param kwargs: any additional keyword arguments passed to the `client.post` method
    :return: response of `client.post`
    """
    if parameters is None:
        parameters = {}
    client = get_jina_client(host=request_model.host, port=request_model.port)
    auth_dict = {}
    if request_model.api_key is not None:
        auth_dict['api_key'] = request_model.api_key
    if request_model.jwt is not None:
        auth_dict['jwt'] = request_model.jwt
    try:
        result = client.post(
            endpoint,
            inputs=inputs,
            parameters={
                **auth_dict,
                **parameters,
                'access_paths': '@cc',
            },
            *args,
            **kwargs,
        )
    except BadServer as e:
        if 'Not a valid user' in e.args[0].status.description:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='You are not authorised to use this flow',
            )
        else:
            raise e
    return result


def fetch_user_input(request_model) -> UserInput:
    """Fetches the user input from the preprocessor.

    :param request_model: contains the request model of the flow
    :return: user input
    """
    client = get_jina_client(host=request_model.host, port=request_model.port)
    auth_dict = {}
    if request_model.api_key is not None:
        auth_dict['api_key'] = request_model.api_key
    if request_model.jwt is not None:
        auth_dict['jwt'] = request_model.jwt
    user_input_flow_response = client.post(
        '/get_user_input',
        inputs=DocumentArray(),
        parameters=auth_dict,
        target_executor=r'\Apreprocessor\Z',
        return_responses=True,
    )[0].parameters
    user_input_dict = list(user_input_flow_response['__results__'].values())[0][
        'user_input'
    ]
    user_input = UserInput(**user_input_dict)

    return user_input
