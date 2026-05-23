"""
=============================================================================
Face Surveillance - AI Embedding Service (OpenCLIP / SigLIP)
=============================================================================
Module ini menangani:
1. Load model AI (sekali saat startup, disimpan di memori)
2. Encode gambar (PIL Image) → vector embedding
3. Encode teks query → vector embedding (untuk text search)
=============================================================================
"""

import time
import logging
import numpy as np
from typing import List, Optional
from PIL import Image

import torch
import open_clip

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service untuk mengelola model AI dan menghasilkan embeddings.
    Singleton pattern: model di-load sekali, dipakai berkali-kali.
    """

    def __init__(self):
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        self.device = None
        self.model_name = None
        self.embedding_dim = None
        self._is_loaded = False

    def load_model(self):
        """
        Load model AI ke memori berdasarkan preset di config.
        """
        if not settings.CLIP_ENABLED:
            logger.info("[AI Search] CLIP disabled in settings — skipping model load")
            return

        model_info = settings.get_clip_model_info()
        self.model_name = model_info["model_name"]
        pretrained = model_info["pretrained"]
        self.embedding_dim = model_info.get("embedding_dim")

        logger.info("[AI Search] Loading model: %s (pretrained: %s) ...", self.model_name, pretrained)
        start_time = time.time()

        # Deteksi device: gunakan GPU (CUDA) jika tersedia, jika tidak → CPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("[AI Search] Using device: %s", self.device)

        # Load model via OpenCLIP
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name=self.model_name,
            pretrained=pretrained,
            device=self.device
        )

        # Load tokenizer
        self.tokenizer = open_clip.get_tokenizer(self.model_name)

        # Tokenizer patch for SigLIP compatibility
        if hasattr(self.tokenizer, 'tokenizer'):
            inner = self.tokenizer.tokenizer
            if not hasattr(inner, 'batch_encode_plus'):
                logger.info("[AI Search] Patching tokenizer compatibility (batch_encode_plus) ...")
                inner.batch_encode_plus = inner.__call__

        self.model.eval()

        # Detect actual embedding dimension if not predefined
        if self.embedding_dim is None:
            with torch.no_grad():
                dummy = torch.randn(1, 3, 224, 224).to(self.device)
                out = self.model.encode_image(dummy)
                self.embedding_dim = out.shape[-1]

        elapsed = time.time() - start_time
        self._is_loaded = True
        logger.info(
            "[AI Search] ✅ Model loaded in %.1fs (dim: %s, device: %s)",
            elapsed, self.embedding_dim, self.device
        )

    def ensure_loaded(self):
        """Pastikan model sudah di-load sebelum digunakan."""
        if not self._is_loaded:
            self.load_model()

    @torch.no_grad()
    def encode_image(self, image: Image.Image) -> np.ndarray:
        """
        Encode satu gambar PIL menjadi vector embedding ternormalisasi L2.
        """
        self.ensure_loaded()
        if not self.model:
            raise RuntimeError("CLIP Model is disabled or not loaded")
        image_tensor = self.preprocess(image).unsqueeze(0).to(self.device)
        image_features = self.model.encode_image(image_tensor)
        image_features /= image_features.norm(dim=-1, keepdim=True)
        return image_features.cpu().numpy().squeeze()

    @torch.no_grad()
    def encode_text(self, text: str) -> np.ndarray:
        """
        Encode satu teks query menjadi vector embedding ternormalisasi L2.
        """
        self.ensure_loaded()
        if not self.model:
            raise RuntimeError("CLIP Model is disabled or not loaded")
        tokens = self.tokenizer([text]).to(self.device)
        text_features = self.model.encode_text(tokens)
        text_features /= text_features.norm(dim=-1, keepdim=True)
        return text_features.cpu().numpy().squeeze()

    @torch.no_grad()
    def encode_images_batch(self, images: List[Image.Image]) -> np.ndarray:
        """
        Encode batch gambar sekaligus.
        """
        self.ensure_loaded()
        if not self.model:
            raise RuntimeError("CLIP Model is disabled or not loaded")
        image_tensors = torch.stack([
            self.preprocess(img) for img in images
        ]).to(self.device)
        image_features = self.model.encode_image(image_tensors)
        image_features /= image_features.norm(dim=-1, keepdim=True)
        return image_features.cpu().numpy()


# Singleton instance
embedding_service = EmbeddingService()
