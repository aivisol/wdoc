"""
Main class.
"""

# import this first because it sets the logging level
from .utils.logger import whi, yel, red, md_printer, log, set_docstring

import json
import pyfiglet
import copy
from textwrap import indent
from functools import wraps
from typing import List, Union, Any, Optional, Callable
from typeguard import typechecked, check_type, TypeCheckError
import tldextract
from joblib import Parallel, delayed
from threading import Lock
from pathlib import Path
import time
from datetime import datetime
import re
import textwrap
import os
import asyncio
from tqdm import tqdm
import lazy_import

# cannot be lazy loaded because some are not callable but objects directly
from .utils.misc import (
    ankiconnect, debug_chain, model_name_matcher,
    cache_dir, average_word_length, wpm, get_splitter,
    check_docs_tkn_length, get_tkn_length,
    extra_args_keys, disable_internet)
from .utils.prompts import PR_CONDENSE_QUESTION, PR_EVALUATE_DOC, PR_ANSWER_ONE_DOC, PR_COMBINE_INTERMEDIATE_ANSWERS
from .utils.tasks.query import format_chat_history, refilter_docs, check_intermediate_answer, parse_eval_output, doc_eval_cache

# lazy loading from local files
NoDocumentsRetrieved = lazy_import.lazy_class("DocToolsLLM.utils.errors.NoDocumentsRetrieved")
NoDocumentsAfterLLMEvalFiltering = lazy_import.lazy_class("DocToolsLLM.utils.errors.NoDocumentsAfterLLMEvalFiltering")
do_summarize = lazy_import.lazy_function("DocToolsLLM.utils.tasks.summary.do_summarize")
optional_typecheck = lazy_import.lazy_function("DocToolsLLM.utils.typechecker.optional_typecheck")
load_llm = lazy_import.lazy_function("DocToolsLLM.utils.llm.load_llm")
AnswerConversationBufferMemory = lazy_import.lazy_class("DocToolsLLM.utils.llm.AnswerConversationBufferMemory")
ask_user = lazy_import.lazy_function("DocToolsLLM.utils.interact.ask_user")
create_hyde_retriever = lazy_import.lazy_function("DocToolsLLM.utils.retrievers.create_hyde_retriever")
create_parent_retriever = lazy_import.lazy_function("DocToolsLLM.utils.retrievers.create_parent_retriever")
load_embeddings = lazy_import.lazy_function("DocToolsLLM.utils.embeddings.load_embeddings")
batch_load_doc = lazy_import.lazy_module("DocToolsLLM.utils.batch_file_loader").batch_load_doc

# lazy imports
set_verbose = lazy_import.lazy_function("langchain.globals.set_verbose")
set_debug = lazy_import.lazy_function("langchain.globals.set_debug")
set_llm_cache = lazy_import.lazy_function("langchain.globals.set_llm_cache")
MergerRetriever = lazy_import.lazy_class("langchain.retrievers.merger_retriever.MergerRetriever")
Document = lazy_import.lazy_class("langchain.docstore.document.Document")
EmbeddingsRedundantFilter = lazy_import.lazy_class("langchain_community.document_transformers.EmbeddingsRedundantFilter")
DocumentCompressorPipeline = lazy_import.lazy_class("langchain.retrievers.document_compressors.DocumentCompressorPipeline")
ContextualCompressionRetriever = lazy_import.lazy_class("langchain.retrievers.ContextualCompressionRetriever")
from langchain_community.retrievers import KNNRetriever, SVMRetriever
SQLiteCache = lazy_import.lazy_class("langchain_community.cache.SQLiteCache")
from operator import itemgetter
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
chain = lazy_import.lazy_class("langchain_core.runnables.chain")
RunnableEach = lazy_import.lazy_class("langchain_core.runnables.base.RunnableEach")
StrOutputParser = lazy_import.lazy_class("langchain_core.output_parsers.string.StrOutputParser")
BaseGenerationOutputParser = lazy_import.lazy_class("langchain_core.output_parsers.BaseGenerationOutputParser")
Generation = lazy_import.lazy_class("langchain_core.outputs.Generation")
ChatGeneration = lazy_import.lazy_class("langchain_core.outputs.ChatGeneration")
litellm = lazy_import.lazy_module("litellm")


os.environ["TOKENIZERS_PARALLELISM"] = "true"

@set_docstring
class DocToolsLLM_class:
    "This docstring is dynamically replaced by the content of DocToolsLLM/docs/USAGE.md"

    VERSION: str = "0.27"

    #@optional_typecheck
    @typechecked
    def __init__(
        self,
        task: str,
        filetype: str = "infer",

        modelname: str = "openai/gpt-4o",
        # modelname: str = "openai/gpt-3.5-turbo-0125",
        # modelname: str = "mistral/mistral-large-latest",

        embed_model: str = "openai/text-embedding-3-small",
        # embed_model: str =  "sentencetransformers/BAAI/bge-m3",
        # embed_model: str =  "sentencetransformers/paraphrase-multilingual-mpnet-base-v2",
        # embed_model: str =  "sentencetransformers/distiluse-base-multilingual-cased-v1",
        # embed_model: str =  "sentencetransformers/msmarco-distilbert-cos-v5",
        # embed_model: str =  "sentencetransformers/all-mpnet-base-v2",
        # embed_model: str =  "huggingface/google/gemma-2b",
        embed_kwargs: Optional[dict] = None,
        save_embeds_as: str = "{user_cache}/latest_docs_and_embeddings",
        load_embeds_from: Optional[str] = None,
        top_k: int = 20,

        query: Optional[Union[str, bool]] = None,
        query_retrievers: str = "default",
        query_eval_modelname: Optional[str] = "openai/gpt-3.5-turbo",
        # query_eval_modelname: str = "mistral/open-mixtral-8x7b",
        # query_eval_modelname: str = "mistral/open-small",
        query_eval_check_number: int = 3,
        query_relevancy: float = 0.1,
        query_condense_question: bool = True,

        summary_n_recursion: int = 0,
        summary_language: str = "[same as input]",

        llm_verbosity: bool = False,
        debug: bool = False,
        dollar_limit: int = 5,
        notification_callback: Optional[Callable] =  None,
        chat_memory: bool = True,
        no_llm_cache: bool = False,
        file_loader_parallel_backend: str = "loky",
        private: bool = False,
        llms_api_bases: Optional[Union[dict, str]] = None,
        DIY_rolling_window_embedding: bool = False,
        import_mode: bool = False,

        **cli_kwargs,
        ) -> None:
        "This docstring is dynamically replaced by the content of DocToolsLLM/docs/USAGE.md"
        red(pyfiglet.figlet_format("DocToolsLLM"))
        log.info("Starting DocToolsLLM")

        # make sure the extra args are valid
        for k in cli_kwargs:
            if k not in extra_args_keys:
                raise Exception(red(f"Found unexpected keyword argument: '{k}'"))

            # type checking of extra args
            if os.environ["DOCTOOLS_TYPECHECKING"] in ["crash", "warn"]:
                val = cli_kwargs[k]
                curr_type = type(val)
                expected_type = extra_args_keys[k]
                if not check_type(val, expected_type):
                    if os.environ["DOCTOOLS_TYPECHECKING"] == "warn":
                        red(f"Invalid type in cli_kwargs: '{k}' is {val} of type {curr_type} instead of {expected_type}")
                    elif os.environ["DOCTOOLS_TYPECHECKING"] == "crash":
                        raise TypeCheckError(f"Invalid type in cli_kwargs: '{k}' is {val} of type {curr_type} instead of {expected_type}")
                if expected_type is str:
                    assert val.strip(), f"Empty string found for cli_kwargs: '{k}'"
                if isinstance(val, list):
                    assert val, f"Empty list found for cli_kwargs: '{k}'"

        # checking argument validity
        assert "loaded_docs" not in cli_kwargs, "'loaded_docs' cannot be an argument as it is used internally"
        assert "loaded_embeddings" not in cli_kwargs, "'loaded_embeddings' cannot be an argument as it is used internally"
        task = task.replace("summary", "summarize")
        assert task in ["query", "search", "summarize", "summarize_then_query"], "invalid task value"
        if task in ["summarize", "summarize_then_query"]:
            assert not load_embeds_from, "can't use load_embeds_from if task is summary"
        if task in ["query", "search", "summarize_then_query"]:
            assert query_eval_modelname is not None, "query_eval_modelname can't be None if doing RAG"
        else:
            query_eval_modelname = None
        if filetype == "infer":
            assert "path" in cli_kwargs and cli_kwargs["path"], "If filetype is 'infer', a --path must be given"
        assert "/" in embed_model, "embed model must contain slash"
        assert embed_model.split("/", 1)[0] in ["openai", "sentencetransformers", "huggingface", "llamacppembeddings"], "Backend of embeddings must be either openai, sentencetransformers, huggingface of llamacppembeddings"
        if embed_kwargs is None:
            embed_kwargs = {}
        if isinstance(embed_kwargs, str):
            try:
                embed_kwargs = json.loads(embed_kwargs)
            except Exception as err:
                raise Exception(f"Failed to parse embed_kwargs: '{embed_kwargs}'")
        assert isinstance(embed_kwargs, dict), f"Not a dict but {type(embed_kwargs)}"
        assert query_eval_check_number > 0, "query_eval_check_number value"

        if llms_api_bases is None:
            llms_api_bases = {}
        elif isinstance(llms_api_bases, str):
            try:
                llms_api_bases = json.loads(llms_api_bases)
            except Exception as err:
                raise Exception(f"Error when parsing llms_api_bases as a dict: {err}")
        assert isinstance(llms_api_bases, dict), "llms_api_bases must be a dict"
        for k in llms_api_bases:
            assert k in ["model", "query_eval_model"], (
                f"Invalid k of llms_api_bases: {k}")
        for k in ["model", "query_eval_model"]:
            if k not in llms_api_bases:
                llms_api_bases[k] = None
        if llms_api_bases["model"] == llms_api_bases["query_eval_model"] and llms_api_bases["model"]:
            red("Setting litellm wide api_base because it's the same for model and query_eval_model")
            litellm.api_base = llms_api_bases["model"]
        assert isinstance(private, bool), "private arg should be a boolean, not {private}"
        if private:
            assert llms_api_bases["model"], "private is set but llms_api_bases['model'] is not set"
            assert llms_api_bases["query_eval_model"], "private is set but llms_api_bases['query_eval_model'] is not set"
            os.environ["DOCTOOLS_PRIVATEMODE"] = "true"
            for k in dict(os.environ):
                if k.endswith("_API_KEY") or k.endswith("_API_KEYS"):
                    red(f"private mode enabled: overwriting '{k}' from environment variables just in case")
                    os.environ[k] = "REDACTED_BECAUSE_DOCTOOLSLLM_IN_PRIVATE_MODE"

            # to be extra safe, let's try to block any remote connection
            disable_internet(
                allowed=llms_api_bases,
            )

        else:
            os.environ["DOCTOOLS_PRIVATEMODE"] = "false"

        if (not modelname.startswith("testing/")) and (not llms_api_bases["model"]):
            modelname = model_name_matcher(modelname)
        if (query_eval_modelname is not None) and (not llms_api_bases["query_eval_model"]):
            if modelname.startswith("testing/"):
                if not query_eval_modelname.startswith("testing/"):
                    query_eval_modelname = "testing/testing"
                    red(f"modelname uses 'testing' backend so setting query_eval_modelname to '{query_eval_modelname}'")
            else:
                assert not query_eval_modelname.startswith("testing/"), "query_eval_modelname can't use 'testing' backend if modelname isn't set to testing too"
                query_eval_modelname = model_name_matcher(query_eval_modelname)

        if query is True:
            # otherwise specifying --query and forgetting to add text fails
            query = None
        if isinstance(query, str):
            query = query.strip() or None
        assert file_loader_parallel_backend in ["loky", "threading"], "Invalid value for file_loader_parallel_backend"
        if "{user_cache}" in save_embeds_as:
            save_embeds_as = save_embeds_as.replace("{user_cache}", str(cache_dir))

        if debug:
            llm_verbosity = True

        # storing as attributes
        self.modelbackend = modelname.split("/")[0].lower() if "/" in modelname else "openai"
        self.modelname = modelname
        if query_eval_modelname is not None:
            self.query_eval_modelbackend = query_eval_modelname.split("/")[0].lower() if "/" in modelname else "openai"
            self.query_eval_modelname = query_eval_modelname
        self.task = task
        self.filetype = filetype
        self.embed_model = embed_model
        self.embed_kwargs = embed_kwargs
        self.save_embeds_as = save_embeds_as
        self.load_embeds_from = load_embeds_from
        self.top_k = top_k
        self.query_retrievers = query_retrievers if "testing" not in modelname else query_retrievers.replace("hyde", "")
        self.query_eval_check_number = int(query_eval_check_number)
        self.query_relevancy = query_relevancy
        self.debug = debug
        self.cli_kwargs = cli_kwargs
        self.llm_verbosity = llm_verbosity
        self.summary_n_recursion = summary_n_recursion
        self.summary_language = summary_language
        self.dollar_limit = dollar_limit
        self.query_condense_question = bool(query_condense_question) if "testing" not in modelname else False
        self.chat_memory = chat_memory if "testing" not in modelname else False
        self.private = bool(private)
        self.no_llm_cache = bool(no_llm_cache)
        self.file_loader_parallel_backend = file_loader_parallel_backend
        self.llms_api_bases = llms_api_bases
        self.DIY_rolling_window_embedding = bool(DIY_rolling_window_embedding)
        self.import_mode = import_mode

        if not no_llm_cache:
            if not private:
                set_llm_cache(SQLiteCache(database_path=cache_dir / "langchain.db"))
            else:
                set_llm_cache(SQLiteCache(database_path=cache_dir / "private_langchain.db"))

        if llms_api_bases["model"]:
            red(f"Disabling price computation for model because api_base was modified")
            self.llm_price = [0, 0]
        elif modelname in litellm.model_cost:
            self.llm_price = [
                litellm.model_cost[modelname]["input_cost_per_token"],
                litellm.model_cost[modelname]["output_cost_per_token"]
            ]
        elif modelname.split("/")[1] in litellm.model_cost:
            self.llm_price = [
                litellm.model_cost[modelname.split("/")[1]]["input_cost_per_token"],
                litellm.model_cost[modelname.split("/")[1]]["output_cost_per_token"]
            ]
        else:
            raise Exception(red(f"Can't find the price of {modelname}"))
        if query_eval_modelname is not None:
            if llms_api_bases["query_eval_model"]:
                red(f"Disabling price computation for query_eval_model because api_base was modified")
                self.query_evalllm_price = [0, 0]
            elif query_eval_modelname in litellm.model_cost:
                self.query_evalllm_price = [
                    litellm.model_cost[query_eval_modelname]["input_cost_per_token"],
                    litellm.model_cost[query_eval_modelname]["output_cost_per_token"]
                ]
            elif query_eval_modelname.split("/")[1] in litellm.model_cost:
                self.query_evalllm_price = [
                    litellm.model_cost[query_eval_modelname.split("/")[1]]["input_cost_per_token"],
                    litellm.model_cost[query_eval_modelname.split("/")[1]]["output_cost_per_token"]
                ]
            else:
                raise Exception(red(f"Can't find the price of {query_eval_modelname}"))

        if notification_callback is not None:
            @optional_typecheck
            def ntfy(text: str) -> str:
                out = notification_callback(text)
                assert out == text, "The notification callback must return the same string"
                return out
            ntfy("Starting DocToolsLLM")
        else:
            @optional_typecheck
            def ntfy(text: str) -> str:
                return text
            self.ntfy = ntfy

        if self.debug:
            # os.environ["LANGCHAIN_TRACING_V2"] = "true"
            set_verbose(True)
            set_debug(True)
            cli_kwargs["file_loader_n_jobs"] = 1
            litellm.set_verbose=True
        else:
            litellm.set_verbose=False
            # fix from https://github.com/BerriAI/litellm/issues/2256
            import logging
            for logger_name in ["LiteLLM Proxy", "LiteLLM Router", "LiteLLM"]:
                logger = logging.getLogger(logger_name)
                # logger.setLevel(logging.CRITICAL + 1)
                logger.setLevel(logging.WARNING)

        # don't crash if extra arguments are used for a model
        # litellm.drop_params = True  # drops parameters that are not used by some models

        # compile include / exclude regex
        if "include" in self.cli_kwargs:
            for i, inc in enumerate(self.cli_kwargs["include"]):
                if inc == inc.lower():
                    self.cli_kwargs["include"][i] = re.compile(inc, flags=re.IGNORECASE)
                else:
                    self.cli_kwargs["include"][i] = re.compile(inc)
        if "exclude" in self.cli_kwargs:
            for i, exc in enumerate(self.cli_kwargs["exclude"]):
                if exc == exc.lower():
                    self.cli_kwargs["exclude"][i] = re.compile(exc, flags=re.IGNORECASE)
                else:
                    self.cli_kwargs["exclude"][i] = re.compile(exc)

        # loading llm
        self.llm = load_llm(
            modelname=modelname,
            backend=self.modelbackend,
            no_llm_cache=self.no_llm_cache,
            temperature=0,
            verbose=self.llm_verbosity,
            api_base=self.llms_api_bases["model"],
            private=self.private,
        )

        # loading documents
        if not load_embeds_from:
            self.loaded_docs = batch_load_doc(
                filetype=self.filetype,
                task=self.task,
                backend=self.file_loader_parallel_backend,
                **self.cli_kwargs)

            # check that the hash are unique
            if len(self.loaded_docs) > 1:
                ids = [id(d.metadata) for d in self.loaded_docs]
                assert len(ids) == len(set(ids)), (
                        "Same metadata object is used to store information on "
                        "multiple documents!")

                hashes = [d.metadata["hash"] for d in self.loaded_docs]
                uniq_hashes = list(set(hashes))
                removed_paths = []
                removed_docs = []
                counter = {h: hashes.count(h) for h in uniq_hashes}
                if len(hashes) != len(uniq_hashes):
                    red("Found duplicate hashes after loading documents:")

                    for i, doc in enumerate(tqdm(self.loaded_docs, desc="Looking for duplicates")):
                        h = doc.metadata['hash']
                        n = counter[h]
                        if n > 1:
                            removed_docs.append(self.loaded_docs[i])
                            self.loaded_docs[i] = None
                            counter[h] -= 1
                        assert counter[h] > 0
                    red(f"Removed {len(removed_docs)}/{len(hashes)} documents because they had the same hash")

                    # check if deduplication likely amputated documents
                    self.loaded_docs = [d for d in self.loaded_docs if d is not None]
                    present_path = [d.metadata["path"] for d in self.loaded_docs]

                    intersect = set(removed_paths).intersection(set(present_path))
                    if intersect:
                        red(f"Found {len(intersect)} documents that were only partially removed, this results in incomplete documents.")
                        for i, inte in enumerate(intersect):
                            red(f"  * #{i + 1}: {inte}")
                        raise Exception()
                    else:
                        red(f"Removed {len(removed_paths)}/{len(hashes)} documents because they had the same hash")

        else:
            self.loaded_docs = None  # will be loaded when embeddings are loaded

        if self.task in ["summarize", "summarize_then_query"]:
            self._summary_task()

            if self.task == "summary_then_query":
                whi("Done summarizing. Switching to query mode.")
                if self.modelbackend == "openai":
                    del self.llm.model_kwargs["logit_bias"]
            else:
                whi("Done summarizing. Exiting.")
                raise SystemExit()

        assert self.task in ["query", "search", "summary_then_query"], f"Invalid task: {self.task}"
        self.prepare_query_task()

        if not self.import_mode:
            while True:
                self._query(query=query)
                query = None
        else:
            whi("Ready to query, call your_instance._query(your_question)")

    def _summary_task(self):
        docs_tkn_cost = {}
        for doc in self.loaded_docs:
            meta = doc.metadata["path"]
            if meta not in docs_tkn_cost:
                docs_tkn_cost[meta] = get_tkn_length(doc.page_content)
            else:
                docs_tkn_cost[meta] += get_tkn_length(doc.page_content)

        full_tkn = sum(list(docs_tkn_cost.values()))
        red("Token price of each document:")
        for k, v in docs_tkn_cost.items():
            pr = v * (self.llm_price[0] * 4 + self.llm_price[1]) / 5
            red(f"- {v:>6}: {k:>10} - ${pr:04f}")

        red(f"Total number of tokens in documents to summarize: '{full_tkn}'")
        # use an heuristic to estimate the price to summarize
        adj_price = (self.llm_price[0] * 3 + self.llm_price[1] * 2) / 5
        estimate_dol = full_tkn * adj_price / 100 * 1.2
        if self.summary_n_recursion:
            for i in range(1, self.summary_n_recursion + 1):
                estimate_dol += full_tkn * ((2/5) ** i) * adj_price / 100 * 1.2
        whi(self.ntfy(f"Estimate of the LLM cost to summarize: ${estimate_dol:.4f} for {full_tkn} tokens."))
        if estimate_dol > self.dollar_limit:
            if self.llms_api_bases["model"]:
                raise Exception(red(self.ntfy(f"Cost estimate ${estimate_dol:.5f} > ${self.dollar_limit} which is absurdly high. Has something gone wrong? Quitting.")))
            else:
                red(f"Cost estimate > limit but the api_base was modified so not crashing.")

        if self.modelbackend == "openai":
            # increase likelyhood that chatgpt will use indentation by
            # biasing towards adding space.
            logit_val = 3
            self.llm.model_kwargs["logit_bias"] = {
                12: logit_val,  # '-'
                # 220: logit_val,  # ' '
                # 532: logit_val,  # ' -'
                # 9: logit_val,  # '*'
                # 1635: logit_val,  # ' *'
                # 197: logit_val,  # '\t'
                334: logit_val,  # '**'
                # 25: logit_val,  # ':'
                # 551: logit_val,  # ' :'
                # 13: -1,  # '.'
                # logit bias for indentation, the number of space, because it consumes less token than using \t
                257: logit_val,      # "    "
                260: logit_val,      # "        "
                1835: logit_val,     # "            "
                338: logit_val,      # "                "
                3909: logit_val,     # "                    "
                5218: logit_val,     # "                        "
                6663: logit_val,     # "                            "
                792: logit_val,      # "                                "
                10812: logit_val,    # "                                    "
                13137: logit_val,    # "                                        "
                15791: logit_val,    # "                                            "
                19273: logit_val,    # "                                                "
                25343: logit_val,    # "                                                    "
                29902: logit_val,    # "                                                        "
                39584: logit_val,    # "                                                            "
                5341: logit_val,     # "                                                                "
                52168: logit_val,    # "                                                                    "
                38244: logit_val,    # "                                                                        "
                56899: logit_val,    # "                                                                            "
                98517: logit_val,    # "                                                                                "
                }
            self.llm.model_kwargs["frequency_penalty"] = 0.0
            self.llm.model_kwargs["presence_penalty"] = 0.0
            self.llm.model_kwargs["temperature"] = 0.0

        @optional_typecheck
        def summarize_documents(
            path: Any,
            relevant_docs: List,
            ) -> dict:
            assert relevant_docs, 'Empty relevant_docs!'

            # parse metadata from the doc
            metadata = []
            if "http" in path:
                item_name = tldextract.extract(path).registered_domain
            elif "/" in path and Path(path).exists():
                item_name = Path(path).name
            else:
                item_name = path

            if "title" in relevant_docs[0].metadata:
                item_name = f"{relevant_docs[0].metadata['title'].strip()} - {item_name}"
            else:
                metadata.append(f"Title: '{item_name.strip()}'")


            # replace # in title as it would be parsed as a tag
            item_name = item_name.replace("#", r"\#")

            if "docs_reading_time" in relevant_docs[0].metadata:
                doc_reading_length = relevant_docs[0].metadata["docs_reading_time"]
                metadata.append(f"Reading length: {doc_reading_length:.1f} minutes")
            else:
                doc_reading_length = None
            if "author" in relevant_docs[0].metadata:
                author = relevant_docs[0].metadata["author"].strip()
                metadata.append(f"Author: '{author}'")
            else:
                author = None

            if metadata:
                metadata = "- Text metadata:\n    - " + "\n    - ".join(metadata) + "\n"
                metadata += "    - Section number: [PROGRESS]\n"
            else:
                metadata = ""

            splitter = get_splitter("recursive_summary", modelname=self.modelname)

            # summarize each chunk of the link and return one text
            summary, n_chunk, doc_total_tokens, doc_total_cost = do_summarize(
                    docs=relevant_docs,
                    metadata=metadata,
                    language=self.summary_language,
                    modelbackend=self.modelbackend,
                    llm=self.llm,
                    llm_price=self.llm_price,
                    verbose=self.llm_verbosity,
                    )

            # get reading length of the summary
            real_text = "".join([letter for letter in list(summary) if letter.isalpha()])
            sum_reading_length = len(real_text) / average_word_length / wpm
            whi(f"{item_name} reading length is {sum_reading_length:.1f}")

            n_recursion_done = 0
            recursive_summaries = {n_recursion_done: summary}
            if self.summary_n_recursion > 0:
                summary_text = summary

                for n_recur in range(1, self.summary_n_recursion + 1):
                    red(f"Doing recursive summary #{n_recur} of {item_name}")

                    # remove any chunk count that is not needed to summarize
                    sp = summary_text.split("\n")
                    for i, l in enumerate(sp):
                        if l.strip() == "- ---":
                            sp[i] = None
                        elif re.search(r"- Chunk \d+/\d+", l):
                            sp[i] = None
                        elif l.strip().startswith("- BEFORE RECURSION #"):
                            for new_i in range(i, len(sp)):
                                sp[new_i] = None
                            break
                    summary_text = "\n".join([s.rstrip() for s in sp if s])
                    assert "- ---" not in summary_text, "Found chunk separator"
                    assert "- Chunk " not in summary_text, "Found chunk marker"
                    assert "- BEFORE RECURSION # " not in summary_text, "Found recursion block"

                    summary_docs = [Document(page_content=summary_text)]
                    summary_docs = splitter.transform_documents(summary_docs)
                    try:
                        check_docs_tkn_length(summary_docs, item_name)
                    except Exception as err:
                        red(f"Exception when checking if {item_name} could be recursively summarized for the #{n_recur} time: {err}")
                        break
                    summary_text, n_chunk, new_doc_total_tokens, new_doc_total_cost = do_summarize(
                            docs=summary_docs,
                            metadata=metadata,
                            language=self.summary_language,
                            modelbackend=self.modelbackend,
                            llm=self.llm,
                            llm_price=self.llm_price,
                            verbose=self.llm_verbosity,
                            n_recursion=n_recur,
                            )
                    doc_total_tokens += new_doc_total_tokens
                    doc_total_cost += new_doc_total_cost
                    n_recursion_done += 1

                    recursive_summaries[n_recursion_done] = summary_text

                    # clean text again to compute the reading length
                    sp = summary_text.split("\n")
                    for i, l in enumerate(sp):
                        if l.strip() == "- ---":
                            sp[i] = None
                        elif re.search(r"- Chunk \d+/\d+", l):
                            sp[i] = None
                        elif l.strip().startswith("- BEFORE RECURSION #"):
                            for new_i in range(i, len(sp)):
                                sp[new_i] = None
                            break
                    real_text = "\n".join([s.rstrip() for s in sp if s])
                    assert "- ---" not in real_text, "Found chunk separator"
                    assert "- Chunk " not in real_text, "Found chunk marker"
                    assert "- BEFORE RECURSION # " not in real_text, "Found recursion block"
                    real_text = "".join([letter for letter in list(real_text) if letter.isalpha()])
                    sum_reading_length = len(real_text) / average_word_length / wpm
                    whi(f"{item_name} reading length after recursion #{n_recur} is {sum_reading_length:.1f}")
                summary = summary_text

            print("\n\n")
            md_printer("# Summary")
            md_printer(f'## {path}')
            md_printer(summary)

            red(f"Tokens used for {path}: '{doc_total_tokens}' (${doc_total_cost:.5f})")

            summary_tkn_length = get_tkn_length(summary)

            header = f"\n- {item_name}    cost: {doc_total_tokens} (${doc_total_cost:.5f})"
            if doc_reading_length:
                header += f"    {doc_reading_length:.1f} minutes"
            if author:
                header += f"    by '{author}'"
            header += f"    original path: '{path}'"
            header += f"    DocToolsLLM version {self.VERSION} with model {self.modelname} of {self.modelbackend}"
            header += f"    parameters: n_recursion_summary={self.summary_n_recursion};n_recursion_done={n_recursion_done}"

            # save to output file
            if "out_file" in self.cli_kwargs:
                for nrecur, sum in recursive_summaries.items():
                    outfile = Path(self.cli_kwargs["out_file"])
                    if len(recursive_summaries) > 1 and nrecur < max(list(recursive_summaries.keys())):
                        # also store intermediate summaries if present
                        outfile = outfile.parent / (outfile.stem + f".{nrecur}.md")

                    with open(str(outfile), "a") as f:
                        if outfile.exists() and outfile.read_text().strip():
                            f.write("\n\n\n")
                        f.write(header)
                        for bulletpoint in sum.split("\n"):
                            f.write("\n")
                            bulletpoint = bulletpoint.rstrip()
                            # # make sure the line begins with a bullet point
                            # if not bulletpoint.lstrip().startswith("- "):
                            #     begin_space = re.search(r"^(\s+)", bulletpoint)
                            #     if not begin_space:
                            #         begin_space = [""]
                            #     bulletpoint = begin_space[0] + "- " + bulletpoint
                            f.write(f"    {bulletpoint}")

            return {
                    "path": path,
                    "sum_reading_length": sum_reading_length,
                    "doc_reading_length": doc_reading_length,
                    "doc_total_tokens": doc_total_tokens,
                    "doc_total_cost": doc_total_cost,
                    "summary": summary,
                    }

        results = summarize_documents(
            path=self.cli_kwargs["path"],
            relevant_docs=self.loaded_docs,
        )

        red(self.ntfy(f"Total cost of those summaries: '{results['doc_total_tokens']}' (${results['doc_total_cost']:.5f}, estimate was ${estimate_dol:.5f})"))
        red(self.ntfy(f"Total time saved by those summaries: {results['doc_reading_length']:.1f} minutes"))

        assert len(self.llm.callbacks) == 1, "Unexpected number of callbacks for llm"
        llmcallback = self.llm.callbacks[0]
        total_cost = self.llm_price[0] * llmcallback.prompt_tokens + self.llm_price[1] * llmcallback.completion_tokens
        if llmcallback.total_tokens != results['doc_total_tokens']:
            red(f"Discrepancy? Tokens used according to the callback: '{llmcallback.total_tokens}' (${total_cost:.5f})")

    def prepare_query_task(self):
        # load embeddings for querying
        self.loaded_embeddings, self.embeddings = load_embeddings(
            embed_model=self.embed_model,
            embed_kwargs=self.embed_kwargs,
            load_embeds_from=self.load_embeds_from,
            save_embeds_as=self.save_embeds_as,
            loaded_docs=self.loaded_docs,
            dollar_limit=self.dollar_limit,
            private=self.private,
            use_rolling=self.DIY_rolling_window_embedding,
            cli_kwargs=self.cli_kwargs,
        )

        # conversational memory
        self.memory = AnswerConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True)

        # set default ask_user argument
        self.interaction_settings = {
                "top_k": self.top_k,
                "multiline": False,
                "retriever": self.query_retrievers,
                "task": self.task,
                "relevancy": self.query_relevancy,
                }
        self.all_texts = [v.page_content for k, v in self.loaded_embeddings.docstore._dict.items()]

        # parse filters as callable for faiss filtering
        if "filter_metadata" in self.cli_kwargs or "filter_content" in self.cli_kwargs:
            if "filter_metadata" in self.cli_kwargs:
                if isinstance(self.cli_kwargs["filter_metadata"], str):
                    filter_metadata = self.cli_kwargs["filter_metadata"].split(",")
                else:
                    filter_metadata = self.cli_kwargs["filter_metadata"]
                assert isinstance(filter_metadata, list), f"filter_metadata must be a list, not {self.cli_kwargs['filter_metadata']}"

                # storing fast as list then in tupples for faster iteration
                filters_k_plus = []
                filters_k_minus = []
                filters_v_plus = []
                filters_v_minus = []
                filters_b_plus_keys = []
                filters_b_plus_values = []
                filters_b_minus_keys = []
                filters_b_minus_values = []
                for f in filter_metadata:
                    assert isinstance(f, str), f"Filter must be a string: '{f}'"
                    kvb = f[0]
                    assert kvb in ["k", "v", "b"], f"filter 1st character must be k, v or b: '{f}'"
                    incexc = f[1]
                    assert incexc in ["+", "-"], f"filter 2nd character must be + or -: '{f}'"
                    incexc_str = "plus" if incexc == "+" else "minus"
                    assert f[2:].strip(), f"Filter can't be an empty regex: '{f}'"
                    pattern = f[2:].strip()
                    if kvb == "b":
                        assert ":" in f, (
                            "Filter starting with b must contain "
                            "a ':' to distinguish the key regex and the value "
                            f"regex: '{f}'")
                        key_pat, value_pat = pattern.split(":", 1)
                        if key_pat == key_pat.lower():
                            key_pat = re.compile(key_pat, flags=re.IGNORECASE)
                        else:
                            key_pat = re.compile(key_pat)
                        if value_pat == value_pat.lower():
                            value_pat = re.compile(value_pat, flags=re.IGNORECASE)
                        else:
                            value_pat = re.compile(value_pat)
                        assert key_pat not in locals()[f"filters_b_{incexc_str}_keys"], (
                            f"Can't use several filters for the same key "
                            "regex. Use a single but more complex regex"
                            f": '{f}'"
                        )
                        locals()[f"filters_b_{incexc_str}_keys"].append(key_pat)
                        locals()[f"filters_b_{incexc_str}_values"].append(value_pat)
                    else:
                        if pattern == pattern.lower():
                            pattern = re.compile(pattern, flags=re.IGNORECASE)
                        else:
                            pattern = re.compile(pattern)
                        locals()[f"filters_{kvb}_{incexc_str}"].append(pattern)
                assert len(filters_b_plus_keys) == len(filters_b_plus_values)
                assert len(filters_b_minus_keys) == len(filters_b_minus_values)

                # store as tuple for faster iteration
                filters_k_plus = tuple(filters_k_plus)
                filters_k_minus = tuple(filters_k_minus)
                filters_v_plus = tuple(filters_v_plus)
                filters_v_minus = tuple(filters_v_minus)
                filters_b_plus_keys = tuple(filters_b_plus_keys)
                filters_b_plus_values = tuple(filters_b_plus_values)
                filters_b_minus_keys = tuple(filters_b_minus_keys)
                filters_b_minus_values = tuple(filters_b_minus_values)

                def filter_meta(meta: dict) -> bool:
                    # match keys
                    for inc in filters_k_plus:
                        if not any(inc.match(k) for k in meta.keys()):
                            return False
                    for exc in filters_k_minus:
                        if any(exc.match(k) for k in meta.keys()):
                            return False

                    # match values
                    for inc in filters_v_plus:
                        if not any(inc.match(v) for v in meta.values()):
                            return False
                    for exc in filters_v_minus:
                        if any(exc.match(v) for v in meta.values()):
                            return False

                    # match both
                    for kp, vp in zip(filters_b_plus_keys, filters_b_plus_values):
                        good_keys = (k for k in meta.keys() if kp.match(k))
                        gk_checked = 0
                        for gk in good_keys:
                            if vp.match(meta[gk]):
                                gk_checked += 1
                                break
                        if not gk_checked:
                            return False
                    for kp, vp in zip(filters_b_minus_keys, filters_b_minus_values):
                        good_keys = (k for k in meta.keys() if kp.match(k))
                        gk_checked = 0
                        for gk in good_keys:
                            if vp.match(meta[gk]):
                                return False
                            gk_checked += 1
                        if not gk_checked:
                            return False

                    return True
            else:
                def filter_meta(meta: dict) -> bool:
                    return True

            if "filter_content" in self.cli_kwargs:
                if isinstance(self.cli_kwargs["filter_content"], str):
                    filter_content = self.cli_kwargs["filter_content"].split(",")
                else:
                    filter_content = self.cli_kwargs["filter_content"]
                assert isinstance(filter_content, list), f"filter_content must be a list, not {self.cli_kwargs['filter_content']}"

                # storing fast as list then in tupples for faster iteration
                filters_cont_plus = []
                filters_cont_minus = []

                for f in filter_content:
                    assert isinstance(f, str), f"Filter must be a string: '{f}'"
                    incexc = f[0]
                    assert incexc in ["+", "-"], f"filter 1st character must be + or -: '{f}'"
                    incexc_str = "plus" if incexc == "+" else "minus"
                    assert f[1:].strip(), f"Filter can't be an empty regex: '{f}'"
                    pattern = f[1:].strip()
                    if pattern == pattern.lower():
                        pattern = re.compile(pattern, flags=re.IGNORECASE)
                    else:
                        pattern = re.compile(pattern)
                    locals()[f"filters_cont_{incexc_str}"].append(pattern)
                filters_cont_plus = tuple(filters_cont_plus)
                filters_cont_minus = tuple(filters_cont_minus)

                def filter_cont(cont: str) -> bool:
                    if not all(inc.match(cont) for inc in filters_cont_plus):
                        return False
                    if any(exc.match(cont) for exc in filters_cont_minus):
                        return False
                    return True

            else:
                def filter_cont(cont: str) -> bool:
                    return True

            # check filtering is valid
            checked = 0
            good = 0
            ids_to_del = []
            for doc_id, doc in tqdm(
                self.loaded_embeddings.docstore._dict.items(),
                desc="filtering",
                unit="docs",
                ):
                checked += 1
                if filter_meta(doc.metadata) and filter_cont(doc.page_content):
                    good += 1
                else:
                    ids_to_del.append(doc_id)
            red(f"Keeping {good}/{checked} documents from vectorstore after filtering")
            if good == checked:
                red("Your filter matched all stored documents!")
            assert good, "No documents in the vectorstore match the given filter"

            # directly remove the filtered documents from the docstore
            # but first store the docstore before altering it to allow
            # unfiltering in the prompt
            self.unfiltered_docstore = self.loaded_embeddings.serialize_to_bytes()
            status = self.loaded_embeddings.delete(ids_to_del)

            # checking deletiong want well
            if status is False:
                raise Exception("Vectorstore filtering failed")
            elif status is None:
                raise Exception("Vectorstore filtering not implemented")
            assert len(self.loaded_embeddings.docstore._dict) == checked - len(ids_to_del), "Something went wrong when deleting filtered out documents"
            assert len(self.loaded_embeddings.docstore._dict), "Something went wrong when deleting filtered out documents: no document left"
            assert len(self.loaded_embeddings.docstore._dict) == len(self.loaded_embeddings.index_to_docstore_id), "Something went wrong when deleting filtered out documents"


    #@optional_typecheck
    def _query(self, query: Optional[str]) -> Optional[str]:
        if not query:
            query, self.interaction_settings = ask_user(self.interaction_settings)
            if "do_reset_memory" in self.interaction_settings:
                assert self.interaction_settings["do_reset_memory"]
                del self.interaction_settings["do_reset_memory"]
                self.memory = AnswerConversationBufferMemory(
                        memory_key="chat_history",
                        return_messages=True)
        assert all(
            retriev in ["default", "hyde", "knn", "svm", "parent"]
            for retriev in self.interaction_settings["retriever"].split("_")
        ), f"Invalid retriever value: {self.interaction_settings['retriever']}"
        retrievers = []
        if "hyde" in self.interaction_settings["retriever"].lower():
            retrievers.append(
                    create_hyde_retriever(
                        query=query,

                        llm=self.llm,
                        top_k=self.interaction_settings["top_k"],
                        relevancy=self.interaction_settings["relevancy"],

                        embeddings=self.embeddings,
                        loaded_embeddings=self.loaded_embeddings,
                        )
                    )

        if "knn" in self.interaction_settings["retriever"].lower():
            retrievers.append(
                    KNNRetriever.from_texts(
                        self.all_texts,
                        self.embeddings,
                        relevancy_threshold=self.interaction_settings["relevancy"],
                        k=self.interaction_settings["top_k"],
                        )
                    )
        if "svm" in self.interaction_settings["retriever"].lower():
            retrievers.append(
                    SVMRetriever.from_texts(
                        self.all_texts,
                        self.embeddings,
                        relevancy_threshold=self.interaction_settings["relevancy"],
                        k=self.interaction_settings["top_k"],
                        )
                    )
        if "parent" in self.interaction_settings["retriever"].lower():
            retrievers.append(
                    create_parent_retriever(
                        task=self.task,
                        loaded_embeddings=self.loaded_embeddings,
                        loaded_docs=self.loaded_docs,
                        top_k=self.interaction_settings["top_k"],
                        relevancy=self.interaction_settings["relevancy"],
                        )
                    )

        if "default" in self.interaction_settings["retriever"].lower():
            retrievers.append(
                    self.loaded_embeddings.as_retriever(
                        search_type="similarity_score_threshold",
                        search_kwargs={
                            "k": self.interaction_settings["top_k"],
                            "distance_metric": "cos",
                            "score_threshold": self.interaction_settings["relevancy"],
                            })
                        )

        assert retrievers, "No retriever selected. Probably cause by a wrong cli_command or query_retrievers arg."
        if len(retrievers) == 1:
            retriever = retrievers[0]
        else:
            retriever = MergerRetriever(retrievers=retrievers)

            # remove redundant results from the merged retrievers:
            filtered = EmbeddingsRedundantFilter(
                    embeddings=self.embeddings,
                    similarity_threshold=0.999,
                    )
            pipeline = DocumentCompressorPipeline(transformers=[filtered])
            retriever = ContextualCompressionRetriever(
                base_compressor=pipeline, base_retriever=retriever
            )

        if " // " in query:
            sp = query.split(" // ")
            assert len(sp) == 2, "The query must contain a maximum of 1 // symbol"
            query_fe = sp[0].strip()
            query_an = sp[1].strip()
        else:
            query_fe, query_an = copy.copy(query), copy.copy(query)
        whi(f"Query for the embeddings: {query_fe}")
        whi(f"Question to answer: {query_an}")

        # the eval doc chain needs its own caching
        if not self.no_llm_cache:
            eval_cache_wrapper = doc_eval_cache.cache
        else:
            def eval_cache_wrapper(func): return func

        @chain
        @optional_typecheck
        @eval_cache_wrapper
        def evaluate_doc_chain(
                inputs: dict,
                query_nb: int = self.query_eval_check_number,
                eval_model_name: str = self.query_eval_modelname,
            ) -> List[str]:
            if "n" in self.eval_llm_params or self.query_eval_check_number == 1:
                out = self.eval_llm._generate(PR_EVALUATE_DOC.format_messages(**inputs))
                outputs = [gen.text for gen in out.generations]
                assert outputs, "No generations found by query eval llm"
                outputs = [parse_eval_output(o) for o in outputs]
                new_p = out.llm_output["token_usage"]["prompt_tokens"]
                new_c = out.llm_output["token_usage"]["completion_tokens"]
            else:
                outputs = []
                new_p = 0
                new_c = 0
                async def eval(inputs):
                    return await self.eval_llm._agenerate(PR_EVALUATE_DOC.format_messages(**inputs))
                outs = [
                    eval(inputs)
                    for i in range(self.query_eval_check_number)
                ]
                try:
                    loop = asyncio.get_event_loop()
                except:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                outs = loop.run_until_complete(asyncio.gather(*outs))
                for out in outs:
                    assert len(out.generations) == 1, f"Query eval llm produced more than 1 evaluations: '{out.generations}'"
                    outputs.append(out.generations[0].text)
                    new_p += out.llm_output["token_usage"]["prompt_tokens"]
                    new_c += out.llm_output["token_usage"]["completion_tokens"]
                assert outputs, "No generations found by query eval llm"
                outputs = [parse_eval_output(o) for o in outputs]

            assert len(outputs) == self.query_eval_check_number, f"query eval model failed to produce {self.query_eval_check_number} outputs"

            self.eval_llm.callbacks[0].prompt_tokens += new_p
            self.eval_llm.callbacks[0].completion_tokens += new_c
            self.eval_llm.callbacks[0].total_tokens += new_p + new_c
            return outputs

        if self.task == "search":
            if self.query_eval_modelname:
                # uses in most places to increase concurrency limit
                multi = {"max_concurrency": 50 if not self.debug else 1}

                # answer 0 or 1 if the document is related
                if not hasattr(self, "eval_llm"):
                    self.eval_llm_params = litellm.get_supported_openai_params(
                        model=self.query_eval_modelname,
                        custom_llm_provider=self.query_eval_modelbackend,
                    )
                    eval_args = {}
                    if "n" in self.eval_llm_params:
                        eval_args["n"] = self.query_eval_check_number
                    else:
                        red(f"Model {self.query_eval_modelname} does not support parameter 'n' so will be called multiple times instead. This might cost more.")
                    if "max_tokens" in self.eval_llm_params:
                        eval_args["max_tokens"] = 2
                    else:
                        red(f"Model {self.query_eval_modelname} does not support parameter 'max_token' so the result might be of less quality.")
                    self.eval_llm = load_llm(
                        modelname=self.query_eval_modelname,
                        backend=self.query_eval_modelbackend,
                        no_llm_cache=self.no_llm_cache,
                        verbose=self.llm_verbosity,
                        temperature=1,
                        api_base=self.llms_api_bases["query_eval_model"],
                        private=self.private,
                        **eval_args,
                    )

                # for some reason I needed to have at least one chain object otherwise rag_chain is a dict
                @chain
                def retrieve_documents(inputs):
                    return {
                            "unfiltered_docs": retriever.get_relevant_documents(inputs["question_for_embedding"]),
                            "question_to_answer": inputs["question_to_answer"],
                    }
                    return inputs

                refilter_documents =  {
                    "filtered_docs": (
                            RunnablePassthrough.assign(
                                evaluations=RunnablePassthrough.assign(
                                    doc=lambda inputs: inputs["unfiltered_docs"],
                                    q=lambda inputs: [inputs["question_to_answer"] for i in range(len(inputs["unfiltered_docs"]))],
                                    )
                                | RunnablePassthrough.assign(
                                    inputs=lambda inputs: [
                                        {"doc":d.page_content, "q":q}
                                        for d, q in zip(inputs["doc"], inputs["q"])])
                                    | itemgetter("inputs")
                                    | RunnableEach(bound=evaluate_doc_chain.with_config(multi)).with_config(multi)
                        )
                        | refilter_docs
                    ),
                    "unfiltered_docs": itemgetter("unfiltered_docs"),
                    "question_to_answer": itemgetter("question_to_answer")
                }
                rag_chain = (
                    retrieve_documents
                    | refilter_documents
                )
                output = rag_chain.invoke(
                    {
                        "question_for_embedding": query_fe,
                        "question_to_answer": query_an,
                    }
                )
                docs = output["filtered_docs"]
            else:

                docs = retriever.get_relevant_documents(query)
                if len(docs) < self.interaction_settings["top_k"]:
                    red(f"Only found {len(docs)} relevant documents")


            md_printer("\n\n# Documents")
            anki_cid = []
            to_print = ""
            for id, doc in enumerate(docs):
                to_print += f"## Document #{id + 1}\n"
                content = doc.page_content.strip()
                wrapped = "\n".join(textwrap.wrap(content, width=240))
                to_print += "```\n" + wrapped + "\n ```\n"
                for k, v in doc.metadata.items():
                    to_print += f"* **{k}**: `{v}`\n"
                to_print += "\n"
                if "anki_cid" in doc.metadata:
                    cid_str = str(doc.metadata["anki_cid"]).split(" ")
                    for cid in cid_str:
                        if cid not in anki_cid:
                            anki_cid.append(cid)
            md_printer(to_print)
            if self.query_eval_modelname:
                red(f"Number of documents using embeddings: {len(output['unfiltered_docs'])}")
                red(f"Number of documents after query eval filter: {len(output['filtered_docs'])}")

            if anki_cid:
                open_answ = input(f"\nAnki cards found, open in anki? (yes/no/debug)\n(cids: {anki_cid})\n> ")
                if open_answ == "debug":
                    breakpoint()
                elif open_answ in ["y", "yes"]:
                    whi("Opening anki.")
                    query = f"cid:{','.join(anki_cid)}"
                    ankiconnect(
                            action="guiBrowse",
                            query=query,
                            )
            all_filepaths = []
            for doc in docs:
                if "path" in doc.metadata:
                    path = doc.metadata["path"]
                    try:
                        path = str(Path(path).resolve().absolute())
                    except Exception as err:
                        pass
                    all_filepaths.append(path)
            if all_filepaths:
                md_printer("### All file paths")
                md_printer("* " + "\n* ".join(all_filepaths))

        else:
            if self.query_condense_question:
                loaded_memory = RunnablePassthrough.assign(
                    chat_history=RunnableLambda(self.memory.load_memory_variables) | itemgetter("chat_history"),
                )
                standalone_question = {
                    "question_to_answer": RunnablePassthrough(),
                    "question_for_embedding": {
                        "question_for_embedding": lambda x: x["question_for_embedding"],
                        "chat_history": lambda x: format_chat_history(x["chat_history"]),
                    }
                        | PR_CONDENSE_QUESTION
                        | self.llm
                        | StrOutputParser()
                }

            # uses in most places to increase concurrency limit
            multi = {"max_concurrency": 50 if not self.debug else 1}

            # answer 0 or 1 if the document is related
            if not hasattr(self, "eval_llm"):
                self.eval_llm_params = litellm.get_supported_openai_params(
                    model=self.query_eval_modelname,
                    custom_llm_provider=self.query_eval_modelbackend,
                )
                eval_args = {}
                if "n" in self.eval_llm_params:
                    eval_args["n"] = self.query_eval_check_number
                else:
                    red(f"Model {self.query_eval_modelname} does not support parameter 'n' so will be called multiple times instead. This might cost more.")
                if "max_tokens" in self.eval_llm_params:
                    eval_args["max_tokens"] = 2
                else:
                    red(f"Model {self.query_eval_modelname} does not support parameter 'max_token' so the result might be of less quality.")
                self.eval_llm = load_llm(
                    modelname=self.query_eval_modelname,
                    backend=self.query_eval_modelbackend,
                    no_llm_cache=self.no_llm_cache,
                    verbose=self.llm_verbosity,
                    temperature=1,
                    api_base=self.llms_api_bases["query_eval_model"],
                    private=self.private,
                    **eval_args,
                )

            # the eval doc chain needs its own caching
            if self.no_llm_cache:
                def eval_cache_wrapper(func): return func
            else:
                eval_cache_wrapper = doc_eval_cache.cache

            @chain
            @optional_typecheck
            @eval_cache_wrapper
            def evaluate_doc_chain(
                    inputs: dict,
                    query_nb: int = self.query_eval_check_number,
                    eval_model_name: str = self.query_eval_modelname,
                ) -> List[str]:
                if "n" in self.eval_llm_params or self.query_eval_check_number == 1:
                    out = self.eval_llm._generate(PR_EVALUATE_DOC.format_messages(**inputs))
                    reasons = [gen.generation_info["finish_reason"] for gen in out.generations]
                    assert all(r == "stop" for r in reasons), f"Unexpected generation finish_reason: '{reasons}'"
                    outputs = [gen.text for gen in out.generations]
                    assert outputs, "No generations found by query eval llm"
                    outputs = [parse_eval_output(o) for o in outputs]
                    new_p = out.llm_output["token_usage"]["prompt_tokens"]
                    new_c = out.llm_output["token_usage"]["completion_tokens"]
                else:
                    outputs = []
                    new_p = 0
                    new_c = 0
                    async def eval(inputs):
                        return await self.eval_llm._agenerate(PR_EVALUATE_DOC.format_messages(**inputs))
                    outs = [
                        eval(inputs)
                        for i in range(self.query_eval_check_number)
                    ]
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    outs = loop.run_until_complete(asyncio.gather(*outs))
                    for out in outs:
                        assert len(out.generations) == 1, f"Query eval llm produced more than 1 evaluations: '{out.generations}'"
                        outputs.append(out.generations[0].text)
                        finish_reason = out.generations[0].generation_info["finish_reason"]
                        assert finish_reason == "stop", f"unexpected finish_reason: '{finish}'"
                        new_p += out.llm_output["token_usage"]["prompt_tokens"]
                        new_c += out.llm_output["token_usage"]["completion_tokens"]
                    assert outputs, "No generations found by query eval llm"
                    outputs = [parse_eval_output(o) for o in outputs]

                assert len(outputs) == self.query_eval_check_number, f"query eval model failed to produce {self.query_eval_check_number} outputs"

                self.eval_llm.callbacks[0].prompt_tokens += new_p
                self.eval_llm.callbacks[0].completion_tokens += new_c
                self.eval_llm.callbacks[0].total_tokens += new_p + new_c
                return outputs

            # for some reason I needed to have at least one chain object otherwise rag_chain is a dict
            @chain
            def retrieve_documents(inputs):
                return {
                        "unfiltered_docs": retriever.get_relevant_documents(inputs["question_for_embedding"]),
                        "question_to_answer": inputs["question_to_answer"],
                }
                return inputs
            refilter_documents =  {
                "filtered_docs": (
                        RunnablePassthrough.assign(
                            evaluations=RunnablePassthrough.assign(
                                doc=lambda inputs: inputs["unfiltered_docs"],
                                q=lambda inputs: [inputs["question_to_answer"] for i in range(len(inputs["unfiltered_docs"]))],
                                )
                            | RunnablePassthrough.assign(
                                inputs=lambda inputs: [
                                    {"doc":d.page_content, "q":q}
                                    for d, q in zip(inputs["doc"], inputs["q"])])
                                | itemgetter("inputs")
                                | RunnableEach(bound=evaluate_doc_chain.with_config(multi)).with_config(multi)
                    )
                    | refilter_docs
                ),
                "unfiltered_docs": itemgetter("unfiltered_docs"),
                "question_to_answer": itemgetter("question_to_answer")
            }
            answer_each_doc_chain = (
                PR_ANSWER_ONE_DOC
                | self.llm.bind(max_tokens=1000)
                | StrOutputParser()
            )
            combine_answers = (
                PR_COMBINE_INTERMEDIATE_ANSWERS
                | self.llm.bind(max_tokens=2000)
                | StrOutputParser()
            )

            answer_all_docs = RunnablePassthrough.assign(
                inputs=lambda inputs: [
                    {"context":d.page_content, "question_to_answer":q}
                    for d, q in zip(
                        inputs["filtered_docs"],
                        [inputs["question_to_answer"]] * len(inputs["filtered_docs"])
                    )
                ]
            ) | {
                    "intermediate_answers": itemgetter("inputs") | RunnableEach(bound=answer_each_doc_chain),
                    "question_to_answer": itemgetter("question_to_answer"),
                    "filtered_docs": itemgetter("filtered_docs"),
                    "unfiltered_docs": itemgetter("unfiltered_docs"),
                }

            final_answer_chain = RunnablePassthrough.assign(
                        final_answer=RunnablePassthrough.assign(
                            question=lambda inputs: inputs["question_to_answer"],
                            # remove answers deemed irrelevant
                            intermediate_answers=lambda inputs: "\n".join(
                                [
                                    inp
                                    for inp in inputs["intermediate_answers"]
                                    if check_intermediate_answer(inp)
                                ]
                            )
                        )
                        | combine_answers,
                )
            if self.query_condense_question:
                rag_chain = (
                    loaded_memory
                    | standalone_question
                    | retrieve_documents
                    | refilter_documents
                    | answer_all_docs
                )
            else:
                rag_chain = (
                    retrieve_documents
                    | refilter_documents
                    | answer_all_docs
                )

            if self.debug:
                rag_chain.get_graph().print_ascii()

            chain_time = 0
            try:
                start_time = time.time()
                output = rag_chain.invoke(
                    {
                        "question_for_embedding": query_fe,
                        "question_to_answer": query_an,
                    }
                )
                chain_time = time.time() - start_time
            except NoDocumentsRetrieved as err:
                return md_printer(f"## No documents were retrieved with query '{query_fe}'", color="red")
            except NoDocumentsAfterLLMEvalFiltering as err:
                return md_printer(f"## No documents remained after query eval LLM filtering using question '{query_an}'", color="red")

            # group the intermediate answers by batch, then do a batch reduce mapping
            batch_size = 5
            intermediate_answers = output["intermediate_answers"]
            all_intermediate_answers = [intermediate_answers]
            while len(intermediate_answers) > batch_size:
                batches = [[]]
                for ia in intermediate_answers:
                    if not check_intermediate_answer(ia):
                        continue
                    if len(batches[-1]) >= batch_size:
                        batches.append([])
                    if len(batches[-1]) < batch_size:
                        batches[-1].append(ia)
                batch_args = [
                    {"question_to_answer": query_an, "intermediate_answers": b}
                    for b in batches]
                intermediate_answers = [a["final_answer"] for a in final_answer_chain.batch(batch_args)]
            all_intermediate_answers.append(intermediate_answers)
            final_answer = final_answer_chain.invoke({"question_to_answer": query_an, "intermediate_answers": intermediate_answers})["final_answer"]
            output["final_answer"] = final_answer
            output["all_intermediate_answeers"] = all_intermediate_answers
            # output["intermediate_answers"] = intermediate_answers  # better not to overwrite that

            output["relevant_filtered_docs"] = []
            output["relevant_intermediate_answers"] = []
            for ia, a in enumerate(output["intermediate_answers"]):
                if check_intermediate_answer(a):
                    output["relevant_filtered_docs"].append(output["filtered_docs"][ia])
                    output["relevant_intermediate_answers"].append(a)

            if not output["relevant_intermediate_answers"]:
                md_printer("\n\n# No document filtered so no intermediate answers to combine.\nThe answer will be based purely on the LLM's internal knowledge.", color="red")
                md_printer("\n\n# No document filtered so no intermediate answers to combine")
            else:
                md_printer("\n\n# Intermediate answers for each document:")
            counter = 0
            to_print = ""
            for ia, doc in zip(output["relevant_intermediate_answers"], output["relevant_filtered_docs"]):
                counter += 1
                to_print += f"## Document #{counter}\n"
                content = doc.page_content.strip()
                wrapped = "\n".join(textwrap.wrap(content, width=240))
                to_print += "```\n" + wrapped + "\n ```\n"
                for k, v in doc.metadata.items():
                    to_print += f"* **{k}**: `{v}`\n"
                to_print += indent("### Intermediate answer:\n" + ia, "> ")
                to_print += "\n"
            md_printer(to_print)

            md_printer(indent(f"# Answer:\n{output['final_answer']}\n", "> "))

            red(f"Number of documents using embeddings: {len(output['unfiltered_docs'])}")
            red(f"Number of documents after query eval filter: {len(output['filtered_docs'])}")
            red(f"Number of documents found relevant by eval llm: {len(output['relevant_filtered_docs'])}")
            if chain_time:
                red(f"Time took by the chain: {chain_time:.2f}s")

            if self.import_mode:
                return output

            assert len(self.llm.callbacks) == 1, "Unexpected number of callbacks for llm"
            llmcallback = self.llm.callbacks[0]
            total_cost = self.llm_price[0] * llmcallback.prompt_tokens + self.llm_price[1] * llmcallback.completion_tokens
            yel(f"Tokens used by strong model: '{llmcallback.total_tokens}' (${total_cost:.5f})")

            assert len(self.eval_llm.callbacks) == 1, "Unexpected number of callbacks for eval_llm"
            evalllmcallback = self.eval_llm.callbacks[0]
            wtotal_cost = self.query_evalllm_price[0] * evalllmcallback.prompt_tokens + self.query_evalllm_price[1] * evalllmcallback.completion_tokens
            yel(f"Tokens used by query_eval model: '{evalllmcallback.total_tokens}' (${wtotal_cost:.5f})")

            red(f"Total cost: ${total_cost + wtotal_cost:.5f}")
