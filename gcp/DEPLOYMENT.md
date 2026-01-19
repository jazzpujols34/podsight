# GCP Deployment Guide for Gooaye Transcription

This guide shows how to run the transcription pipeline on Google Cloud Platform.

## Option 1: Compute Engine with GPU (Recommended)

Best for batch processing all 624 episodes.

### 1. Create VM with GPU

```bash
# Create a VM with T4 GPU
gcloud compute instances create gooaye-transcribe \
    --zone=asia-east1-a \
    --machine-type=n1-standard-4 \
    --accelerator=type=nvidia-tesla-t4,count=1 \
    --image-family=pytorch-latest-gpu \
    --image-project=deeplearning-platform-release \
    --boot-disk-size=100GB \
    --maintenance-policy=TERMINATE
```

### 2. SSH and Setup

```bash
# SSH into the VM
gcloud compute ssh gooaye-transcribe --zone=asia-east1-a

# Clone or upload your pipeline code
git clone <your-repo> gooaye_pipeline
cd gooaye_pipeline

# Install dependencies
pip install -r requirements.txt

# Verify GPU is available
python -c "import torch; print(torch.cuda.is_available())"
```

### 3. Run Pipeline

```bash
# Run full pipeline
python run_pipeline.py

# Or run in background with logging
nohup python run_pipeline.py > pipeline.log 2>&1 &
tail -f pipeline.log
```

### 4. Download Results

```bash
# Compress transcripts
tar -czvf transcripts.tar.gz data/transcripts/

# Download to local machine (run from your local terminal)
gcloud compute scp gooaye-transcribe:~/gooaye_pipeline/transcripts.tar.gz . --zone=asia-east1-a
```

### 5. Cleanup

```bash
# Delete VM when done
gcloud compute instances delete gooaye-transcribe --zone=asia-east1-a
```

### Cost Estimate
- n1-standard-4 + T4: ~$0.50/hour
- 624 episodes × ~2 min each = ~21 hours
- **Total: ~$10-15**

---

## Option 2: Cloud Run Jobs (Serverless)

Better if you want to transcribe incrementally or trigger via API.

### 1. Build and Push Docker Image

```bash
# Set your project
export PROJECT_ID=your-project-id
export REGION=asia-east1

# Build image
cd gcp
gcloud builds submit --tag gcr.io/$PROJECT_ID/gooaye-transcribe

# Or build locally and push
docker build -t gcr.io/$PROJECT_ID/gooaye-transcribe .
docker push gcr.io/$PROJECT_ID/gooaye-transcribe
```

### 2. Create Cloud Run Job

```bash
gcloud run jobs create gooaye-transcribe \
    --image gcr.io/$PROJECT_ID/gooaye-transcribe \
    --region $REGION \
    --cpu 4 \
    --memory 16Gi \
    --task-timeout 3600 \
    --max-retries 1
```

Note: Cloud Run doesn't support GPUs, so transcription will be slower (CPU only).

### 3. Execute Job

```bash
gcloud run jobs execute gooaye-transcribe --region $REGION
```

---

## Option 3: Vertex AI Custom Training (Most Powerful)

For very fast processing with multiple GPUs.

### 1. Create Training Script

```python
# vertex_train.py
from google.cloud import storage
import subprocess

def main():
    # Download audio from GCS
    # Run transcription
    # Upload results to GCS
    pass
```

### 2. Submit Training Job

```bash
gcloud ai custom-jobs create \
    --region=asia-east1 \
    --display-name=gooaye-transcribe \
    --worker-pool-spec=machine-type=n1-standard-8,accelerator-type=NVIDIA_TESLA_T4,accelerator-count=1,container-image-uri=gcr.io/$PROJECT_ID/gooaye-transcribe
```

---

## Storing Results in GCS

Add this to your pipeline to automatically upload transcripts:

```python
from google.cloud import storage

def upload_to_gcs(local_path, bucket_name, blob_name):
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)
    print(f"Uploaded to gs://{bucket_name}/{blob_name}")

# Usage after transcription
upload_to_gcs(
    "data/transcripts/EP0621.txt",
    "your-bucket-name",
    "gooaye/transcripts/EP0621.txt"
)
```

---

## Recommended Approach

For 624 episodes, I recommend **Option 1 (Compute Engine)**:

1. Cheapest for batch processing
2. Full GPU support
3. Easy to monitor progress
4. Can pause/resume by stopping VM

Timeline:
- Setup: 30 minutes
- Download audio: 2-3 hours
- Transcribe: 15-20 hours
- Total: ~1 day

Cost: $10-20 total
