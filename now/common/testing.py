import os

from now.constants import EXECUTOR_PREFIX


def handle_test_mode(config):
    if os.environ.get('NOW_TESTING', False):
        from now.executor.autocomplete import NOWAutoCompleteExecutor2
        from now.executor.indexer.in_memory import InMemoryIndexer
        from now.executor.preprocessor import NOWPreprocessor

        # this is a hack to make sure the import is not removed
        if NOWPreprocessor and NOWAutoCompleteExecutor2 and InMemoryIndexer:
            pass

        for k, v in config.items():
            if not (isinstance(v, str) and v.startswith(EXECUTOR_PREFIX)):
                continue
            # replace only those executor config values which you want to locally test
            if k == 'INDEXER_NAME':
                config[k] = 'InMemoryIndexer'
            elif k == 'AUTOCOMPLETE_EXECUTOR_NAME':
                config[k] = 'NOWAutoCompleteExecutor2'
            elif k == 'PREPROCESSOR_NAME':
                config[k] = 'NOWPreprocessor'
            else:
                continue
