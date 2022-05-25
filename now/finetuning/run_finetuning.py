""" This module is the entry point to the finetuning package."""
import os
import tempfile
import warnings
from contextlib import contextmanager
from copy import deepcopy
from os.path import join as osp

import finetuner
from docarray import DocumentArray
from docarray.math.evaluation import ndcg_at_k
from finetuner.tuner.callback import (
    BestModelCheckpoint,
    EarlyStopping,
    EvaluationCallback,
)
from finetuner.tuner.pytorch.losses import TripletLoss
from finetuner.tuner.pytorch.miner import TripletEasyHardMiner
from yaspin import yaspin

from now.constants import Modalities
from now.dialog import UserInput
from now.finetuning.dataset import FinetuneDataset, build_finetuning_dataset
from now.finetuning.embeddings import embed_now
from now.finetuning.settings import FinetuneSettings
from now.hub.head_encoder.head_encoder import LinearHead, get_bi_modal_embedding
from now.hub.hub import push_to_hub
from now.improvements.improvements import show_improvement
from now.utils import sigmap

_BASE_SAVE_DIR = 'now/hub/head_encoder'


def finetune_now(
    user_input: UserInput,
    dataset: DocumentArray,
    finetune_settings: FinetuneSettings,
    kubectl_path: str,
):
    """
    TODO: Write docs at the end

    :param user_input:
    :param dataset:
    :param finetune_settings:
    :param kubectl_path:
    :return:
    """
    dataset = _maybe_add_embeddings(user_input, dataset, kubectl_path)

    dataset = dataset.shuffle(42)

    if finetune_settings.bi_modal:
        _prepare_dataset_bi_modal(dataset)

    finetune_ds = build_finetuning_dataset(dataset, finetune_settings)

    with _finetune_dir() as save_dir:

        finetuned_model_path = _finetune_layer(finetune_ds, finetune_settings, save_dir)

        if (
            "NOW_CI_RUN" not in os.environ
            and user_input.output_modality == Modalities.IMAGE
        ):
            _show_finetune_improvements(
                user_input, finetune_settings, finetune_ds, finetuned_model_path
            )

        executor_name = push_to_hub(save_dir)
    return executor_name


def _finetune_layer(
    finetune_ds: FinetuneDataset, finetune_settings: FinetuneSettings, save_dir: str
) -> str:
    for ds_name, ds in finetune_ds.as_dict().items():
        for doc in ds:
            doc.tensor = doc.embedding
            doc.embedding = None

    assert all([d.embedding is not None for d in finetune_ds.index])

    save_dir = os.path.join(save_dir, 'now', 'hub', 'head_encoder')
    os.makedirs(save_dir, exist_ok=True)

    callbacks = [
        EvaluationCallback(
            finetune_ds.val_query,
            finetune_ds.val_index,
            limit=finetune_settings.eval_match_limit,
            num_workers=8,
            metrics={'ndcg': (ndcg_at_k, {})},
        ),
        BestModelCheckpoint(monitor='ndcg', save_dir=save_dir),
        EarlyStopping(
            monitor='ndcg',
            verbose=False,
            patience=finetune_settings.early_stopping_patience,
        ),
    ]

    print('💪 fine-tuning:')
    input_size = (
        finetune_settings.pre_trained_embedding_size
        if not finetune_settings.bi_modal
        else finetune_settings.pre_trained_embedding_size * 2
    )
    head = LinearHead(input_size, finetune_settings.finetune_layer_size)

    finetuner.fit(
        head,
        train_data=finetune_ds.train,
        eval_data=finetune_ds.val,
        epochs=finetune_settings.epochs,
        learning_rate=finetune_settings.learning_rate,
        batch_size=finetune_settings.batch_size,
        loss=TripletLoss(
            miner=TripletEasyHardMiner(
                pos_strategy=finetune_settings.pos_mining_strat,
                neg_strategy=finetune_settings.neg_mining_strat,
            ),
        ),
        num_items_per_class=finetune_settings.num_items_per_class,
        callbacks=callbacks,
    )
    print('🧠 Perfect! Early stopping triggered since accuracy is great already')

    return os.path.join(save_dir, 'best_model_ndcg')


@contextmanager
def _finetune_dir() -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        full_save_path = osp(tmpdir, _BASE_SAVE_DIR)
        os.makedirs(full_save_path, exist_ok=True)
        yield full_save_path


def _maybe_add_embeddings(
    user_input: UserInput, dataset: DocumentArray, kubectl_path: str
):
    with yaspin(
        sigmap=sigmap, text="Check if embeddings already exist", color="green"
    ) as spinner:
        if all([d.embedding is not None for d in dataset]):
            spinner.ok('👍')
            return dataset
        else:
            spinner.fail('👎')

    embed_now(user_input, dataset, kubectl_path=kubectl_path)

    assert all([d.embedding is not None for d in dataset]), (
        "Some docs slipped through and" " still have no embedding..."
    )


def _prepare_dataset_bi_modal(dataset: DocumentArray):
    for doc in dataset:
        doc.embedding = get_bi_modal_embedding(doc)


def _show_finetune_improvements(
    user_input: UserInput,
    finetune_settings: FinetuneSettings,
    finetune_ds: FinetuneDataset,
    finetuned_model_path: str,
):
    def restore_content_attribute():
        for doc in finetune_ds.val:
            index_doc = finetune_ds.index[doc.id]
            if index_doc.text:
                doc.text = index_doc.text
            elif index_doc.blob:
                doc.blob = index_doc.blob

    restore_content_attribute()
    val_index_image = deepcopy(DocumentArray(d for d in finetune_ds.val if d.blob))
    val_query_image = deepcopy(
        val_index_image.sample(k=finetune_settings.num_val_queries, seed=42)
    )
    with yaspin(sigmap=sigmap, text="Create overview", color="green") as spinner:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                show_improvement(
                    user_input.data,
                    user_input.quality,
                    val_query_image,
                    val_index_image,
                    finetune_ds.val_query,
                    finetune_ds.val_index,
                    finetune_settings.pre_trained_embedding_size,
                    finetune_settings.finetune_layer_size,
                    finetuned_model_path,
                    class_label='finetuner_label',
                )
        except Exception as e:
            pass
        spinner.ok('🖼')
        print(
            f'before-after comparison result is saved in the current working directory as image'
        )