import numpy as np
from docarray import DocumentArray, Document

from src.data_loading.embed_datasets import to_jpg


def test_to_jpg():
    da = DocumentArray([Document(tensor=np.zeros((200, 200, 3), dtype=np.uint8))])
    to_jpg(da)
    assert da