import os
from huggingface_hub import hf_hub_download
import shutil

# 모델 저장 디렉토리 생성
models_dir = os.path.join(os.getcwd(), 'models')
os.makedirs(models_dir, exist_ok=True)

print(f"Downloading models to {models_dir}...")

# 1. Detection Model (PP-OCRv5)
print("Downloading Detection Model...")
det_path = hf_hub_download(repo_id="monkt/paddleocr-onnx", filename="detection/v5/det.onnx")
shutil.copy(det_path, os.path.join(models_dir, "det.onnx"))

# 2. Recognition Model (Korean, PP-OCRv5)
print("Downloading Recognition Model (Korean)...")
rec_path = hf_hub_download(repo_id="monkt/paddleocr-onnx", filename="languages/korean/rec.onnx")
shutil.copy(rec_path, os.path.join(models_dir, "rec.onnx"))

# 3. Dictionary (Korean)
print("Downloading Dictionary (Korean)...")
dict_path = hf_hub_download(repo_id="monkt/paddleocr-onnx", filename="languages/korean/dict.txt")
shutil.copy(dict_path, os.path.join(models_dir, "dict.txt"))

print("✅ All models downloaded successfully!")
print(f"- Detection: {os.path.join(models_dir, 'det.onnx')}")
print(f"- Recognition: {os.path.join(models_dir, 'rec.onnx')}")
print(f"- Dictionary: {os.path.join(models_dir, 'dict.txt')}")
