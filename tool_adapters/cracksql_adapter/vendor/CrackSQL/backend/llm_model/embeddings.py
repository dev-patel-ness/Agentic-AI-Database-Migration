import asyncio
import os
import numpy as np
from typing import List, Union, Optional, Dict
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings.huggingface import HuggingFaceEmbeddings
from tenacity import retry, stop_after_attempt, wait_random_exponential

from models import LLMModel
from config.db_config import db, db_session_manager
from config.logging_config import logger


class BedrockEmbeddings:
    """AWS Bedrock embeddings (e.g. Titan Embed) exposing the same
    aembed_query/aembed_documents surface EmbeddingManager expects from a
    LangChain-style embeddings object. Bedrock's invoke_model has no native
    batch endpoint, so aembed_documents fans out with bounded concurrency
    instead of one call per text sequentially."""

    def __init__(self, model_id: str, region_name: str, max_concurrency: int = 10):
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=region_name)
        self._model_id = model_id
        self._max_concurrency = max_concurrency

    def _embed_one(self, text: str) -> List[float]:
        import json

        body = json.dumps({"inputText": text[:8192]})
        response = self._client.invoke_model(
            modelId=self._model_id, body=body, contentType="application/json", accept="application/json"
        )
        payload = json.loads(response["body"].read())
        return payload["embedding"]

    async def aembed_query(self, text: str) -> List[float]:
        return await asyncio.to_thread(self._embed_one, text)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        # Semaphore is created fresh per call (bound to the current running
        # loop) rather than in __init__ -- EmbeddingManager caches this
        # instance across calls, and each get_embeddings() invocation runs in
        # its own asyncio.run() event loop, so a semaphore created once in
        # __init__ would be bound to the first loop only and raise
        # 'bound to a different event loop' on every subsequent call.
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def _bounded(t: str) -> List[float]:
            async with semaphore:
                return await asyncio.to_thread(self._embed_one, t)

        return list(await asyncio.gather(*[_bounded(t) for t in texts]))


class EmbeddingManager:
    """Embedding Manager"""

    def __init__(self):
        self._embeddings = {}

    @db_session_manager
    def get_embedding_config_from_db(self, model_name: str):
        """
        Get Embedding model configuration
        """
        config = db.session.query(LLMModel).filter_by(name=model_name,
                                                      category='embedding',
                                                      is_active=True).first()

        return {
            'name': config.name,
            'model_path': config.path,
            'api_base': config.api_base,
            'api_key': config.api_key,
            'deployment_type': config.deployment_type,
            'dimension': config.dimension
        }
    
    def release_embedding(self, model_name: str):
        """Release Embedding model"""
        if model_name in self._embeddings:
            embedding_model = self._embeddings[model_name]
            try:
                # For HuggingFace models, need to release CUDA memory
                if isinstance(embedding_model, HuggingFaceEmbeddings):
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    if hasattr(embedding_model, 'client'):
                        del embedding_model.client
                
                # OpenAI models don't need special release operations
                del self._embeddings[model_name]
                
            except Exception as e:
                logger.error(f"Failed to release Embedding model {model_name}: {str(e)}")

    def release_all_embeddings(self):
        """Release all Embedding models"""
        # Create a copy to avoid modifying dictionary during iteration
        model_names = list(self._embeddings.keys())
        for model_name in model_names:
            self.release_embedding(model_name)


    def get_embedding(self, model_name: str, model_config: Optional[Dict] = None):
        """
        Get Embedding model instance, load if it doesn't exist
        Args:
            model_name: Model name
            model_config: Model configuration
        Returns:
            Embedding model instance
        """
        if model_name not in self._embeddings:
            # Lazy loading: only load model when first used
            if model_config is None:
                model_config = self.get_embedding_config_from_db(model_name)
                if not model_config:
                    raise ValueError(f"Embedding model does not exist or is not enabled: {model_name}")
            self.load_embedding(model_config)

        return self._embeddings.get(model_name)

    def load_embedding(self, model_config: dict):
        """
        Load a single Embedding model
        Args:
            model_config: Model configuration
        """
        try:
            if model_config['deployment_type'] == 'cloud':
                # Cloud model (OpenAI)
                embedding = OpenAIEmbeddings(
                    model=model_config['name'],
                    openai_api_key=model_config['api_key'],
                    openai_api_base=model_config['api_base']
                )
            elif model_config['deployment_type'] == 'bedrock':
                region = model_config.get('api_base') or os.getenv('AWS_REGION', 'us-east-1')
                embedding = BedrockEmbeddings(model_id=model_config['name'], region_name=region)
            else:
                import torch
                # Determine device
                device = "cuda" if torch.cuda.is_available() else "cpu"
                # Local model (HuggingFace)
                embedding = HuggingFaceEmbeddings(
                    model_name=model_config['model_path'],
                    model_kwargs={'device': device},
                    encode_kwargs={'normalize_embeddings': True}
                )
            self._embeddings[model_config['name']] = embedding
            logger.info(f"Successfully loaded Embedding model: {model_config['name']}")
        except Exception as e:
            logger.error(f"Failed to load Embedding model {model_config['name']}: {str(e)}")
            raise


# Global Embedding manager instance
embedding_manager = EmbeddingManager()


@retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(3))
async def get_embeddings(text: Union[str, List[str]], model_name: str,
                         model_config: Optional[Dict] = None) -> np.ndarray:
    """
    Get embedding vectors for text
    Args:
        text: Input text or list of texts
        model_name: Model name
    Returns:
        numpy.ndarray: Vector or list of vectors
    """
    try:
        return await _get_embeddings_with_context(text, model_name, model_config=model_config)
    except Exception as e:
        logger.error(f"Failed to get Embedding: {str(e)}")
        raise


async def _get_embeddings_with_context(text: Union[str, List[str]], model_name: str,
                                       model_config: Optional[Dict] = None) -> np.ndarray:
    """Get embedding vectors in application context"""
    # Get model instance
    embedding_model = embedding_manager.get_embedding(model_name, model_config)
    if not embedding_model:
        raise ValueError(f"Embedding model does not exist or is not enabled: {model_name}")
    try:
        # Use LangChain's embed_query/embed_documents methods
        if isinstance(text, str):
            embedding = await embedding_model.aembed_query(text[:8192])
        else:
            text = [t[:8192] for t in text]
            embedding = await embedding_model.aembed_documents(text)
        return np.array(embedding)
    except Exception as e:
        logger.error(f"Failed to generate Embedding: {str(e)}")
        raise
