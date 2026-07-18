import torch
import joblib
import logging
import time
from pathlib import Path
from typing import Dict, Any
import lightgbm as lgb
from app.core.config import settings

logger = logging.getLogger(__name__)





def _torch_major_minor() -> tuple:

    parts = torch.__version__.split("+")[0].split(".")

    try:

        return int(parts[0]), int(parts[1])

    except Exception:

        return (0, 0)





def _load_torch_model(path, device):

    """Load a torch model with the safe `weights_only` mode when available.



    `weights_only=True` (PyTorch >= 2.6) prevents arbitrary code execution

    from a malicious pickle payload inside the .pt file. Older torch falls

    back to the default loader (warn the operator to upgrade / trust the file).

    """

    load_kwargs = {"map_location": device}

    if _torch_major_minor() >= (2, 6):

        load_kwargs["weights_only"] = True

    try:

        model = torch.load(str(path), **load_kwargs)

    except Exception as e:  # noqa: BLE001

        if load_kwargs.get("weights_only"):

            logger.warning(

                "weights_only load failed (%s); retrying with full unpickler. "

                "Only load .pt files from trusted sources.",

                e,

            )

            model = torch.load(str(path), map_location=device)

        else:

            raise

    return model

class ModelRegistry:
    """Loads and manages production ML models."""
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.tft_model = None
        self.lgbm_model = None
        self.feature_scaler = None
        self.target_scaler = None
        self._initialized = True

    async def initialize(self):
        logger.info("Initializing model registry...")
        start = time.time()
        try:
            lgbm_path = Path(settings.LGBM_MODEL_PATH)
            if lgbm_path.exists():
                self.lgbm_model = lgb.Booster(model_file=str(lgbm_path))
                logger.info(f"LightGBM loaded from {lgbm_path}")
            tft_path = Path(settings.TFT_MODEL_PATH)
            if tft_path.exists():
                device = torch.device(settings.DEVICE)
                self.tft_model = _load_torch_model(tft_path, device)
                if hasattr(self.tft_model, "eval"):
                    self.tft_model.eval()
                logger.info(f"TFT loaded on {settings.DEVICE}")
            scaler_path = Path(settings.SCALER_PATH)
            if scaler_path.exists():
                scalers = joblib.load(str(scaler_path))
                self.feature_scaler = scalers["feature"]
                self.target_scaler = scalers["target"]
                logger.info("Scalers loaded")
            elapsed = (time.time() - start) * 1000
            logger.info(f"Model registry initialized in {elapsed:.0f}ms")
        except Exception as e:
            logger.error(f"Model initialization failed: {e}", exc_info=True)
            raise

    def predict_tft(self, sequence: torch.Tensor) -> Dict[str, Any]:
        if self.tft_model is None:
            raise RuntimeError("TFT model not loaded")
        device = torch.device(settings.DEVICE)
        sequence = sequence.to(device)
        with torch.no_grad():
            output = self.tft_model(sequence)
        if isinstance(output, dict):
            price_pred = output.get("prediction", output.get("price"))
        else:
            price_pred = output
        return {
            "prediction": price_pred.cpu().numpy().tolist() if hasattr(price_pred, "cpu") else price_pred,
        }

    def predict_lgbm(self, features: Dict[str, float]) -> Dict[str, float]:
        if self.lgbm_model is None:
            raise RuntimeError("LightGBM model not loaded")
        feature_names = self.lgbm_model.feature_name()
        feature_vector = [features.get(name, 0.0) for name in feature_names]
        prediction = self.lgbm_model.predict([feature_vector])[0]
        return {
            "prediction": float(prediction),
        }

model_registry = ModelRegistry()
