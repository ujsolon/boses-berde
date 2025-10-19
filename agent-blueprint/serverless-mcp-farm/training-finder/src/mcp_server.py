#!/usr/bin/env python3
"""
Training Finder MCP Server — Matches user profiles to training opportunities.
"""

import json
import boto3
import os
import re
import math
from typing import List, Dict
from collections import Counter
from awslabs.mcp_lambda_handler import MCPLambdaHandler

print("Starting Training MCP server...")

mcp = MCPLambdaHandler(name="training-finder", version="1.0.0")

S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
TRAINING_FOLDER = os.environ.get("TRAINING_FOLDER", "trainings/")

# --- Utility Functions ---

def normalize_text(text: str) -> List[str]:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    words = text.split()
    stop_words = {
        "the","a","an","and","or","but","in","on","at","to","for","of","with","by",
        "is","are","was","were","be","been","have","has","had","do","does","did",
        "will","would","could","should","may","might","must","can"
    }
    return [w for w in words if len(w) > 2 and w not in stop_words]

def calculate_semantic_similarity(profile_text: str, training_text: str) -> float:
    try:
        user_words = normalize_text(profile_text)
        train_words = normalize_text(training_text)
        if not user_words or not train_words:
            return 0.0

        all_words = set(user_words + train_words)
        user_freq = Counter(user_words)
        train_freq = Counter(train_words)

        def tfidf_vector(freq, all_words, total_words):
            vec = {}
            for w in all_words:
                tf = freq.get(w, 0) / total_words
                idf = math.log(len(all_words) / (1 + sum(1 for x in all_words if x in freq)))
                vec[w] = tf * idf
            return vec

        uvec = tfidf_vector(user_freq, all_words, len(user_words))
        tvec = tfidf_vector(train_freq, all_words, len(train_words))

        dot = sum(uvec[w] * tvec[w] for w in all_words)
        umag = math.sqrt(sum(v ** 2 for v in uvec.values()))
        tmag = math.sqrt(sum(v ** 2 for v in tvec.values()))

        if umag == 0 or tmag == 0:
            return 0.0

        return dot / (umag * tmag)

    except Exception as e:
        print(f"Similarity error: {e}")
        return 0.0

def extract_topics_from_text(text: str) -> List[str]:
    topics = [
        "energy efficiency", "renewable energy", "solar", "wind", "green jobs",
        "digital skills", "data analysis", "excel", "python", "leadership",
        "communication", "waste management", "sustainability", "climate action",
        "agriculture", "entrepreneurship", "community development"
    ]
    text_lower = text.lower()
    return [t for t in topics if t in text_lower]

# --- MCP Tools ---

@mcp.tool()
def listTrainings() -> str:
    """List all training opportunities in the S3 bucket."""
    try:
        s3 = boto3.client("s3")
        response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=TRAINING_FOLDER)
        files = [
            {"filename": obj["Key"].replace(TRAINING_FOLDER, ""), "size": obj["Size"]}
            for obj in response.get("Contents", []) if not obj["Key"].endswith("/")
        ]
        return json.dumps({"trainings": files, "total": len(files)}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@mcp.tool()
def matchTrainingsToProfile(profile_text: str, min_similarity: float = 0.3) -> str:
    """Find trainings matching a user's profile, interests, or skill text."""
    try:
        s3 = boto3.client("s3")
        response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=TRAINING_FOLDER)
        trainings = []

        for obj in response.get("Contents", []):
            if obj["Key"].endswith("/"):
                continue

            file_obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=obj["Key"])
            content = file_obj["Body"].read().decode("utf-8")

            training_data = json.loads(content) if content.strip().startswith("{") else {"description": content}

            title = training_data.get("title", obj["Key"])
            provider = training_data.get("provider", "Unknown")
            description = training_data.get("description", "")
            format_ = training_data.get("format", "Unspecified")
            schedule = training_data.get("schedule", "TBA")
            register = training_data.get("register", "See provider site")

            score = calculate_semantic_similarity(profile_text, description)
            if score >= min_similarity:
                trainings.append({
                    "title": title,
                    "provider": provider,
                    "similarity_score": round(score * 100, 1),
                    "topics_matched": extract_topics_from_text(description),
                    "format": format_,
                    "schedule": schedule,
                    "register": register,
                    "recommendation": (
                        "🟢 Strong Fit" if score >= 0.7 else
                        "🟡 Moderate Fit" if score >= 0.5 else
                        "🟠 Slight Fit"
                    )
                })

        trainings.sort(key=lambda t: t["similarity_score"], reverse=True)

        return json.dumps({
            "total_matches": len(trainings),
            "matches": trainings,
            "summary": f"Found {len(trainings)} training matches with ≥{min_similarity:.0%} similarity"
        }, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@mcp.tool()
def generateTrainingInsights() -> str:
    """Generate insights about training topics and trends."""
    try:
        s3 = boto3.client("s3")
        response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=TRAINING_FOLDER)
        descriptions = []

        for obj in response.get("Contents", []):
            if obj["Key"].endswith("/"):
                continue
            file_obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=obj["Key"])
            content = file_obj["Body"].read().decode("utf-8")
            training_data = json.loads(content) if content.strip().startswith("{") else {"description": content}
            descriptions.append(training_data.get("description", ""))

        all_topics = []
        for desc in descriptions:
            all_topics.extend(extract_topics_from_text(desc))
        topic_counts = Counter(all_topics)
        top_topics = topic_counts.most_common(10)

        return json.dumps({
            "total_trainings": len(descriptions),
            "top_topics": dict(top_topics),
            "observation": "Free trainings in energy efficiency and digital skills are trending among Filipino youth."
        }, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)
